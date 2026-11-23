#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera a naracao em pt-BR (edge-tts) e os timings de palavras/segmentos.

Por que usar a API Python em vez da CLI ``python3 -m edge_tts --write-subtitles``?
No edge-tts 7.3.1 a CLI usa ``boundary='SentenceBoundary'`` por padrao e o
``--write-subtitles`` gera um SRT por *frase* (nao por palavra). Para lip-sync e
legenda karaoke precisamos de uma entrada por palavra. A classe Communicate
aceita ``boundary='WordBoundary'`` e emite eventos com offset/duracao por
palavra -- exatamente os dados que o contrato de timings.json exige. O audio
gerado e identico ao da CLI (mesmo servico, voz e rate).

Fluxo:
  1. Le video/data/roteiro.json (voz + segmentos[].texto).
  2. Para cada segmento, gera build/voz_tmp/seg_<id>.mp3 e coleta os
     WordBoundary events (offset/duracao em ticks de 100 ns).
  3. Concatena os MP3s com ffmpeg (concat demuxer + libmp3lame) em build/voz.mp3.
  4. Soma offsets acumulados (duracao real de cada MP3) e escreve:
       - build/timings.json  (palavras + segmentos com indices [ini, fim))
       - build/voz.vtt       (uma entrada por palavra, tempo global)
  5. Mede a duracao com ffprobe e ajusta --rate (0..12%) se fora de 50..66s.
"""

import asyncio
import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------- config ----
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../video
ROTEIRO = os.path.join(ROOT, "data", "roteiro.json")
BUILD = os.path.join(ROOT, "build")
TMP = os.path.join(BUILD, "voz_tmp")
AUDIO_FINAL = os.path.join(BUILD, "voz.mp3")
VTT_FINAL = os.path.join(BUILD, "voz.vtt")
TIMINGS = os.path.join(BUILD, "timings.json")

VOICE = "pt-BR-AntonioNeural"
RATE_INICIAL = 4          # começa em +4% (conforme spec); ajustado se necessario
RATE_MIN, RATE_MAX = 0, 12
DUR_MIN, DUR_MAX = 50.0, 66.0
TENTATIVAS = 3
TICKS_PER_SEC = 10_000_000  # edge-tts reporta offset/duration em 100 ns

# ---------------------------------------------------------------- utils -----


def log(msg):
    print(msg, flush=True)


def ffprobe_duration(path):
    """Duracao (segundos) de um arquivo de audio via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"ffprobe falhou para {path}: {r.stderr.strip()}")
    return float(r.stdout.strip().splitlines()[0])


def parse_ts(s):
    """Converte 'HH:MM:SS.mmm' ou 'MM:SS,mmm' em segundos."""
    s = s.strip().replace(",", ".")
    partes = s.split(":")
    if len(partes) == 3:
        h, m, sec = partes
    elif len(partes) == 2:
        h, m, sec = "0", partes[0], partes[1]
    else:
        h, m, sec = "0", "0", partes[0]
    return int(h) * 3600 + int(m) * 60 + float(sec)


def fmt_ts(seg):
    """Converte segundos em 'HH:MM:SS.mmm' (formato WebVTT)."""
    if seg < 0:
        seg = 0.0
    h = int(seg // 3600)
    m = int((seg % 3600) // 60)
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def limpar_palavra(t):
    """Texto da palavra sem espacos; pontuacao preservada no original."""
    return (t or "").strip()


def chave_compare(t):
    """Versao sem pontuacao, apenas para comparacoes internas."""
    return re.sub(r"[^\w]", "", t or "", flags=re.UNICODE).lower()


# ---------------------------------------------------------------- TTS -------

async def _gerar_segmento(texto, mp3_path, rate):
    """
    Gera o MP3 de um segmento e devolve a lista de WordBoundary events.
    Faz ate TENTATIVAS tentativas em caso de erro de rede.
    """
    import edge_tts  # importado aqui para mensagem de erro mais clara

    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            comm = edge_tts.Communicate(
                texto, VOICE, rate=f"+{rate}%", boundary="WordBoundary"
            )
            audio = bytearray()
            palavras = []
            async for chunk in comm.stream():
                ctype = chunk.get("type")
                if ctype == "audio":
                    audio.extend(chunk["data"])
                elif ctype == "WordBoundary":
                    palavras.append({
                        "texto": limpar_palavra(chunk.get("text", "")),
                        "offset": chunk["offset"] / TICKS_PER_SEC,
                        "duracao": chunk["duration"] / TICKS_PER_SEC,
                    })
            if not audio:
                raise RuntimeError("servico nao retornou audio")
            if not palavras:
                raise RuntimeError("servico nao retornou WordBoundary (palavras)")
            with open(mp3_path, "wb") as f:
                f.write(audio)
            return palavras
        except Exception as e:  # inclui erros de rede /cancelamento do edge-tts
            ultimo_erro = e
            if tentativa < TENTATIVAS:
                log(f"  [aviso] geracao falhou (tentativa {tentativa}/{TENTATIVAS}): {e}")
                await asyncio.sleep(1.0)
            else:
                log(f"  [erro] geracao falhou apos {TENTATIVAS} tentativas: {e}")

    raise RuntimeError(
        f"Falha ao gerar TTS para o segmento '{texto[:50]}...' "
        f"apos {TENTATIVAS} tentativas. Verifique a conexao com a internet. "
        f"Ultimo erro: {ultimo_erro}"
    )


def concatenar(lista_mp3, saida):
    """Concatena MP3s via ffmpeg concat demuxer (re-encode para MP3 44.1kHz)."""
    lista_txt = os.path.join(TMP, "lista.txt")
    with open(lista_txt, "w", encoding="utf-8") as f:
        for p in lista_mp3:
            # aspas simples protegem os espacos no caminho
            f.write(f"file '{p}'\n")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista_txt,
        "-c:a", "libmp3lame", "-q:a", "2", "-ar", "44100", "-ac", "1", saida,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg concat falhou: {r.stderr.strip()[-1000:]}")


def escrever_vtt(palavras, path):
    """Escreve WebVTT com uma entrada por palavra, usando tempo global."""
    linhas = ["WEBVTT", ""]
    for p in palavras:
        linhas.append(f"{fmt_ts(p['inicio'])} --> {fmt_ts(p['fim'])}")
        linhas.append(p["texto"] if p["texto"] else " ")
        linhas.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))


# ---------------------------------------------------------------- build -----

def build(rate, roteiro):
    """Gera tudo para um dado rate. Retorna (timings, duracao_total)."""
    os.makedirs(TMP, exist_ok=True)
    # limpa geracoes anteriores
    for nome in os.listdir(TMP):
        if nome.endswith((".mp3", ".vtt", ".txt")):
            os.remove(os.path.join(TMP, nome))

    segmentos = roteiro["segmentos"]
    todas_palavras = []
    info_segmentos = []
    mp3s = []
    offset = 0.0

    log(f"=== Gerando TTS (voz={VOICE}, rate=+{rate}%) ===")
    for seg in segmentos:
        sid = seg["id"]
        mp3 = os.path.join(TMP, f"seg_{sid}.mp3")
        log(f"  segmento {sid}: {len(seg['texto'].split())} palavras")

        brutos = asyncio.run(_gerar_segmento(seg["texto"], mp3, rate))
        dur_seg = ffprobe_duration(mp3)

        primeiro_idx = len(todas_palavras)
        for w in brutos:
            ini = offset + w["offset"]
            fim = offset + w["offset"] + w["duracao"]
            todas_palavras.append({
                "texto": w["texto"],
                "inicio": round(ini, 3),
                "fim": round(fim, 3),
            })
        ultimo_idx = len(todas_palavras)  # exclusivo

        info_segmentos.append({
            "id": sid,
            "texto": seg["texto"],
            "palavras_idx": [primeiro_idx, ultimo_idx],
            "offset": offset,
            "dur": dur_seg,
        })
        mp3s.append(mp3)
        offset += dur_seg
        log(f"    -> {len(brutos)} palavras, {dur_seg:.3f}s, offset global {offset:.3f}s")

    # Seguranca: garante monotonicidade mesmo com arredondamento/concat.
    prev_fim = -1.0
    for p in todas_palavras:
        if p["inicio"] < prev_fim:
            p["inicio"] = prev_fim
        if p["fim"] < p["inicio"]:
            p["fim"] = p["inicio"]
        p["inicio"] = round(p["inicio"], 3)
        p["fim"] = round(p["fim"], 3)
        prev_fim = p["fim"]

    log("=== Concatenando audio ===")
    concatenar(mp3s, AUDIO_FINAL)
    dur_total = ffprobe_duration(AUDIO_FINAL)

    # Segmentos com inicio/fim derivados dos indices de palavras.
    segmentos_out = []
    for info in info_segmentos:
        i0, i1 = info["palavras_idx"]
        ini = todas_palavras[i0]["inicio"] if i1 > i0 else info["offset"]
        fim = todas_palavras[i1 - 1]["fim"] if i1 > i0 else info["offset"] + info["dur"]
        segmentos_out.append({
            "id": info["id"],
            "texto": info["texto"],
            "inicio": round(ini, 3),
            "fim": round(fim, 3),
            "palavras": [i0, i1],
        })

    timings = {
        "voz": roteiro.get("voz", VOICE),
        "duracao_audio_seg": round(dur_total, 3),
        "palavras": todas_palavras,
        "segmentos": segmentos_out,
    }

    with open(TIMINGS, "w", encoding="utf-8") as f:
        json.dump(timings, f, ensure_ascii=False, indent=2)
        f.write("\n")
    escrever_vtt(todas_palavras, VTT_FINAL)

    return timings, dur_total


# ---------------------------------------------------------------- main ------

def validar(timings, dur):
    """Validacao obrigatoria. Retorna True se tudo passou."""
    ok = True
    # JSON valido
    r = subprocess.run(
        [sys.executable, "-m", "json.tool", TIMINGS],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    if r.returncode != 0:
        log(f"[FALHA] timings.json invalido: {r.stderr.strip()}")
        ok = False
    else:
        log("[OK] timings.json e JSON valido")

    if DUR_MIN <= dur <= DUR_MAX:
        log(f"[OK] duracao {dur:.3f}s esta entre {DUR_MIN} e {DUR_MAX}s")
    else:
        log(f"[FALHA] duracao {dur:.3f}s fora de {DUR_MIN}..{DUR_MAX}s")
        ok = False

    n = len(timings["palavras"])
    if n >= 100:
        log(f"[OK] {n} palavras (>= 100)")
    else:
        log(f"[FALHA] apenas {n} palavras (< 100)")
        ok = False

    mono = all(
        p["inicio"] <= p["fim"]
        and (i == 0 or p["inicio"] >= timings["palavras"][i - 1]["inicio"])
        for i, p in enumerate(timings["palavras"])
    )
    if mono:
        log("[OK] tempos monotonicamente crescentes")
    else:
        log("[FALHA] tempos nao monotonicos")
        ok = False

    return ok


def main():
    with open(ROTEIRO, encoding="utf-8") as f:
        roteiro = json.load(f)

    rate = RATE_INICIAL
    timings = None
    dur = 0.0
    for tentativa in range(6):
        timings, dur = build(rate, roteiro)
        if DUR_MIN <= dur <= DUR_MAX:
            break
        antigo = rate
        if dur < DUR_MIN:
            rate = max(RATE_MIN, rate - 2)
        else:
            rate = min(RATE_MAX, rate + 2)
        if rate == antigo:
            log(f"[aviso] duracao {dur:.3f}s fora da faixa, mas rate ja esta no limite ({rate}%)")
            break
        log(f"[aviso] duracao {dur:.3f}s fora de {DUR_MIN}..{DUR_MAX}s; "
            f"regenerando com rate +{rate}% (tentativa {tentativa + 2}/6)")

    log("")
    log("=== Resultado final ===")
    log(f"  duracao: {dur:.3f}s")
    log(f"  palavras: {len(timings['palavras'])}")
    log(f"  segmentos: {len(timings['segmentos'])}")
    log(f"  audio:    {AUDIO_FINAL}")
    log(f"  timings:  {TIMINGS}")
    log(f"  vtt:      {VTT_FINAL}")
    log("")
    if not validar(timings, dur):
        sys.exit(1)
    log("Validacao concluida com sucesso.")


if __name__ == "__main__":
    main()
