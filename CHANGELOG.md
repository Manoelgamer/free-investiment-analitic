# Changelog

Todas as versões notáveis deste projeto são documentadas aqui. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [v1.6.7] — 2026-11-25

### Alterado
- Mapa de setores reescrito a partir da **classificação oficial Brapi/B3** (setor + subsetor), validada na web para casos como Klabin (Papel e Celulose), Braskem (Químicos/Petroquímicos) e Itaúsa (Financeiro).
- "Outros" caiu de ~1.250 ativos para 65; os subsetores oficiais passam a definir Bancos, Seguros, Siderurgia, Mineração, Papel, Utilidades, Química, TI, Saúde etc.
- Cache do universo versionado (`tm_asset_universe_v2`) para descartar classificações antigas salvas no navegador.
- Novos testes unitários para a classificação por subsetor.

## [v1.6.6] — 2026-11-25

### Corrigido
- Classificação setorial ampliada e corrigida: **KLBN11/KLBN3/KLBN4 agora em Papel**, CSNA3/GGBR4/USIM5/GOAU4 em Siderurgia, VALE3/CMIN3 em Mineração, BRKM5 em Química, ITSA4 em Finanças, EMBJ3 em Máquinas, além de ~120 tickers mapeados manualmente.
- Correções aplicadas também sobre o catálogo em cache, para que um `localStorage` antigo não mantenha setores errados.
- Novos testes unitários para os casos Klabin e Vale.

## [v1.6.5] — 2026-11-25

### Adicionado
- Prints das principais funcionalidades em `docs/screenshots/` (destaques, busca, mapa de setores, gráfico de ativo, carteira, calculadoras, comparador, alertas e painel Brapi), exibidos no `README.md`.
- Ajuste de enquadramento: páginas com cabeçalho e título visíveis, painéis centralizados com margem, carteira com cotações salvas e alertas com três exemplos preenchidos.

## [v1.6.4] — 2026-11-24

### Adicionado
- Períodos adicionais nos gráficos de ativos: **2A, 5A e 10A**, além de 1D, 5D, 1M, 6M e 1A.
- **MÁX agora cobre todo o período de existência do ativo**: o ano de listagem de cada ativo curado é usado para dimensionar a série e os rótulos do eixo (ex.: PETR4 desde 2000, MXRF11 desde 2013), com fallback para 2010 nos ativos vindos da Brapi. A legenda exibe "desde `ano`".
- Comparador de ativos também ganha os períodos 2A, 5A e 10A.

## [v1.6.3] — 2026-11-23

### Alterado
- Repositório renomeado no GitHub de `free-investiment-analitic` para **trade-radar** — nome curto, alinhado ao "radar de mercado" (mapa de setores, alertas e varredura da B3). Remote, links e `package.json` atualizados.

## [v1.6.2] — 2026-11-23

### Alterado
- Auditoria e enxugamento do repositório: de 23 para 19 arquivos. Removidos `.editorconfig`, `.gitattributes`, `backend/README.md` e `tests/check-version.js` (sem uso ou duplicados).
- Consolidação: checagem de versão incorporada ao `tests/smoke.js`; instruções do backend incorporadas ao `README.md`; `npm test` agora roda smoke + testes Python do backend.
- Corrigido teste de setores no smoke (aceita a lista dinâmica filtrada, não mais 24 fixos).

## [v1.6.1] — 2026-11-22

### Corrigido
- Página de detalhe aceita agora **todos os tickers exibidos no app**: ações, BDRs, ETFs, FIIs, cripto (ETH, BTC...), câmbio (USD/BRL...) e índices (IBOVESPA...). Antes esses cliques mostravam "Ativo não encontrado".
- Tickers desconhecidos tentam busca na Brapi (via backend ou direto) e exibem mensagem de erro clara, sem quebrar a navegação.
- Formatação de preços exibidos (`USDT 60.138,04`, `R$ 5,8889`, `166.376`) corrigida: cripto aparece em US$, índices na escala correta.
- Busca global e página `#/busca` incluem cripto, câmbio e índices nos resultados.

## [v1.6.0] — 2026-11-22

### Adicionado
- **Backend** em `backend/` (Python stdlib, sem dependências): `/api/health`, `/api/catalog`, `/api/catalog/summary`, `/api/validate`, `/api/coverage`, `/api/quotes`, `/api/recommendations` e `POST /api/refresh`. Cache em `data/`, CORS liberado e token Brapi opcional via variável de ambiente.
- `tests/test_backend.py` com 6 testes unitários; `backend/README.md` com instruções.
- Três agentes analisaram o catálogo e produziram listas prioritárias de **25 ações, 15 ETFs e 20 FIIs** ausentes da base curada, salvas em `backend/recommendations.json`.
- Campo de busca do topo virou **input com autocomplete real** (ativos, notícias, setores e páginas), navegação por setas/Enter e busca completa via `#/busca?q=...`.
- Frontend usa o backend automaticamente em `localhost` e faz fallback para a Brapi; autocomplete do modal de ativos consulta primeiro o catálogo local.

### Corrigido
- BDRs separados das ações (classe própria), duplicatas com sufixo `F` removidas e setores corrigidos por mapa manual (VALE3, CSNA3, GGBR4, USIM5, KLBN11, MXRF11 etc.).
- Preços da base curada passam a ser atualizados com a cotação da Brapi ao carregar o universo.

## [v1.5.0] — 2026-11-22

### Adicionado
- **Universo completo de ativos da B3**: carrega todos os tickers disponíveis na Brapi em duas requisições paginadas (~2.300 ativos, já com preço e variação) e funde com a base curada do projeto. Ações/BDRs, FIIs e ETFs passam a aparecer nas listas, busca, detalhe, alertas e comparador.
- Cache do catálogo no `localStorage` por 24 h e botão **⟳ Universo** nas páginas de mercado para forçar a atualização. Sem conexão, o app usa a base local.
- Comparador com campo de busca (60 primeiros resultados) para evitar listas enormes; simulador histórico e alertas limitam o seletor a ativos curados + 100 primeiros.
- Ativos vindos apenas da Brapi exibem aviso de que não possuem LPA/VPA e preços-alvo na base demonstrativa.

## [v1.4.5] — 2026-11-22

### Alterado
- Painel da chave Brapi redesenhado: cabeçalho com ícone de chave e *pill* de status, campo com ícone de cadeado e botão de visibilidade em SVG, cartão de status com estados (vazio/ok/erro/carregando), botões hierárquicos e nota de segurança com link para a Brapi.

## [v1.4.4] — 2026-11-22

### Corrigido
- O mapa de setores (home, página completa e busca) agora mostra apenas setores que possuem empresas/FIIs cadastrados na base. Setores vazios como Siderurgia, TI e Energia não aparecem mais.
- Cada bloco do mapa exibe a quantidade de ativos do setor; a página de detalhe e a busca usam a mesma lista filtrada.

## [v1.4.3] — 2026-11-22

### Alterado
- A cor do gráfico de ativos agora acompanha a **variação do período selecionado** (1D, 5D, 1M, 6M, 1A, MÁX), e não mais a variação do último dia: linha/área, candles, volume, fundo e etiqueta do último preço usam a tendência do período.
- Legenda e estatísticas passam a exibir explicitamente **“Var. período”** com o sinal e a cor correspondentes.
- Corrigido bloco duplicado no handler de cliques que impedia a execução do script em algumas situações.

## [v1.4.2] — 2026-11-22

### Alterado
- **Rebranding**: ícone original (gráfico de barras com linha de alta), identidade **Free Invest Analytic / FreeInvest** no cabeçalho, menu, título, manifesto PWA, service worker e nome dos arquivos exportados.
- Rodapé reescrito com licença MIT, link para o repositório e aviso explícito de que o projeto é open-source, independente e apenas inspirado no TradeMap.
- Páginas institucionais atualizadas: "Sobre", "Termos de Uso" e "Preferências de cookies" agora falam do projeto, não do clone.
- "TradeLetter" passou a se chamar **Carta Semanal** (as rotas antigas continuam funcionando).

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
