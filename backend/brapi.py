"""Cliente da API Brapi e normalização do catálogo de ativos."""
import json
import urllib.parse
import urllib.request

API = "https://brapi.dev/api/v2"
TIMEOUT = 20
USER_AGENT = "free-invest-analytic/1.5 (+backend)"

CLASS_MAP = {
    "stock": "Ações", "unit": "Ações", "bdr": "BDRs",
    "fii": "FIIs", "fi-infra": "FIIs", "fi-agro": "FIIs",
    "fip": "FIIs", "fidc": "FIIs", "etf": "ETFs",
}

# Setores que a Brapi classifica mal (revisão dos agentes de cobertura)
MANUAL_SECTOR = {
    "VALE3": "Mineração", "CSNA3": "Siderurgia", "GGBR4": "Siderurgia",
    "USIM5": "Siderurgia", "KLBN11": "Papel", "MXRF11": "Imobiliário",
    "ITSA4": "Finanças", "EMBJ3": "Máquinas", "NATU3": "Varejo",
    "RENT3": "Transporte", "ALOS3": "Imobiliário",
}

SECTOR_KEYWORDS = [
    ("Petroquímica", ["petróleo", "petroquím", "petroquim", "energy minerals", "oil & gas", "integrated oil"]),
    ("Mineração", ["miner"]),
    ("Bancos", ["banco", "bank"]),
    ("Finanças", ["financeir", "dados financeiros", "títulos e val", "crédito", "capital markets"]),
    ("Varejo", ["varejo", "retail", "vestuário"]),
    ("Máquinas", ["máq", "maq", "equip", "motores"]),
    ("Bebidas", ["bebida", "cerveja"]),
    ("Transporte", ["transporte", "rodov", "aéreo", "ferrovi", "hidrovi", "logística"]),
    ("Papel", ["papel", "celulose"]),
    ("Imobiliário", ["imobili", "fundos imobili", "lajes", "shoppings", "incorpora"]),
    ("Construção", ["constru", "engenharia"]),
    ("Química", ["quím", "quim"]),
    ("Alimentos", ["aliment", "açucar", "acucar", "carnes"]),
    ("Saúde", ["saúde", "saude", "hospital", "medic"]),
    ("Educação", ["educa"]),
    ("TI", ["tecnologia", "software", "comput", "program", "dados"]),
    ("Telecom", ["telecom", "comunica"]),
    ("Utilidades", ["energia elétrica", "água", "saneamento", "gás", "utilit"]),
    ("Agronegócio", ["agricult", "agro", "fertiliz"]),
    ("Siderurgia", ["siderurg", "aço", "ferro"]),
    ("Eletrodomésticos", ["eletrodom", "utensílios"]),
    ("Seguros", ["segur"]),
]


def _get(path, token=None):
    url = API + path
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.load(response)


def fetch_page(page=1, limit=2000, token=None):
    """Busca uma página do catálogo de tickers."""
    query = urllib.parse.urlencode({"limit": limit, "page": page})
    return _get("/tickers?" + query, token)


def fetch_all(token=None):
    """Busca o catálogo completo (paginado) e o metadado de paginação."""
    first = fetch_page(1, 2000, token)
    pagination = first.get("pagination") or {}
    pages = min(3, int(pagination.get("totalPages") or 1))
    results = list(first.get("results") or [])
    for page in range(2, pages + 1):
        results.extend(fetch_page(page, 2000, token).get("results") or [])
    return results, pagination


def infer_class(raw):
    """Alguns tickers da Brapi vêm sem subType; infere pela razão social."""
    name = (str(raw.get("name") or "") + " " + str(raw.get("longName") or "")).upper()
    symbol = (raw.get("symbol") or "").upper()
    if "FUNDO" in name or "FII" in name:
        return "FIIs"
    if any(key in name for key in ("ETF", "IT NOW", "ISHARES", "INVESTO", "IBOVESPA")):
        return "ETFs"
    if symbol.endswith("11"):
        return "FIIs"
    return "Outros"


def normalize(raw):
    """Converte um item da Brapi no formato usado pelo frontend."""
    sub = raw.get("subType") or ""
    kind = CLASS_MAP.get(sub) or infer_class(raw)
    symbol = raw.get("symbol")
    text = ((raw.get("subsector") or "") + " " + (raw.get("sector") or "")).lower()
    sector = "Mercado" if kind == "ETFs" else "Outros"
    if symbol in MANUAL_SECTOR:
        sector = MANUAL_SECTOR[symbol]
    elif kind != "ETFs":
        for name, keys in SECTOR_KEYWORDS:
            if any(k in text for k in keys):
                sector = name
                break
    quote = raw.get("quote") or {}
    return {
        "s": raw.get("symbol"),
        "n": raw.get("longName") or raw.get("name") or raw.get("symbol"),
        "c": kind,
        "set": sector,
        "p": _number(quote.get("lastPrice")),
        "ch": _number(quote.get("changePercent")),
        "active": bool(raw.get("isActive", True)),
        "exchange": raw.get("exchange"),
        "currency": raw.get("currency"),
        "subType": sub,
        "logo": raw.get("logoUrl"),
    }


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_all(raw_items):
    symbols = {item.get("symbol") for item in raw_items if item.get("symbol")}
    out = []
    for item in raw_items:
        symbol = item.get("symbol")
        if not symbol:
            continue
        # Tickers com sufixo F repetem o ativo-base; evita duplicação funcional
        if symbol.endswith("F") and symbol[:-1] in symbols:
            continue
        out.append(normalize(item))
    return out
