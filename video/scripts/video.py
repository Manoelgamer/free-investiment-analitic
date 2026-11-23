#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Animacao final do video vertical de investimentos (1080x1920 / 30 fps).

Sincronizacao: fontes da verdade = build/timings.json (tempos REAIS do audio
de 62,955 s). Os tempos planejados do roteiro.json (58 s) NAO sao usados para
animacao — apenas seus metadados (visual, dado, enfase, aviso).

Uso:
    python3 video/scripts/video.py
    python3 video/scripts/video.py --test-frame 5.0   # PNG de depuracao
"""

from __future__ import annotations

import bisect
import math
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import legenda  # noqa: E402
import presenter  # noqa: E402

W, H = 1080, 1920
FPS = 30

TIMINGS_PATH = BASE / "build" / "timings.json"
ROTEIRO_PATH = BASE / "data" / "roteiro.json"
VOZ_PATH = BASE / "build" / "voz.mp3"
OUT_PATH = BASE / "build" / "final.mp4"
TEST_PATH = BASE / "build" / "test_frame.png"

# ---------------------------------------------------------------------------
# Cores / fonte
# ---------------------------------------------------------------------------
BRANCO = (255, 255, 255, 255)
BRANCO_SUAVE = (222, 234, 250, 255)
AMARELO = (255, 216, 77, 255)
CIANO = (90, 214, 255, 255)
VERDE = (43, 212, 125, 255)
VERMELHO = (255, 92, 108, 255)
PRETO = (6, 12, 26, 255)

# Acents por segmento (id 1..7); re-hook amarelo no id 5, verde/ciano no 6/7.
ACENTOS = {
    1: (255, 205, 66),    # gancho — amarelo
    2: (255, 92, 108),    # queda — vermelho
    3: (255, 92, 108),    # ibovespa — vermelho
    4: (255, 74, 96),     # medo — vermelho intenso
    5: (255, 200, 60),    # re-hook — amarelo
    6: (43, 212, 125),    # oportunidade — verde
    7: (90, 214, 255),    # cta — ciano
}

DADOS_CARTAO = {
    1: dict(label="VIX (20/11)", ini=19.30, fim=35.89, fmt="num2",
            delta="+26,20% no dia", dir="up", data="20/11", cor=AMARELO),
    2: dict(label="NASDAQ (20/11)", ini=0.0, fim=-5.3, fmt="pct1",
            delta="apagou 2026", dir="down", data="20/11", cor=VERMELHO),
    3: dict(label="IBOVESPA (19/11)", ini=160000, fim=166376, fmt="pts",
            delta="-0,69% no dia", dir="down", data="19/11", cor=VERMELHO),
    4: dict(label="VIX (20/11)", ini=19.30, fim=35.89, fmt="num2",
            delta="+26,20% · máx 40", dir="up", data="20/11", cor=VERMELHO),
    5: dict(label="DÓLAR (19/11)", ini=5.700, fim=5.934, fmt="brl",
            delta="+1,15% · 6ª alta", dir="up", data="19/11", cor=AMARELO),
    6: dict(label="EWZ (20/11)", ini=30.00, fim=28.54, fmt="usd",
            delta="-3,3% · mín 14m", dir="down", data="20/11", cor=VERDE),
    7: dict(label="B3 · PRÓXIMO PREGÃO", ini=None, fim=None, fmt="static",
            valor="SEGUNDA 23/11", delta="reabre após o feriado",
            dir="flat", data="20/11", cor=CIANO),
}

PALAVRAS_GESTO = {
    "medo", "explodiu", "VIX", "subiu", "cento", "caiu", "Nvidia",
    "Ibovespa", "dólar", "EWZ", "mercado", "avalie", "atenção",
    "educativo", "descontos", "reabre", "segunda", "Nasdaq", "quarenta",
}

_FONTES: dict[int, ImageFont.FreeTypeFont] = {}


def fonte(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONTES:
        for cand in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ):
            try:
                _FONTES[size] = ImageFont.truetype(cand, size)
                break
            except OSError:
                continue
        else:
            _FONTES[size] = ImageFont.load_default()
    return _FONTES[size]


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def smooth(p: float) -> float:
    p = clamp(p)
    return p * p * (3.0 - 2.0 * p)


def ease_out(p: float) -> float:
    p = clamp(p)
    return 1.0 - (1.0 - p) ** 3


def rgb(a3):
    return tuple(int(v) for v in a3)


def with_alpha(c3, a):
    return (int(c3[0]), int(c3[1]), int(c3[2]), int(a))


def texto_central(d, x, y, txt, f, cor, stroke=0):
    largura = d.textlength(txt, font=f)
    d.text((x - largura / 2, y), txt, font=f, fill=cor,
           stroke_width=stroke, stroke_fill=(0, 0, 0, 190))


# ---------------------------------------------------------------------------
# Estado carregado uma vez
# ---------------------------------------------------------------------------
TIMINGS = None
ROTEIRO = None
BLOCOS = None
SEG = []                 # segmentos reais (timings.json)
SEG_STARTS = []
ROTEIRO_POR_ID = {}
DUR_AUDIO = 0.0
DUR_TOTAL = 0.0
WHOOSH = 0.18
GRADS = []               # 7 gradientes RGBA precomputados (1 por segmento)
GRID_LINHAS = []
PARTICULAS = []
VELAS = []
SPARKS = {}


def carregar():
    global TIMINGS, ROTEIRO, BLOCOS, SEG, SEG_STARTS, ROTEIRO_POR_ID
    global DUR_AUDIO, DUR_TOTAL, GRADS, GRID_LINHAS, PARTICULAS, VELAS, SPARKS

    with open(TIMINGS_PATH, "r", encoding="utf-8") as fh:
        TIMINGS = __import__("json").load(fh)
    with open(ROTEIRO_PATH, "r", encoding="utf-8") as fh:
        ROTEIRO = __import__("json").load(fh)

    BLOCOS = legenda.construir_blocos(TIMINGS, 7)
    DUR_AUDIO = float(TIMINGS["duracao_audio_seg"])
    DUR_TOTAL = DUR_AUDIO + 1.20
    SEG = TIMINGS["segmentos"]
    SEG_STARTS = [float(s["inicio"]) for s in SEG]
    ROTEIRO_POR_ID = {int(s["id"]): s for s in ROTEIRO["segmentos"]}

    # Gradientes: #0A1128 -> #101E3A, com leve tint do acento de cada bloco.
    top = np.array([10, 17, 40], dtype=np.float32)
    bot = np.array([16, 30, 58], dtype=np.float32)
    ramp = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None, None]
    base = top[None, None, :] * (1 - ramp) + bot[None, None, :] * ramp
    base = np.repeat(base, W, axis=1)
    for sid in range(1, 8):
        a = np.array(ACENTOS[sid], dtype=np.float32)
        tinted = base + (a[None, None, :] - 32.0) * 0.055
        arr = np.empty((H, W, 4), dtype=np.uint8)
        arr[..., :3] = np.clip(tinted, 0, 255).astype(np.uint8)
        arr[..., 3] = 255
        GRADS.append(arr)

    GRID_LINHAS = list(range(0, W, 90)) + list(range(0, H, 90))

    rnd = random.Random(20261120)
    for i in range(78):
        PARTICULAS.append((
            rnd.uniform(8, W - 8), rnd.uniform(0, H),
            rnd.uniform(1.2, 3.4), rnd.uniform(7, 26),
            rnd.random() * math.tau, rnd.choice((0, 1, 2)),
            rnd.uniform(28, 86),
        ))

    for col in (58, 1022):
        for i in range(11):
            VELAS.append((col, 330 + i * 88, rnd.uniform(0, math.tau),
                          rnd.uniform(0.5, 1.3)))

    for sid in DADOS_CARTAO:
        r = random.Random(1000 + sid)
        d = DADOS_CARTAO[sid]["dir"]
        vals = []
        v = 50.0
        for i in range(30):
            drift = (2.4 if d == "up" else -2.4 if d == "down" else 0.0)
            v += drift + r.uniform(-9, 9)
            vals.append(v)
        SPARKS[sid] = vals


def idx_em(t: float) -> int:
    return max(0, bisect.bisect_right(SEG_STARTS, t) - 1)


def bloco_em(t: float):
    """Ultimo bloco cujo inicio ja passou; None antes da primeira palavra."""
    starts = getattr(bloco_em, "_starts", None)
    if starts is None:
        starts = [b["inicio"] for b in BLOCOS]
        bloco_em._starts = starts
    i = bisect.bisect_right(starts, t) - 1
    if i < 0:
        return None
    return BLOCOS[i]


def fundo_array(t: float, idx: int, local: float) -> np.ndarray:
    base = GRADS[idx]
    if idx > 0 and local < 0.55:
        w = smooth(local / 0.55)
        if w < 0.999:
            return (GRADS[idx - 1] * (1.0 - w) + base * w).astype(np.uint8)
    return base.copy()


# ---------------------------------------------------------------------------
# Camadas
# ---------------------------------------------------------------------------
def desenhar_fundo(d, t, idx, local, acento):
    # Grid sutil
    grade = (118, 156, 214, 17)
    for x in GRID_LINHAS[:12]:
        d.line([(x, 0), (x, H)], fill=grade, width=1)
    for y in GRID_LINHAS[12:]:
        d.line([(0, y), (W, y)], fill=grade, width=1)

    # Particulas subindo devagar
    cores = (
        rgb(acento),
        (43, 212, 125),
        (255, 92, 108),
    )
    for x0, y0, r, sp, ph, ci, al in PARTICULAS:
        y = (y0 - t * sp) % H
        x = x0 + 9.0 * math.sin(t * 0.35 + ph)
        c = cores[ci]
        d.ellipse((x - r, y - r, x + r, y + r),
                  fill=(c[0], c[1], c[2], int(al)))

    # Candlesticks decorativos nas bordas (alpha baixa)
    up = with_alpha((43, 212, 125), 62)
    down = with_alpha((255, 92, 108), 58)
    for x, y, ph, amp in VELAS:
        osc = math.sin(t * 0.9 + ph) * amp
        alt = int(26 + 22 * abs(math.sin(t * 0.35 + ph)))
        cor = up if osc >= 0 else down
        d.rounded_rectangle((x - 2, y - alt, x + 2, y + alt + int(8 * osc)),
                            radius=2, fill=cor)
        d.rectangle((x - 7, y - 3, x + 7, y + 3), fill=cor)


def desenhar_cabecalho(d, t, idx, acento):
    # Barra de progresso (decorativa, pode ficar acima de y=200)
    d.rectangle((0, 0, W, 9), fill=(10, 20, 42, 255))
    p = clamp(t / DUR_TOTAL)
    d.rectangle((0, 0, int(W * p), 9), fill=with_alpha(acento, 255))
    d.rectangle((int(W * p) - 3, 0, int(W * p) + 3, 9),
                fill=(255, 255, 255, 210))

    # Texto<< todo a partir de y=200 (zona segura)
    f42, f40 = fonte(42), fonte(40)
    d.text((40, 198), "MERCADO EM FOCO", font=f42, fill=BRANCO,
           stroke_width=2, stroke_fill=(0, 0, 0, 170))
    data = "SEXTA 20/11/2026"
    larg = d.textlength(data, font=f40)
    d.text((W - 40 - larg, 200), data, font=f40, fill=(188, 210, 238, 255),
           stroke_width=2, stroke_fill=(0, 0, 0, 170))


def formatar_valor(cfg, v):
    fmt = cfg["fmt"]
    if fmt == "num2":
        return ("%.2f" % v).replace(".", ",")
    if fmt == "pct1":
        return ("%+.1f" % v).replace(".", ",") + "%"
    if fmt == "pts":
        return ("{:,.0f}".format(v)).replace(",", ".") + " pts"
    if fmt == "brl":
        return "R$ " + ("%.3f" % v).replace(".", ",")
    if fmt == "usd":
        return "US$ " + ("%.2f" % v).replace(".", ",")
    return cfg.get("valor", "")


def desenhar_spark(d, sid, cfg, p, acento):
    x0, y0, x1, y1 = 624, 312, 1008, 502
    vals = SPARKS[sid]
    lo, hi = min(vals), max(vals)
    span = max(1.0, hi - lo)
    n = max(2, int(len(vals) * clamp(p)))

    def px(i):
        return x0 + (x1 - x0) * i / (len(vals) - 1)

    def py(v):
        return y1 - (y1 - y0) * (v - lo) / span

    # area preenchida
    if n >= 2:
        pts = [(px(i), py(vals[i])) for i in range(n)]
        d.polygon(pts + [(px(n - 1), y1), (px(0), y1)],
                  fill=with_alpha(acento, 26))
        d.line(pts, fill=with_alpha(acento, 225), width=5, joint="curve")

    # velas illustrative no grafico
    for k in range(0, n, 5):
        x = px(k)
        v = vals[k]
        anterior = vals[k - 1] if k > 0 else v
        c = with_alpha((43, 212, 125) if v >= anterior else (255, 92, 108), 190)
        d.line([(x, py(v) - 9), (x, py(v) + 9)], fill=c, width=2)
        d.rectangle((x - 4, py(v) - 4, x + 4, py(v) + 4), fill=c)

    # seta final de tendencia
    if n >= 3:
        ex, ey = px(n - 1), py(vals[n - 1])
        direcao = cfg["dir"]
        if direcao == "down":
            d.polygon([(ex, ey + 17), (ex - 11, ey - 5), (ex + 11, ey - 5)],
                      fill=with_alpha((255, 92, 108), 235))
        elif direcao == "up":
            d.polygon([(ex, ey - 17), (ex - 11, ey + 5), (ex + 11, ey + 5)],
                      fill=with_alpha((43, 212, 125), 235))


def desenhar_cartao(d, sid, local, acento, fonte_dados):
    cfg = DADOS_CARTAO[sid]
    x0, y0, x1, y1 = 40, 264, 1040, 560
    d.rounded_rectangle((x0, y0, x1, y1), radius=28,
                        fill=(9, 19, 39, 236), outline=with_alpha(acento, 155),
                        width=3)
    d.rounded_rectangle((x0 + 3, y0 + 3, x1 - 3, y0 + 11), radius=4,
                        fill=with_alpha(acento, 245))

    f42 = fonte(42)
    d.text((70, 286), cfg["label"], font=f42, fill=with_alpha(acento, 255),
           stroke_width=2, stroke_fill=(0, 0, 0, 160))

    # chip de data sempre visivel (feriado 19/11 vs 20/11)
    data = cfg["data"]
    dw = d.textlength(data, font=f42)
    d.rounded_rectangle((1008 - dw - 32, 280, 1012, 332), radius=13,
                        fill=(20, 38, 66, 245), outline=with_alpha(acento, 170),
                        width=2)
    d.text((1008 - dw - 16, 288), data, font=f42, fill=BRANCO)

    # contador com easing out
    p = ease_out(local / 1.05)
    if cfg["ini"] is None:
        valor = cfg["valor"]
    else:
        valor = formatar_valor(cfg, cfg["ini"] + (cfg["fim"] - cfg["ini"]) * p)
    fb = fonte(84 if len(valor) <= 13 else 72)
    d.text((66, 344), valor, font=fb, fill=BRANCO,
           stroke_width=3, stroke_fill=(0, 0, 0, 200))

    d.text((70, 468), cfg["delta"], font=fonte(46), fill=cfg["cor"],
           stroke_width=2, stroke_fill=(0, 0, 0, 170))

    desenhar_spark(d, sid, cfg, clamp(local / 1.25), acento)

    # selo de integridade / CTA (min 40 px)
    if sid == 7:
        selo, cor, borda = "CONTEÚDO EDUCATIVO", (20, 30, 50, 250), AMARELO
    elif fonte_dados == "real":
        selo, cor, borda = "DADOS REAIS", (16, 48, 58, 235), CIANO
    else:
        selo, cor, borda = "DADOS ILUSTRATIVOS", (58, 42, 16, 235), AMARELO
    fs = fonte(40)
    sw = d.textlength(selo, font=fs)
    bx0 = 1008 - sw - 34
    d.rounded_rectangle((bx0, 512, 1012, 552), radius=12,
                        fill=cor, outline=with_alpha(borda[:3], 210), width=2)
    d.text((bx0 + 17, 516), selo, font=fs, fill=borda)


def desenhar_enfase(gfx, sid, local, acento):
    if local >= 1.22:
        return
    enfase = ROTEIRO_POR_ID[sid].get("enfase")
    if not enfase:
        return
    p = clamp(local / 1.22)
    escala = 0.72 + 0.36 * ease_out(p) + 0.045 * math.sin(math.pi * p)
    alpha = int(255 * clamp(p / 0.16))
    if alpha <= 2:
        return
    f = fonte(74)
    tmp = Image.new("RGBA", (1080, 130), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    td.text((540, 0), enfase, font=f, fill=with_alpha(acento, 255),
            anchor="ma", stroke_width=4, stroke_fill=(3, 8, 20, 255))
    nw = max(1, int(1080 * escala))
    nh = max(1, int(130 * escala))
    if escala != 1.0:
        tmp = tmp.resize((nw, nh), Image.Resampling.LANCZOS)
    tmp.putalpha(tmp.getchannel("A").point(lambda v: v * alpha // 255))
    # Re-centraliza apos escala (o texto ja estava centralizado em 540)
    gfx.alpha_composite(tmp, dest=((W - nw) // 2, 606))


def desenhar_aviso(frame, sid, t, local):
    if sid != 7:
        return
    alpha = int(255 * smooth((local - 0.4) / 0.6))
    if alpha <= 2:
        return
    d = ImageDraw.Draw(frame, "RGBA")
    x0, y0, x1, y1 = 40, 1678, 1040, 1774
    d.rounded_rectangle((x0, y0, x1, y1), radius=18,
                        fill=(8, 16, 34, int(226 * alpha / 255)),
                        outline=with_alpha(AMARELO, int(150 * alpha / 255)),
                        width=2)
    f = fonte(40)
    linhas = ("CONTEÚDO EDUCATIVO — NÃO É",
              "RECOMENDAÇÃO DE INVESTIMENTO")
    for j, linha in enumerate(linhas):
        texto_central(d, W // 2, y0 + 4 + j * 44, linha, f,
                      with_alpha(BRANCO_SUAVE[:3], alpha), 1)


def aplicar_whoosh(gfx, dx, alpha):
    if dx == 0 and alpha >= 0.999:
        return gfx
    out = Image.new("RGBA", gfx.size, (0, 0, 0, 0))
    out.paste(gfx, (dx, 0))
    if alpha < 0.999:
        a = out.getchannel("A").point(lambda v: int(v * alpha))
        out.putalpha(a)
    return out


def desenhar_whoosh_flash(d, idx, local):
    if idx == 0 or local >= WHOOSH:
        return
    p = clamp(local / WHOOSH)
    x = int(W * p)
    a = int(85 * math.sin(math.pi * p))
    d.line([(x, 210), (x - 170, 1420)], fill=(255, 255, 255, a), width=9)
    d.line([(x + 18, 210), (x - 152, 1420)],
           fill=with_alpha((255, 216, 77)[:3], int(a * 0.6)), width=4)


# ---------------------------------------------------------------------------
# Animacao do apresentador
# ---------------------------------------------------------------------------
def estado_apresentador(t, idx, local, palavra):
    # boca: oscilacao rapida (~6 Hz) apenas com palavra ativa
    if palavra is not None:
        u = clamp((t - palavra["inicio"]) / 0.045) * clamp((palavra["fim"] - t) / 0.055)
        boca = (0.48 + 0.42 * math.sin(math.tau * 6.0 * t)) * u
        boca = clamp(boca, 0.0, 1.0)
    else:
        boca = 0.0

    # piscada: pulso de 0.12 s a cada 3.6 s
    fase = t % 3.6
    piscar = math.sin(math.pi * fase / 0.12) if fase < 0.12 else 0.0

    # sobrancelha com transicao suave entre segmentos
    alvos = {4: -0.8, 6: 0.8, 7: 0.8}
    atual = alvos.get(idx + 1, 0.0)
    anterior = alvos.get(idx, 0.0) if idx > 0 else 0.0
    w = smooth(local / 0.75)
    sobrancelha = anterior * (1 - w) + atual * w

    # olhar: deriva senoidal suave em [-0.3, 0.3]
    olhar = 0.30 * (0.72 * math.sin(math.tau * 0.13 * t + 0.4)
                    + 0.28 * math.sin(math.tau * 0.37 * t))
    olhar = max(-0.3, min(0.3, olhar))

    # braco: gesto curto sincronizado com palavras de enfase
    braco = 0.0
    if palavra is not None and palavra["texto"] in PALAVRAS_GESTO:
        span = max(0.05, palavra["fim"] - palavra["inicio"])
        u = clamp((t - palavra["inicio"]) / span)
        braco = 0.78 * (math.sin(math.pi * u) ** 1.4)

    inclinar = 0.34 * math.sin(math.tau * 0.11 * t + 1.0)
    bob = int(round(5.0 * math.sin(math.tau * 0.52 * t)))
    return dict(boca=boca, olhar=olhar, piscar=piscar,
                sobrancelha=sobrancelha, braco=braco,
                inclinar=inclinar), bob


# ---------------------------------------------------------------------------
# Frame completo
# ---------------------------------------------------------------------------
def make_frame(t: float) -> np.ndarray:
    t = max(0.0, min(float(t), DUR_TOTAL - 1.0 / FPS))
    idx = idx_em(t)
    sid = idx + 1
    local = t - SEG_STARTS[idx]
    acento3 = ACENTOS[sid]

    # 1) fundo
    frame = Image.fromarray(fundo_array(t, idx, local), "RGBA")
    d = ImageDraw.Draw(frame, "RGBA")
    desenhar_fundo(d, t, idx, local, acento3)

    # 2..4, 7) camada grafica (cabecalho / cartao / enfase / CTA)
    gfx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gfx, "RGBA")
    desenhar_cabecalho(gd, t, idx, acento3)
    desenhar_cartao(gd, sid, local, acento3, ROTEIRO.get("fonte_dados", "real"))
    try:
        desenhar_enfase(gfx, sid, local, acento3)
    except Exception:
        pass

    # transicao whoosh de 0.18 s (entrada) + fade de saida antes do proximo
    dx, alpha = 0, 1.0
    if idx > 0 and local < WHOOSH:
        p = ease_out(local / WHOOSH)
        dx, alpha = int((1 - p) * 72), 0.18 + 0.82 * p
    if idx + 1 < len(SEG):
        restante = SEG_STARTS[idx + 1] - t
        if 0.0 <= restante < WHOOSH:
            q = clamp(restante / WHOOSH)
            dx, alpha = int(-42 * (1 - q)), 0.25 + 0.75 * q
    gfx = aplicar_whoosh(gfx, dx, alpha)
    frame.alpha_composite(gfx)
    desenhar_whoosh_flash(d, idx, local)

    # 5) apresentador
    bloco = bloco_em(t)
    palavra = None
    if bloco is not None:
        for p in bloco["palavras"]:
            if p["inicio"] <= t <= p["fim"]:
                palavra = p
                break
    params, bob = estado_apresentador(t, idx, local, palavra)
    pres = presenter.render_frame(**params)
    frame.paste(pres, (0, bob), pres)

    # 6) legenda karaoke (somente enquanto ha fala/audio)
    if bloco is not None and t <= DUR_AUDIO:
        legenda.desenhar_legenda(frame, bloco, t)

    # aviso do roteiro por cima do apresentador (rodape)
    desenhar_aviso(frame, sid, t, local)

    # encerramento visual (audio ja terminou): fade para cartao final
    if t > DUR_AUDIO:
        p = smooth((t - DUR_AUDIO) / 1.20)
        over = Image.new("RGBA", (W, H), (5, 11, 24, int(210 * p)))
        frame.alpha_composite(over)
        od = ImageDraw.Draw(frame, "RGBA")
        a = int(255 * p)
        texto_central(od, W // 2, 880, "MERCADO EM FOCO", fonte(72),
                      with_alpha(BRANCO[:3], a), 3)
        texto_central(od, W // 2, 990, "CONTEÚDO EDUCATIVO", fonte(46),
                      with_alpha(AMARELO[:3], a), 2)

    return np.array(frame)[..., :3]


# ---------------------------------------------------------------------------
# Renderizacao / CLI
# ---------------------------------------------------------------------------
def renderizar():
    from moviepy import AudioFileClip, VideoClip

    print("Carregando insumos...", flush=True)
    carregar()
    print("Blocos de legenda: %d | audio %.3fs | video %.3fs" %
          (len(BLOCOS), DUR_AUDIO, DUR_TOTAL), flush=True)

    t0 = time.perf_counter()
    clip = VideoClip(frame_function=make_frame, duration=DUR_TOTAL)
    audio = AudioFileClip(str(VOZ_PATH))
    clip = clip.with_audio(audio)
    clip.write_videofile(
        str(OUT_PATH),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        preset="fast",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        logger="bar",
    )
    clip.close()
    audio.close()
    print("Renderizado em %.1fs -> %s" % (time.perf_counter() - t0, OUT_PATH),
          flush=True)


def testar_frame(t):
    carregar()
    arr = make_frame(t)
    Image.fromarray(arr).save(TEST_PATH)
    print("Frame de teste t=%.2f -> %s" % (t, TEST_PATH))


if __name__ == "__main__":
    if "--test-frame" in sys.argv:
        i = sys.argv.index("--test-frame")
        testar_frame(float(sys.argv[i + 1]))
    else:
        renderizar()
