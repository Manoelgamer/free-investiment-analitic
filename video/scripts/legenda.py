#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Legenda karaoke sincronizada para o video vertical de investimentos.

Contrato publico:
    carregar_timings(caminho)            -> dict
    construir_blocos(timings, 7)         -> list[dict]
    escrever_srt(blocos, caminho)        -> None
    desenhar_legenda(frame, bloco, t)    -> frame (MESMA imagem RGBA modificada)

Os tempos das palavras vem de build/timings.json (tempo REAL do audio de 62,955s).
O karaoke usa esses tempos reais, pois 't' em desenhar_legenda e o tempo do frame
de video (que acompanha o audio). Os blocos nunca se sobrepoem: o inicio de um
bloco e, no minimo, o fim do anterior + 0.02s.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMINGS_PATH = os.path.join(BASE_DIR, "build", "timings.json")
SRT_PATH = os.path.join(BASE_DIR, "build", "legenda.srt")

MAX_LINHAS = 2
DUR_MIN = 0.7
DUR_MAX = 3.2
SPAN_MAX = 2.2          # span das palavras de um grupo (deixa folga p/ o silencio
                        # seguinte, garantindo bloco <= 3.2s e SEP exato de 0.02s)
GAP_MAX = 0.60          # silencio maior que isso separa frases / blocos
SEP = 0.02              # espaco minimo entre blocos (inicio = fim anterior + SEP)

FONTE_TAMANHO = 58
AMARELO = (255, 216, 77, 255)     # #FFD84D - palavra ativa
BRANCO = (255, 255, 255, 255)     # #FFFFFF - palavra futura
BRANCO_FRANCO = (255, 255, 255, 150)  # palavra ja dita (alpha 150)
PRETO_CAIXA = (0, 0, 0, 150)      # caixa de fundo semitransparente
BORDA = (0, 0, 0, 255)            # contorno escuro do texto

REGIAO_X0, REGIAO_X1 = 30, 1050   # margens horizontais
REGIAO_Y0, REGIAO_Y1 = 1490, 1660 # faixa vertical da legenda


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def carregar_timings(caminho: str) -> dict:
    """Carrega o JSON de timings (palavras com texto/inicio/fim)."""
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    return dados


def construir_blocos(timings: dict, max_palavras: int = 7) -> list[dict]:
    """
    Agrupa as palavras em blocos curtos (no maximo `max_palavras` e 2 linhas),
    quebrando apenas em espacos (entre palavras) e em silencios naturais.

    Cada bloco: {"texto", "inicio", "fim",
                 "palavras": [{"texto","inicio","fim"}, ...]}
    """
    palavras = timings["palavras"]
    if not palavras:
        return []

    # 1) Agrupamento greedy: ate `max_palavras`, sem ultrapassar DUR_MAX e sem
    #    atravessar silencios longos (quebras naturais de frase).
    grupos: list[list[dict]] = []
    i = 0
    n = len(palavras)
    while i < n:
        grupo = [palavras[i]]
        j = i + 1
        while j < n and len(grupo) < max_palavras:
            gap = palavras[j]["inicio"] - grupo[-1]["fim"]
            if gap > GAP_MAX:
                break
            if palavras[j]["fim"] - grupo[0]["inicio"] > SPAN_MAX:
                break
            grupo.append(palavras[j])
            j += 1
        grupos.append(grupo)
        i = j

    # 2) Fundir grupos muito curtos (< DUR_MIN) com o seguinte, quando couber.
    fundidos: list[list[dict]] = []
    k = 0
    while k < len(grupos):
        atual = grupos[k]
        span = atual[-1]["fim"] - atual[0]["inicio"]
        if span < DUR_MIN and k + 1 < len(grupos):
            prox = grupos[k + 1]
            if (len(atual) + len(prox) <= max_palavras and
                    prox[-1]["fim"] - atual[0]["inicio"] <= SPAN_MAX):
                atual = atual + prox
                k += 1
        fundidos.append(atual)
        k += 1
    grupos = fundidos

    # 2b) Rebalancear blocos da mesma fraque para evitar palavras orfas (ex.:
    #     "... por" + "cento" -> "... por cento"). Nunca cruza silencios longos.
    for k in range(len(grupos) - 1):
        a, b = grupos[k], grupos[k + 1]
        gap = b[0]["inicio"] - a[-1]["fim"]
        if gap > GAP_MAX:
            continue
        if len(a) >= 5 and len(b) <= 2 and len(a) + len(b) <= 2 * max_palavras:
            total = a + b
            meio = len(total) // 2
            meio = min(max(meio, len(total) - max_palavras), max_palavras)
            if meio != len(a):
                grupos[k] = total[:meio]
                grupos[k + 1] = total[meio:]

    # 3) Tempos reais + garantia de nao sobreposicao (inicio = fim anterior + SEP).
    blocos: list[dict] = []
    anterior_fim: float | None = None
    for idx, grupo in enumerate(grupos):
        inicio = float(grupo[0]["inicio"])
        fim = float(grupo[-1]["fim"])

        # Se houver proximo bloco, estende a exibicao ate pouco antes dele.
        # Isso faz o limite entre blocos ser exatamente: inicio = fim + SEP.
        if idx + 1 < len(grupos):
            fim = float(grupos[idx + 1][0]["inicio"]) - SEP

        # Nao sobrepor, mesmo que a extensao acima tenha sido curta.
        if anterior_fim is not None and inicio < anterior_fim + SEP:
            inicio = anterior_fim + SEP

        # Duracao minima: se couber antes do proximo bloco, estende o fim;
        # caso contrario, antecipa o inicio (sem invadir o bloco anterior).
        if fim - inicio < DUR_MIN:
            if idx + 1 < len(grupos):
                limite = float(grupos[idx + 1][0]["inicio"]) - SEP
            else:
                limite = math.inf
            if limite - inicio >= DUR_MIN:
                fim = inicio + DUR_MIN
            else:
                inicio = max(
                    (anterior_fim + SEP) if anterior_fim is not None else inicio,
                    fim - DUR_MIN,
                )

        # Duracao maxima (seguranca).
        if fim - inicio > DUR_MAX:
            fim = inicio + DUR_MAX

        fim = max(fim, inicio + 0.01)

        blocos.append({
            "texto": " ".join(p["texto"] for p in grupo),
            "inicio": round(inicio, 3),
            "fim": round(fim, 3),
            "palavras": [
                {"texto": p["texto"], "inicio": float(p["inicio"]), "fim": float(p["fim"])}
                for p in grupo
            ],
        })
        anterior_fim = fim

    return blocos


def escrever_srt(blocos: list[dict], caminho: str) -> None:
    """Escreve o SRT padrao (sem tags HTML), com numeracao a partir de 1."""
    linhas: list[str] = []
    for numero, bloco in enumerate(blocos, start=1):
        inicio = _fmt_srt(bloco["inicio"])
        fim = _fmt_srt(bloco["fim"])
        texto = "\n".join(" ".join(p["texto"] for p in linha)
                          for linha in _dividir_linhas(bloco["palavras"]))
        linhas.extend([str(numero), f"{inicio} --> {fim}", texto, ""])

    diretorio = os.path.dirname(caminho)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))


def desenhar_legenda(frame, bloco: dict, t: float):
    """
    Desenha a legenda karaoke em `frame` (PIL.Image RGBA 1080x1920) e retorna a
    MESMA imagem modificada.

    - palavra ativa (inicio <= t <= fim): amarelo #FFD84D
    - palavra ja dita (t > fim): branco com alpha 150
    - palavra futura: branco
    - caixa preta semitransparente (alpha 150) com cantos arredondados
    - contorno escuro (stroke_width=3)

    Pura o suficiente para ser chamada a cada frame: usa um overlay novo e
    compoe apenas dentro da regiao da legenda, sem acumular efeitos.
    """
    if frame.mode != "RGBA":
        raise ValueError("frame deve ser RGBA")

    largura, altura = frame.size
    fonte = _obter_fonte()

    linhas = _dividir_linhas(bloco["palavras"])
    espaco = fonte.getlength(" ")
    altura_linha = int(FONTE_TAMANHO * 1.17)
    padding_x, padding_y = 22, 14

    # Largura de cada linha (soma das palavras + espacos).
    larguras = []
    for linha in linhas:
        w = sum(fonte.getlength(p["texto"]) for p in linha)
        w += espaco * max(0, len(linha) - 1)
        larguras.append(w)
    largura_conteudo = max(larguras) if larguras else 0

    box_w = min(largura - 2 * 20, int(largura_conteudo) + 2 * padding_x)
    box_h = min(altura_linha * len(linhas) + 2 * padding_y, REGIAO_Y1 - REGIAO_Y0)
    box_w = max(box_w, 120)

    box_x0 = max(0, (largura - box_w) // 2)
    faixa = max(1, REGIAO_Y1 - REGIAO_Y0)
    box_y0 = REGIAO_Y0 + max(0, (faixa - box_h) // 2)
    box_y0 = max(0, min(box_y0, altura - box_h))
    box_x1 = min(largura, box_x0 + box_w)
    box_y1 = min(altura, box_y0 + box_h)

    # Overlay novo -> nada acumula entre frames.
    overlay = Image.new("RGBA", (box_x1 - box_x0, box_y1 - box_y0), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        (0, 0, overlay.width - 1, overlay.height - 1),
        radius=18, fill=PRETO_CAIXA,
    )

    y = float(padding_y)
    for linha, largura_linha in zip(linhas, larguras):
        x = (overlay.width - largura_linha) / 2.0
        for palavra in linha:
            if palavra["inicio"] <= t <= palavra["fim"]:
                cor = AMARELO
            elif t > palavra["fim"]:
                cor = BRANCO_FRANCO
            else:
                cor = BRANCO
            draw.text(
                (x, y), palavra["texto"], font=fonte, fill=cor,
                stroke_width=3, stroke_fill=BORDA,
            )
            x += fonte.getlength(palavra["texto"]) + espaco
        y += altura_linha

    # Compondo apenas na regiao da legenda, com blending correto do alpha.
    frame.alpha_composite(overlay, dest=(box_x0, box_y0))
    return frame


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _dividir_linhas(palavras: list[dict]) -> list[list[dict]]:
    """Quebra as palavras em no maximo 2 linhas, nunca no meio de uma palavra."""
    if not palavras:
        return [[]]
    if len(palavras) <= 4:
        return [list(palavras)]
    meio = math.ceil(len(palavras) / 2)
    return [list(palavras[:meio]), list(palavras[meio:])]


def _fmt_srt(segundos: float) -> str:
    ms = int(round(segundos * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


_FONTE_CACHE: Any = None


def _obter_fonte():
    global _FONTE_CACHE
    if _FONTE_CACHE is not None:
        return _FONTE_CACHE

    candidatos = [
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for caminho in candidatos:
        try:
            _FONTE_CACHE = ImageFont.truetype(caminho, FONTE_TAMANHO)
            return _FONTE_CACHE
        except OSError:
            continue

    base = ImageFont.load_default()
    try:
        _FONTE_CACHE = base.font_variant(size=FONTE_TAMANHO)
    except Exception:
        _FONTE_CACHE = base
    return _FONTE_CACHE


# ---------------------------------------------------------------------------
# Execucao standalone
# ---------------------------------------------------------------------------
def _validar(blocos: list[dict], timings: dict) -> None:
    """Validacoes internas rapidas das regras de legenda."""
    assert blocos, "nenhum bloco gerado"
    anterior_fim = None
    for idx, b in enumerate(blocos):
        assert 0 < len(b["palavras"]) <= 7, f"bloco {idx}: word count"
        assert len(_dividir_linhas(b["palavras"])) <= 2, f"bloco {idx}: linhas"
        assert b["fim"] - b["inicio"] >= DUR_MIN - 0.06, f"bloco {idx}: duracao minima"
        assert b["fim"] - b["inicio"] <= DUR_MAX + 0.06, f"bloco {idx}: duracao maxima"
        if anterior_fim is not None:
            assert b["inicio"] >= anterior_fim - 1e-6, f"bloco {idx}: sobreposicao"
        anterior_fim = b["fim"]

    duracao_audio = float(timings["duracao_audio_seg"])
    assert blocos[-1]["fim"] < duracao_audio + 1, "ultimo timestamp fora do audio"


if __name__ == "__main__":
    timings = carregar_timings(TIMINGS_PATH)
    blocos = construir_blocos(timings, max_palavras=7)
    _validar(blocos, timings)
    escrever_srt(blocos, SRT_PATH)
    print(f"OK: {len(blocos)} blocos -> {SRT_PATH}")
    print(f"ultimo timestamp: {blocos[-1]['fim']:.3f}s / audio {timings['duracao_audio_seg']}s")
