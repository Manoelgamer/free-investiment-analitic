# free-investiment-analitic

Um clone demonstrativo do **TradeMap** feito com ajuda de IA para auxiliar quem quer acompanhar investimentos. É uma aplicação **100% front-end** (HTML + CSS + JavaScript puro), sem build e sem dependências.

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
