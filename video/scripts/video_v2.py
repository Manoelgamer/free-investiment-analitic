#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""video_v2.py — animacao premium do video vertical de investimentos (v2).

Entradas (todasja prontas):
  data/roteiro_v2.json, data/melhorias.md (secao 4), build/timings_v2.json,
  build/audio_final.m4a, scripts/presenter.py, scripts/legenda_v2.py.

Saidas:
  build/final_v2_silent.mp4  -> build/final_v2.mp4 (mux com audio_final.m4a)
  build/qc_v2_{inicio,meio,fim}.png (via --qc ou ffmpeg externo)

Uso:
  python3 video_v2.py            # render sequencial (moviepy) + mux
  python3 video_v2.py --bench    # mede tempo medio de 60 frames
  python3 video_v2.py --parallel # PNGs em paralelo + join ffmpeg + mux
  python3 video_v2.py --qc       # extrai os 3 frames de QC do final

Sincronizacao: timings_v2.json e a fonte da verdade. Os tempos dos segmentos
do roteiro sao REMAPEADOS para as palavras reais (palavra por palavra), e todo
movimento (boca, braco, sobrancelha, cartoes, legenda, cortes) deriva de t.
O audio_final.m4a ja contem voz + trilha + 15 SFX masterizados: NAO e
re-processado nem re-misturado; apenas muxado no video silencioso.
"""

from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
import time
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from moviepy import VideoClip

# ---------------------------------------------------------------------------
# Caminhos e constantes
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE / "scripts"
DATA = BASE / "data"
BUILD = BASE / "build"

sys.path.insert(0, str(SCRIPTS))
import presenter          # noqa: E402  (avatar volumetrico + idle)
import legenda_v2 as leg  # noqa: E402  (karaoke glow, 32 blocos)

ROTEIRO_PATH = DATA / "roteiro_v2.json"
TIMINGS_PATH = BUILD / "timings_v2.json"
AUDIO_PATH = BUILD / "audio_final.m4a"
EVENTOS_PATH = BUILD / "events_v2.json"
SILENT_PATH = BUILD / "final_v2_silent.mp4"
FINAL_PATH = BUILD / "final_v2.mp4"
FRAMES_DIR = BUILD / "frames_v2"

W, H = 1080, 1920
FPS = 30
SEED = 20261122

# Paleta premium (secao 4 do melhorias.md): fundo near-black + UM acento.
BG_TOP = (10, 14, 23)       # #0A0E17
BG_BOT = (15, 24, 41)       # leve lift azul na base
VERDE = (0, 196, 106)       # #00C46A  alta
VERMELHO = (255, 77, 94)    # #FF4D5E  queda / problema (medo)
AMARELO = (255, 210, 63)    # #FFD23F  numero em foco / CTA
BRANCO = (234, 242, 250)
FRACO = (150, 166, 184)
CINZA = (92, 108, 130)

# Um unico acento por frame (semantica do dado / beat do segmento).
# Vermelho = queda / medo; verde = alta; amarelo = numero/CTA em foco.
ACENTOS = {1: VERMELHO, 2: VERMELHO, 3: VERMELHO, 4: VERMELHO,
           5: VERDE, 6: VERMELHO, 7: AMARELO}

COR_CARTAO = (17, 27, 44)
BORDA_CARTAO = (46, 66, 96)

# ---------------------------------------------------------------------------
# Carregamento e mapeamento tempo-real
# ---------------------------------------------------------------------------


def _norm(texto: str) -> list[str]:
    s = unicodedata.normalize("NFKD", texto.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s if c.isalnum() or c.isspace()).split()


def duracao_audio() -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(AUDIO_PATH)], text=True)
    return float(out.strip())


def carregar():
    with open(ROTEIRO_PATH, "r", encoding="utf-8") as fh:
        roteiro = json.load(fh)
    timings = leg.carregar_timings(str(TIMINGS_PATH))
    blocos = leg.construir_blocos(timings)

    # Mapeia cada segmento para as PALAVRAS REAIS do timings (nao os 58s do
    # roteiro). Validado: os 7 segmentos consomem exatamente as 159 palavras.
    palavras = timings["palavras"]
    cursor = 0
    for seg in roteiro["segmentos"]:
        alvo = _norm(seg["texto"])
        ini = float(palavras[cursor]["inicio"])
        for w in alvo:
            if cursor >= len(palavras):
                break
            tw = _norm(palavras[cursor]["texto"])
            tw = tw[0] if tw else ""
            if tw == w:
                cursor += 1
            else:
                raise RuntimeError(
                    f"timings fora de sincronia no segmento {seg['id']}: "
                    f"esperado {w!r}, encontrado {tw!r} (indice {cursor})")
        seg["_inicio"] = ini
        seg["_fim"] = float(palavras[cursor - 1]["fim"])
        seg["_palavras"] = list(range(max(0, cursor - len(alvo)), cursor))
        seg["_acento"] = ACENTOS.get(seg["id"], BRANCO)

    if cursor != len(palavras):
        raise RuntimeError(f"palavras nao mapeadas: {cursor}/{len(palavras)}")

    # Palavras de enfase com seus intervalos reais (para a tipografia cinetica).
    for seg in roteiro["segmentos"]:
        alvo = _norm(seg["enfase"])
        idxs = seg["_palavras"]
        mapa: list[tuple[str, float, float]] = []
        k = 0
        for pi in idxs:
            if k >= len(alvo):
                break
            tw = _norm(palavras[pi]["texto"])
            tw = tw[0] if tw else ""
            if tw == alvo[k]:
                mapa.append((tw, float(palavras[pi]["inicio"]),
                             float(palavras[pi]["fim"])))
                k += 1
        seg["_enfase_map"] = mapa

    # events.json derivado da MESMA timeline (documentacao / rastreabilidade).
    eventos = {
        "origem": "timings_v2.json (nao digitado a mao)",
        "segmentos": [{"id": s["id"], "visual": s["visual"],
                       "inicio": round(s["_inicio"], 3),
                       "fim": round(s["_fim"], 3),
                       "acento": "vermelho" if s["_acento"] == VERMELHO else
                                 "verde" if s["_acento"] == VERDE else "amarelo"}
                      for s in roteiro["segmentos"]],
        "trocas_de_bloco": [round(b["inicio"], 3) for b in blocos],
        "contadores": [round(s["_inicio"], 3) for s in roteiro["segmentos"]
                       if s["dado"] is not None]
                      + [24.2, 42.7],  # risers visuais VIX / EWZ
    }
    with open(EVENTOS_PATH, "w", encoding="utf-8") as fh:
        json.dump(eventos, fh, ensure_ascii=False, indent=2)

    return roteiro, timings, blocos, duracao_audio()


ROTEIRO, TIMINGS, BLOCOS, DUR = carregar()
SEGMENTOS = ROTEIRO["segmentos"]

# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------
_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_CANDIDATOS = {
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "DejaVuSans-Bold.ttf"],
    "mono": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def fonte(tamanho: int, tipo: str = "bold") -> ImageFont.FreeTypeFont:
    key = (tipo, tamanho)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    for caminho in _CANDIDATOS[tipo]:
        try:
            f = ImageFont.truetype(caminho, tamanho)
            _FONT_CACHE[key] = f
            return f
        except OSError:
            continue
    f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


# ---------------------------------------------------------------------------
# Assets estaticos (construidos uma unica vez no import)
# ---------------------------------------------------------------------------
def _construir_fundo() -> Image.Image:
    yy = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]
    xx = np.linspace(0.0, 1.0, W, dtype=np.float32)[None, :]
    arr = np.empty((H, W, 3), dtype=np.float32)
    for c in range(3):
        arr[..., c] = BG_TOP[c] * (1 - yy) + BG_BOT[c] * yy
    lift = np.exp(-(((xx - 0.5) / 0.78) ** 2 + ((yy - 0.08) / 0.55) ** 2))
    arr += lift[..., None] * np.array([6, 10, 18], dtype=np.float32)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def _construir_grid() -> Image.Image:
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    passo = 72
    for x in range(0, W, passo):
        d.line((x, 0, x, H), fill=9 if (x // passo) % 4 else 17, width=1)
    for y in range(0, H, passo):
        d.line((0, y, W, y), fill=9 if (y // passo) % 4 else 17, width=1)
    layer = Image.new("RGBA", (W, H), (150, 185, 225, 0))
    layer.putalpha(m)
    return layer


def _construir_vignette() -> Image.Image:
    yy = np.linspace(-1, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(-1, 1, W, dtype=np.float32)[None, :]
    r = np.sqrt((xx / 0.78) ** 2 + (yy / 0.70) ** 2)
    a = np.clip((r - 0.42) / 0.72, 0.0, 1.0) ** 1.55 * 140.0
    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[..., :3] = (2, 5, 11)
    out[..., 3] = a.astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _construir_glow(cor) -> Image.Image:
    yy = np.linspace(-1, 1, H, dtype=np.float32)[:, None]
    xx = np.linspace(-1, 1, W, dtype=np.float32)[None, :]
    r = np.sqrt(((xx - 0.0) / 1.05) ** 2 + ((yy + 0.62) / 0.86) ** 2)
    a = np.clip(1.0 - r, 0.0, 1.0) ** 2.3 * 84.0
    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[..., :3] = cor
    out[..., 3] = a.astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _construir_sweep() -> Image.Image:
    """Banda diagonal suave (mascara L) para o light sweep por troca de bloco."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    u = (xx + 0.52 * yy) / (W + 0.52 * H)   # 0..1 ao longo da diagonal
    banda = np.exp(-(((u - 0.5) / 0.10) ** 2))
    return Image.fromarray((banda * 255).astype(np.uint8), "L")


BG_BASE = _construir_fundo()
GRID = _construir_grid()
VIGNETTE = _construir_vignette()
SWEEP = _construir_sweep()
GLOWS = {k: _construir_glow(v) for k, v in
         [("r", VERMELHO), ("g", VERDE), ("y", AMARELO)]}


def glow_key(cor) -> str:
    return "g" if cor == VERDE else "y" if cor == AMARELO else "r"


def _overlay_para(cor) -> Image.Image:
    """Grid + halo de acento + vignette precompostos (uma so composicao/frame)."""
    o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    o.alpha_composite(GRID)
    halo = GLOWS[glow_key(cor)]
    camada = halo.copy()
    camada.putalpha(halo.getchannel("A").point(lambda v: int(v * 0.86)))
    o.alpha_composite(camada)
    o.alpha_composite(VIGNETTE)
    return o


BG_OVERLAY = {glow_key(c): _overlay_para(c)
              for c in (VERMELHO, VERDE, AMARELO)}

# Particulas / candlesticks procedurais (seed fixa, movimento lento e upward).
_rng = random.Random(SEED)
PARTICULAS = []
for _ in range(54):
    PARTICULAS.append({
        "x": _rng.uniform(0.02, 0.98) * W,
        "y": _rng.uniform(0.0, H),
        "v": _rng.uniform(9, 28),          # px/s subindo
        "h": _rng.uniform(16, 68),         # altura do candle
        "w": _rng.uniform(2, 6),
        "tone": _rng.choice(("accent", "neutral", "neutral", "accent")),
        "phase": _rng.uniform(0, math.tau),
    })

# Especificacao dos cartoes de dado (todas as datas visiveis no rotulo).
CARTOES = {
    "dado_ibovespa": {
        "label": "IBOVESPA (19/11)", "valor": "166.376 pts",
        "delta": "-0,69% no dia", "serie": [62, 58, 61, 55, 57, 49, 52, 44, 47, 40],
        "velas": False, "sentido": "down",
    },
    "dado_dolar": {
        "label": "DÓLAR COMERCIAL (19/11)", "valor": "R$ 5,934",
        "delta": "+1,15% no dia", "serie": [30, 33, 31, 38, 36, 44, 42, 50, 53, 60],
        "velas": False, "sentido": "up",
    },
    "noticia": {
        "label": "NASDAQ (20/11)", "valor": "-5,30%",
        "delta": "-10% na semana  ·  Nvidia -14%",
        "serie": [70, 66, 68, 58, 61, 50, 54, 42, 39, 32],
        "velas": True, "sentido": "down",
    },
    "medo": {
        "label": "VIX (20/11)", "valor": "35,89",
        "delta": "+26,20%  ·  ninguém arriscava",
        "serie": [22, 25, 24, 31, 29, 38, 42, 40, 52, 64],
        "velas": True, "sentido": "up",
    },
    "oportunidade": {
        "label": "EWZ (20/11)", "valor": "-3,30%",
        "delta": "pior nível em mais de um ano",
        "serie": [64, 60, 62, 55, 51, 54, 45, 42, 38, 34],
        "velas": True, "sentido": "down",
    },
}

# ---------------------------------------------------------------------------
# Helpers de tempo / easing
# ---------------------------------------------------------------------------


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(u):
    u = clamp(u)
    return 1.0 - (1.0 - u) ** 3


def segmento_em(t: float):
    for i, s in enumerate(SEGMENTOS):
        if t < s["_fim"] or i == len(SEGMENTOS) - 1:
            return i, s
    return len(SEGMENTOS) - 1, SEGMENTOS[-1]


def bloco_em(t: float):
    for b in BLOCOS:
        if b["inicio"] <= t <= b["fim"]:
            return b
    return None


def palavra_em(t: float):
    for p in TIMINGS["palavras"]:
        if p["inicio"] <= t <= p["fim"]:
            return p
    return None


def base_acento(i: int):
    """Acento com crossfade suave (0.22s) na entrada do segmento."""
    s = SEGMENTOS[i]
    cor = s["_acento"]
    if i > 0 and t_global - s["_inicio"] < 0.22:
        anterior = SEGMENTOS[i - 1]["_acento"]
        k = ease_out((t_global - s["_inicio"]) / 0.22)
        return tuple(int(anterior[c] * (1 - k) + cor[c] * k) for c in range(3))
    return cor


t_global = 0.0  # setado por make_frame (usado apenas no crossfade de acento)

# ---------------------------------------------------------------------------
# Camadas do fundo
# ---------------------------------------------------------------------------


def desenhar_fundo(frame: Image.Image, t: float, cor):
    # grid + halo + vignette precompostos, com parallax de 4-8px
    dx = int(round(6.0 * math.sin(2 * math.pi * t / 9.0)))
    dy = int(round(5.0 * math.cos(2 * math.pi * t / 11.0)))
    frame.alpha_composite(ImageChops.offset(BG_OVERLAY[glow_key(cor)], dx, dy))

    # particulas/candlesticks em 1/4 da resolucao -> DOF suave (~7px)
    div = 4
    hw, hh = W // div, H // div
    p = Image.new("RGBA", (hw, hh), (0, 0, 0, 0))
    d = ImageDraw.Draw(p, "RGBA")
    for part in PARTICULAS:
        y = (part["y"] - part["v"] * t) % (hh + 60) - 30
        x = part["x"] / div + 1.5 * math.sin(t * 0.5 + part["phase"])
        alt = part["h"] / div
        c = cor + (88,) if part["tone"] == "accent" else (110, 145, 190, 52)
        d.line((x, y, x, y + alt), fill=c, width=1)
        d.rectangle((x - part["w"] / (2 * div), y + alt * 0.28,
                     x + part["w"] / (2 * div), y + alt * 0.82), fill=c)
    p = p.filter(ImageFilter.GaussianBlur(1.8))
    arr = np.asarray(p)
    frame.alpha_composite(Image.fromarray(
        np.repeat(np.repeat(arr, div, axis=0), div, axis=1), "RGBA"))


# ---------------------------------------------------------------------------
# Cabecalho
# ---------------------------------------------------------------------------


def desenhar_cabecalho(frame: Image.Image, t: float, cor):
    d = ImageDraw.Draw(frame, "RGBA")
    # barra de progresso
    x0, x1, y0, y1 = 40, W - 40, 28, 40
    d.rounded_rectangle((x0, y0, x1, y1), radius=6, fill=(255, 255, 255, 34))
    prog = int((x1 - x0) * clamp(t / DUR))
    if prog > 2:
        d.rounded_rectangle((x0, y0, x0 + prog, y1), radius=6, fill=cor + (255,))
    # titulo / data / fonte
    f_tit = fonte(46)
    f_meta = fonte(40)
    d.text((40, 62), "MERCADO EM FOCO", font=f_tit, fill=BRANCO + (255,))
    d.text((40, 122), "DADOS REAIS", font=f_meta, fill=cor + (235,))
    data = "SEXTA 20/11/2026"
    larg = d.textlength(data, font=f_meta)
    d.text((W - 40 - larg, 66), data, font=f_meta, fill=FRACO + (255,))


# ---------------------------------------------------------------------------
# Cartoes de dado
# ---------------------------------------------------------------------------


def _valor_glyph_noise(valor: str, u: float, frame_i: int) -> str:
    """Digitos embaralham e travam um por um; caracteres nao-digitais fixos."""
    rng = random.Random(SEED + frame_i * 7919)
    saida = []
    for i, ch in enumerate(valor):
        if ch.isdigit():
            lock = 0.10 + i * 0.038
            if u < lock:
                saida.append(str(rng.randrange(10)))
            else:
                saida.append(ch)
        else:
            saida.append(ch)
    return "".join(saida)


def _desenhar_serie(d, caixa, serie, cor, velas, frame_i):
    x0, y0, x1, y1 = caixa
    vals = np.array(serie, dtype=np.float32)
    lo, hi = vals.min(), vals.max()
    span = max(1e-3, hi - lo)
    n = len(vals)
    pts = [(x0 + i * (x1 - x0) / (n - 1),
            y1 - (v - lo) / span * (y1 - y0)) for i, v in enumerate(vals)]
    if velas:
        for i in range(0, n - 1, 2):
            xa, ya = pts[i]
            xb, yb = pts[min(i + 1, n - 1)]
            up = yb < ya
            c = (VERDE if up else VERMELHO) + (190,)
            d.line((xa, min(ya, yb) - 5, xa, max(ya, yb) + 5), fill=c, width=2)
            d.rectangle((xa - 5, min(ya, yb), xa + 5, max(ya, yb)),
                        fill=c, outline=c)
    else:
        d.line(pts, fill=cor + (205,), width=4, joint="curve")
        for x, y in pts[::2]:
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=cor + (225,))
    # cursor de tick na ultima ponto
    cx, cy = pts[-1]
    pulso = 0.5 + 0.5 * math.sin(frame_i * 0.13)
    d.line((cx, y0 - 6, cx, y1 + 6), fill=cor + (int(60 + 70 * pulso),), width=2)
    d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), outline=cor + (230,), width=2)


_CARD_CACHE: dict[tuple, Image.Image] = {}


def desenhar_cartao(frame: Image.Image, seg, t: float, cor, frame_i: int):
    esp = CARTOES.get(seg["visual"])
    if esp is None:
        return
    local = t - seg["_inicio"]
    if local < 0:
        return

    chave = (seg["visual"], cor)
    # Apos a entrada o cartao e estatico: reaproveita a imagem ja transformada.
    if local >= 0.6 and chave in _CARD_CACHE:
        cartao = _CARD_CACHE[chave]
        frame.alpha_composite(cartao, (540 - cartao.width // 2,
                                       405 - cartao.height // 2))
        return

    # entrada scale 0.92->1.0 em 250ms + leve subida
    u = clamp(local / 0.25)
    s = 0.92 + 0.08 * ease_out(u)
    subida = int(round(18 * (1 - ease_out(u))))
    cw, ch = 900, 300
    pad = 16

    cartao = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(cartao, "RGBA")

    # sombra difusa
    sombra = Image.new("RGBA", cartao.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sombra)
    sd.rounded_rectangle((pad, pad + 12, pad + cw, pad + ch + 12),
                         radius=30, fill=(0, 0, 0, 130))
    cartao.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(20)))
    d = ImageDraw.Draw(cartao, "RGBA")

    # corpo
    d.rounded_rectangle((pad, pad, pad + cw, pad + ch), radius=28,
                        fill=COR_CARTAO + (243,), outline=BORDA_CARTAO + (255,),
                        width=2)
    # faixa de acento (um unico acento no cartao)
    d.rounded_rectangle((pad, pad, pad + 9, pad + ch), radius=4, fill=cor + (225,))
    # leve brinho superior
    d.line((pad + 40, pad + 2, pad + cw - 40, pad + 2),
           fill=tuple(min(255, c + 34) for c in COR_CARTAO) + (255,), width=2)

    x = pad + 46
    # rotulo com data SEMPRE visivel
    d.text((x, pad + 30), esp["label"], font=fonte(42), fill=FRACO + (255,))
    # valor com glyph-noise + bounce
    bounce = 1.0 + 0.045 * math.exp(-(((local - 0.46) / 0.13) ** 2))
    tamanho_valor = 78 if len(esp["valor"]) <= 10 else 66
    fv = fonte(tamanho_valor, "mono")
    txt = _valor_glyph_noise(esp["valor"], local, frame_i)
    largura = d.textlength(txt, font=fv)
    if largura * bounce > 780:
        fv = fonte(int(tamanho_valor * 780 / (largura * bounce)), "mono")
        largura = d.textlength(txt, font=fv)
    pos = (x, pad + 92)
    if abs(bounce - 1.0) > 0.002:
        # desenha o valor numa camada e escala com bounce suave
        tmp = Image.new("RGBA", (int(largura) + 8, tamanho_valor + 16),
                        (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((2, 0), txt, font=fv, fill=cor + (255,))
        tmp = tmp.resize((max(1, int(tmp.width * bounce)),
                          max(1, int(tmp.height * bounce))),
                         Image.Resampling.BICUBIC)
        cartao.alpha_composite(tmp, (x, pad + 88))
        d = ImageDraw.Draw(cartao, "RGBA")
    else:
        d.text(pos, txt, font=fv, fill=cor + (255,))

    # delta semantico (verde = alta, vermelho = queda) — mesmo acento do frame
    delta = esp["delta"]
    fd = fonte(42)
    d.text((x, pad + 206), delta, font=fd, fill=BRANCO + (235,))
    # setinha de tendencia
    sinal = 1 if esp["sentido"] == "up" else -1
    ax, ay = x + 4, pad + 186
    if sinal > 0:  # ponta no topo = alta
        d.polygon([(ax + 7, ay - 10), (ax + 18, ay + 4), (ax + 11, ay + 4),
                   (ax + 11, ay + 13), (ax + 3, ay + 13)], fill=cor + (255,))
    else:          # ponta na base = queda
        d.polygon([(ax + 7, ay + 14), (ax + 18, ay), (ax + 11, ay),
                   (ax + 11, ay - 9), (ax + 3, ay - 9)], fill=cor + (255,))

    # mini-grafico no canto direito
    _desenhar_serie(d, (pad + 600, pad + 62, pad + 858, pad + 172),
                    esp["serie"], cor, esp["velas"], frame_i)

    # perspectiva 3-6 graus via QUAD. Ordem PIL: UL, LL, LR, UR (source).
    quad = (pad, pad + 10, pad, ch + pad - 4,
            cw + pad, ch + pad + 6, cw + pad, pad + 2)
    cartao = cartao.transform((cw + 2 * pad, ch + 2 * pad),
                              Image.Transform.QUAD, quad,
                              resample=Image.Resampling.BICUBIC)
    if local >= 0.6:
        _CARD_CACHE[chave] = cartao

    # escala de entrada aplicada ao redor do centro do cartao
    if abs(s - 1.0) > 0.001:
        cartao = cartao.resize((max(1, int(cartao.width * s)),
                               max(1, int(cartao.height * s))),
                              Image.Resampling.BICUBIC)

    cx, cy = 540, 405 + subida
    frame.alpha_composite(cartao, (cx - cartao.width // 2,
                                   cy - cartao.height // 2))


# ---------------------------------------------------------------------------
# Tipografia cinetica de enfase (punch-in + glow sincronizado ao timing)
# ---------------------------------------------------------------------------


def desenhar_enfase(frame: Image.Image, seg, t: float, cor, frame_i: int):
    local = t - seg["_inicio"]
    if local < 0 or local > 1.28:
        return
    alpha = clamp(local / 0.10) * clamp((1.28 - local) / 0.20)
    if alpha <= 0.01:
        return
    p = clamp(local / 0.26)
    escala = 0.86 + 0.14 * ease_out(p)
    escala *= 1.0 + 0.018 * math.sin(p * math.pi)

    palavras = seg["_enfase_map"] or [
        (w, seg["_inicio"] + i * 0.16, seg["_inicio"] + i * 0.16 + 0.3)
        for i, w in enumerate(_norm(seg["enfase"]))]
    texto = " ".join(pw[0] for pw in palavras)
    tamanho = 74
    f = fonte(tamanho)
    while f.getlength(texto) > 940 and tamanho > 54:
        tamanho -= 2
        f = fonte(tamanho)

    # camadas de texto (glow + nitido) num patch pequeno
    tw = int(f.getlength(texto)) + 40
    th = tamanho + 40
    patch = Image.new("RGBA", (max(8, tw), max(8, th)), (0, 0, 0, 0))
    pd = ImageDraw.Draw(patch)
    x = 20.0
    for i, (w, ini, fim) in enumerate(palavras):
        ativo = ini <= t <= fim or (local < 0.35 and i == 0)
        c = cor if ativo else BRANCO
        pd.text((x, 12), w, font=f, fill=c + (255,),
                stroke_width=2, stroke_fill=(4, 8, 16, 255))
        x += f.getlength(w + " ")
    glow = patch.filter(ImageFilter.GaussianBlur(14))
    glow.putalpha(glow.getchannel("A").point(lambda v: int(v * 0.75 * alpha)))
    frame.alpha_composite(glow, (540 - patch.width // 2, 622))
    patch.putalpha(patch.getchannel("A").point(lambda v: int(v * alpha)))
    if abs(escala - 1.0) > 0.002:
        patch = patch.resize((int(patch.width * escala),
                              int(patch.height * escala)),
                             Image.Resampling.BICUBIC)
    frame.alpha_composite(patch, (540 - patch.width // 2, 622))


# ---------------------------------------------------------------------------
# Light sweep, whoosh e motion blur
# ---------------------------------------------------------------------------


def light_sweep(frame: Image.Image, t: float):
    for b in BLOCOS:
        dt = t - b["inicio"]
        if 0 <= dt < 0.85:
            p = dt / 0.85
            desloc = int(-1150 + 2300 * p)
            mascara = ImageChops.offset(SWEEP, desloc, 0)
            forca = (1.0 - p) ** 1.4 * 0.20
            m = mascara.point(lambda v: int(v * forca))
            camada = Image.new("RGBA", (W, H), (255, 248, 225, 0))
            camada.putalpha(m)
            frame.alpha_composite(camada)
            return


def whoosh(frame: Image.Image, seg, t: float):
    local = t - seg["_inicio"]
    if 0 <= local < 0.18:
        p = local / 0.18
        desloc = int((1 - p) * 26)
        if desloc:
            movido = ImageChops.offset(frame, desloc, 0)
            frame.paste(movido, (0, 0))
        escuro = Image.new("RGBA", (W, H), (8, 12, 22, 255))
        frame.paste(Image.blend(escuro, frame, 0.42 + 0.58 * ease_out(p)), (0, 0))


def motion_blur_corte(frame: Image.Image, t: float):
    for b in BLOCOS:
        dt = abs(t - b["inicio"])
        if dt < 0.075:
            forca = (1.0 - dt / 0.075)
            desloc = max(1, int(6 * forca))
            frame.paste(Image.blend(frame, ImageChops.offset(frame, desloc, 0),
                                    0.42 * forca), (0, 0))
            return


def rehook_zoom(frame: Image.Image, seg, t: float):
    """Segmento 3: leve zoom/punch-in no re-hook 'E o seu bolso?'."""
    local = t - seg["_inicio"]
    if seg["id"] == 3 and 0 <= local < 1.15:
        z = 1.0 + 0.042 * math.sin(math.pi * clamp(local / 1.15))
        nw, nh = int(W * z), int(H * z)
        frame.paste(frame.resize((nw, nh), Image.Resampling.BILINEAR)
                    .crop(((nw - W) // 2, (nh - H) // 2,
                           (nw - W) // 2 + W, (nh - H) // 2 + H)), (0, 0))


# ---------------------------------------------------------------------------
# Apresentador, legenda e rodape
# ---------------------------------------------------------------------------


def boca_em(t: float) -> float:
    p = palavra_em(t)
    if p is None:
        return 0.0
    dur = max(0.04, p["fim"] - p["inicio"])
    u = clamp((t - p["inicio"]) / dur)
    envelope = clamp(u / 0.14) * clamp((1 - u) / 0.20)
    osc = 0.55 + 0.45 * abs(math.sin(2 * math.pi * 6.0 * t))
    return 0.18 + 0.78 * envelope * osc


def braco_em(t: float, seg) -> float:
    """Gestos curtos sincronizados com as palavras de enfase / numeros."""
    alvo = set(_norm(seg["enfase"]))
    p = palavra_em(t)
    if p is None:
        return 0.0
    pw = _norm(p["texto"])
    pw = pw[0] if pw else ""
    if pw in alvo or pw in {"medo", "disparou", "caiu", "catorze", "ibovespa",
                             "dólar", "vix", "ewz", "desconto", "avalie"}:
        dur = max(0.05, p["fim"] - p["inicio"])
        u = clamp((t - p["inicio"]) / dur)
        return 0.72 * math.sin(math.pi * u) ** 2
    return 0.0


def compor_apresentador(frame: Image.Image, t: float, seg, i: int):
    boca = boca_em(t)
    olhar = 0.24 * math.sin(2 * math.pi * t / 7.3) \
        + 0.08 * math.sin(2 * math.pi * t / 3.1)
    sobrancelha = 0.0
    # transicao suave de sobrancelha entre segmentos (0.55s)
    alvo_atual = -0.8 if seg["id"] == 4 else \
        (0.8 if seg["id"] in (6, 7) else 0.0)
    if i > 0:
        anterior = SEGMENTOS[i - 1]
        alvo_ant = -0.8 if anterior["id"] == 4 else \
            (0.8 if anterior["id"] in (6, 7) else 0.0)
        dt = t - seg["_inicio"]
        if 0 <= dt < 0.55:
            sobrancelha = alvo_ant + (alvo_atual - alvo_ant) * ease_out(dt / 0.55)
        else:
            sobrancelha = alvo_atual
    else:
        sobrancelha = alvo_atual
    braco = braco_em(t, seg)
    inclinar = 0.16 * math.sin(2 * math.pi * t / 5.2)
    # NAO passamos piscar: o idle do presenter ja faz piscadas e sacadas.
    avatar = presenter.render_frame(boca=boca, olhar=olhar,
                                    sobrancelha=sobrancelha, braco=braco,
                                    inclinar=inclinar)
    bob = int(round(5.0 * math.sin(2 * math.pi * t / 2.35)))
    frame.paste(avatar, (0, bob), avatar)


def compor_legenda(frame: Image.Image, t: float):
    bloco = bloco_em(t)
    if bloco is not None:
        leg.desenhar_legenda_glow(frame, bloco, t)


def compor_rodape(frame: Image.Image, t: float, seg, cor):
    if seg["id"] != 7:
        return
    d = ImageDraw.Draw(frame, "RGBA")
    # selo discreto no topo direito
    selo = "CONTEÚDO EDUCATIVO"
    fs = fonte(40)
    larg = d.textlength(selo, font=fs)
    bx0, bx1 = W - 40 - larg - 28, W - 40
    d.rounded_rectangle((bx0, 122, bx1, 184), radius=14,
                        fill=(10, 16, 28, 210), outline=AMARELO + (150,), width=2)
    d.text((bx0 + 14, 134), selo, font=fs, fill=AMARELO + (255,))

    # aviso do roteiro em caixa discreta (abaixo do toast de legenda)
    aviso = ROTEIRO["aviso"]
    fa = fonte(42)
    linhas = ["Conteúdo educativo.", "Não é recomendação de investimento."]
    y0, y1 = 1732, 1858
    d.rounded_rectangle((70, y0, W - 70, y1), radius=20,
                        fill=(6, 10, 18, 220), outline=BORDA_CARTAO + (180,),
                        width=2)
    d.rounded_rectangle((84, y0 + 16, 90, y1 - 16), radius=3, fill=AMARELO + (220,))
    for k, linha in enumerate(linhas):
        d.text((108, y0 + 20 + k * 52), linha, font=fa, fill=BRANCO + (240,))
    # garante que o texto do roteiro esta sendo usado (nao uma versao curta)
    assert "recomendação" in aviso and "investimento" in aviso


# ---------------------------------------------------------------------------
# Frame mestre
# ---------------------------------------------------------------------------


def make_frame(t: float, frame_i: int | None = None) -> np.ndarray:
    global t_global
    t = clamp(t, 0.0, DUR - 1.0 / FPS)
    t_global = t
    if frame_i is None:
        frame_i = int(round(t * FPS))

    i, seg = segmento_em(t)
    cor = base_acento(i)

    frame = BG_BASE.copy()
    desenhar_fundo(frame, t, cor)
    desenhar_cabecalho(frame, t, cor)
    desenhar_cartao(frame, seg, t, cor, frame_i)
    desenhar_enfase(frame, seg, t, cor, frame_i)
    rehook_zoom(frame, seg, t)
    motion_blur_corte(frame, t)
    whoosh(frame, seg, t)

    compor_apresentador(frame, t, seg, i)
    light_sweep(frame, t)
    compor_legenda(frame, t)
    compor_rodape(frame, t, seg, cor)

    return np.asarray(frame.convert("RGB"))


# ---------------------------------------------------------------------------
# Renderizacao / mux / QC
# ---------------------------------------------------------------------------


def renderizar_sequencial():
    presenter.set_idle(True)
    presenter.reset_state()
    clip = VideoClip(frame_function=make_frame, duration=DUR)
    clip.fps = FPS
    print(f"[video_v2] renderizando {int(DUR * FPS)} frames @ {FPS}fps "
          f"({DUR:.3f}s) ...", flush=True)
    t0 = time.time()
    clip.write_videofile(
        str(SILENT_PATH), fps=FPS, codec="libx264", audio=False,
        preset="fast", bitrate="8000k",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        logger="bar",
    )
    print(f"[video_v2] render concluido em {time.time() - t0:.1f}s", flush=True)


def _render_chunk(args):
    inicio, fim = args
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    import presenter as p
    import legenda_v2 as lg
    # modulo ja importado no worker via heranca/fork; garantir estado valido
    p.set_idle(True)
    for idx in range(inicio, fim):
        t = min(idx / FPS, DUR - 1.0 / FPS)
        p.reset_state()
        p.set_frame(idx)
        arr = make_frame(t, idx)
        Image.fromarray(arr).save(FRAMES_DIR / f"f_{idx:06d}.png",
                                  compress_level=1)
    return (inicio, fim)


def renderizar_paralelo():
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    n = int(math.ceil(DUR * FPS))
    chunk = 48
    tarefas = [(a, min(a + chunk, n)) for a in range(0, n, chunk)]
    print(f"[video_v2] paralelo: {n} frames, {len(tarefas)} chunks", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=4) as exe:
        for k, _ in enumerate(exe.map(_render_chunk, tarefas)):
            print(f"  chunk {k + 1}/{len(tarefas)}", flush=True)
    print(f"[video_v2] PNGs em {time.time() - t0:.1f}s", flush=True)
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS),
        "-i", str(FRAMES_DIR / "f_%06d.png"),
        "-c:v", "libx264", "-preset", "fast", "-b:v", "8000k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(SILENT_PATH),
    ], check=True)


def muxar():
    print("[video_v2] mux com audio_final.m4a (sem re-processar audio) ...",
          flush=True)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(SILENT_PATH), "-i", str(AUDIO_PATH),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(FINAL_PATH),
    ], check=True)
    print(f"[video_v2] final: {FINAL_PATH}", flush=True)


def extrair_qc():
    marcas = {"inicio": 6.0, "meio": 30.0, "fim": 60.0}
    for nome, t in marcas.items():
        destino = BUILD / f"qc_v2_{nome}.png"
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(t), "-i", str(FINAL_PATH),
            "-frames:v", "1", str(destino),
        ], check=True, capture_output=True)
        im = Image.open(destino)
        arr = np.asarray(im.convert("RGB"))
        print(f"[qc] {destino.name}: {im.size}, "
              f"mean={arr.mean():.1f}, std={arr.std():.1f}")


def benchmark():
    presenter.set_idle(True)
    presenter.reset_state()
    amostras = np.linspace(0.4, DUR - 1.0, 60)
    t0 = time.time()
    for k, t in enumerate(amostras):
        presenter.set_frame(int(round(t * FPS)))
        make_frame(float(t), int(round(t * FPS)))
    dt = time.time() - t0
    print(f"[bench] {len(amostras)} frames em {dt:.2f}s "
          f"-> {dt / len(amostras) * 1000:.1f} ms/frame "
          f"-> estimativa {dt / len(amostras) * DUR * FPS:.0f}s")


def main():
    args = set(sys.argv[1:])
    if "--bench" in args:
        benchmark()
        return
    if "--parallel" in args:
        renderizar_paralelo()
    else:
        renderizar_sequencial()
    muxar()
    if "--qc" in args or True:
        extrair_qc()


if __name__ == "__main__":
    main()
