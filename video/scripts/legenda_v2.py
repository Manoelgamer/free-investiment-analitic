#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Legenda karaoke v2 - video vertical de investimentos.

MELHORIAS em relacao a v1:
  * Karaoke com HALO (GaussianBlur em camada separada) na palavra ativa #FFD23F.
  * Palavras ja ditas: branco alpha 150. Proximas: cinza claro.
  * Toast preto semitransparente com borda amarela sutil, y=1490..1680.
  * Quebra em PONTUACAO NATURAL (pausas de virgula/ponto) via programacao dinamica.
  * Fonte adaptativa (62px -> menor so quando necessario p/ caber 2 linhas sem cortar).
  * Desenho IDEMPOTENTE: restore da regiao antes de compor -> 100 chamadas no mesmo
    frame produzem exatamente o mesmo resultado de 1 chamada.

API publica (nomes mantidos da v1 para o animador importar):
    carregar_timings(caminho)                 -> dict
    construir_blocos(timings, max_palavras=7) -> list[dict]
    escrever_srt(blocos, caminho)             -> None
    desenhar_legenda(frame, bloco, t)         -> frame RGBA (MESMA imagem)
    desenhar_legenda_glow(frame, bloco, t)    -> frame RGBA (MESMA imagem, com halo)

Excecao documentada: o AVISO FINAL ("Conteudo educativo: nao e recomendacao de
investimento.") e mantido em UM unico bloco de 7 palavras, conforme solicitado.
Seu span natural e ~3,53s (audio termina em 61,704s). Para nao cortar o aviso,
esse bloco final pode ultrapassar o limite geral de 3,2s; nenhum outro bloco o faz.
"""

from __future__ import annotations

import json
import os
import unicodedata
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIMINGS_PATH = os.path.join(BASE_DIR, "build", "timings_v2.json")
SRT_PATH = os.path.join(BASE_DIR, "build", "legenda_v2.srt")

MAX_LINHAS = 2
DUR_MIN = 0.7
DUR_MAX = 3.2
SEP = 0.02                  # inicio do proximo = fim do anterior + SEP
SPAN_MAX_DP = 3.8           # permite o bloco final do aviso na DP
GAP_FRASE = 0.18            # pausa de virgula (palavras tem 0,20..0,27)
GAP_SENTENCA = 0.34         # pausa de ponto (0,386..0,474)

FONTE_TAMANHO = 62          # tamanho alvo (60-64px); reduzido so se necessario
FONTE_MIN = 48
MARGEM_X = 24
PAD_X, PAD_Y = 14, 12

AMARELO = (255, 210, 63, 255)          # #FFD23F - palavra ativa
AMARELO_HALO = (255, 210, 63, 255)
CINZA_CLARO = (205, 210, 215, 255)     # palavras proximas
BRANCO_FRANCO = (255, 255, 255, 150)   # palavras ja ditas
PRETO_CAIXA = (0, 0, 0, 150)           # toast semitransparente
BORDA_AMARELA = (255, 210, 63, 95)     # contorno sutil do toast
PRETO_CONTORNO = (0, 0, 0, 255)        # stroke do texto

REGIAO_X0, REGIAO_X1 = MARGEM_X, 1080 - MARGEM_X
REGIAO_Y0, REGIAO_Y1 = 1490, 1680

AVISO_CHAVES = ("conteudo", "recomendacao", "investimento")
LIGADORES = {"e", "em", "de", "do", "da", "por", "na", "no", "a", "o",
             "os", "as", "com", "um", "uma", "que", "vírgula"}

# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def carregar_timings(caminho: str) -> dict:
    """Carrega o JSON de timings v2 (palavras com texto/inicio/fim)."""
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def construir_blocos(timings: dict, max_palavras: int = 7) -> list[dict]:
    """
    Agrupa palavras em blocos de ate `max_palavras` e 2 linhas, preferindo
    cortes em pausas naturais (virgula/ponto) e evitando cortes no meio de
    frases numericas ("... cinco virgula tres por cento").

    Cada bloco: {"texto", "inicio", "fim",
                 "palavras": [{"texto","inicio","fim"}, ...]}
    """
    todas = timings["palavras"]
    if not todas:
        return []

    # --- 1) isola o aviso final como UM bloco obrigatorio -------------------
    palavras = todas
    aviso: list[dict] | None = None
    for k in range(max(0, len(todas) - max_palavras), len(todas)):
        cand = todas[k:]
        if len(cand) <= max_palavras and _eh_aviso(cand):
            palavras = todas[:k]
            aviso = cand
            break

    # --- 2) particao otima por programacao dinamica -------------------------
    grupos: list[list[dict]] = []
    if palavras:
        n = len(palavras)
        gap_depois = [
            (palavras[i + 1]["inicio"] - palavras[i]["fim"]) if i + 1 < n else 0.6
            for i in range(n)
        ]
        gap_antes = [
            (palavras[i]["inicio"] - palavras[i - 1]["fim"]) if i > 0 else 0.6
            for i in range(n)
        ]
        infinito = float("inf")
        custo = [infinito] * (n + 1)
        escolha = [-1] * (n + 1)
        custo[n] = 0.0
        for i in range(n - 1, -1, -1):
            for j in range(i, min(i + max_palavras, n)):
                # quebra de SENTENCA dentro do grupo: nunca atravessar
                if any(gap_depois[k] >= GAP_SENTENCA for k in range(i, j)):
                    continue
                span = float(palavras[j]["fim"]) - float(palavras[i]["inicio"])
                if span > SPAN_MAX_DP:
                    continue
                proxima = palavras[j + 1]["texto"] if j + 1 < n else None
                c = _custo_grupo(palavras[i:j + 1], span, gap_depois[j],
                                 gap_antes[i], proxima)
                total = c + custo[j + 1]
                if total < custo[i]:
                    custo[i] = total
                    escolha[i] = j
        i = 0
        while i < n:
            j = escolha[i]
            if j < i:
                j = i
            grupos.append(palavras[i:j + 1])
            i = j + 1
    if aviso:
        # o roteiro traz "Conteúdo educativo: ... investimento."; o TTS nao
        # cola essa pontuacao nas palavras, entao anexamos aqui (fidelidade).
        aviso = [dict(p) for p in aviso]
        for p in aviso:
            limpo = p["texto"].lower().strip(".,?!:;")
            if limpo == "educativo":
                p["texto"] = "educativo:"
            elif limpo == "investimento":
                p["texto"] = "investimento."
        grupos.append(aviso)

    # --- 3) tempos: inicio[i] = fim[i-1] + SEP (exato) ----------------------
    # 1a passada: define os inicios de modo que cada bloco (exceto o ultimo)
    # tenha duracao entre DUR_MIN e DUR_MAX ate o inicio do proximo.
    inicios: list[float] = []
    for idx, grupo in enumerate(grupos):
        ini = float(grupo[0]["inicio"])
        if idx + 1 < len(grupos):
            prox_ini = float(grupos[idx + 1][0]["inicio"])
            janela = prox_ini - SEP - ini
            if janela < DUR_MIN:
                ini = prox_ini - SEP - DUR_MIN   # antecipa um pouco o inicio
            elif janela > DUR_MAX:
                ini = prox_ini - SEP - DUR_MAX   # atrasa para nao exceder 3,2s
        inicios.append(max(0.0, ini))

    # 2a passada: fim exato = inicio do proximo - SEP (garante a regra).
    blocos: list[dict] = []
    for idx, grupo in enumerate(grupos):
        ini = inicios[idx]
        if idx + 1 < len(grupos):
            fim = inicios[idx + 1] - SEP
        else:
            fim = float(grupo[-1]["fim"])
            if fim - ini < DUR_MIN:
                ini = max(0.0, fim - DUR_MIN)
                inicios[idx] = ini
        blocos.append({
            "texto": " ".join(p["texto"] for p in grupo),
            "inicio": round(ini, 3),
            "fim": round(fim, 3),
            "palavras": [
                {"texto": p["texto"], "inicio": float(p["inicio"]),
                 "fim": float(p["fim"])}
                for p in grupo
            ],
        })
        cursor = fim + SEP

    return blocos


def escrever_srt(blocos: list[dict], caminho: str) -> None:
    """SRT padrao (sem HTML), numerado a partir de 1, com ate 2 linhas."""
    linhas: list[str] = []
    for numero, bloco in enumerate(blocos, start=1):
        ini = _fmt_srt(bloco["inicio"])
        fim = _fmt_srt(bloco["fim"])
        texto = "\n".join(" ".join(p["texto"] for p in linha)
                          for linha in _dividir_linhas(bloco["palavras"]))
        linhas.extend([str(numero), f"{ini} --> {fim}", texto, ""])
    diretorio = os.path.dirname(caminho)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))


def desenhar_legenda(frame, bloco: dict, t: float):
    """Desenha o karaoke SEM halo. Retorna a MESMA imagem RGBA modificada."""
    return _desenhar(frame, bloco, t, com_glow=False)


def desenhar_legenda_glow(frame, bloco: dict, t: float):
    """Desenha o karaoke COM halo suave na palavra ativa. Retorna a MESMA imagem."""
    return _desenhar(frame, bloco, t, com_glow=True)


# ---------------------------------------------------------------------------
# Desenho
# ---------------------------------------------------------------------------
def _desenhar(frame, bloco: dict, t: float, com_glow: bool):
    if frame.mode != "RGBA":
        raise ValueError("frame deve ser RGBA")

    largura, altura = frame.size
    linhas, fonte, tamanho = _preparar_texto(bloco, largura)
    espaco = fonte.getlength(" ")
    altura_linha = int(tamanho * 1.18)

    larguras = [
        sum(fonte.getlength(p["texto"]) for p in linha)
        + espaco * max(0, len(linha) - 1)
        for linha in linhas
    ]
    conteudo_w = max(larguras) if larguras else 0.0

    box_w = min(largura - 2 * MARGEM_X, int(conteudo_w) + 2 * PAD_X + 8)
    box_w = max(box_w, 120)
    box_h = min(altura_linha * len(linhas) + 2 * PAD_Y, REGIAO_Y1 - REGIAO_Y0)
    box_x0 = max(0, (largura - box_w) // 2)
    faixa = max(1, REGIAO_Y1 - REGIAO_Y0)
    box_y0 = REGIAO_Y0 + max(0, (faixa - box_h) // 2)
    box_y0 = max(0, min(box_y0, altura - box_h))
    caixa = (box_x0, box_y0, box_x0 + box_w, box_y0 + box_h)

    # --- idempotencia: restaura o que havia na regiao antes do ultimo desenho
    estado = getattr(frame, "_legenda_estado_v2", None)
    if estado is None:
        backup = frame.crop(caixa)
    else:
        antiga_caixa, antigo_backup = estado
        frame.paste(antigo_backup, (antiga_caixa[0], antiga_caixa[1]))
        backup = frame.crop(caixa)
    frame._legenda_estado_v2 = (caixa, backup)

    overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        (0, 0, box_w - 1, box_h - 1), radius=16,
        fill=PRETO_CAIXA, outline=BORDA_AMARELA, width=2,
    )

    # posicoes e cores de cada palavra
    posicoes: list[tuple[float, float, dict, tuple[int, int, int, int]]] = []
    y = float(PAD_Y)
    for linha, largura_linha in zip(linhas, larguras):
        x = (box_w - largura_linha) / 2.0
        for palavra in linha:
            if palavra["inicio"] <= t <= palavra["fim"]:
                cor = AMARELO
            elif t > palavra["fim"]:
                cor = BRANCO_FRANCO
            else:
                cor = CINZA_CLARO
            posicoes.append((x, y, palavra, cor))
            x += fonte.getlength(palavra["texto"]) + espaco
        y += altura_linha

    # --- halo: camada separada, so com as palavras ativas -------------------
    if com_glow and any(cor == AMARELO for _, _, _, cor in posicoes):
        halo = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        for x, y, palavra, cor in posicoes:
            if cor == AMARELO:
                hd.text((x, y), palavra["texto"], font=fonte, fill=AMARELO_HALO)
        largo = halo.filter(ImageFilter.GaussianBlur(16))
        curto = halo.filter(ImageFilter.GaussianBlur(7))
        overlay = Image.alpha_composite(overlay, largo)
        overlay = Image.alpha_composite(overlay, curto)
        draw = ImageDraw.Draw(overlay)

    # --- texto nitido com contorno escuro -----------------------------------
    for x, y, palavra, cor in posicoes:
        draw.text(
            (x, y), palavra["texto"], font=fonte, fill=cor,
            stroke_width=3, stroke_fill=PRETO_CONTORNO,
        )

    frame.alpha_composite(overlay, dest=(box_x0, box_y0))
    return frame


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _eh_aviso(palavras: list[dict]) -> bool:
    texto = " ".join(p["texto"] for p in palavras).lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    norm = "".join(c for c in texto if c.isalnum() or c.isspace())
    return all(chave in norm for chave in AVISO_CHAVES)


def _custo_grupo(grupo: list[dict], span: float, gap_fim: float,
                 gap_ini: float, proxima: str | None = None) -> float:
    """Custo baixo = bom ponto de quebra (pontuacao natural, 4-6 palavras)."""
    n = len(grupo)
    c = 0.0
    if n <= 2:
        c += 2.2
    elif n == 3:
        c += 0.8
    elif n >= 7:
        c += 0.25

    if span < DUR_MIN:
        c += (DUR_MIN - span) * 2.0
    if span > 2.9:
        c += (span - 2.9) * 4.0

    if gap_fim >= GAP_SENTENCA:
        c -= 1.30                      # ponto / fim de segmento
    elif gap_fim >= GAP_FRASE:
        c -= 0.85                      # virgula
    elif gap_fim < 0.06:
        c += 0.75                      # corte no meio da frase (ruim)

    if grupo[-1]["texto"][-1:] in ".,?!:;":
        c -= 0.35                      # pontuacao colada na palavra

    # nao termine bloco em palavra ligadora ("... cinco vírgula" / "... trinta e")
    ultima = grupo[-1]["texto"].lower().strip(".,?!:;")
    if ultima == "vírgula":
        c += 2.5
    elif ultima in LIGADORES:
        c += 1.3
    if proxima and proxima.lower() == "e" and gap_fim < 0.06:
        c += 1.0                       # mantem "vinte e seis" no mesmo bloco

    if gap_ini >= GAP_FRASE:
        c -= 0.25
    elif gap_ini < 0.06 and n > 1:
        c += 0.25
    return c


def _dividir_linhas(palavras: list[dict], fonte=None) -> list[list[dict]]:
    """Ate 2 linhas, quebrando so entre palavras e equilibrando larguras."""
    if not palavras:
        return [[]]
    if len(palavras) <= 3:
        return [list(palavras)]
    if fonte is None:
        fonte = _obter_fonte(FONTE_TAMANHO)
    esp = fonte.getlength(" ")
    melhor = None
    melhor_score = float("inf")
    for k in range(1, len(palavras)):
        a = sum(fonte.getlength(p["texto"]) for p in palavras[:k]) + esp * (k - 1)
        b = sum(fonte.getlength(p["texto"]) for p in palavras[k:]) + esp * (len(palavras) - k - 1)
        score = max(a, b) + 0.01 * abs(a - b)
        if score < melhor_score:
            melhor_score = score
            melhor = k
    return [list(palavras[:melhor]), list(palavras[melhor:])]


def _preparar_texto(bloco: dict, largura_frame: int):
    """Escolhe o maior tamanho de fonte que caiba em 2 linhas sem cortar."""
    palavras = bloco["palavras"]
    for tamanho in range(FONTE_TAMANHO, FONTE_MIN - 1, -1):
        fonte = _obter_fonte(tamanho)
        linhas = _dividir_linhas(palavras, fonte)
        esp = fonte.getlength(" ")
        maior = max(
            (sum(fonte.getlength(p["texto"]) for p in linha)
             + esp * max(0, len(linha) - 1)) for linha in linhas
        )
        disponivel = largura_frame - 2 * MARGEM_X - 2 * PAD_X - 8
        if maior <= disponivel and len(linhas) <= MAX_LINHAS:
            return linhas, fonte, tamanho
    fonte = _obter_fonte(FONTE_MIN)
    return _dividir_linhas(palavras, fonte), fonte, FONTE_MIN


def _fmt_srt(segundos: float) -> str:
    ms = int(round(segundos * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


_FONTES: dict[int, Any] = {}


def _obter_fonte(tamanho: int):
    if tamanho in _FONTES:
        return _FONTES[tamanho]
    candidatos = [
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ]
    for caminho in candidatos:
        try:
            _FONTES[tamanho] = ImageFont.truetype(caminho, tamanho)
            return _FONTES[tamanho]
        except OSError:
            continue
    try:
        _FONTES[tamanho] = ImageFont.load_default().font_variant(size=tamanho)
    except Exception:
        _FONTES[tamanho] = ImageFont.load_default()
    return _FONTES[tamanho]


# ---------------------------------------------------------------------------
# Execucao standalone
# ---------------------------------------------------------------------------
def _validar(blocos: list[dict], timings: dict) -> None:
    assert blocos, "nenhum bloco gerado"
    anterior_fim = None
    for i, b in enumerate(blocos):
        assert 0 < len(b["palavras"]) <= 7, f"bloco {i}: word count"
        assert len(_dividir_linhas(b["palavras"])) <= 2, f"bloco {i}: linhas"
        dur = b["fim"] - b["inicio"]
        assert dur >= DUR_MIN - 0.06, f"bloco {i}: duracao minima ({dur:.2f})"
        if anterior_fim is not None:
            assert b["inicio"] >= anterior_fim - 1e-6, f"bloco {i}: sobreposicao"
        anterior_fim = b["fim"]
        if i < len(blocos) - 1:
            assert dur <= DUR_MAX + 0.06, f"bloco {i}: duracao maxima ({dur:.2f})"
    assert blocos[-1]["fim"] < 63.0, "ultimo timestamp >= 63s"
    assert _eh_aviso(blocos[-1]["palavras"]), "aviso final nao esta no ultimo bloco"


if __name__ == "__main__":
    timings = carregar_timings(TIMINGS_PATH)
    blocos = construir_blocos(timings, max_palavras=7)
    _validar(blocos, timings)
    escrever_srt(blocos, SRT_PATH)
    print(f"OK: {len(blocos)} blocos -> {SRT_PATH}")
    print(f"ultimo timestamp: {blocos[-1]['fim']:.3f}s (limite 63s)")
    print(f"aviso final: '{blocos[-1]['texto']}'")
