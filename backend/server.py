"""Servidor HTTP do backend do Free Invest Analytic (stdlib, sem dependências)."""
import json
import mimetypes
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import brapi
import quality
import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_TTL = 24 * 60 * 60
PORT = int(os.environ.get("PORT", "8765"))
VERSION = "1.5.0"


def get_catalog(force=False):
    cached = None if force else store.load("catalog", CACHE_TTL)
    if cached is None:
        raw, pagination = brapi.fetch_all(os.environ.get("BRAPI_TOKEN"))
        cached = {
            "items": brapi.normalize_all(raw),
            "pagination": pagination,
            "source": "brapi",
        }
        store.save("catalog", cached)
    return cached


class Handler(BaseHTTPRequestHandler):
    server_version = "FreeInvestBackend/" + VERSION

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.address_string(), fmt % args))

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.abspath(os.path.join(ROOT, rel))
        if not full.startswith(ROOT):
            self._json({"error": "fora do projeto"}, 403)
            return
        if not os.path.isfile(full):
            self._json({"error": "arquivo não encontrado"}, 404)
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as handle:
            body = handle.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/health":
                return self._json({"ok": True, "service": "free-invest-backend",
                                   "version": VERSION, "has_token": bool(os.environ.get("BRAPI_TOKEN"))})
            if path == "/api/catalog":
                catalog = get_catalog(force="1" in query.get("refresh", []))
                return self._json({"items": catalog["items"],
                                   "pagination": catalog.get("pagination", {}),
                                   "total": len(catalog["items"])})
            if path == "/api/catalog/summary":
                catalog = get_catalog()
                items = catalog["items"]
                return self._json({"total": len(items),
                                   "by_class": quality.validate_catalog(items)["by_class"],
                                   "cached": store.load("catalog") is not None})
            if path == "/api/recommendations":
                rec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recommendations.json")
                with open(rec_path, "r", encoding="utf-8") as handle:
                    return self._json(json.load(handle))
            if path == "/api/validate":
                catalog = get_catalog()
                return self._json(quality.validate_catalog(catalog["items"]))
            if path == "/api/coverage":
                catalog = get_catalog()
                return self._json(quality.coverage(catalog["items"]))
            if path == "/api/quotes":
                symbols = (query.get("symbols") or [""])[0]
                symbols = [s.upper() for s in symbols.split(",") if s.strip()][:100]
                if not symbols:
                    return self._json({"error": "informe symbols"}, 400)
                result = brapi._get("/stocks/quote?symbols=" +
                                    urllib.parse.quote(",".join(symbols)),
                                    os.environ.get("BRAPI_TOKEN"))
                return self._json(result)
            if path.startswith("/api/"):
                return self._json({"error": "endpoint não encontrado"}, 404)
            return self._static(path)
        except Exception as exc:  # noqa: BLE001 - resposta amigável ao cliente
            return self._json({"error": str(exc)}, 502)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/refresh":
            return self._json({"error": "endpoint não encontrado"}, 404)
        try:
            catalog = get_catalog(force=True)
            validation = quality.validate_catalog(catalog["items"])
            coverage = quality.coverage(catalog["items"])
            report = {"catalog_total": len(catalog["items"]),
                      "validation": validation, "coverage": coverage}
            store.save("last_report", report)
            return self._json(report)
        except Exception as exc:  # noqa: BLE001
            return self._json({"error": str(exc)}, 502)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Free Invest Analytic backend em http://localhost:%d" % PORT)
    print("Endpoints: /api/health /api/catalog /api/catalog/summary /api/validate /api/coverage /api/quotes /api/refresh")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
