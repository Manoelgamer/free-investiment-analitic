# Pipeline de vídeo vertical — Investimentos

Gera um vídeo vertical de ~60s (1080×1920, 30fps) com apresentador 2D cartoon,
voz em pt-BR (`pt-BR-AntonioNeural`), gráficos de mercado e legenda karaoke.

## Agentes envolvidos

Definições em `.opencode/agents/`:

| Agente | Modo | Entregável |
|---|---|---|
| `video-orquestrador` | primary |Coordena tudo e valida o MP4 final |
| `video-pesquisador` | subagent | `data/pesquisa.md` — dados reais de sexta + técnicas de vídeos semelhantes |
| `video-roteirista` | subagent | `data/roteiro.json` — falas, tempos e direções visuais |
| `video-apresentador` | subagent | `scripts/presenter.py` + `assets/presenter/*.png` |
| `video-voz` | subagent | `build/voz.mp3` + `build/timings.json` |
| `video-legenda` | subagent | `scripts/legenda.py` + `build/legenda.srt` |
| `video-animacao` | subagent | `scripts/video.py` + `build/final.mp4` |

## Como usar

No OpenCode, selecione o agente orquestrador com **Shift+Tab** (ou `/agents`) e peça:

```text
Rode o pipeline de vídeo vertical de investimentos.
```

Ou acione especialistas diretamente:

```text
Use o subagente video-pesquisador para atualizar os dados de mercado.
Use o subagente video-voz para regenerar a narração com outro ritmo.
```

## Ordem de dependências

```
Fase 1 (paralelo)   pesquisa.md  +  apresentador
Fase 2              roteiro.json      (depende de pesquisa.md)
Fase 3              voz.mp3/timings.json  →  legenda.srt
Fase 4              final.mp4             (depende de tudo)
```

## Estrutura

```
video/
├── data/          pesquisa.md, roteiro.json
├── scripts/       presenter.py, voz.py, legenda.py, video.py
├── assets/        presenter/ (preview, estados, manifest)
└── build/         voz.mp3, voz.vtt, timings.json, legenda.srt, final.mp4, qc_*.png
```

## Stack

Python 3.12 + Pillow, moviepy, numpy, edge-tts, ffmpeg/ffprobe. Sem Node.js.

## Conteúdo educativo

O roteiro evita promessas de retorno e inclui o aviso:
**"Conteúdo educativo. Não é recomendação de investimento."**

Se algum número de mercado não for confirmado na pesquisa, ele é marcado como
`ILUSTRATIVO` e o vídeo exibe o aviso correspondente.
