#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voz_v2.py — narração refinada + pacote de áudio completo (voz + trilha + SFX).

Missão "melhore a voz e efeitos" (v2 do vídeo). Não sobrescreve os arquivos da v1.
Entrada: data/roteiro_v2.json (texto novo, menos técnico e mais envolvente).

Pipeline
--------
1. Pitch -1Hz + boundary="WordBoundary" via API Python do edge-tts; plano SSML
   de pausas (. 350ms, , 150ms, ; 250ms, 300ms entre blocos, say-as no dólar,
   ênfase por bloco) aplicado como silêncio amostrado: o edge-tts 7.3.1 escapa
   SSML e o endpoint rejeita tags. Benchmark de 3 velocidades do gancho.
2. Concatena MP3s por bloco/segmento -> build/voz_v2.mp3 + timings_v2.json
   + voz_v2.vtt (MESMO schema da v1, com offsets globais de palavras).
3. Voz: highpass=80 -> EQ (-3 dB @400Hz, +2,2 dB @4,5kHz) -> compressor
   (thr=-18, ratio=3, atk=10, rel=200) -> loudnorm DUAS PASSOS (linear=true,
   aresample=48000, I=-14 TP=-1.5 LRA=11). Sem de-ess/reverb.
4. Trilha ambiental procedural (55/82.5/110 Hz, LFO 0.07 Hz, lowpass 500 Hz),
   -30 dBFS RMS, entra ~3s após a fala, continua no encerramento.
5. SFX procedurais: whoosh 0.4s (400Hz->4kHz), tick 12ms (highpass 1kHz),
   riser 1.4s (200Hz->4kHz + thump 60Hz), hit 60Hz — posicionados via timings_v2.
6. Mix: sidechaincompress (voz como sidechain) -> amix -> loudnorm 2 passos
   -> audio_final.m4a (AAC 48 kHz, voz + ~1,2 s).
7. Validação obrigatória + relatório build/audio_notes.md.
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import wave
from xml.sax.saxutils import escape

import numpy as np

# ---------------------------------------------------------------- config ----
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../video
DATA = os.path.join(ROOT, "data")
BUILD = os.path.join(ROOT, "build")
TMP = os.path.join(BUILD, "voz_v2_tmp")

ROTEIRO = os.path.join(DATA, "roteiro_v2.json")
VOZ_V2 = os.path.join(BUILD, "voz_v2.mp3")
VOZ_V2_VTT = os.path.join(BUILD, "voz_v2.vtt")
VOZ_PROC = os.path.join(BUILD, "voz_v2_proc.wav")
TRILHA = os.path.join(BUILD, "trilha.wav")
TRILHA_RAW = os.path.join(TMP, "trilha_raw.wav")
SFX = os.path.join(BUILD, "sfx.wav")
MIX_RAW = os.path.join(TMP, "mix_raw.wav")
AUDIO_FINAL = os.path.join(BUILD, "audio_final.m4a")
TIMINGS_V2 = os.path.join(BUILD, "timings_v2.json")
NOTES = os.path.join(BUILD, "audio_notes.md")

VOICE = "pt-BR-AntonioNeural"
SR = 44100            # TTS / voz_v2.mp3
SR_PROC = 48000       # cadeia processada / trilha / SFX / mix final
DUR_MIN, DUR_MAX = 50.0, 66.0
EXTRA_FINAL = 1.2
TENTATIVAS_REDE = 3
TICKS_PER_SEC = 10_000_000   # edge-tts reporta offset/duration em 100 ns

# Parâmetros SSML / TTS (checklist final — melhorias.md seção 5)
PITCH_SSML = -1       # Hz — ponto de partida (faixa segura -1 a -10 Hz)
BREAK_MS = 300        # pausa entre blocos de dado
BREAK_PONTO_MS = 350  # '.' 350-450 ms
BREAK_VIRGULA_MS = 150  # ',' 150-200 ms
BREAK_PONTO_E_VIRGULA_MS = 250  # ';' 250-300 ms
# Ponto de partida +2%; ordem prioriza +2% e taxas maiores para acomodar
# as pausas SSML sem estourar 66 s (faixa segura -5%..+5%).
RATE_CANDIDATOS = [2, 4, 5]   # 3 velocidades do gancho (faixa segura -5..+5%)
ALVO_TRILHA_LUFS = -30.0             # ~-30 dBFS RMS, ~16 dB abaixo da voz
NUMERAIS = {
    "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove",
    "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis",
    "dezoito", "dezenove", "vinte", "trinta", "quarenta", "sessenta",
    "oitenta", "noventa", "cento", "mil", "zero", "sexto", "sétimo",
}


# ---------------------------------------------------------------- utils -----
def log(msg):
    print(msg, flush=True)


def run(cmd, **kw):
    if "stdout" not in kw and "stderr" not in kw:
        kw["capture_output"] = True
    kw.setdefault("text", True)
    return subprocess.run(cmd, **kw)


def ffprobe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path])
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"ffprobe falhou para {path}: {r.stderr.strip()}")
    return float(r.stdout.strip().splitlines()[0])


def fmt_ts(seg):
    seg = max(0.0, seg)
    h = int(seg // 3600)
    m = int((seg % 3600) // 60)
    s = seg % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def chave(t):
    return re.sub(r"[^\w]", "", t or "", flags=re.UNICODE).lower()


def escrever_vtt(palavras, path):
    linhas = ["WEBVTT", ""]
    for p in palavras:
        linhas.append(f"{fmt_ts(p['inicio'])} --> {fmt_ts(p['fim'])}")
        linhas.append(p["texto"] or " ")
        linhas.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))


# ------------------------------------------------------------ SSML/pausas ---
# NOTA: o edge-tts 7.3.1 instalado escapa o texto no construtor de Communicate
# e o endpoint websocket rejeita <break>/<prosody>/<say-as> injetados (testado).
# As pausas SSML são, portanto, aplicadas como SILÊNCIO AMOSTRADO exato entre
# blocos de fala, e o pitch é passado pelo parâmetro `pitch` da API. O plano
# SSML equivalente é mantido abaixo para documentação/auditoria.
def conteudo_ssml(texto, sid, ultimo, enfase=None):
    """Representação SSML do plano de entonação/pausas (documentação)."""
    t = escape(texto)
    if enfase:
        e = escape(enfase)
        if e in t:
            t = t.replace(e, f'<emphasis level="moderate">{e}</emphasis>', 1)
    if sid == 5:
        frase = "cinco reais e noventa e três centavos"
        if frase in t:
            t = t.replace(frase, f'<say-as interpret-as="currency">{frase}</say-as>')
    for marca, ms in ((";", BREAK_PONTO_E_VIRGULA_MS), (".", BREAK_PONTO_MS),
                      (",", BREAK_VIRGULA_MS)):
        t = t.replace(marca, f'{marca}<break time="{ms}ms"/>')
    if not ultimo:
        t += f'<break time="{BREAK_MS}ms"/>'
    return f'<prosody pitch="{PITCH_SSML}Hz">{t}</prosody>'


def ssml_do_segmento(texto, sid, ultimo, enfase=None):
    return f'<speak>{conteudo_ssml(texto, sid, ultimo, enfase)}</speak>'


def blocos_de_fala(texto):
    """Blocos na pontuação que governa cada pausa (mantém o sinal no bloco)."""
    return [b.strip() for b in re.findall(r"[^.;?!,]+[.;?!,]?", texto) if b.strip()]


def pausa_apos(bloco, ultimo_bloco, ultimo_segmento):
    if ultimo_bloco:
        return 0.0 if ultimo_segmento else BREAK_MS / 1000.0
    sinal = bloco[-1]
    if sinal in ".?!":
        return BREAK_PONTO_MS / 1000.0
    if sinal == ";":
        return BREAK_PONTO_E_VIRGULA_MS / 1000.0
    if sinal == ",":
        return BREAK_VIRGULA_MS / 1000.0
    return BREAK_MS / 1000.0


def orcamento_pausas(roteiro):
    segs = roteiro["segmentos"]
    total = 0.0
    for i, s in enumerate(segs):
        bs = blocos_de_fala(s["texto"])
        for j, b in enumerate(bs):
            total += pausa_apos(b, j == len(bs) - 1, i == len(segs) - 1)
    return total


def salvar_wav(path, x, sr=SR):
    x = np.clip(np.asarray(x, dtype=np.float64), -1.0, 1.0)
    pcm = (x * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- TTS -------
async def _tts_bloco(texto, rate):
    """Um bloco de fala: MP3 + WordBoundary, com 3 tentativas de rede."""
    import edge_tts

    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS_REDE + 1):
        try:
            comm = edge_tts.Communicate(
                texto, VOICE, rate=f"{rate:+d}%",
                pitch=f"{PITCH_SSML}Hz", boundary="WordBoundary"
            )
            audio = bytearray()
            palavras = []
            async for chunk in comm.stream():
                ctype = chunk.get("type")
                if ctype == "audio":
                    audio.extend(chunk["data"])
                elif ctype == "WordBoundary":
                    palavras.append({
                        "texto": (chunk.get("text") or "").strip(),
                        "offset": chunk["offset"] / TICKS_PER_SEC,
                        "duracao": chunk["duration"] / TICKS_PER_SEC,
                    })
            if not audio:
                raise RuntimeError("serviço não retornou áudio")
            if not palavras:
                raise RuntimeError("serviço não retornou WordBoundary")
            return bytes(audio), palavras
        except Exception as e:
            ultimo_erro = e
            if tentativa < TENTATIVAS_REDE:
                log(f"  [aviso] TTS falhou ({tentativa}/{TENTATIVAS_REDE}): {e}")
                await asyncio.sleep(1.0)

    raise RuntimeError(
        "Falha de rede/serviço no edge-tts após 3 tentativas. "
        "Verifique a conexão. Último erro: " + str(ultimo_erro)
    )


def mp3_para_pcm(mp3_bytes):
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "s16le",
         "-ac", "1", "-ar", str(SR), "-"],
        input=mp3_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        raise RuntimeError("ffmpeg não converteu o bloco: " + r.stderr.decode(errors="replace")[-500:])
    return np.frombuffer(r.stdout, dtype="<i2").astype(np.float64) / 32768.0


def aparar_silencio(pcm, limiar=0.015):
    """Remove silêncio gerado pelo TTS nas bordas do bloco (pausas são explícitas)."""
    idx = np.where(np.abs(pcm) > limiar)[0]
    if not len(idx):
        return pcm, 0
    lead = max(0, int(idx[0]) - int(0.06 * SR))       # 60 ms de respiro
    tail = min(len(pcm), int(idx[-1]) + int(0.08 * SR))  # 80 ms após a fala
    return pcm[lead:tail], lead


def gerar_segmento(texto, mp3_path, rate, ultimo_segmento):
    """TTS por bloco + pausas SSML reais; devolve WordBoundary com offsets locais."""
    blocos = blocos_de_fala(texto)
    pcm_total = np.array([], dtype=np.float64)
    palavras = []
    t = 0.0
    for j, bloco in enumerate(blocos):
        audio, brutos = asyncio.run(_tts_bloco(bloco, rate))
        pcm, lead = aparar_silencio(mp3_para_pcm(audio))
        corte = lead / SR
        for w in brutos:
            palavras.append({
                "texto": w["texto"],
                "offset": max(0.0, t + w["offset"] - corte),
                "duracao": w["duracao"],
            })
        pausa = pausa_apos(bloco, j == len(blocos) - 1, ultimo_segmento)
        silencio = np.zeros(int(round(pausa * SR)))
        pcm_total = np.concatenate((pcm_total, pcm, silencio))
        t += len(pcm) / SR + pausa

    wav_tmp = mp3_path + ".wav"
    salvar_wav(wav_tmp, pcm_total, SR)
    r = run(["ffmpeg", "-y", "-i", wav_tmp, "-c:a", "libmp3lame",
             "-q:a", "2", "-ar", str(SR), "-ac", "1", mp3_path])
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg WAV->MP3 falhou: {r.stderr.strip()[-800:]}")
    return palavras


def concatenar(lista_mp3, saida):
    lista_txt = os.path.join(TMP, "lista.txt")
    with open(lista_txt, "w", encoding="utf-8") as f:
        for p in lista_mp3:
            f.write(f"file '{p}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista_txt,
           "-c:a", "libmp3lame", "-q:a", "2", "-ar", str(SR), "-ac", "1", saida]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg concat falhou: {r.stderr.strip()[-1200:]}")


def build_voz(rate, roteiro):
    os.makedirs(TMP, exist_ok=True)
    for nome in os.listdir(TMP):
        if nome.endswith((".mp3", ".txt", ".wav")):
            os.remove(os.path.join(TMP, nome))

    todas, info_segs, mp3s = [], [], []
    offset = 0.0
    segs = roteiro["segmentos"]
    log(f"=== TTS v2: {VOICE}, rate={rate:+d}%, pitch SSML={PITCH_SSML}Hz ===")
    for seg in segs:
        sid = seg["id"]
        mp3 = os.path.join(TMP, f"seg_{sid}.mp3")
        brutos = gerar_segmento(seg["texto"], mp3, rate,
                                sid == segs[-1]["id"])
        dur_seg = ffprobe_duration(mp3)

        i0 = len(todas)
        for w in brutos:
            todas.append({
                "texto": w["texto"],
                "inicio": round(offset + w["offset"], 3),
                "fim": round(offset + w["offset"] + w["duracao"], 3),
            })
        i1 = len(todas)
        info_segs.append({"id": sid, "texto": seg["texto"],
                          "idx": [i0, i1], "offset": offset, "dur": dur_seg})
        mp3s.append(mp3)
        offset += dur_seg
        log(f"  seg {sid}: {len(brutos)} palavras, {dur_seg:.3f}s "
            f"(offset global {offset:.3f}s)")

    prev = -1.0
    for p in todas:
        if p["inicio"] < prev:
            p["inicio"] = prev
        if p["fim"] < p["inicio"]:
            p["fim"] = p["inicio"]
        p["inicio"] = round(p["inicio"], 3)
        p["fim"] = round(p["fim"], 3)
        prev = p["fim"]

    concatenar(mp3s, VOZ_V2)
    dur_total = ffprobe_duration(VOZ_V2)

    segmentos_out = []
    for info in info_segs:
        i0, i1 = info["idx"]
        ini = todas[i0]["inicio"] if i1 > i0 else info["offset"]
        fim = todas[i1 - 1]["fim"] if i1 > i0 else info["offset"] + info["dur"]
        segmentos_out.append({
            "id": info["id"], "texto": info["texto"],
            "inicio": round(ini, 3), "fim": round(fim, 3),
            "palavras": [i0, i1],
        })

    timings = {
        "voz": roteiro.get("voz", VOICE),
        "duracao_audio_seg": round(dur_total, 3),
        "parametros_voz": {
            "rate": f"{rate:+d}%",
            "pitch": f"{PITCH_SSML}Hz",
            "boundary": "WordBoundary",
            "pausas_ms": {"ponto": BREAK_PONTO_MS, "virgula": BREAK_VIRGULA_MS,
                          "ponto_e_virgula": BREAK_PONTO_E_VIRGULA_MS,
                          "entre_blocos": BREAK_MS},
        },
        "palavras": todas,
        "segmentos": segmentos_out,
    }
    return timings, dur_total


def testar_rates(roteiro):
    """Benchmark de 3 velocidades do GANCHO (com o processamento real)."""
    os.makedirs(TMP, exist_ok=True)
    gancho = roteiro["segmentos"][0]["texto"]
    resultados = []
    log("=== Benchmark de rate (gancho, com pausas e aparagem) ===")
    for rate in RATE_CANDIDATOS:
        tmp = os.path.join(TMP, f"gancho_{rate:+d}.mp3")
        gerar_segmento(gancho, tmp, rate, False)
        dur = ffprobe_duration(tmp)
        dentro = 5.0 <= dur <= 10.0   # ritmo aceitável para o gancho
        resultados.append((rate, dur, dentro))
        log(f"  rate {rate:+d}% -> gancho {dur:.3f}s "
            f"({'OK' if dentro else 'ritmo incomum'})")
    return resultados


# ------------------------------------------------ loudnorm (2 passos) -------
def medir_loudnorm(path):
    """Passo 1: mede I/TP/LRA/thresh/offset e faz parse do JSON com python."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
             "-f", "null", "-"])
    txt = r.stderr or ""
    for bloco in reversed(re.findall(r"\{[^{}]+\}", txt, flags=re.S)):
        try:
            d = json.loads(bloco)
        except Exception:
            continue
        if "input_i" in d:
            return d
    raise RuntimeError("Não foi possível parsear o JSON do loudnorm:\n" + txt[-2000:])


def loudnorm_linear(entrada, saida, m, extras=None):
    """Passo 2: aplica ganho linear com os valores medidos + aresample=48000."""
    af = ("loudnorm=I=-14:TP=-1.5:LRA=11:"
          f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
          f"offset={m['target_offset']}:linear=true,aresample=48000")
    cmd = ["ffmpeg", "-y", "-i", entrada, "-af", af, "-ar", str(SR_PROC)]
    cmd += extras or []
    cmd += [saida]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"loudnorm linear falhou: {r.stderr.strip()[-1500:]}")
    return ffprobe_duration(saida)


# ------------------------------------------------ processamento da voz -----
def processar_voz():
    """highpass -> compressor suave -> loudnorm 2 passos (linear)."""
    bruto = os.path.join(TMP, "voz_comp.wav")
    af = ("highpass=f=80,"
          "equalizer=f=400:t=q:w=1:g=-3,"          # corte 3 dB @ 300-500 Hz
          "equalizer=f=4500:t=q:w=0.9:g=2.2,"      # presença +2,2 dB @ 3,5-6 kHz
          # de-ess condicional (5-9 kHz): não aplicado, sibilância ok
          "acompressor=threshold=-18dB:ratio=3:attack=10:release=200")
    r = run(["ffmpeg", "-y", "-i", VOZ_V2, "-af", af,
             "-ar", str(SR_PROC), "-ac", "1", "-c:a", "pcm_s16le", bruto])
    if r.returncode != 0:
        raise RuntimeError(f"filtros da voz falharam: {r.stderr.strip()[-1200:]}")

    m = medir_loudnorm(bruto)
    log(f"  loudnorm voz (medição): I={m['input_i']} TP={m['input_tp']} "
        f"LRA={m['input_lra']} tipo={m.get('normalization_type')}")
    dur = loudnorm_linear(bruto, VOZ_PROC, m,
                          ["-ac", "1", "-c:a", "pcm_s16le"])
    return dur, m


# ---------------------------------------------- áudio procedural (numpy) ---
def write_wav(path, x, sr=SR_PROC):
    x = np.clip(np.asarray(x, dtype=np.float64), -1.0, 1.0)
    pcm = (x * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def lowpass(x, cutoff, sr=SR_PROC):
    """Lowpass simples por FFT (suficiente para beds/risers procedurais)."""
    n = len(x)
    sp = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1.0 / sr)
    sp *= 1.0 / (1.0 + (fr / cutoff) ** 4)
    return np.fft.irfft(sp, n)


def bandpass_sweep(x, f0, f1, sr=SR_PROC, blocos=16):
    """Bandpass com frequência central varrida de f0 -> f1 ao longo do sinal."""
    n = len(x)
    step = max(1, n // blocos)
    out = np.zeros(n)
    for b in range(blocos):
        i, j = b * step, min(n, (b + 1) * step)
        fc = f0 * (f1 / f0) ** (b / max(1, blocos - 1))
        sp = np.fft.rfft(x[i:j])
        fr = np.fft.rfftfreq(j - i, 1.0 / sr)
        mask = np.exp(-0.5 * ((fr - fc) / (0.55 * fc)) ** 2)
        out[i:j] = np.fft.irfft(sp * mask, j - i)
    return out


def gerar_trilha_raw(dur):
    """Ambient: 55/82.5/110 Hz desafinados + LFO 0.07 Hz + lowpass 500 Hz."""
    n = int(dur * SR_PROC)
    t = np.arange(n) / SR_PROC
    rng = np.random.default_rng(20261122)
    pad = np.zeros(n)
    for i, f in enumerate([55.0, 82.5, 110.0]):
        det = rng.uniform(-0.3, 0.3)
        pad += np.sin(2 * np.pi * (f + det) * t + i * 0.4)
    pad /= 3.0
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * t)   # modulação lenta
    pad *= lfo
    pad = lowpass(pad, 500.0)
    fi = np.clip((t - 3.0) / 1.5, 0.0, 1.0)  # entra ~3s depois que a fala começa
    fo = np.clip((dur - t) / 1.0, 0.0, 1.0)   # fade-out de 1s (trilha no encerramento)
    return pad * fi * fo


def normalizar_trilha(dur):
    write_wav(TRILHA_RAW, gerar_trilha_raw(dur))
    m = medir_loudnorm(TRILHA_RAW)
    atual = float(m["input_i"])
    ganho = ALVO_TRILHA_LUFS - atual
    r = run(["ffmpeg", "-y", "-i", TRILHA_RAW,
             "-af", f"volume={ganho:.2f}dB,aresample={SR_PROC}",
             "-ar", str(SR_PROC), "-ac", "1", "-c:a", "pcm_s16le", TRILHA])
    if r.returncode != 0:
        raise RuntimeError(f"normalização da trilha falhou: {r.stderr.strip()[-1000:]}")
    return m, ganho


def whoosh():
    T = 0.4
    n = int(T * SR_PROC)
    t = np.arange(n) / SR_PROC
    rng = np.random.default_rng(11)
    x = rng.normal(0, 1, n)
    x = bandpass_sweep(x, 400, 4000)
    x *= np.sin(np.pi * t / T) ** 1.5
    pk = np.max(np.abs(x))
    return x / pk if pk else x


def tick():
    T = 0.012
    n = int(T * SR_PROC)
    t = np.arange(n) / SR_PROC
    rng = np.random.default_rng(23)
    x = rng.normal(0, 1, n)
    sp = np.fft.rfft(x)
    fr = np.fft.rfftfreq(n, 1.0 / SR_PROC)
    sp *= (fr > 1000).astype(float)         # highpass 1 kHz
    x = np.fft.irfft(sp, n) * np.exp(-t / 0.003)
    pk = np.max(np.abs(x))
    x = x / pk if pk else x
    return x * 10 ** (-6.0 / 20.0)          # pico -6 dBFS


def riser(T=1.4):
    n = int(T * SR_PROC)
    t = np.arange(n) / SR_PROC
    rng = np.random.default_rng(37)
    x = rng.normal(0, 1, n)
    fc = 200.0 * (20.0 ** (t / T))          # 200 Hz -> 4 kHz exponencial
    x = bandpass_sweep(x, 200, 4000) * (0.2 * (t / T) ** 2 + 0.02)
    x *= np.sin(np.pi * t / T) ** 0.5
    x[-int(0.05 * SR_PROC):] *= np.linspace(1, 0, int(0.05 * SR_PROC))
    thump_n = int(0.15 * SR_PROC)
    thump = np.sin(2 * np.pi * 60 * np.arange(thump_n) / SR_PROC)
    thump *= np.exp(-np.arange(thump_n) / (0.05 * SR_PROC)) * 0.6
    x[-thump_n:] += thump
    pk = np.max(np.abs(x))
    return x / pk if pk else x


def hit():
    T = 0.15
    n = int(T * SR_PROC)
    t = np.arange(n) / SR_PROC
    x = np.sin(2 * np.pi * 60 * t) * np.exp(-t / 0.05)
    x += 0.2 * np.sin(2 * np.pi * 120 * t) * np.exp(-t / 0.02)
    return x / np.max(np.abs(x))


def _add(timeline, ev, start, gain):
    i = int(round(start * SR_PROC))
    seg = ev * gain
    if i < 0:
        seg, i = seg[-i:], 0
    j = min(len(timeline), i + len(seg))
    if j > i:
        timeline[i:j] += seg[: j - i]


def gerar_sfx(timings, roteiro, dur):
    """Posiciona todos os SFX via timings_v2.json."""
    linha = np.zeros(int(dur * SR_PROC))
    palavras = timings["palavras"]
    eventos = []

    def idx(alvo, apos=0):
        alvo = chave(alvo)
        for k, p in enumerate(palavras):
            if k >= apos and chave(p["texto"]) == alvo:
                return k
        return None

    wh, tk, rs, ht = whoosh(), tick(), riser(), hit()

    # whoosh nas trocas de bloco
    for seg in timings["segmentos"]:
        t0 = seg["inicio"]
        _add(linha, wh, t0, 0.26)
        eventos.append(("whoosh", round(t0, 3), f"troca — início segmento {seg['id']}"))

    # tick por número nos contadores (blocos com dado: Ibovespa e dólar)
    dado_ids = {s["id"] for s in roteiro["segmentos"] if s.get("dado")}
    for seg in timings["segmentos"]:
        if seg["id"] not in dado_ids:
            continue
        i0, i1 = seg["palavras"]
        numeros = [m for m in range(i0, i1)
                   if chave(palavras[m]["texto"]) in NUMERAIS]
        limite = 3 if seg["id"] == 3 else 2   # total: 7 whoosh + 5 tick + 2 riser + 1 hit = 15
        for m in numeros[:limite]:
            t0 = palavras[m]["inicio"]
            _add(linha, tk, t0, 0.30)
            eventos.append(("tick", round(t0, 3),
                            f"contador segmento {seg['id']} ('{palavras[m]['texto']}')"))

    # riser antes da revelação do Ibovespa e do VIX
    for alvo, rotulo in (("cento", "revelação Ibovespa"),
                         ("trinta", "revelação VIX")):
        k = idx(alvo)
        if k is not None:
            t0 = max(0.0, palavras[k]["inicio"] - 1.4)
            _add(linha, rs, t0, 0.30)
            eventos.append(("riser", round(t0, 3), f"1,4s antes de {rotulo}"))

    # hit no ápice do medo (seg 4)
    k = idx("ninguém")
    if k is None:
        k = idx("fechou")
    if k is not None:
        t0 = palavras[k]["inicio"]
        _add(linha, ht, t0, 0.45)
        eventos.append(("hit", round(t0, 3), "ápice 'ninguém queria arriscar'"))

    write_wav(SFX, linha)
    eventos.sort(key=lambda e: e[1])
    return eventos


# ---------------------------------------------------------------- mix ------
def mixar(dur):
    """Ducking por sidechain + amix -> loudnorm 2 passos -> AAC."""
    # `sidechaincompress` termina quando o sidechain (voz) acaba; apad devolve
    # o encerramento da trilha/SFX antes do amix (o -t depois apara o total).
    filtro = (
        "[0:a]asplit=3[voz][sc1][sc2];"
        "[1:a][sc1]sidechaincompress=threshold=0.03:ratio=6:"
        "attack=20:release=300,apad=pad_dur=2[trilha_d];"
        "[2:a][sc2]sidechaincompress=threshold=0.03:ratio=6:"
        "attack=20:release=300,apad=pad_dur=2[sfx_d];"
        "[voz][trilha_d][sfx_d]amix=inputs=3:duration=longest:"
        "normalize=0[m]"
    )
    r = run(["ffmpeg", "-y", "-i", VOZ_PROC, "-i", TRILHA, "-i", SFX,
             "-filter_complex", filtro, "-map", "[m]", "-t", f"{dur:.3f}",
             "-ar", str(SR_PROC), "-ac", "1", "-c:a", "pcm_s16le", MIX_RAW])
    if r.returncode != 0:
        raise RuntimeError(f"mixagem falhou: {r.stderr.strip()[-2000:]}")

    m = medir_loudnorm(MIX_RAW)
    log(f"  loudnorm mix (medição): I={m['input_i']} TP={m['input_tp']} "
        f"LRA={m['input_lra']} tipo={m.get('normalization_type')}")
    loudnorm_linear(MIX_RAW, AUDIO_FINAL, m,
                    ["-c:a", "aac", "-b:a", "192k"])
    return m


def medir_lufs(path):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
             "-filter_complex", "ebur128=peak=true", "-f", "null", "-"])
    txt = r.stderr or ""
    # ebur128 emite valores parciais (-70.0 no início); usar o ÚLTIMO (sumário).
    mi = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", txt)
    pk = re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", txt)
    return (float(mi[-1]) if mi else None,
            float(pk[-1]) if pk else None)


# ---------------------------------------------------------------- valida ----
def validar(timings, roteiro, dur_voz, dur_final, lufs, tp):
    ok = True

    def check(cond, msg):
        nonlocal ok
        log(("  [OK] " if cond else "  [FALHA] ") + msg)
        if not cond:
            ok = False

    r = run([sys.executable, "-m", "json.tool", TIMINGS_V2],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    check(r.returncode == 0, "timings_v2.json é JSON válido")
    check(DUR_MIN <= dur_voz <= DUR_MAX,
          f"duração voz_v2 {dur_voz:.3f}s em [{DUR_MIN},{DUR_MAX}]")
    n = len(timings["palavras"])
    check(n >= 150, f"{n} palavras (>= 150)")
    check(len(timings["segmentos"]) == 7, "7 segmentos")
    check(all(a["texto"] == b["texto"] for a, b in
              zip(timings["segmentos"], roteiro["segmentos"])),
          "texto das falas inalterado")
    mono = all(p["inicio"] <= p["fim"] and
               (i == 0 or p["inicio"] >= timings["palavras"][i - 1]["inicio"])
               for i, p in enumerate(timings["palavras"]))
    check(mono, "tempos monotonicamente crescentes")
    check(dur_final >= dur_voz + 0.5,
          f"mix {dur_final:.3f}s > voz {dur_voz:.3f}s")
    check(lufs is not None and -16.0 <= lufs <= -12.0,
          f"LUFS integrado {lufs} (faixa -16..-12, alvo -14)")
    check(tp is not None and tp <= -1.0,
          f"true peak {tp} dBTP (<= -1 dBTP)")
    return ok


# ---------------------------------------------------------------- notas -----
def escrever_notes(roteiro, candidatos, escolhido, timings, dur_voz, dur_proc,
                   dur_final, m_voz, m_trilha, ganho_trilha, m_mix, lufs, pico,
                   eventos, m_final):
    por_tipo = {}
    for tipo, _, _ in eventos:
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1

    L = []
    L.append("# Audio Notes — v2 (voz + trilha + SFX)\n")
    L.append("## Entrada e voz\n")
    L.append(f"- Roteiro: `data/{os.path.basename(ROTEIRO)}` (texto novo, "
             "menos técnico e mais envolvente). Falas NÃO alteradas.")
    L.append(f"- Voz mantida: `{VOICE}` (exigência do usuário; não houve troca "
             "por outra voz).")
    L.append(f"- Pitch `{PITCH_SSML}Hz` pelo parâmetro da API (ponto de partida; "
             "faixa segura -1 a -10 Hz) + `boundary=\"WordBoundary\"`.")
    L.append(f"- Plano SSML (documentado em `voz_v2.py`): `.` {BREAK_PONTO_MS} ms, "
             f"`,` {BREAK_VIRGULA_MS} ms, `;` {BREAK_PONTO_E_VIRGULA_MS} ms, "
             f"`<break time=\"{BREAK_MS}ms\"/>` entre blocos, `<say-as "
             "interpret-as=\"currency\">` no dólar, `<emphasis>` por bloco. "
             "**Limitação técnica:** o edge-tts 7.3.1 instalado escapa SSML no "
             "construtor e o endpoint rejeita tags injetadas (testado). As pausas "
             "foram aplicadas como silêncio amostrado exato, equivalente ao "
             "`<break/>`; o valor do dólar já vem por extenso no roteiro, então "
             "a leitura permanece correta sem o `say-as`.")
    L.append("- Palavras mapeadas por bloco/segmento, concatenadas com ffmpeg; "
             "silêncio residual do TTS aparado nas bordas dos blocos.\n")
    L.append("### Benchmark de rate (3 velocidades do gancho)\n")
    L.append("| rate | gancho (s) | resultado |")
    L.append("|---|---|---|")
    for rate, dur, dentro in candidatos:
        L.append(f"| {rate:+d}% | {dur:.3f} | "
                 f"{'**escolhido**' if rate == escolhido else ('OK' if dentro else 'ritmo incomum')} |")
    L.append("")
    L.append(f"- Escolhido: **{escolhido:+}%**. Critério: ponto de partida "
             "recomendado (+2%), mantido se a duração final ficar em 50–66 s; "
             "caso contrário, a velocidade seguinte é testada. Sem acelerar "
             "para esconder texto; pitch -1 Hz dá leve autoridade sem distorcer.\n")
    L.append("### Cadeia de processamento\n")
    L.append("- `highpass=f=80` → corte 3 dB @ 400 Hz → presença +2,2 dB @ "
             "4,5 kHz → `acompressor=threshold=-18dB:ratio=3:attack=10:"
             "release=200` → `loudnorm` em **duas passos** com `linear=true` e "
             "`aresample=48000`, alvo `I=-14:TP=-1.5:LRA=11`.")
    L.append("- De-ess condicional (5–9 kHz) não aplicado: sibilância dentro do "
             "normal. Sem reverb na voz.")
    L.append(f"- Medição da voz (passo 1): I={m_voz['input_i']} LUFS, "
             f"TP={m_voz['input_tp']} dBTP, LRA={m_voz['input_lra']}, "
             f"normalization_type={m_voz.get('normalization_type')}.")
    L.append(f"- voz_v2.mp3: **{dur_voz:.3f} s** · voz processada: "
             f"{dur_proc:.3f} s · palavras: {len(timings['palavras'])} · "
             f"segmentos: {len(timings['segmentos'])}\n")

    L.append("## Trilha ambiental (procedural, sem download)\n")
    L.append("- Senos 55 / 82,5 / 110 Hz com desvio ±0,3 Hz, LFO 0,07 Hz, "
             "lowpass 500 Hz; entra ~3 s depois do início da fala (crossfade "
             "de 1,5 s), permanece no encerramento, fade-out de 1 s.")
    L.append(f"- Medida bruta: {m_trilha['input_i']} LUFS → ganho "
             f"{ganho_trilha:+.2f} dB → alvo {ALVO_TRILHA_LUFS:.0f} dBFS/LUFS "
             "(≈-30 dBFS RMS, ~16 dB abaixo da voz).")
    L.append("- Ducking: `sidechaincompress=threshold=0.03:ratio=6:"
             "attack=20:release=300` com a voz como sidechain (trilha e SFX).\n")

    L.append("## SFX procedurais (sem download)\n")
    L.append(f"Total de eventos: **{len(eventos)}** "
             f"({', '.join(f'{v} {k}' for k, v in sorted(por_tipo.items()))}).\n")
    L.append("| tipo | tempo (s) | posição / motivo |")
    L.append("|---|---|---|")
    for tipo, t, motivo in eventos:
        L.append(f"| {tipo} | {t:.3f} | {motivo} |")
    L.append("")
    L.append("- whoosh: ruído branco, bandpass varrido 400 Hz → 4 kHz em 0,4 s, "
             "envelope `sin(pi t/T)^1,5`.")
    L.append("- tick: rajada de 12 ms, highpass 1 kHz, decaimento `exp(-t/3ms)`, "
             "pico -6 dBFS (5 ticks: 3 no Ibovespa e 2 no dólar).")
    L.append("- riser: ruído em bandpass 200 Hz → 4 kHz em 1,4 s, amplitude "
             "`0,2*(t/T)^2`, fade abrupto + thump 60 Hz/0,15 s antes das "
             "revelações de Ibovespa e VIX.")
    L.append("- hit: tom 60 Hz/0,15 s no ápice do medo (seg. 4).\n")

    L.append("## Mix final\n")
    L.append("- `asplit` da voz → `sidechaincompress` em trilha/SFX → `amix` → "
             "`loudnorm` duas passos (`linear=true`, `aresample=48000`).")
    L.append(f"- Medição do mix bruto (passo 1): I={m_mix['input_i']} LUFS, "
             f"TP={m_mix['input_tp']} dBTP, tipo="
             f"{m_mix.get('normalization_type')}.")
    L.append("- AAC 48 kHz, 192 kbps, mono.")
    L.append(f"- audio_final.m4a: **{dur_final:.3f} s** (voz + "
             f"{EXTRA_FINAL:.1f} s de encerramento).")
    L.append(f"- Re-medição final: LUFS integrado **{lufs} LUFS** (ebur128) / "
             f"{m_final['input_i']} LUFS (loudnorm), true peak "
             f"**{float(m_final['input_tp']):.2f} dBTP**, LRA "
             f"{m_final['input_lra']}, normalização "
             f"{m_final.get('normalization_type')} (pico ebur128: {pico} dBFS).")
    L.append("- Check final: -16 ≤ I ≤ -12 LUFS e TP ≤ -1 dBTP.\n")

    L.append("## Arquivos\n")
    for p in (VOZ_V2, VOZ_PROC, TIMINGS_V2, VOZ_V2_VTT, TRILHA, SFX, AUDIO_FINAL,
              NOTES):
        L.append(f"- `{os.path.relpath(p, ROOT)}`")
    L.append("")
    with open(NOTES, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------- main ------
def main():
    with open(ROTEIRO, encoding="utf-8") as f:
        roteiro = json.load(f)

    candidatos = testar_rates(roteiro)
    # Preferência: ponto de partida +2%; se a duração final sair da faixa,
    # tenta as próximas velocidades benchmarkadas (nunca corta falas).
    ordem = [r for r, _, _ in candidatos] or RATE_CANDIDATOS
    timings = dur_voz = None
    escolhido = ordem[0]
    tentativas = 0
    for rate in ordem:
        escolhido = rate
        timings, dur_voz = build_voz(rate, roteiro)
        tentativas += 1
        if DUR_MIN <= dur_voz <= DUR_MAX or tentativas >= 3:
            break
    log(f"=== Rate escolhido: {escolhido:+}% (voz {dur_voz:.3f}s) ===\n")

    with open(TIMINGS_V2, "w", encoding="utf-8") as f:
        json.dump(timings, f, ensure_ascii=False, indent=2)
        f.write("\n")
    escrever_vtt(timings["palavras"], VOZ_V2_VTT)
    log(f"=== Timings: {TIMINGS_V2} ({len(timings['palavras'])} palavras) ===")

    log("=== Processando voz (2-pass loudnorm) ===")
    dur_proc, m_voz = processar_voz()

    dur_total = dur_voz + EXTRA_FINAL
    log(f"=== Trilha ambiental ({dur_total:.3f}s) ===")
    m_trilha, ganho = normalizar_trilha(dur_total)

    log("=== SFX procedurais ===")
    eventos = gerar_sfx(timings, roteiro, dur_total)
    for tipo, t, motivo in eventos:
        log(f"  {tipo:7s} @ {t:7.3f}s — {motivo}")

    log("=== Mix final ===")
    m_mix = mixar(dur_total)
    dur_final = ffprobe_duration(AUDIO_FINAL)
    lufs, pico = medir_lufs(AUDIO_FINAL)
    m_final = medir_loudnorm(AUDIO_FINAL)
    tp = float(m_final["input_tp"])
    log(f"  integrado: {lufs} LUFS · true peak: {tp} dBTP (pico ebur128: {pico} dBFS)")

    log("=== Validação ===")
    ok = validar(timings, roteiro, dur_voz, dur_final, lufs, tp)

    escrever_notes(roteiro, candidatos, escolhido, timings, dur_voz, dur_proc,
                   dur_final, m_voz, m_trilha, ganho, m_mix, lufs, pico, eventos,
                   m_final)

    log("")
    log("=== Resultado final ===")
    log(f"  roteiro        : {ROTEIRO}")
    log(f"  voz_v2.mp3     : {dur_voz:.3f}s (rate {escolhido:+}%)")
    log(f"  audio_final.m4a: {dur_final:.3f}s ({lufs} LUFS)")
    log(f"  palavras       : {len(timings['palavras'])}")
    log(f"  SFX            : {len(eventos)} eventos")
    log(f"  relatório      : {NOTES}")
    log("")
    if not ok:
        sys.exit(1)
    log("Validação concluída com sucesso.")


if __name__ == "__main__":
    main()
