# Audio Notes — v2 (voz + trilha + SFX)

## Entrada e voz

- Roteiro: `data/roteiro_v2.json` (texto novo, menos técnico e mais envolvente). Falas NÃO alteradas.
- Voz mantida: `pt-BR-AntonioNeural` (exigência do usuário; não houve troca por outra voz).
- Pitch `-1Hz` pelo parâmetro da API (ponto de partida; faixa segura -1 a -10 Hz) + `boundary="WordBoundary"`.
- Plano SSML (documentado em `voz_v2.py`): `.` 350 ms, `,` 150 ms, `;` 250 ms, `<break time="300ms"/>` entre blocos, `<say-as interpret-as="currency">` no dólar, `<emphasis>` por bloco. **Limitação técnica:** o edge-tts 7.3.1 instalado escapa SSML no construtor e o endpoint rejeita tags injetadas (testado). As pausas foram aplicadas como silêncio amostrado exato, equivalente ao `<break/>`; o valor do dólar já vem por extenso no roteiro, então a leitura permanece correta sem o `say-as`.
- Palavras mapeadas por bloco/segmento, concatenadas com ffmpeg; silêncio residual do TTS aparado nas bordas dos blocos.

### Benchmark de rate (3 velocidades do gancho)

| rate | gancho (s) | resultado |
|---|---|---|
| +2% | 7.158 | **escolhido** |
| +4% | 7.053 | OK |
| +5% | 6.975 | OK |

- Escolhido: **+2%**. Critério: ponto de partida recomendado (+2%), mantido se a duração final ficar em 50–66 s; caso contrário, a velocidade seguinte é testada. Sem acelerar para esconder texto; pitch -1 Hz dá leve autoridade sem distorcer.

### Cadeia de processamento

- `highpass=f=80` → corte 3 dB @ 400 Hz → presença +2,2 dB @ 4,5 kHz → `acompressor=threshold=-18dB:ratio=3:attack=10:release=200` → `loudnorm` em **duas passos** com `linear=true` e `aresample=48000`, alvo `I=-14:TP=-1.5:LRA=11`.
- De-ess condicional (5–9 kHz) não aplicado: sibilância dentro do normal. Sem reverb na voz.
- Medição da voz (passo 1): I=-24.55 LUFS, TP=-7.55 dBTP, LRA=1.50, normalization_type=dynamic.
- voz_v2.mp3: **61.571 s** · voz processada: 61.539 s · palavras: 159 · segmentos: 7

## Trilha ambiental (procedural, sem download)

- Senos 55 / 82,5 / 110 Hz com desvio ±0,3 Hz, LFO 0,07 Hz, lowpass 500 Hz; entra ~3 s depois do início da fala (crossfade de 1,5 s), permanece no encerramento, fade-out de 1 s.
- Medida bruta: -12.63 LUFS → ganho -17.37 dB → alvo -30 dBFS/LUFS (≈-30 dBFS RMS, ~16 dB abaixo da voz).
- Ducking: `sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300` com a voz como sidechain (trilha e SFX).

## SFX procedurais (sem download)

Total de eventos: **15** (1 hit, 2 riser, 5 tick, 7 whoosh).

| tipo | tempo (s) | posição / motivo |
|---|---|---|
| whoosh | 0.000 | troca — início segmento 1 |
| whoosh | 7.158 | troca — início segmento 2 |
| riser | 8.588 | 1,4s antes de revelação Ibovespa |
| whoosh | 15.491 | troca — início segmento 3 |
| tick | 17.469 | contador segmento 3 ('dezenove') |
| tick | 19.503 | contador segmento 3 ('zero') |
| tick | 20.263 | contador segmento 3 ('sessenta') |
| whoosh | 23.693 | troca — início segmento 4 |
| riser | 25.128 | 1,4s antes de revelação VIX |
| hit | 31.343 | ápice 'ninguém queria arriscar' |
| whoosh | 32.967 | troca — início segmento 5 |
| tick | 33.636 | contador segmento 5 ('dezenove') |
| tick | 35.535 | contador segmento 5 ('cinco') |
| whoosh | 42.057 | troca — início segmento 6 |
| whoosh | 52.872 | troca — início segmento 7 |

- whoosh: ruído branco, bandpass varrido 400 Hz → 4 kHz em 0,4 s, envelope `sin(pi t/T)^1,5`.
- tick: rajada de 12 ms, highpass 1 kHz, decaimento `exp(-t/3ms)`, pico -6 dBFS (5 ticks: 3 no Ibovespa e 2 no dólar).
- riser: ruído em bandpass 200 Hz → 4 kHz em 1,4 s, amplitude `0,2*(t/T)^2`, fade abrupto + thump 60 Hz/0,15 s antes das revelações de Ibovespa e VIX.
- hit: tom 60 Hz/0,15 s no ápice do medo (seg. 4).

## Mix final

- `asplit` da voz → `sidechaincompress` em trilha/SFX → `amix` → `loudnorm` duas passos (`linear=true`, `aresample=48000`).
- Medição do mix bruto (passo 1): I=-14.16 LUFS, TP=-1.35 dBTP, tipo=dynamic.
- AAC 48 kHz, 192 kbps, mono.
- audio_final.m4a: **62.800 s** (voz + 1.2 s de encerramento).
- Re-medição final: LUFS integrado **-14.0 LUFS** (ebur128) / -14.02 LUFS (loudnorm), true peak **-1.41 dBTP**, LRA 2.10, normalização dynamic (pico ebur128: -1.4 dBFS).
- Check final: -16 ≤ I ≤ -12 LUFS e TP ≤ -1 dBTP.

## Arquivos

- `build/voz_v2.mp3`
- `build/voz_v2_proc.wav`
- `build/timings_v2.json`
- `build/voz_v2.vtt`
- `build/trilha.wav`
- `build/sfx.wav`
- `build/audio_final.m4a`
- `build/audio_notes.md`
