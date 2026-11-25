"""Testes unitários do backend (sem dependências externas)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import brapi  # noqa: E402
import quality  # noqa: E402


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.samples = [
            {"symbol": "PETR4", "longName": "Petrobras PN", "subType": "stock",
             "sector": "Energy Minerals", "quote": {"lastPrice": 40.1, "changePercent": 1.2}},
            {"symbol": "MXRF11", "name": "Maxi Renda", "subType": "fii",
             "subsector": "Logística", "quote": {"lastPrice": 10.3, "changePercent": 0.1}},
            {"symbol": "IVVB11", "name": "iShares S&P 500", "subType": "etf",
             "quote": {"lastPrice": 360.0, "changePercent": -0.4}},
        ]

    def test_normalize_classes(self):
        items = brapi.normalize_all(self.samples)
        self.assertEqual([i["c"] for i in items], ["Ações", "FIIs", "ETFs"])
        self.assertEqual(items[0]["set"], "Petroquímica")
        self.assertEqual(items[1]["set"], "Imobiliário")
        self.assertEqual(items[2]["set"], "Mercado")

    def test_bdr_separado_e_duplicata_f(self):
        raw = [
            {"symbol": "PETR4", "name": "Petrobras", "subType": "stock", "quote": {"lastPrice": 40, "changePercent": 1}},
            {"symbol": "PETR4F", "name": "Petrobras", "subType": "stock", "quote": {"lastPrice": 40, "changePercent": 1}},
            {"symbol": "TSLA34", "name": "Tesla", "subType": "bdr", "quote": {"lastPrice": 50, "changePercent": 0}},
        ]
        items = brapi.normalize_all(raw)
        self.assertEqual([i["s"] for i in items], ["PETR4", "TSLA34"])
        self.assertEqual(items[1]["c"], "BDRs")

    def test_setor_manual(self):
        item = brapi.normalize({"symbol": "VALE3", "name": "Vale", "subType": "stock",
                                "sector": "Energy Minerals", "quote": {"lastPrice": 60, "changePercent": 1}})
        self.assertEqual(item["set"], "Mineração")

    def test_klabin_nao_e_petroquimica(self):
        item = brapi.normalize({"symbol": "KLBN11", "name": "Klabin", "subType": "stock",
                                "sector": "Energy Minerals", "subsector": "Petróleo e Gás",
                                "quote": {"lastPrice": 17, "changePercent": 0.5}})
        self.assertEqual(item["set"], "Papel")
        self.assertNotEqual(item["set"], "Petroquímica")

    def test_validate_detects_duplicates(self):
        items = brapi.normalize_all(self.samples + [self.samples[0]])
        report = quality.validate_catalog(items)
        self.assertEqual(report["total"], 4)
        self.assertTrue(any(i["type"] == "duplicado" for i in report["issues"]))
        self.assertFalse(report["ok"])

    def test_validate_detects_bad_prices(self):
        items = brapi.normalize_all([{"symbol": "BAD", "name": "Sem preço",
                                      "subType": "stock", "quote": {}}])
        report = quality.validate_catalog(items)
        self.assertTrue(any(i["type"] == "sem_preco" for i in report["issues"]))

    def test_coverage_finds_missing(self):
        catalog = brapi.normalize_all(self.samples)
        report = quality.coverage(catalog, curated={"PETR4"})
        self.assertEqual(report["missing_count"], 2)
        self.assertEqual(report["missing_by_class"].get("FIIs"), 1)
        self.assertEqual(report["curated_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
