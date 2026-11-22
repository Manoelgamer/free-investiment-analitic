"""Validação de dados e comparação de cobertura com a base do frontend."""
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")


def validate_catalog(items):
    """Encontra problemas de qualidade no catálogo normalizado."""
    issues = []
    seen = set()
    for item in items:
        symbol = item.get("s")
        if not symbol:
            issues.append({"type": "symbol_vazio", "symbol": "", "detail": "ativo sem código"})
            continue
        if symbol in seen:
            issues.append({"type": "duplicado", "symbol": symbol, "detail": "código repetido"})
        seen.add(symbol)
        if not item.get("n"):
            issues.append({"type": "sem_nome", "symbol": symbol, "detail": "sem nome"})
        if not item.get("p") or item["p"] <= 0:
            issues.append({"type": "sem_preco", "symbol": symbol, "detail": "preço zerado"})
        if item.get("ch") is None:
            issues.append({"type": "sem_variacao", "symbol": symbol, "detail": "variação ausente"})
        if item.get("c") == "Outros":
            issues.append({"type": "classe_desconhecida", "symbol": symbol,
                           "detail": "subType " + str(item.get("subType"))})
    kinds = Counter(item.get("c") for item in items)
    return {
        "total": len(items),
        "issues_count": len(issues),
        "issues": issues[:300],
        "by_class": dict(kinds),
        "ok": len(issues) == 0,
    }


def curated_symbols():
    """Lê os símbolos da base curada direto do array `assets` do index.html."""
    if not os.path.exists(INDEX):
        return set()
    with open(INDEX, "r", encoding="utf-8") as handle:
        html = handle.read()
    block = re.search(r"const assets = \[(.*?)\n\];", html, re.S)
    if not block:
        return set()
    return set(re.findall(r"\{s:'([A-Z0-9]+)'", block.group(1)))


def coverage(catalog, curated=None):
    """Compara o catálogo da Brapi com a base curada do frontend."""
    curated = curated if curated is not None else curated_symbols()
    missing = [item for item in catalog if item.get("s") not in curated]
    by_class = Counter(item.get("c") for item in missing)
    examples = {}
    for item in missing:
        kind = item.get("c")
        examples.setdefault(kind, [])
        if len(examples[kind]) < 12:
            examples[kind].append({"s": item.get("s"), "n": item.get("n"), "p": item.get("p")})
    return {
        "curated_count": len(curated),
        "catalog_count": len(catalog),
        "covered": len(catalog) - len(missing),
        "missing_count": len(missing),
        "missing_by_class": dict(by_class),
        "examples": examples,
    }
