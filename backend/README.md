# Backend do Free Invest Analytic

Servidor HTTP leve, escrito em **Python puro (stdlib)**, sem dependências e sem build. Ele centraliza a busca de dados, a validação e o relatório de cobertura de ativos.

## Como rodar

```bash
python3 backend/server.py
# ou
PORT=9000 python3 backend/server.py
```

Se você tiver uma chave da Brapi, use-a no servidor (ela nunca vai para o navegador):

```bash
BRAPI_TOKEN=sua_chave python3 backend/server.py
```

O servidor também serve o `index.html` em `http://localhost:8765/`.

## Endpoints

| Método | Rota | O que faz |
| --- | --- | --- |
| `GET` | `/api/health` | Status do serviço e se há token configurado |
| `GET` | `/api/catalog` | Catálogo completo da B3 (Brapi), cacheado por 24 h. `?refresh=1` força recarga |
| `GET` | `/api/catalog/summary` | Contagem por classe (ações, FIIs, ETFs) |
| `GET` | `/api/validate` | Problemas de qualidade: duplicados, sem preço, sem nome, classe desconhecida |
| `GET` | `/api/coverage` | Ativos da Brapi que faltam na base curada do `index.html` |
| `GET` | `/api/recommendations` | Listas prioritárias de ações, ETFs e FIIs encontradas pelos agentes + problemas de dados |
| `GET` | `/api/quotes?symbols=PETR4,VALE3` | Cotações via Brapi (proxy, com token opcional) |
| `POST` | `/api/refresh` | Recarrega catálogo, roda validação + cobertura e salva `data/last_report.json` |

Todas as respostas são JSON com CORS liberado (`*`).

## Cache

Os arquivos em `data/` são gerados em runtime e **não devem ser comitados**:

- `data/catalog.json` — catálogo normalizado
- `data/last_report.json` — último relatório de validação/cobertura

## Testes

```bash
python3 -m unittest tests.test_backend -v
```
