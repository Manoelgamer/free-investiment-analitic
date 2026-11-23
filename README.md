# Free Invest Analytic

Projeto **open-source** e educacional **inspirado no TradeMap**, criado para ajudar quem quer acompanhar investimentos. É uma aplicação **100% front-end** (HTML + CSS + JavaScript puro), sem build e sem dependências.

> Não somos afiliados ao TradeMap nem à Valemobi. O nome e o visual do projeto original foram usados apenas como referência de estudo; todos os dados de mercado, notícias e recomendações aqui são ilustrativos.

## Propósito

Este projeto nasceu como **estudo e ferramenta educacional**. A ideia é simples: **qualquer pessoa pode copiar, usar, modificar e melhorar** — seja para aprender, para montar seu próprio painel de investimentos ou para adicionar funcionalidades novas.

Não é um produto comercial, não há cadastro e não há servidor próprio. Se você achou algo que pode ficar melhor, **faça um fork**, experimente e mande um pull request (ou abra uma issue com a sugestão). Não existe “jeito certo” de contribuir: correção de bug, ajuste de acessibilidade, novo gráfico, texto mais claro e tradução são igualmente bem-vindos.

O projeto é distribuído sob a licença [MIT](LICENSE): use, copie, altere e compartilhe, inclusive em projetos fechados, mantendo o aviso de copyright.

> **Aviso:** o conteúdo é apenas demonstrativo e educacional. Nada aqui é recomendação de investimento. Dados ilustrativos e cotações com atraso não devem orientar decisões reais.

## Como abrir

Basta abrir `index.html` no navegador. Também é possível publicar como site estático via **GitHub Pages** (o `index.html` já está na raiz).

Se quiser servir localmente:

```bash
python3 -m http.server 8000
# acesse http://localhost:8000
```

## Arquivos

| Arquivo | Descrição |
| --- | --- |
| `index.html` | Versão atual da aplicação (a que o GitHub Pages serve). |
| `assets/icon.svg`, `manifest.json`, `sw.js` | Suporte a PWA/instalação e cache offline. |
| `assets/videos/` | Vídeos da página `#/videos` e a legenda `.srt`. |
| `tests/` | Smoke test (rotas, interface e versão) e testes do backend. |
| `backend/` | Servidor opcional em Python puro (catálogo, validação, cotações). |
| `CHANGELOG.md` | Histórico de mudanças. |

> O vídeo estendido `video-dolar-b3-pro.mp4` (~28 MB) fica apenas local e é ignorado pelo Git. Se quiser usá-lo, coloque-o em `assets/videos/`; ele não é necessário para rodar o projeto. O projeto auxiliar `chat-qr/` também fica fora do repositório.

## Testes

```bash
npm install
npm test
```

O `npm test` roda duas checagens:

- `tests/smoke.js` — carrega o HTML em um DOM simulado (jsdom), percorre as principais rotas, valida a versão em `package.json`/`sw.js`/README/CHANGELOG e verifica erros de JavaScript;
- `tests/test_backend.py` — 6 testes unitários da normalização, validação e cobertura do backend.

### Backend opcional

```bash
python3 backend/server.py
# http://localhost:8765 — serve index.html e /api/*
BRAPI_TOKEN=sua_chave python3 backend/server.py   # token fica no servidor
```

Endpoints: `/api/health`, `/api/catalog`, `/api/catalog/summary`, `/api/validate`, `/api/coverage`, `/api/quotes?symbols=PETR4`, `/api/recommendations` e `POST /api/refresh`. Cache em `data/` (ignorado pelo Git). Em `localhost`, o frontend usa o backend automaticamente; sem ele, consulta a Brapi direto.

## O que tem

- **Mercados:** ticker animado e **universo completo da B3 via Brapi** (~2.300 ativos: ações/BDRs, FIIs e ETFs, com cotação), além de índices, cripto e câmbio. O catálogo é carregado em runtime e guardado em cache por 24 h; sem rede, a base curada continua funcionando. Botão **⟳ Universo** recarrega a lista.
- **Destaques do mercado:** carrossel calculado com as maiores quedas do dia, os maiores descontos por Graham, os descontos segundo o preço-alvo dos *players* (BTG, XP, Itaú BBA etc.) e o ranking das casas. Mini-gráficos interativos: clique/`Enter` seleciona a barra e mostra dados completos, `←`/`→` navegam, duplo clique abre o ativo; são recalculados quando chegam cotações ao vivo. Transição suave em loop, autoplay com barra de progresso e arrasto/swipe no mobile.
- **Mapa de setores:** visualização de altas e baixas com detalhe por setor.
- **Notícias e Carta Semanal:** listas filtráveis e páginas de leitura (conteúdo demonstrativo).
- **Ferramentas:** calculadoras, simulador de aportes, simulador histórico e comparador de ativos com gráficos em canvas/SVG.
- **Gráficos:** linha ou candles, volume, crosshair e indicadores MM20, Bandas de Bollinger e RSI(14).
- **Alertas de preço:** cadastre alvos por ativo; o sino no cabeçalho avisa quando uma cotação atinge o valor definido (dados salvos apenas no navegador).
- **Carteira:** cadastro de ativos com autocomplete via Brapi, cálculo de patrimônio, donut de alocação, persistência em `localStorage`.
- **Busca global no cabeçalho** com autocomplete de ativos, notícias, setores e páginas (setas + Enter); a página `#/busca` aceita `?q=...`. O autocomplete da carteira também consulta o catálogo local antes da Brapi.
- **Backend opcional** em `backend/` (Python puro): catálogo, validação, cobertura, cotações via proxy e lista de recomendações dos agentes. Em `localhost`, o frontend usa o backend automaticamente.

## Dados

As cotações da carteira e o autocomplete de tickers vêm da API pública [Brapi](https://brapi.dev/). Sem chave, respondem apenas os quatro tickers gratuitos atuais (`PETR4`, `VALE3`, `ITUB4`, `MGLU3`). Para consultar **outros ativos, FIIs e câmbio (dólar/euro)**, cole sua chave no painel explícito **“Chave da Brapi”** na coluna direita (o botão ⚙ da carteira leva até ele). A chave fica somente no `localStorage` do navegador e não é exportada com a carteira.

O painel tem botões **Salvar chave**, **Testar** (consulta `BBAS3`, que exige autenticação) e **Limpar**, além de um botão para mostrar/ocultar a chave. O módulo de câmbio usa `/api/v2/currency` da Brapi (PTAX); sem chave, a página de câmbio mostra dados ilustrativos e informa isso no status.

Os botões **⟳ Cotações ao vivo** (nas listas e na página do ativo) consultam a Brapi e substituem os preços ilustrativos da tabela quando a consulta funciona. Se falhar, os dados locais continuam sendo exibidos e o status informa o motivo. Os preços de câmbio atualizam também o ticker e o cartão do dólar na página inicial.

Os demais dados de mercado, notícias, séries históricas e preços-alvo são **ilustrativos**, criados para demonstrar a interface. Nada aqui é recomendação de investimento.

### PWA

Ao publicar via HTTPS (GitHub Pages, por exemplo), o app pode ser instalado na tela inicial. O service worker guarda apenas arquivos locais em cache; requisições para a Brapi não são interceptadas. Para testar o service worker localmente, sirva a pasta por HTTP em `localhost` (em `file://` ele é ignorado).

## Versões

Versão atual: **v1.6.2**. Cada release é uma tag Git (`v1.0.0` … `v1.6.2`). O histórico está no [CHANGELOG.md](CHANGELOG.md).

As tags substituem os antigos snapshots em `versions/`. Para inspecionar ou recuperar uma versão antiga sem sair do branch atual:

```bash
git show v1.2.0:index.html > /tmp/freeinvest-v1.2.0.html
git diff v1.4.0..v1.4.1 -- index.html
```

Ao lançar uma versão nova, atualize o número em `package.json`, `sw.js` (nome do cache), `README.md` e `CHANGELOG.md` — o `npm test` falha se algum ficar desatualizado.

## Como contribuir

1. Faça um **fork** do repositório (ou baixe o ZIP e crie seu próprio repo).
2. Crie uma branch: `git checkout -b minha-melhoria`.
3. Edite `index.html` (ou adicione arquivos novos) e rode `npm install && npm test`.
4. Commit e push: `git commit -m "descrição curta" && git push origin minha-melhoria`.
5. Abra um **Pull Request** contando o que mudou e como testar.

Dicas para quem está começando:

- Não precisa saber React, Vue ou build tools — aqui é HTML, CSS e JavaScript puro.
- Use o `npm test` antes de abrir o PR: ele checa se todas as rotas continuam funcionando.
- Se for mexer em cotações, lembre-se de que a Brapi tem limites de requisições e que o token fica só no navegador de quem usa.
- Mudou algo visual? Descreva o antes/depois no PR (print ou GIF ajuda bastante).

## Onde mexer no código

Tudo está em um único `index.html` para facilitar o estudo. Dentro dele:

| Bloco | O que faz |
| --- | --- |
| `<style>` | Design tokens (`:root`), layout responsivo e acessibilidade. |
| `const ticks`, `sectors`, `assets`, `news`... | Base de dados ilustrativa — troque ou conecte à sua API. |
| `genHistory` / `drawPriceChart` | Séries determinísticas e gráfico em canvas com crosshair. |
| `loadQuotes` / `renderPortfolio` | Carteira, Brapi, cache local e donut de alocação. |
| `buildSlides` | Destaques calculados (quedas, descontos Graham e casas de análise). |
| `loadCurrencies` | Câmbio ao vivo via `/api/v2/currency`, com status e fallback ilustrativo. |
| `marketView`, `assetDetail`, `Calculadoras`, `comparadorView` | Páginas renderizadas pelo roteador `#/...`. |
| `routeTable` / `renderRoute` | Roteamento por hash (funciona em `file://` e no Pages). |
| `tests/smoke.js`, `tests/test_backend.py` | Rotas, versão e qualidade dos dados do backend. |

## Ideias para melhorar

Um roadmap aberto, sem ordem de prioridade — pegue o que te interessar:

- [ ] Tema claro/alternante com persistência da escolha.
- [x] Indicadores técnicos no gráfico (MM20, RSI, bandas de Bollinger).
- [x] Alertas de preço salvos no navegador (alertas de dividendos ainda não).
- [ ] Exportação/importação de toda a carteira com senha ou criptografia local.
- [ ] Mais fontes de dados públicas (BACEN, B3, APIs de cripto) com fallback offline.
- [ ] Testes end-to-end com Playwright e capturas de tela versionadas.
- [ ] Acessibilidade auditada com axe e navegação completa por teclado.
- [ ] Internacionalização (pt-BR / en-US).
- [ ] Histórico de simulador com dados reais de preços e dividendos.
- [ ] Versão mobile-first com bottom navigation.

## Créditos

- Inspiração visual: [TradeMap](https://www.trademap.com.br/).
- Cotações e autocomplete: [Brapi](https://brapi.dev/) (API pública, sujeita aos termos do provedor).
- Construído com HTML, CSS, JavaScript e ajuda de IA — sem frameworks, sem build e sem custos de hospedagem.

Se este projeto te ajudou a aprender algo, ele já cumpriu o papel. Melhorações são sempre bem-vindas. 🚀
