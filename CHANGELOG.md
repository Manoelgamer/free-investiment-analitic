# Changelog

Todas as versões notáveis deste projeto são documentadas aqui. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [v1.1.0] — 2026-11-22

### Corrigido
- **Gráficos:** o crosshair acumulava transformações de escala no canvas a cada movimento do mouse, deformando o gráfico. Handlers agora são registrados uma única vez e leem o estado mais recente.
- **Vídeos:** quando o arquivo de vídeo não existe, a página exibia um player preto. Agora há um fallback visual informativo.
- **Carteira:** remoção de ativo pela linha da tabela agora pede confirmação e também limpa o cache de cotação.

### Adicionado
- **Acessibilidade:** link “pular para o conteúdo”, `:focus-visible`, suporte a `prefers-reduced-motion`, `aria-live` no status da carteira, foco no menu/fechamento de modais com `Escape` e navegação do carrossel pelas setas do teclado.
- **Carteira:** exportação e importação em JSON (token Brapi deliberadamente não exportado).
- **Qualidade:** smoke test automatizado cobrindo todas as rotas (`npm test`, requer `npm install`).
- `<noscript>` para navegadores sem JavaScript.

### Alterado
- Redimensionamento da janela com debounce para redesenhar gráficos com menos trabalho.

## [v1.0.0] — 2026-11-22

### Adicionado
- Versão inicial: clone demonstrativo do TradeMap em arquivo único (`trademap-clone.html`).
- Ticker, mapa de setores, indicadores macro, notícias, TradeLetter, Academy, vídeos e páginas institucionais.
- Carteira com Brapi, autocomplete de tickers, donut de alocação e persistência local.
- Calculadoras, simulador histórico e comparador de ativos com gráficos.
- Layout responsivo para desktop, tablet e celular.
