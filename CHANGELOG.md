# Changelog

Todas as versões notáveis deste projeto são documentadas aqui. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [v1.4.1] — 2026-11-22

### Adicionado
- Mini-gráficos dos destaques agora são exploráveis: clique ou `Enter` seleciona uma barra e abre um painel com dados completos (cotação, justo, alvo, recomendação), `←`/`→` navegam entre as barras, duplo clique abre a página do ativo e o tooltip explica os atalhos.
- Indicador visual “dinâmico” com pulso no mini-gráfico; ao atualizar cotações ao vivo, os quatro destaques são recalculados e o slide atual é preservado.

## [v1.4.0] — 2026-11-22

### Adicionado
- **Alertas de preço** (`#/alertas`): cadastro de alvo por ativo (acima/abaixo), verificação com cotação ao vivo/cache/ilustrativa, sino com contador no cabeçalho e atalho na página do ativo. Persistência em `localStorage`.
- **Indicadores técnicos** no gráfico: MM20, Bandas de Bollinger (20,2) e RSI(14), com painel dedicado do RSI e alternância independente por botão.
- ETFs incluídos no menu lateral e rotas adicionais cobertas pelo smoke test.

### Corrigido
- Botão “Ver carteira” começava com o rótulo invertido em relação ao estado da tabela.
- Filtro por letra (A a Z) e exportação CSV ignoravam a seleção ativa.
- Erro de inicialização ao abrir o app diretamente em rotas de tabela (`currencyPairs` acessado antes da declaração).
- Data dos rótulos do gráfico era fixa em nov/2026; agora acompanha a data atual.
- `valuation()` retornava `null` para FIIs com VPA, causando inconsistência entre páginas.
- Linha duplicada de Dólar PTAX na tabela de câmbio ao vivo.

### Alterado
- Organização do repositório: ícone e mídia movidos para `assets/`; vídeos e legenda referenciados a partir de `assets/videos/`.
- Legenda `legenda-dolar-b3.srt` agora associada ao player via `<track kind="subtitles">`.
- Removidos `trademap-clone.html` e o diretório `versions/`: as tags Git (`v1.0.0` … `v1.3.0`) já guardam o histórico e permitem recuperar qualquer versão com `git show vX.Y.Z:index.html`.
- `sw.js` e `manifest.json` atualizados para o novo caminho do ícone.

### Adicionado
- Slide **Players do mercado** recalculado: maiores descontos segundo o preço-alvo de cada casa (BTG, XP, Itaú BBA etc.), com cotação atual, alvo, potencial e recomendação. Novo slide **Casas de análise** com o ranking agregado de alvos e compras.
- Mini-gráficos do carrossel interativos: tooltip com casa/ativo, valor e link, clique e `Enter` levam à página do ativo; barras dos clones marcadas como inertes.
- Carrossel de destaques reescrito: loop infinito com slides clonados, autoplay de 6s com indicador de progresso, arrasto/swipe por Pointer Events (mouse e toque), snap com limite de distância, pausa no hover/foco/aba oculta, navegação por teclado e dica de arrasto no mobile. Fallback por timer garante o loop mesmo quando `transitionend` não é disparado.
- `tests/check-version.js` e `npm test` agora validam a consistência da versão entre `package.json`, `sw.js`, `README.md` e `CHANGELOG.md`.
- `.gitignore` cobre o projeto auxiliar `chat-qr/` e o vídeo estendido de 28 MB.

## [v1.3.0] — 2026-11-22

### Adicionado
- **Destaques do mercado:** o carrossel da página inicial agora é gerado pelos dados — maiores quedas do dia, ações com maior desconto pela fórmula de Graham e *players* do mercado (casas de análise com mais preços-alvo), cada um com mini-gráfico de barras e atalhos para as páginas relacionadas.
- **Painel “Chave da Brapi”:** local explícito na coluna direita para colar, testar, salvar, mostrar/ocultar e limpar a chave. O botão ⚙ da carteira agora leva ao painel.
- **Câmbio ao vivo:** integração com `/api/v2/currency` (PTAX do Banco Central) para USD-BRL, EUR-BRL e GBP-BRL quando há chave. Os valores atualizam a tabela de câmbio, o ticker e o cartão do dólar; sem chave ou em caso de falha, os dados ilustrativos permanecem e o status explica o motivo.

### Alterado
- Lista de tickers gratuitos ajustada para os quatro atuais (`PETR4`, `VALE3`, `ITUB4`, `MGLU3`) — `MXRF11` e `HGLG11` agora exigem chave.
- Mensagens de erro sobre autenticação passam a apontar para o novo painel.
- Smoke test cobre o painel da chave, os três destaques e o fluxo de câmbio ao vivo (com resposta simulada da Brapi).

## [v1.2.0] — 2026-11-22

### Adicionado
- **Cotações ao vivo:** botão “⟳ Cotações ao vivo” nas listas de ativos e “Atualizar cotação” na página do ativo. Consulta a Brapi com o token configurado e mescla os resultados aos dados ilustrativos; se falhar, mantém os dados locais e avisa o usuário.
- **Exportação CSV:** botão “CSV ⬇” nas tabelas de mercado, respeitando o filtro atual.
- **PWA:** `manifest.json`, ícone SVG e service worker com cache offline para o app. Chamadas externas (Brapi) nunca são interceptadas.

### Alterado
- Valuation e potencial nas tabelas agora usam a cotação ao vivo quando disponível.
- Descrição e ícone da página adicionados ao `<head>`.

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
