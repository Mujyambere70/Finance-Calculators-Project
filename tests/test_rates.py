"""Tests for live exchange rates. The internet is replaced by a fake fetch function,
so the tests are fast and work offline."""

import os
import sys
import tempfile
import time
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from currencies import CURRENCY_LIST  # noqa: E402
from rates import ER_API, RatesUnavailable, RateService  # noqa: E402

# test numbers only - not real rates
ER = {"result": "success", "base_code": "USD", "time_last_update_unix": 1761609600, "time_next_update_unix": 1761696000,
      "rates": {"USD": 1, "EUR": 0.9, "RWF": 1400.0, "KES": 130.0, "UGX": 3600.0, "XYZ": 5.0}}
FZ = {"date": "2026-10-28", "usd": {"usd": 1, "eur": 0.91, "rwf": 1390.0, "btc": 0.00001, "tzs": 2500.0}}


class FakeNet:
    def __init__(self, er=True, jsdelivr=True, mirror=True):
        self.er, self.jsdelivr, self.mirror, self.calls = er, jsdelivr, mirror, []

    def __call__(self, url):
        self.calls.append(url)
        if url == ER_API:
            if not self.er:
                raise OSError("no internet")
            return ER
        ok = self.jsdelivr if "jsdelivr" in url else self.mirror
        if not ok:
            raise OSError("down")
        if "@latest" in url or "//latest." in url:
            return FZ
        day = url.split("@")[-1].split("/")[0] if "jsdelivr" in url else url.split("//")[1].split(".")[0]
        n = date.fromisoformat(day).toordinal() % 10                 # a different fake rate per day
        return {"date": day, "usd": {"usd": 1, "eur": 0.9 + n / 100, "rwf": 1400 + n}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")

    def tearDown(self):
        self.tmp.cleanup()


class TestRateService(Base):
    def test_merges_both_sources(self):
        r = RateService(self.db, FakeNet()).latest()
        self.assertEqual(r["rates"]["EUR"], 0.9)          # official source wins
        self.assertEqual(r["rates"]["BTC"], 0.00001)      # only in currency-api
        self.assertEqual(r["rates"]["TZS"], 2500.0)
        self.assertNotIn("XYZ", r["rates"])               # unknown codes dropped
        self.assertEqual(r["updated_at"], "2025-10-28T00:00:00Z")
        self.assertEqual(len(r["sources"]), 2)
        self.assertFalse(r["stale"])

    def test_one_source_is_enough(self):
        r = RateService(self.db, FakeNet(er=False)).latest()
        self.assertEqual(r["rates"]["EUR"], 0.91)
        r = RateService(os.path.join(self.tmp.name, "b.db"), FakeNet(jsdelivr=False, mirror=False)).latest()
        self.assertEqual(r["rates"]["RWF"], 1400.0)

    def test_mirror_used_when_jsdelivr_down(self):
        net = FakeNet(er=False, jsdelivr=False)
        r = RateService(self.db, net).latest()
        self.assertEqual(r["rates"]["RWF"], 1390.0)
        self.assertTrue(any("pages.dev" in u for u in net.calls))

    def test_cache_and_ttl(self):
        net = FakeNet()
        s = RateService(self.db, net, ttl=3600)
        s.latest()
        n = len(net.calls)
        s.latest()
        self.assertEqual(len(net.calls), n)               # served from cache
        s2 = RateService(self.db, net, ttl=0)
        time.sleep(0.01)
        s2.latest()
        self.assertGreater(len(net.calls), n)             # expired -> downloaded again

    def test_offline_uses_last_saved_rates(self):
        RateService(self.db, FakeNet()).latest()
        r = RateService(self.db, FakeNet(False, False, False), ttl=0).latest()
        self.assertTrue(r["stale"])
        self.assertEqual(r["rates"]["RWF"], 1400.0)

    def test_offline_without_cache(self):
        with self.assertRaises(RatesUnavailable):
            RateService(self.db, FakeNet(False, False, False)).latest()

    def test_convert(self):
        s = RateService(self.db, FakeNet())
        self.assertAlmostEqual(s.convert(100, "USD", "RWF"), 140000)
        self.assertAlmostEqual(s.convert(1300, "KES", "RWF"), 14000)
        self.assertAlmostEqual(s.convert(1, "EUR", "EUR"), 1)
        with self.assertRaises(KeyError):
            s.convert(1, "USD", "ABC")

    def test_history_and_its_cache(self):
        net = FakeNet()
        s = RateService(self.db, net)
        pts = s.history("USD", "RWF", days=7, today=date(2026, 10, 20))
        self.assertEqual(len(pts), 8)
        self.assertEqual(pts[0][0], "2026-10-13")
        n = len(net.calls)
        s.history("USD", "RWF", days=7, today=date(2026, 10, 20))
        self.assertEqual(len(net.calls) - n, 1)           # past days cached; only "today" is asked again
        eur_rwf = s.history("EUR", "RWF", days=7, today=date(2026, 10, 20))
        self.assertAlmostEqual(eur_rwf[0][1], pts[0][1] / (0.9 + date(2026, 10, 13).toordinal() % 10 / 100))

    def test_every_currency_has_data(self):
        codes = [c["code"] for c in CURRENCY_LIST]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertGreaterEqual(len(codes), 150)
        for must in ["RWF", "KES", "UGX", "TZS", "BIF", "SSP", "CDF", "SOS", "ETB", "USD", "EUR", "CNY", "BRL", "RUB", "BTC"]:
            self.assertIn(must, codes)


class TestRatesApi(Base):
    def client(self, net):
        app = create_app(self.db, rate_fetch=net)
        c = app.test_client()
        return c

    def test_rates_endpoint(self):
        d = self.client(FakeNet()).get("/api/rates").get_json()
        self.assertEqual(d["base"], "USD")
        self.assertIn("RWF", d["rates"])

    def test_rates_unavailable(self):
        r = self.client(FakeNet(False, False, False)).get("/api/rates")
        self.assertEqual(r.status_code, 503)

    def test_history_endpoint(self):
        c = self.client(FakeNet())
        d = c.get("/api/rates/history?from=USD&to=RWF&days=7").get_json()
        self.assertGreaterEqual(len(d["points"]), 7)
        self.assertEqual(c.get("/api/rates/history?from=ABC&to=RWF").status_code, 400)

    def test_converter_page(self):
        html = self.client(FakeNet()).get("/converter").get_data(as_text=True)
        self.assertIn("Currency converter", html)
        self.assertIn("Exchange Rate API", html)          # required attribution
        for code in ["RWF", "KES", "JPY", "ZWG"]:
            self.assertIn(f'value="{code}"', html)


if __name__ == "__main__":
    unittest.main()
