"""Cache em disco, sem dependências externas."""
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")


def _path(name):
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, name + ".json")


def load(name, max_age=None):
    """Retorna os dados salvos. Se max_age for informado, expira cache antigo."""
    path = _path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    if max_age is not None and time.time() - payload.get("ts", 0) > max_age:
        return None
    return payload.get("data")


def save(name, data):
    path = _path(name)
    payload = {"ts": time.time(), "data": data}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    return path
