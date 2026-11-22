# free-investiment-analitic

Um clone demonstrativo do **TradeMap** feito com ajuda de IA para auxiliar quem quer acompanhar investimentos. É uma aplicação **100% front-end** (HTML + CSS + JavaScript puro), sem build e sem dependências.

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
| `trademap-clone.html` | Cópia exata do arquivo original enviado (baseline v1.0.0). |
| `versions/` | Snapshots imutáveis de cada versão publicada. |
| `tests/smoke.js` | Teste automatizado de rotas e da interface. |
| `manifest.json`, `icon.svg`, `sw.js` | Suporte a PWA/instalação e cache offline. |
| `CHANGELOG.md` | Histórico de mudanças. |

## Testes

```bash
npm install
npm test
```

O smoke test carrega o HTML em um DOM simulado (jsdom), percorre todas as rotas e verifica se não há erros de JavaScript.

## O que tem

- **Mercados:** ticker animado, cotações, ações, FIIs, ETFs, índices, cripto e câmbio.
- **Mapa de setores:** visualização de altas e baixas com detalhe por setor.
- **Notícias e TradeLetter:** listas filtráveis e páginas de leitura.
- **Ferramentas:** calculadoras, simulador de aportes, simulador histórico e comparador de ativos com gráficos em canvas/SVG.
- **Carteira:** cadastro de ativos com autocomplete via Brapi, cálculo de patrimônio, donut de alocação, persistência em `localStorage`.
- **Busca global, Academy e páginas institucionais.**

## Dados

As cotações da carteira e o autocomplete de tickers vêm da API pública [Brapi](https://brapi.dev/). Sem token, respondem apenas os tickers gratuitos (`PETR4`, `VALE3`, `ITUB4`, `MGLU3`, `MXRF11`, `HGLG11`); para outros ativos, configure sua chave gratuita no ícone ⚙ da carteira. A chave fica somente no `localStorage` do navegador.

Os botões **⟳ Cotações ao vivo** (nas listas e na página do ativo) consultam a Brapi e substituem os preços ilustrativos da tabela quando a consulta funciona. Se falhar, os dados locais continuam sendo exibidos e o status informa o motivo.

Os demais dados de mercado, notícias, séries históricas e preços-alvo são **ilustrativos**, criados para demonstrar a interface. Nada aqui é recomendação de investimento.

### PWA

Ao publicar via HTTPS (GitHub Pages, por exemplo), o app pode ser instalado na tela inicial. O service worker guarda apenas arquivos locais em cache; requisições para a Brapi não são interceptadas. Para testar o service worker localmente, sirva a pasta por HTTP em `localhost` (em `file://` ele é ignorado).

## Versões

As versões são marcadas com tags Git (`v1.0.0`, `v1.1.0`, ...) e os arquivos correspondentes ficam em `versions/`. Veja o [CHANGELOG.md](CHANGELOG.md).

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
| `marketView`, `assetDetail`, `Calculadoras`, `comparadorView` | Páginas renderizadas pelo roteador `#/...`. |
| `routeTable` / `renderRoute` | Roteamento por hash (funciona em `file://` e no Pages). |
| `tests/smoke.js` | Verificação automática das rotas e da interface. |

## Ideias para melhorar

Um roadmap aberto, sem ordem de prioridade — pegue o que te interessar:

- [ ] Tema claro/alternante com persistência da escolha.
- [ ] Indicadores técnicos no gráfico (médias móveis, RSI, bandas de Bollinger).
- [ ] Alertas de preço e de dividendos salvos no navegador.
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
