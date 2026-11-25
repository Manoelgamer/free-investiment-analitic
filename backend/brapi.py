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
    "VALE3": "Mineração", "CMIN3": "Mineração", "CBAV3": "Mineração", "BRAP3": "Mineração",
    "CSNA3": "Siderurgia", "GGBR4": "Siderurgia", "USIM5": "Siderurgia",
    "USIM3": "Siderurgia", "GOAU4": "Siderurgia", "PATI3": "Siderurgia",
    "KLBN11": "Papel", "KLBN3": "Papel", "KLBN4": "Papel", "SUZB3": "Papel",
    "PETR4": "Petroquímica", "PETR3": "Petroquímica", "PRIO3": "Petroquímica",
    "RECV3": "Petroquímica", "BRAV3": "Petroquímica", "BRKM5": "Química", "UNIP3": "Química",
    "EQTL3": "Utilidades", "CPFE3": "Utilidades", "CPLE3": "Utilidades", "CMIG4": "Utilidades",
    "CSMG3": "Utilidades", "SBSP3": "Utilidades", "ENEV3": "Utilidades", "ENGI11": "Utilidades",
    "AXIA3": "Utilidades", "AURE3": "Utilidades", "LIGT3": "Utilidades", "EGIE3": "Utilidades",
    "PASS3": "Utilidades", "ORVR3": "Utilidades",
    "BBAS3": "Bancos", "BBDC4": "Bancos", "BBDC3": "Bancos", "ITUB4": "Bancos",
    "ITUB3": "Bancos", "BPAC11": "Bancos", "BPAC5": "Bancos", "SANB11": "Bancos",
    "ABCB4": "Bancos", "BMGB4": "Bancos", "BRBI11": "Bancos", "BAZA3": "Bancos", "BEES3": "Bancos",
    "BBSE3": "Seguros", "PSSA3": "Seguros", "IRBR3": "Seguros", "CXSE3": "Seguros", "WIZC3": "Seguros",
    "B3SA3": "Finanças", "ITSA4": "Finanças",
    "MGLU3": "Varejo", "LREN3": "Varejo", "ASAI3": "Varejo", "NATU3": "Varejo",
    "PCAR3": "Varejo", "RADL3": "Varejo", "CEAB3": "Varejo", "PGMN3": "Varejo",
    "CVCB3": "Varejo", "BHIA3": "Varejo", "VBBR3": "Varejo", "UGPA3": "Varejo", "GMAT3": "Varejo",
    "RENT3": "Transporte", "RAIL3": "Transporte", "ECOR3": "Transporte", "MOTV3": "Transporte",
    "JSLG3": "Transporte", "TUPY3": "Máquinas",
    "WEGE3": "Máquinas", "EMBJ3": "Máquinas", "ROMI3": "Máquinas", "KEPL3": "Máquinas",
    "MILS3": "Máquinas", "ARML3": "Máquinas", "INTB3": "Máquinas", "OPCT3": "Máquinas",
    "INEP3": "Máquinas", "LUPA3": "Máquinas",
    "HAPV3": "Saúde", "RDOR3": "Saúde", "FLRY3": "Saúde", "HYPE3": "Saúde", "VVEO3": "Saúde",
    "BIOM3": "Saúde", "PFRM3": "Saúde", "BLAU3": "Saúde", "DMVF3": "Saúde", "OFSA3": "Saúde", "SAUD3": "Saúde",
    "COGN3": "Educação", "ANIM3": "Educação", "YDUQ3": "Educação", "VTRU3": "Educação",
    "CSED3": "Educação", "SEER3": "Educação", "BIED3": "Educação",
    "TOTS3": "TI", "LWSA3": "TI", "CASH3": "TI", "BMOB3": "TI", "IFCM3": "TI", "DOTZ3": "TI", "PDTC3": "TI",
    "VIVT3": "Telecom", "TIMS3": "Telecom", "FIQE3": "Telecom", "DESK3": "Telecom",
    "BRST3": "Telecom", "TELB3": "Telecom",
    "BEEF3": "Alimentos", "MBRF3": "Alimentos", "CAML3": "Alimentos", "MDIA3": "Alimentos",
    "JALL3": "Alimentos", "JOPA3": "Alimentos",
    "TTEN3": "Agronegócio", "SLCE3": "Agronegócio", "SOJA3": "Agronegócio", "AGRO3": "Agronegócio",
    "LAND3": "Agronegócio", "AGXY3": "Agronegócio", "FHER3": "Agronegócio", "NUTR3": "Agronegócio", "VITT3": "Agronegócio",
    "CYRE3": "Construção", "MRVE3": "Construção", "DIRR3": "Construção", "EZTC3": "Construção",
    "TEND3": "Construção", "JHSF3": "Construção", "EVEN3": "Construção", "CURY3": "Construção",
    "AZEV3": "Construção", "PTBL3": "Construção", "HAGA3": "Construção", "GFSA3": "Construção",
    "WHRL3": "Eletrodomésticos", "ALLD3": "Eletrodomésticos",
    "MXRF11": "Imobiliário", "HGLG11": "Imobiliário", "KNRI11": "Imobiliário",
    "HGBS11": "Imobiliário", "VISC11": "Imobiliário",
}

SECTOR_KEYWORDS = [
    ("Petroquímica", ["petróleo", "petroquím", "petroquim", "energy minerals", "oil & gas", "integrated oil"]),
    ("Mineração", ["miner", "mining"]),
    ("Bancos", ["banco", "bank"]),
    ("Finanças", ["financeir", "dados financeiros", "títulos e val", "crédito", "capital markets"]),
    ("Varejo", ["varejo", "retail", "vestuário"]),
    ("Máquinas", ["máq", "maq", "equip", "motores", "machinery"]),
    ("Bebidas", ["bebida", "cerveja", "beverage", "brew"]),
    ("Transporte", ["transporte", "rodov", "aéreo", "ferrovi", "hidrovi", "logística", "transportation"]),
    ("Papel", ["papel", "celulose", "paper"]),
    ("Imobiliário", ["imobili", "fundos imobili", "lajes", "shoppings", "incorpora"]),
    ("Construção", ["constru", "engenharia", "construction"]),
    ("Química", ["quím", "quim", "chemical"]),
    ("Alimentos", ["aliment", "açucar", "acucar", "carnes", "food"]),
    ("Saúde", ["saúde", "saude", "hospital", "medic", "health"]),
    ("Educação", ["educa", "education"]),
    ("TI", ["tecnologia", "software", "comput", "program", "dados"]),
    ("Telecom", ["telecom", "comunica"]),
    ("Utilidades", ["energia elétrica", "água", "saneamento", "gás", "utilit", "utilities"]),
    ("Agronegócio", ["agricult", "agro", "fertiliz"]),
    ("Siderurgia", ["siderurg", "aço", "ferro", "steel"]),
    ("Eletrodomésticos", ["eletrodom", "utensílios"]),
    ("Seguros", ["segur", "insurance"]),
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
    text = ((raw.get("subsector") or "") + " " + (raw.get("sector") or "") + " "
            + str(raw.get("longName") or raw.get("name") or "")).lower()
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
