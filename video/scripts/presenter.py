#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apresentador 2D cartoon corporate - versao 2 (volume, curvas e idle organico).

Uso:
    python3 video/scripts/presenter.py

API publica (inalterada): CANVAS, DESCRIPTION, PALETA, render_frame(...).

Pipeline de qualidade
---------------------
* Nao ha poligonos de cantos retos: todas as silhuetas sao curvas Catmull-Rom
  densamente amostradas, com juntas fundidas por mascara alpha unica (face +
  orelhas, camisa + mangas, cabelo + mechas). Contornos finos (1-2 px) e
  semitransparentes, nao o traco escuro de 6-7 px da v1.
* `sphere_shade()` (secao 1 do melhorias.md) aplica as cinco zonas de luz com
  uma UNICA fonte LUZ: highlight, lado iluminado, core, rim frio e sombra
  projetada. SSS quente (#FF9E7A) em orelhas, nariz e bochechas.
* Supersampling s=3 + LANCZOS em `_finish()` para todas as camadas estaticas
  (custo pago uma vez no import). Partes dinamicas usam patches 3x reduzidos
  com filtro de caixa para permanecer abaixo de 25 ms/frame.
* Idle deterministico (SEED 20261122): respiracao 1,2%/3,4 s, tilt de cabeca
  por bloco, micro-sacadas com settle de ~60 ms, piscadas assimetricas de
  180 ms (18% duplas). Transicoes de boca/olhar/sobrancelha com ease-out
  exponencial de ~90 ms. Piscada fornecida pelo chamador e instantanea.

Auxiliares extras (nao alteram a API exigida): set_idle(), reset_state(),
set_frame().
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
CANVAS = (1080, 1920)  # largura, altura

DESCRIPTION = (
    "Apresentador cartoon corporate volumetrico: homem ~35 anos, cabelo curto "
    "azul-escuro, pele quente com SSS e textura sutil, terno azul-marinho e "
    "gravata teal. Silhuetas em curvas Catmull-Rom, cinco zonas de luz com "
    "fonte unica, rim frio e camadas animaveis (boca, olhos, sobrancelhas, "
    "braco e inclinacao da cabeca)."
)

PALETA = {
    "contorno": "#12203A",
    "pele": "#E8B68F",
    "pele_clara": "#FFD9B4",
    "pele_sombra": "#B97955",
    "sombra_pele": "#7A4631",
    "sss": "#FF9E7A",
    "cabelo": "#1B2742",
    "cabelo_claro": "#3C5379",
    "camisa": "#1B2E4F",
    "camisa_claro": "#365A8C",
    "camisa_sombra": "#101D36",
    "gola": "#EAF2FA",
    "acento_verde": "#20B58D",
    "acento_azul": "#2F80ED",
    "olho_branco": "#F7FBFF",
    "iris": "#2A5D94",
    "iris_claro": "#5E9FD6",
    "pupila": "#0C1526",
    "boca": "#4A1B24",
    "lingua": "#E86A82",
    "dente": "#F5FAFF",
    "halo": "#7FC8FF",
    "sombra": "#0A1424",
}

# ---------------------------------------------------------------------------
# Constantes internas
# ---------------------------------------------------------------------------


def _rgb(hexstr: str):
    h = hexstr.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


C = {k: _rgb(v) for k, v in PALETA.items()}
OUT = C["contorno"]
OUT_SOFT = OUT + (168,)          # contorno fino semitransparente
SS = 3                            # supersampling das camadas estaticas
SEED = 20261122
FPS = 30
IDLE_FRAMES = 3600                # 120 s de idle deterministico

# Fonte de luz UNICA (alta-esquerda), compartilhada por todas as formas.
LUZ = (0.45, 0.75, 0.50)
LIGHT_X = 0.5 + (LUZ[0] - 0.5) * 1.6   # 0.42
LIGHT_Y = 0.5 - (LUZ[1] - 0.5) * 1.0   # 0.25

BROW_LIGHT = tuple(int(C["cabelo"][i] * 0.55 + C["cabelo_claro"][i] * 0.45) for i in range(3))
LIP_LIGHT = tuple(int(C["pele_sombra"][i] * 0.45 + C["boca"][i] * 0.55) for i in range(3))
SHIRT_SEAM = tuple(int(C["camisa"][i] * 0.7 + OUT[i] * 0.3) for i in range(3))

# Cabeca (coordenadas locais do patch).
HEAD_W, HEAD_H = 380, 520
HCX, HCY = 190, 170
HEAD_DEST = (540 - HCX, 980 - HCY)  # cabeca centrada em (540, 980)
MAX_TILT = 12

FEAT_BOX = (20, 55, 360, 325)        # regiao dos elementos faceis (com margem)

TORSO_W, TORSO_H = 540, 660
TORSO_DEST = (270, 1150)

# Contornos organicos (pontos de controle Catmull-Rom fechados).
FACE_PTS = [
    (190, 27), (250, 33), (292, 71), (306, 131), (302, 195),
    (272, 257), (220, 299), (190, 312), (160, 299), (108, 257),
    (78, 195), (74, 131), (88, 71), (130, 33),
]
EAR_L = [(76, 140), (52, 143), (44, 176), (54, 210), (76, 215), (89, 187)]
EAR_R = [(304, 140), (328, 143), (336, 176), (326, 210), (304, 215), (291, 187)]
NECK_PTS = [(151, 248), (229, 248), (238, 380), (234, 488), (146, 488), (142, 380)]
HAIR_PTS = [
    (58, 151), (50, 92), (78, 42), (140, 14), (214, 9), (278, 25),
    (313, 69), (311, 127), (288, 113), (262, 73), (214, 55),
    (160, 61), (112, 93), (84, 141),
]
NOSE_PTS = [(175, 188), (196, 181), (209, 199), (213, 216), (200, 227), (179, 223), (171, 205)]

SHIRT_PTS = [
    (270, 34), (345, 43), (415, 76), (453, 138), (465, 242), (458, 394),
    (442, 562), (428, 638), (112, 638), (98, 562), (82, 394), (75, 242),
    (87, 138), (125, 76), (195, 43),
]
COLLAR_L = [(224, 40), (270, 118), (198, 102), (181, 55)]
COLLAR_R = [(316, 40), (270, 118), (342, 102), (359, 55)]
TIE_KNOT = [(251, 110), (289, 110), (298, 140), (270, 163), (242, 140)]
TIE_BODY = [(258, 160), (282, 160), (293, 252), (284, 428), (270, 474),
            (256, 428), (247, 252)]
POCKET_PTS = [(116, 300), (186, 300), (178, 342), (126, 342)]

# ---------------------------------------------------------------------------
# Geometria e sombreamento
# ---------------------------------------------------------------------------


def _clamp(v, lo=-1.0, hi=1.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(x) or math.isinf(x):
        return 0.0
    return max(lo, min(hi, x))


def _mix(a, b, t):
    return tuple(int(round(a[i] * (1.0 - t) + b[i] * t)) for i in range(3))


def _cr(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return tuple(
        0.5 * ((2 * p1[i]) + (-p0[i] + p2[i]) * t
               + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * t2
               + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * t3)
        for i in (0, 1)
    )


def _curve(points, steps=7, closed=True):
    pts = list(points)
    n = len(pts)
    if n < 2:
        return pts[:]
    out = []
    if closed:
        for i in range(n):
            p0, p1 = pts[(i - 1) % n], pts[i]
            p2, p3 = pts[(i + 1) % n], pts[(i + 2) % n]
            for k in range(steps):
                out.append(_cr(p0, p1, p2, p3, k / steps))
        out.append(out[0])
    else:
        for i in range(n - 1):
            p0 = pts[i - 1] if i > 0 else pts[0]
            p1, p2 = pts[i], pts[i + 1]
            p3 = pts[i + 2] if i + 2 < n else pts[-1]
            for k in range(steps):
                out.append(_cr(p0, p1, p2, p3, k / steps))
        out.append(pts[-1])
    return out


def _spoly(d, pts, fill, outline=None, width=1, closed=True, steps=7,
           k=SS, T=None):
    """Contorno preenchido por spline Catmull-Rom, em coordenadas de projeto."""
    p = _curve(pts, steps, closed)
    if T is not None:
        p = [T(x, y) for x, y in p]
    q = [(int(round(x * k)), int(round(y * k))) for x, y in p]
    if closed:
        d.polygon(q, fill=fill)
        if outline is not None and width > 0:
            d.line(q, fill=outline, width=max(1, int(round(width * k))), joint="curve")
    else:
        n = max(1, int(round(width * k)))
        d.line(q, fill=outline or fill, width=n, joint="curve")
    return q


def _grad(w, h, c0, c1, kind="radial", cx=0.5, cy=0.45, r=0.8,
          angle=math.pi / 2, gamma=1.0):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xn, yn = xx / max(1, w - 1), yy / max(1, h - 1)
    if kind == "radial":
        t = np.sqrt(((xn - cx) / r) ** 2 + ((yn - cy) / (r * 1.12)) ** 2)
    else:
        t = 0.5 + ((xn - 0.5) * math.cos(angle) + (yn - 0.5) * math.sin(angle)) * 1.25
    t = np.clip(t, 0.0, 1.0) ** gamma
    arr = np.empty((h, w, 3), dtype=np.uint8)
    for i in range(3):
        arr[..., i] = (c0[i] * (1.0 - t) + c1[i] * t).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def sphere_shade(mask_img, base, highlight, core, cx, cy, power=1.25,
                 rim=C["halo"], rim_alpha=0.06, sss=None, sss_center=None,
                 sss_alpha=0.0, spec=0.28):
    """Cinco zonas de luz numa forma redonda (secao 1 do melhorias.md).

    highlight -> lado iluminado -> core -> rim frio, com specular unico na
    direcao de LUZ e SSS quente opcional. `mask_img` e uma mascara L (silhueta).
    """
    a = np.asarray(mask_img, dtype=np.float32) / 255.0
    h, w = a.shape
    Y, X = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((X - cx * w) / (0.52 * w)) ** 2
                + ((Y - cy * h) / (0.52 * h)) ** 2)
    t = np.clip(r, 0.0, 1.0) ** power

    base_a = np.array(base, dtype=np.float32)
    hi = np.array(highlight, dtype=np.float32)
    co = np.array(core, dtype=np.float32)

    t1 = np.clip(t / 0.35, 0.0, 1.0)[..., None]
    col = hi * (1.0 - t1) + base_a * t1
    t2 = np.clip((t - 0.35) / 0.65, 0.0, 1.0)[..., None]
    col = col * (1.0 - t2) + co * t2

    # specular deslocado para a fonte de luz (um unico ponto difuso)
    sw = (np.exp(-r * 6.0) * spec)[..., None]
    col = col * (1.0 - sw) + hi * sw

    # rim frio somente na borda superior da silhueta
    eroded = np.asarray(mask_img.filter(ImageFilter.MinFilter(7)), dtype=np.float32) / 255.0
    edge = np.clip(a - eroded, 0.0, 1.0)
    upper = np.clip(1.0 - Y / (0.6 * h), 0.0, 1.0)
    rw = (edge * upper * rim_alpha)[..., None]
    col = col * (1.0 - rw) + np.array(rim, dtype=np.float32) * rw

    # SSS: brilho quente que atravessa a pele (nariz, orelhas, bochechas)
    if sss is not None and sss_center is not None:
        sx, sy = sss_center
        g = np.exp(-(((X - sx * w) / (0.17 * w)) ** 2
                     + ((Y - sy * h) / (0.17 * h)) ** 2))
        gw = (g * sss_alpha * a)[..., None]
        col = col * (1.0 - gw) + np.array(sss, dtype=np.float32) * gw

    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = np.clip(col, 0, 255).astype(np.uint8)
    out[..., 3] = (a * 255.0).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _tinted_mask(mask, color, blur=0):
    layer = Image.new("RGBA", mask.size, color + (0,))
    if blur > 0:
        layer.putalpha(mask.filter(ImageFilter.GaussianBlur(blur * SS)))
    else:
        layer.putalpha(mask)
    return layer


def _shape_mask(size, *shape_fns):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for fn in shape_fns:
        fn(d)
    return m


def _finish(img, size):
    """Supersampling s=3 + LANCZOS, aplicado uma unica vez por camada."""
    return img.resize(size, Image.Resampling.LANCZOS) if img.size != size else img


# ---------------------------------------------------------------------------
# Camadas estaticas
# ---------------------------------------------------------------------------


_CAP_CACHE = {}


def _capsule(length, r, c_light, c_dark, outline=OUT_SOFT, cuff=False, k=SS):
    """Segmento de membro arredondado. Modelos quantizados em cache (6 px)."""
    key = (int(round(length / 6.0)), r, c_light, c_dark, outline, cuff, k)
    hit = _CAP_CACHE.get(key)
    if hit is not None:
        return hit
    pad = 5
    ri = int(math.ceil(r))
    W = int(math.ceil(length)) + 2 * ri + 2 * pad
    H = 2 * ri + 2 * pad
    w, h = W * k, H * k
    x0 = (r + pad) * k
    x1 = x0 + length * k
    cy = h / 2.0
    rr = r * k
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rectangle((int(x0), int(cy - rr), int(x1), int(cy + rr)), fill=255)
    d.ellipse((int(x0 - rr), int(cy - rr), int(x0 + rr), int(cy + rr)), fill=255)
    d.ellipse((int(x1 - rr), int(cy - rr), int(x1 + rr), int(cy + rr)), fill=255)

    layer = sphere_shade(m, c_dark, c_light, c_dark,
                         cx=0.30, cy=0.22, power=1.1, rim_alpha=0.05)
    od = ImageDraw.Draw(layer)
    lw = max(1, int(round(1.4 * k)))
    od.arc((x0 - rr, cy - rr, x0 + rr, cy + rr), 90, 270, fill=outline, width=lw)
    od.arc((x1 - rr, cy - rr, x1 + rr, cy + rr), 270, 90, fill=outline, width=lw)
    od.line((x0, cy - rr, x1, cy - rr), fill=outline, width=lw)
    od.line((x0, cy + rr, x1, cy + rr), fill=outline, width=lw)
    if cuff:
        cx = x1 - rr * 0.75
        od.line((cx, cy - rr, cx, cy + rr), fill=outline, width=lw)
        od.line((cx - 2 * k, cy - rr + 2 * k, cx - 2 * k, cy + rr - 2 * k),
                fill=C["gola"], width=max(1, int(4 * k)))
    result = layer.reduce(k)
    _CAP_CACHE[key] = result
    return result


def _paste_segment(frame, seg, p0, p1, scale=1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ang = math.degrees(math.atan2(dy, dx))
    rot = seg.rotate(-ang, resample=Image.Resampling.BILINEAR, expand=True)
    if scale != 1:
        rot = rot.resize((rot.width * scale, rot.height * scale),
                         Image.Resampling.BILINEAR)
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    frame.paste(rot, (int(round(mx * scale - rot.width / 2)),
                      int(round(my * scale - rot.height / 2))), rot.getchannel("A"))


def _build_torso():
    w, h = TORSO_W * SS, TORSO_H * SS

    # braco esquerdo (atras do corpo): juntas fundidas por capsulas sobrepostas
    back = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    a = _capsule(285, 31, C["camisa_claro"], C["camisa_sombra"], cuff=True)
    _paste_segment(back, a, (110, 115), (46, 392), scale=SS)
    hm = _shape_mask((w, h),
                     lambda d: d.ellipse((int(16 * SS), int(372 * SS),
                                          int(80 * SS), int(444 * SS)), fill=255))
    hand = sphere_shade(hm, C["pele"], C["pele_clara"], C["pele_sombra"],
                        cx=0.28, cy=0.30, sss=C["sss"], sss_center=(0.35, 0.4), sss_alpha=0.12)
    hd = ImageDraw.Draw(hand)
    hd.ellipse((int(16 * SS), int(372 * SS), int(80 * SS), int(444 * SS)),
               outline=OUT_SOFT, width=int(round(1.4 * SS)))
    for kx in (32, 46, 60):
        hd.line((int(kx * SS), int(392 * SS), int((kx + 1) * SS), int(410 * SS)),
                fill=OUT_SOFT, width=int(round(1.2 * SS)))
    back.alpha_composite(hand)

    # camisa: mesma fonte de luz do rosto, rim frio no ombro
    sm = _shape_mask((w, h), lambda d: _spoly(d, SHIRT_PTS, 255))
    shirt = sphere_shade(sm, C["camisa"], C["camisa_claro"], C["camisa_sombra"],
                         cx=0.30, cy=LIGHT_Y, power=1.05, rim_alpha=0.07)
    shade = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shade).rectangle((0, int(470 * SS), w, h), fill=105)
    shade = ImageChops.multiply(shade.filter(ImageFilter.GaussianBlur(26 * SS)), sm)
    shirt.alpha_composite(_tinted_mask(shade, C["sombra"]))
    sd = ImageDraw.Draw(shirt)
    _spoly(sd, SHIRT_PTS, None, OUT_SOFT, 1.5)
    _spoly(sd, [(70, 200), (110, 300), (102, 520)], None, C["camisa_claro"], 2.5, closed=False)
    _spoly(sd, [(470, 200), (430, 300), (438, 520)], None, SHIRT_SEAM, 2.5, closed=False)

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(back)
    out.alpha_composite(shirt)
    return _finish(out, (TORSO_W, TORSO_H))


def _build_head_base():
    """Rosto volumetrico, orelhas, cabelo e nariz (sem feicoes dinamicas)."""
    w, h = HEAD_W * SS, HEAD_H * SS
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # --- pescoco -----------------------------------------------------------
    nm = _shape_mask((w, h), lambda d: _spoly(d, NECK_PTS, 255))
    neck = sphere_shade(nm, C["pele"], C["pele_clara"], C["pele_sombra"],
                        cx=LIGHT_X - 0.02, cy=0.20)
    nsh = Image.new("L", (w, h), 0)
    ImageDraw.Draw(nsh).ellipse((int((HCX - 66) * SS), int((HCY + 96) * SS),
                                 int((HCX + 66) * SS), int((HCY + 168) * SS)), fill=170)
    nsh = ImageChops.multiply(nsh.filter(ImageFilter.GaussianBlur(13 * SS)), nm)
    neck.alpha_composite(_tinted_mask(nsh, C["sombra_pele"]))
    out.alpha_composite(neck)

    # --- rosto + orelhas (silhueta unica, juntas fundidas) -----------------
    fm = _shape_mask((w, h),
                     lambda d: _spoly(d, FACE_PTS, 255),
                     lambda d: _spoly(d, EAR_L, 255),
                     lambda d: _spoly(d, EAR_R, 255))
    face = sphere_shade(fm, C["pele"], C["pele_clara"], C["pele_sombra"],
                        cx=LIGHT_X - 0.06, cy=LIGHT_Y, power=0.92,
                        rim_alpha=0.07, sss=C["sss"], sss_center=(0.50, 0.45),
                        sss_alpha=0.13)

    # oclusao sob o queixo e ao longo da mandibula (sombra fria)
    jaw = Image.new("L", (w, h), 0)
    ImageDraw.Draw(jaw).ellipse((int(108 * SS), int(250 * SS),
                                 int(272 * SS), int(356 * SS)), fill=120)
    jaw = ImageChops.multiply(jaw.filter(ImageFilter.GaussianBlur(17 * SS)), fm)
    face.alpha_composite(_tinted_mask(jaw, C["sombra_pele"]))

    # SSS quente em bochechas e orelhas (orelhas mais saturadas)
    for box, val in [((96, 196, 148, 242), 46), ((232, 196, 284, 242), 46),
                     ((54, 157, 82, 203), 78), ((298, 157, 326, 203), 78)]:
        bm = Image.new("L", (w, h), 0)
        ImageDraw.Draw(bm).ellipse(tuple(int(v * SS) for v in box), fill=val)
        bm = ImageChops.multiply(bm.filter(ImageFilter.GaussianBlur(9 * SS)), fm)
        face.alpha_composite(_tinted_mask(bm, C["sss"]))

    # specular suave na testa e ponte do nariz (mesma direcao de LUZ)
    for box, val in [((126, 58, 210, 112), 58), ((178, 150, 202, 208), 44)]:
        hm = Image.new("L", (w, h), 0)
        ImageDraw.Draw(hm).ellipse(tuple(int(v * SS) for v in box), fill=val)
        hm = ImageChops.multiply(hm.filter(ImageFilter.GaussianBlur(11 * SS)), fm)
        face.alpha_composite(_tinted_mask(hm, (255, 248, 236)))

    # textura de pele: ruido de baixa amplitude, restrito ao rosto
    rng = np.random.default_rng(SEED)
    noise = rng.normal(0.0, 2.6, (h, w)).astype(np.float32)
    raw = np.asarray(face).astype(np.float32)
    raw[..., :3] += noise[..., None]
    face = Image.fromarray(np.clip(raw, 0, 255).astype(np.uint8), "RGBA")

    fd = ImageDraw.Draw(face)
    _spoly(fd, FACE_PTS, None, OUT_SOFT, 1.5)
    for ear in (EAR_L, EAR_R):
        _spoly(fd, ear, None, OUT_SOFT, 1.3)
    out.alpha_composite(face)

    # --- nariz -------------------------------------------------------------
    nm2 = _shape_mask((w, h), lambda d: _spoly(d, NOSE_PTS, 255))
    nose = sphere_shade(nm2, C["pele"], C["pele_clara"], C["pele_sombra"],
                        cx=0.38, cy=0.24, power=1.0, rim_alpha=0.05,
                        sss=C["sss"], sss_center=(0.52, 0.65), sss_alpha=0.24)
    nd2 = ImageDraw.Draw(nose)
    _spoly(nd2, NOSE_PTS, None, OUT_SOFT, 1.2)
    nd2.ellipse((int(188 * SS), int(188 * SS), int(198 * SS), int(198 * SS)),
                fill=(255, 248, 238, 150))
    out.alpha_composite(nose)

    # --- cabelo com rim frio -----------------------------------------------
    hm = _shape_mask((w, h), lambda d: _spoly(d, HAIR_PTS, 255))
    hair = sphere_shade(hm, C["cabelo"], C["cabelo_claro"], (13, 20, 36),
                        cx=LIGHT_X - 0.12, cy=0.05, power=0.9, rim_alpha=0.10)
    hd = ImageDraw.Draw(hair)
    _spoly(hd, HAIR_PTS, None, OUT_SOFT, 1.4)
    _spoly(hd, [(104, 76), (160, 40), (230, 31), (282, 52)],
           None, BROW_LIGHT, 4, closed=False)
    _spoly(hd, [(126, 86), (176, 52), (240, 46)],
           None, BROW_LIGHT, 2.5, closed=False)
    out.alpha_composite(hair)

    return _finish(out, (HEAD_W, HEAD_H))


def _build_collar():
    """Colarinho, gravata teal, bolso e botoes (a frente do pescoco)."""
    w, h = TORSO_W * SS, TORSO_H * SS
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    tm = _shape_mask((w, h), lambda d: _spoly(d, TIE_BODY, 255),
                     lambda d: _spoly(d, TIE_KNOT, 255))
    tie = sphere_shade(tm, C["acento_verde"], (70, 214, 178), (12, 84, 78),
                       cx=0.40, cy=0.18, rim_alpha=0.04)
    td = ImageDraw.Draw(tie)
    _spoly(td, TIE_BODY, None, OUT_SOFT, 1.4)
    _spoly(td, TIE_KNOT, None, OUT_SOFT, 1.4)
    _spoly(td, [(270, 176), (274, 300), (270, 452)],
           None, C["acento_azul"], 4, closed=False)
    out.alpha_composite(tie)

    cm = _shape_mask((w, h), lambda d: _spoly(d, COLLAR_L, 255),
                     lambda d: _spoly(d, COLLAR_R, 255))
    collar = sphere_shade(cm, C["gola"], (255, 255, 255), (183, 205, 228),
                          cx=0.42, cy=LIGHT_Y, rim_alpha=0.04)
    cd = ImageDraw.Draw(collar)
    _spoly(cd, COLLAR_L, None, OUT_SOFT, 1.4)
    _spoly(cd, COLLAR_R, None, OUT_SOFT, 1.4)
    out.alpha_composite(collar)

    pd = ImageDraw.Draw(out)
    _spoly(pd, POCKET_PTS, C["camisa_claro"], SHIRT_SEAM, 1.5)
    _spoly(pd, [(126, 302), (176, 302), (150, 330)], C["acento_verde"])
    for by in (368, 448, 528):
        pd.ellipse((int(264 * SS), int((by - 6) * SS),
                    int(276 * SS), int((by + 6) * SS)), fill=OUT)
    return _finish(out, (TORSO_W, TORSO_H))


def _build_background(torso, head):
    """Halo + sombra projetada escura-fria (alpha do objeto, blur, offset)."""
    w, h = CANVAS
    tsh = Image.new("L", CANVAS, 0)
    tsh.paste(torso.getchannel("A"), TORSO_DEST)
    hsh = Image.new("L", CANVAS, 0)
    hsh.paste(head.getchannel("A"), HEAD_DEST)
    sil = ImageChops.lighter(tsh, hsh)
    shadow_alpha = sil.filter(ImageFilter.GaussianBlur(26)).point(lambda v: int(v * 0.35))
    shadow_alpha = np.roll(np.asarray(shadow_alpha), 12, axis=0)
    shadow_alpha[0:12, :] = 0
    shadow = Image.new("RGBA", CANVAS, C["sombra"] + (0,))
    shadow.putalpha(Image.fromarray(shadow_alpha, "L"))

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - 540.0) / 620.0) ** 2 + ((yy - 1180.0) / 780.0) ** 2)
    a = np.clip(1.0 - r, 0.0, 1.0) ** 2.2 * 66.0
    arr = np.empty((h, w, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = C["halo"]
    arr[..., 3] = a.astype(np.uint8)
    layer = Image.fromarray(arr, "RGBA")
    layer.alpha_composite(shadow)
    return layer


# Caches de modulo -----------------------------------------------------------
_TORSO = _build_torso()
_HEAD_BASE = _build_head_base()
_COLLAR = _build_collar()
_BG = _build_background(_TORSO, _HEAD_BASE)

_STATIC_FULL = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
_STATIC_FULL.alpha_composite(_BG)
_STATIC_FULL.alpha_composite(_TORSO, TORSO_DEST)

# respiracao 1,2%: versoes escaladas do torso, ancoradas na base
_TORSO_BREATH = {}
for _k in range(-4, 5):
    _sc = 1.0 + 0.012 * _k / 4.0
    _TORSO_BREATH[_k] = (
        _TORSO if _k == 0 else
        _TORSO.resize((int(round(TORSO_W * _sc)), int(round(TORSO_H * _sc))),
                      Image.Resampling.BILINEAR)
    )

# mascaras alpha L precomputadas (evita conversao RGBA->L por frame)
_TORSO_MASK = {k: im.getchannel("A") for k, im in _TORSO_BREATH.items()}
_COLLAR_MASK = _COLLAR.getchannel("A")

# cabecas rotacionadas pre-renderizadas (custo pago uma vez no import)
_HEAD_ROT = {}
_HEAD_MASK = {}
for _deg in range(-MAX_TILT, MAX_TILT + 1):
    _HEAD_ROT[_deg] = (
        _HEAD_BASE if _deg == 0 else
        _HEAD_BASE.rotate(_deg, resample=Image.Resampling.BICUBIC,
                          center=(HCX, HCY), expand=False)
    )
    _HEAD_MASK[_deg] = _HEAD_ROT[_deg].getchannel("A")

_FW, _FH = FEAT_BOX[2] - FEAT_BOX[0], FEAT_BOX[3] - FEAT_BOX[1]
_PW, _PH = _FW * SS, _FH * SS

# Stamps justos + gradientes reutilizados (nao dependem dos parametros).
BROW_STAMP_SIZE = (260, 100)
EYE_STAMP_SIZE = (100, 90)
MOUTH_STAMP_SIZE = (140, 110)
_EYE_PX = (EYE_STAMP_SIZE[0] * SS, EYE_STAMP_SIZE[1] * SS)
_MOUTH_PX = (MOUTH_STAMP_SIZE[0] * SS, MOUTH_STAMP_SIZE[1] * SS)
_EYE_STAMP = _grad(_EYE_PX[0], _EYE_PX[1], (255, 255, 255), (206, 224, 240),
                   kind="linear", angle=math.pi / 2)
_MOUTH_STAMP = _grad(_MOUTH_PX[0], _MOUTH_PX[1], (90, 28, 42), C["boca"],
                     kind="linear", angle=math.pi / 2)


def _new_frame() -> Image.Image:
    img = Image.fromarray(np.empty((CANVAS[1], CANVAS[0], 4), np.uint8), "RGBA")
    img.readonly = 0
    return img


# ---------------------------------------------------------------------------
# Idle deterministico (SEED 20261122)
# ---------------------------------------------------------------------------


def _build_idle():
    rng = random.Random(SEED)
    n = IDLE_FRAMES

    # tilt de cabeca: +/-2 a 4 graus, um valor por bloco de fala (5-7 s)
    tilt = np.zeros(n, dtype=np.float32)
    f = 0
    while f < n:
        block = rng.randint(5 * FPS, 7 * FPS)
        amp = rng.uniform(2.0, 4.0) * rng.choice([-1.0, 1.0])
        tilt[f:f + block] = amp
        f += block

    # micro-sacadas: alvo novo a cada 1,5-4 s, amplitude 0,03, settle ~60 ms
    gaze = np.zeros(n, dtype=np.float32)
    lid = np.zeros(n, dtype=np.float32)
    target, cur, nxt = 0.0, 0.0, 0
    settle = 1.0 - math.exp(-1.0 / (FPS * 0.06))
    for i in range(n):
        if i >= nxt:
            target = rng.uniform(-1.0, 1.0) * 0.03
            nxt = i + rng.randint(int(1.5 * FPS), int(4.0 * FPS))
        cur += (target - cur) * settle
        gaze[i] = cur
        lid[i] = min(1.0, abs(target - cur) / 0.03) * 0.05  # contracao de 5%

    # piscadas: 1,9-4,6 s, 180 ms, fechamento nos primeiros 45%, 18% duplas
    blink = np.zeros(n, dtype=np.float32)
    dur = max(5, int(round(0.18 * FPS)))
    close_f = max(2, int(round(dur * 0.45)))

    def envelope(s):
        if s < 0 or s >= dur:
            return 0.0
        if s < close_f:
            return (s + 1) / close_f
        return max(0.0, 1.0 - (s - close_f + 1) / (dur - close_f))

    t = rng.uniform(0.6, 1.9)
    while t < n / FPS:
        start = int(t * FPS)
        for k in range(dur):
            if start + k < n:
                blink[start + k] = max(blink[start + k], envelope(k))
        if rng.random() < 0.18:
            s2 = start + dur + 5
            for k in range(dur):
                if s2 + k < n:
                    blink[s2 + k] = max(blink[s2 + k], envelope(k))
        t += rng.uniform(1.9, 4.6)
    return tilt, gaze, lid, blink


_IDLE_TILT, _IDLE_GAZE, _IDLE_LID, _IDLE_BLINK = _build_idle()

_IDLE = True
_FRAME = 0
_SMOOTH = {"boca": 0.0, "olhar": 0.0, "sobrancelha": 0.0}
_SMOOTH_A = 1.0 - math.exp(-1.0 / (FPS * 0.03))  # ease-out ~90 ms, sem overshoot


def set_idle(enabled: bool = True) -> None:
    """Liga/desliga o idle deterministico e o easing (digitacao direta)."""
    global _IDLE
    _IDLE = bool(enabled)


def reset_state() -> None:
    """Reinicia contador, easing e fase do idle para uma sequencia reproduzivel."""
    global _FRAME
    _FRAME = 0
    for k in _SMOOTH:
        _SMOOTH[k] = 0.0


def set_frame(index: int) -> None:
    """Posiciona o contador de idle (util para o agente de animacao)."""
    global _FRAME
    _FRAME = max(0, int(index))


# ---------------------------------------------------------------------------
# Elementos dinamicos
# ---------------------------------------------------------------------------


def _feature_transform(deg):
    a = math.radians(deg)
    co, si = math.cos(a), math.sin(a)
    ox, oy = FEAT_BOX[0], FEAT_BOX[1]

    def T(x, y):
        dx, dy = x - HCX, y - HCY
        return (HCX + dx * co + dy * si - ox,
                HCY - dx * si + dy * co - oy)
    return T


def _stamp(T, center, size, draw_fn):
    """Desenha uma feicao num patch 3x justo; devolve (imagem, ox, oy) locais."""
    sw, sh = size
    ox = int(round(center[0] - sw / 2.0))
    oy = int(round(center[1] - sh / 2.0))
    p = Image.new("RGBA", (sw * SS, sh * SS), (0, 0, 0, 0))

    def TL(x, y):
        a, b = T(x, y)
        return (a - ox, b - oy)

    draw_fn(p, ImageDraw.Draw(p), TL)
    return p.reduce(SS), ox, oy


def _draw_face_features(deg, boca, olhar, piscar, sobrancelha, lid=0.0):
    """Devolve stamps RGBA pequenos ja rotacionados: [(imagem, ox, oy), ...]."""
    T = _feature_transform(deg)
    out = []

    # sobrancelhas: arco inteiro muda com sobrancelha
    def draw_brows(p, dp, TL):
        for side in (-1, 1):
            ix, ox = HCX + side * 30, HCX + side * 96
            iy = 118 + 16 * sobrancelha
            oy = 118 - 14 * sobrancelha
            my = (iy + oy) / 2.0 - 9 * (1.0 + sobrancelha)
            thick = 8 + 3 * sobrancelha
            upper = [(ix, iy - thick / 2), (HCX + side * 62, my - thick / 2 - 4),
                     (ox, oy - thick / 2)]
            lower = [(ox, oy + thick / 2), (HCX + side * 62, my + thick / 2 - 4),
                     (ix, iy + thick / 2)]
            _spoly(dp, upper + lower, OUT, None, closed=True, T=TL)
            _spoly(dp, [(ix - side * 2, iy - 2),
                        (HCX + side * 62, my - thick / 2 - 2),
                        (ox - side * 2, oy - 2)],
                   BROW_LIGHT, None, closed=False, T=TL, width=4)
        if sobrancelha < -0.15:
            width = (-sobrancelha - 0.15) * 6
            for x in (HCX - 12, HCX + 12):
                _spoly(dp, [(x, 112), (x - 2, 124), (x, 136)],
                       None, OUT_SOFT, 2.5 + width, closed=False, T=TL)

    out.append(_stamp(T, T(HCX, 120), BROW_STAMP_SIZE, draw_brows))

    # olhos: abertura interpolada, piscada instantanea, duplo highlight
    h = max(0.04, 1.0 - piscar - lid)

    def draw_eye(p, dp, TL, ex):
        if h > 0.14:
            eye = [(ex - 27, 161), (ex - 13, 161 - 18 * h),
                   (ex + 9, 161 - 19 * h), (ex + 27, 161),
                   (ex + 9, 161 + 14 * h), (ex - 13, 161 + 15 * h)]
            em = Image.new("L", _EYE_PX, 0)
            _spoly(ImageDraw.Draw(em), eye, 255, T=TL)
            p.paste(_EYE_STAMP, (0, 0), em)
            _spoly(dp, eye, None, OUT_SOFT, 1.8, T=TL)
            _spoly(dp, [(ex - 25, 160), (ex - 12, 161 - 17 * h),
                        (ex + 9, 161 - 18 * h), (ex + 25, 160)],
                   None, (60, 44, 48, 85), 3, closed=False, T=TL)

            px, py = ex + 10.5 * olhar, 161 + 1.5 * olhar
            cx, cy = TL(px, py)
            cx, cy = cx * SS, cy * SS
            rx, ry = 12.5 * SS, min(13.5, 15.0 * h) * SS
            dp.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=C["iris"])
            dp.ellipse((cx - rx * 0.72, cy - ry * 0.72,
                        cx + rx * 0.72, cy + ry * 0.72), fill=C["iris_claro"])
            dp.ellipse((cx - 6 * SS, cy - 7.5 * h * SS,
                        cx + 6 * SS, cy + 7.5 * h * SS), fill=C["pupila"])
            # highlight duplo: ponto grande difuso + ponto menor intenso
            dp.ellipse((cx - 5.5 * SS, cy - 8.5 * h * SS,
                        cx + 0.5 * SS, cy - 2.0 * h * SS), fill=(255, 255, 255, 165))
            dp.ellipse((cx + 3.5 * SS, cy + 2.5 * h * SS,
                        cx + 6.0 * SS, cy + 5.0 * h * SS), fill=(255, 255, 255, 230))
        else:
            lidc = [(ex - 27, 161), (ex - 14, 170), (ex, 173),
                    (ex + 14, 170), (ex + 27, 161)]
            _spoly(dp, lidc, None, OUT_SOFT, 4, closed=False, T=TL)
            _spoly(dp, [(ex - 20, 175), (ex, 178), (ex + 20, 175)],
                   None, C["pele_sombra"], 2, closed=False, T=TL)

    for ex in (HCX - 60, HCX + 60):
        out.append(_stamp(T, T(ex, 161), EYE_STAMP_SIZE,
                          lambda p, dp, TL, e=ex: draw_eye(p, dp, TL, e)))

    # boca: fechada -> semiaberta -> aberta com dente e lingua
    cx = HCX

    def draw_mouth(p, dp, TL):
        if boca < 0.10:
            dy, dm = -7 * sobrancelha, 2 * sobrancelha
            smile = [(cx - 35, 253 + dy), (cx - 18, 259 + dm),
                     (cx, 260 + dm), (cx + 18, 259 + dm), (cx + 35, 253 + dy)]
            _spoly(dp, smile, None, OUT_SOFT, 4, closed=False, T=TL)
            _spoly(dp, [(cx - 20, 268 + dm), (cx, 271 + dm), (cx + 20, 268 + dm)],
                   None, LIP_LIGHT, 2.5, closed=False, T=TL)
            return
        bw, bh = 33 + 7 * boca, 9 + 44 * boca
        top = 252 - 3 * boca
        cavity = [(cx - bw, top), (cx - bw * 0.7, top - 6),
                  (cx, top - 7), (cx + bw * 0.7, top - 6),
                  (cx + bw, top), (cx + bw * 0.92, top + bh * 0.55),
                  (cx + bw * 0.55, top + bh), (cx, top + bh + 5),
                  (cx - bw * 0.55, top + bh),
                  (cx - bw * 0.92, top + bh * 0.55)]
        cm = Image.new("L", _MOUTH_PX, 0)
        _spoly(ImageDraw.Draw(cm), cavity, 255, T=TL)
        cl = Image.new("RGBA", _MOUTH_PX, (0, 0, 0, 0))
        cl.paste(_MOUTH_STAMP, (0, 0), cm)
        cd = ImageDraw.Draw(cl)
        _spoly(cd, cavity, None, OUT_SOFT, 1.8, T=TL)
        if boca > 0.36:
            teeth = [(cx - bw * 0.78, top - 3), (cx, top - 5),
                     (cx + bw * 0.78, top - 3), (cx + bw * 0.7, top + 7),
                     (cx, top + 9), (cx - bw * 0.7, top + 7)]
            _spoly(cd, teeth, C["dente"], None, T=TL)
        if boca > 0.55:
            th = (boca - 0.55) / 0.45
            tongue = [(cx - 16 * th, top + bh - 3), (cx, top + bh - 9 * th),
                      (cx + 16 * th, top + bh - 3), (cx + 13 * th, top + bh + 2),
                      (cx, top + bh + 4), (cx - 13 * th, top + bh + 2)]
            _spoly(cd, tongue, C["lingua"], None, T=TL)
        p.alpha_composite(cl)
        _spoly(dp, [(cx - bw - 3, top - 1), (cx - 12, top - 11),
                    (cx, top - 5), (cx + 12, top - 11), (cx + bw + 3, top - 1)],
               None, LIP_LIGHT, 3, closed=False, T=TL)
        _spoly(dp, [(cx - bw, top + bh), (cx, top + bh + 9),
                    (cx + bw, top + bh)], None, LIP_LIGHT, 3, closed=False, T=TL)

    out.append(_stamp(T, T(cx, 268), MOUTH_STAMP_SIZE, draw_mouth))
    return out


def _make_hand():
    W, H = 112, 116
    w, h = W * SS, H * SS
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    palm = [(13, 58), (16, 40), (34, 29), (55, 32), (68, 46),
            (69, 68), (58, 87), (37, 93), (19, 81)]
    pm = Image.new("L", (w, h), 0)
    _spoly(ImageDraw.Draw(pm), palm, 255)
    pl = sphere_shade(pm, C["pele"], C["pele_clara"], C["pele_sombra"],
                      cx=0.30, cy=0.28, sss=C["sss"], sss_center=(0.35, 0.4),
                      sss_alpha=0.14)
    pd = ImageDraw.Draw(pl)
    _spoly(pd, palm, None, OUT_SOFT, 1.4)
    sh = Image.new("L", (w, h), 0)
    ImageDraw.Draw(sh).ellipse((int(24 * SS), int(62 * SS),
                                int(66 * SS), int(90 * SS)), fill=75)
    sh = ImageChops.multiply(sh.filter(ImageFilter.GaussianBlur(6 * SS)), pm)
    pl.alpha_composite(_tinted_mask(sh, C["sombra_pele"]))
    img.alpha_composite(pl)

    finger = _capsule(46, 7.5, C["pele_clara"], C["pele_sombra"])
    finger = finger.resize((finger.width * SS, finger.height * SS),
                           Image.Resampling.BILINEAR)
    fr = finger.rotate(45, resample=Image.Resampling.BILINEAR, expand=True)
    img.paste(fr, (int(52 * SS - fr.width / 2), int(22 * SS - fr.height / 2)), fr)
    thumb = _capsule(24, 6, C["pele_clara"], C["pele_sombra"])
    thumb = thumb.resize((thumb.width * SS, thumb.height * SS),
                         Image.Resampling.BILINEAR)
    tr = thumb.rotate(-48, resample=Image.Resampling.BILINEAR, expand=True)
    img.paste(tr, (int(20 * SS - tr.width / 2), int(44 * SS - tr.height / 2)), tr)
    return img.reduce(SS)


_HAND = _make_hand()


def _draw_arm(frame, braco):
    t = braco
    S = (742, 1255)
    E = (800 + 26 * t, 1452 - 128 * t)
    W = (858 + 88 * t, 1470 - 250 * t)
    tip = (W[0] + 34 + 24 * max(0.0, t), W[1] - 62 - 22 * max(0.0, t))

    upper = _capsule(max(10.0, math.dist(S, E)), 32,
                     C["camisa_claro"], C["camisa_sombra"])
    _paste_segment(frame, upper, S, E)
    fore = _capsule(max(10.0, math.dist(E, W)), 25,
                    C["pele_clara"], C["pele_sombra"], cuff=True)
    _paste_segment(frame, fore, E, W)

    fa = math.degrees(math.atan2(tip[1] - W[1], tip[0] - W[0]))
    hand = _HAND.rotate(-(fa - (-45.0)), resample=Image.Resampling.BILINEAR, expand=True)
    frame.paste(hand, (int(round(W[0] - 41)), int(round(W[1] - 60))), hand.getchannel("A"))


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


def render_frame(
    boca: float = 0.0,
    olhar: float = 0.0,
    piscar: float = 0.0,
    sobrancelha: float = 0.0,
    braco: float = 0.0,
    inclinar: float = 0.0,
) -> Image.Image:
    """Retorna um frame RGBA 1080x1920 transparente do apresentador.

    Parametros fora da faixa sao limitados: boca/piscar a [0,1] e os demais
    a [-1,1]. Nenhum arquivo e carregado durante a chamada.
    """
    global _FRAME

    boca = _clamp(boca, 0.0, 1.0)
    piscar = _clamp(piscar, 0.0, 1.0)
    olhar = _clamp(olhar)
    sobrancelha = _clamp(sobrancelha)
    braco = _clamp(braco)
    inclinar = _clamp(inclinar)

    idx = _FRAME % IDLE_FRAMES
    _FRAME += 1

    if _IDLE:
        # ease-out exponencial (~90 ms, sem overshoot)
        for key, target in (("boca", boca), ("olhar", olhar),
                            ("sobrancelha", sobrancelha)):
            _SMOOTH[key] += (target - _SMOOTH[key]) * _SMOOTH_A
        eff_boca = _SMOOTH["boca"]
        eff_olhar = max(-1.0, min(1.0, _SMOOTH["olhar"] + float(_IDLE_GAZE[idx])))
        eff_brow = _SMOOTH["sobrancelha"]
        eff_blink = max(piscar, float(_IDLE_BLINK[idx]))  # piscada instantanea
        eff_lid = float(_IDLE_LID[idx])
        eff_tilt = max(-1.0, min(1.0, inclinar + float(_IDLE_TILT[idx]) / MAX_TILT))
        breath = math.sin(2.0 * math.pi * (idx / FPS) / 3.4)
    else:
        eff_boca, eff_olhar, eff_brow = boca, olhar, sobrancelha
        eff_blink, eff_lid, eff_tilt, breath = piscar, 0.0, inclinar, 0.0

    # respiracao 1,2% ancorada na base do torso; cabeca sobe <= 2 px
    bk = int(round(breath * 4))
    torso = _TORSO_BREATH[bk]
    if bk == 0:
        tx, ty = TORSO_DEST
    else:
        tx = TORSO_DEST[0] - (torso.width - TORSO_W) // 2
        ty = TORSO_DEST[1] - (torso.height - TORSO_H)
    head_dy = int(round(-2.0 * breath))

    frame = _new_frame()
    frame.paste(_STATIC_FULL)
    frame.paste(torso, (tx, ty), _TORSO_MASK[bk])

    deg = int(round(eff_tilt * MAX_TILT))
    head = _HEAD_ROT[deg]
    frame.paste(head, (HEAD_DEST[0], HEAD_DEST[1] + head_dy), _HEAD_MASK[deg])
    frame.paste(_COLLAR, (TORSO_DEST[0], TORSO_DEST[1] + head_dy), _COLLAR_MASK)

    for feat, ox, oy in _draw_face_features(deg, eff_boca, eff_olhar,
                                            eff_blink, eff_brow, eff_lid):
        frame.paste(feat, (HEAD_DEST[0] + FEAT_BOX[0] + ox,
                           HEAD_DEST[1] + FEAT_BOX[1] + head_dy + oy),
                    feat.getchannel("A"))

    _draw_arm(frame, braco)
    return frame


# ---------------------------------------------------------------------------
# Assets de inspecao
# ---------------------------------------------------------------------------
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "presenter"


def _background_for_preview(size=CANVAS):
    w, h = size
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    arr[..., 0] = (9 + 9 * t).astype(np.uint8)
    arr[..., 1] = (16 + 15 * t).astype(np.uint8)
    arr[..., 2] = (31 + 28 * t).astype(np.uint8)
    arr[..., 3] = 255
    return Image.fromarray(arr, "RGBA")


def _save_assets():
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    set_idle(False)  # estados exatos, sem easing/idle

    preview = _background_for_preview()
    preview.alpha_composite(render_frame())
    preview.convert("RGB").save(ASSET_DIR / "preview.png", optimize=True)

    estados = [
        ({}, "neutro"),
        ({"boca": 0.85, "olhar": 0.2}, "falando"),
        ({"sobrancelha": -1.0, "boca": 0.06, "olhar": -0.25}, "preocupado"),
        ({"sobrancelha": 1.0, "boca": 0.35, "olhar": 0.15}, "entusiasmado"),
        ({"piscar": 1.0}, "piscando"),
        ({"braco": 1.0, "boca": 0.6, "sobrancelha": 0.8,
          "inclinar": 0.5}, "braco levantado"),
    ]
    tw, th = 360, 640
    grid = Image.new("RGB", (tw * 3, th * 2), (9, 15, 28))
    font = ImageFont.load_default()
    for idx, (kwargs, label) in enumerate(estados):
        cell = _background_for_preview((tw, th))
        cell.alpha_composite(render_frame(**kwargs).resize((tw, th), Image.Resampling.LANCZOS))
        cd = ImageDraw.Draw(cell, "RGBA")
        cd.rectangle((0, th - 34, tw, th), fill=(9, 15, 28, 255))
        cd.text((10, th - 25), label, fill=(230, 244, 255, 255), font=font)
        grid.paste(cell.convert("RGB"), ((idx % 3) * tw, (idx // 3) * th))
    grid.save(ASSET_DIR / "estados.png", optimize=True)

    manifest = {
        "description": DESCRIPTION,
        "palette": PALETA,
        "api": [
            "CANVAS = (1080, 1920)",
            "DESCRIPTION: str",
            "PALETA: dict",
            "render_frame(boca=0.0, olhar=0.0, piscar=0.0, sobrancelha=0.0, "
            "braco=0.0, inclinar=0.0) -> PIL.Image.Image (RGBA 1080x1920)",
            "aux: set_idle(enabled), reset_state(), set_frame(index)",
        ],
    }
    with open(ASSET_DIR / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    set_idle(True)
    reset_state()


if __name__ == "__main__":
    t0 = time.perf_counter()
    _save_assets()
    print("Assets gravados em:", ASSET_DIR)
    print("Tempo de geracao dos assets: %.1f ms" % ((time.perf_counter() - t0) * 1000))
    for _ in range(10):  # warm-up (caches de capsula/rotacao)
        render_frame(boca=0.7, olhar=0.3, braco=0.5, inclinar=0.2)
    n = 120
    t1 = time.perf_counter()
    for _ in range(n):
        render_frame(boca=0.7, olhar=0.3, braco=0.5, inclinar=0.2)
    print("Tempo medio por frame: %.2f ms (%d frames, apos warm-up)"
          % ((time.perf_counter() - t1) / n * 1000, n))
