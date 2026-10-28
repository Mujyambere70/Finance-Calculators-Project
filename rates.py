"""
rates.py - live exchange rates for every currency.

Sources (free, no API key):
  1. ExchangeRate-API "open access"   https://open.er-api.com/v6/latest/USD
     ~160 official currencies, updated once a day.          https://www.exchangerate-api.com
  2. currency-api by Fawaz Ahmed       https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json
     (mirror: https://latest.currency-api.pages.dev/...)   200+ currencies incl. crypto, daily, with history.

Both are used together: source 2 fills the currencies that source 1 does not have (e.g. Bitcoin),
source 1 wins where both have a rate. If one source is down, the other is enough.

All rates are stored with USD as the base. Every result is cached in SQLite:
  - the latest rates are downloaded again when they are older than TTL (1 hour by default),
  - if the internet is down, the last saved rates are used and marked "stale",
  - history (for the charts) is cached per day forever - old rates never change.
"""

import json
import os
import sqlite3
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from currencies import CURRENCY_LIST

KNOWN = {c["code"] for c in CURRENCY_LIST} | {"USD"}
TTL = int(os.environ.get("FX_TTL", 3600))          # seconds between downloads of the latest rates
TIMEOUT = 8

ER_API = "https://open.er-api.com/v6/latest/USD"
FAWAZ = ["https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{tag}/v1/currencies/usd.json",
         "https://{tag}.currency-api.pages.dev/v1/currencies/usd.json"]
SOURCES_INFO = [
    {"name": "ExchangeRate-API", "url": "https://www.exchangerate-api.com", "text": "Rates By Exchange Rate API"},
    {"name": "currency-api (Fawaz Ahmed)", "url": "https://github.com/fawazahmed0/exchange-api", "text": "currency-api"},
]


class RatesUnavailable(Exception):
    """No rates could be downloaded and nothing is saved yet."""


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "CalcWise/1.0 (finance calculator)",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


class RateService:
    def __init__(self, db_path, fetch=http_json, ttl=TTL):
        self.db_path, self.fetch, self.ttl = db_path, fetch, ttl
        self.lock = threading.Lock()
        with self._db() as con:
            con.execute("CREATE TABLE IF NOT EXISTS fx_cache (key TEXT PRIMARY KEY, data TEXT NOT NULL, fetched_at REAL NOT NULL)")

    def _db(self):
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def _load(self, key):
        with self._db() as con:
            row = con.execute("SELECT data, fetched_at FROM fx_cache WHERE key = ?", (key,)).fetchone()
        return (json.loads(row["data"]), row["fetched_at"]) if row else (None, 0)

    def _store(self, key, data):
        with self._db() as con:
            con.execute("INSERT INTO fx_cache (key, data, fetched_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET data = excluded.data, fetched_at = excluded.fetched_at",
                        (key, json.dumps(data), time.time()))

    # ---------------------------------------------------------------- downloading
    def _from_er_api(self):
        d = self.fetch(ER_API)
        if d.get("result") != "success" or not d.get("rates"):
            raise ValueError("ExchangeRate-API answered without rates")
        return ({k: float(v) for k, v in d["rates"].items()},
                d.get("time_last_update_unix"), d.get("time_next_update_unix"))

    def _from_fawaz(self, tag="latest"):
        last_error = None
        for pattern in FAWAZ:                       # jsDelivr first, then the Cloudflare mirror
            try:
                d = self.fetch(pattern.format(tag=tag))
                rates = {k.upper(): float(v) for k, v in d["usd"].items() if isinstance(v, (int, float)) and v > 0}
                when = datetime.strptime(d["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
                return rates, when
            except Exception as e:                  # try the mirror
                last_error = e
        raise last_error or ValueError("no data")

    def _download(self):
        rates, sources, updated, next_update, errors = {}, [], None, None, []
        try:
            fz, fz_time = self._from_fawaz()
            rates.update(fz)
            sources.append(SOURCES_INFO[1])
            updated = fz_time
        except Exception as e:
            errors.append(f"currency-api: {e}")
        try:
            er, er_time, er_next = self._from_er_api()
            rates.update(er)                        # official rates win
            sources.insert(0, SOURCES_INFO[0])
            updated, next_update = er_time, er_next
        except Exception as e:
            errors.append(f"ExchangeRate-API: {e}")
        rates = {k: v for k, v in rates.items() if k in KNOWN and v > 0}
        if not rates:
            raise RatesUnavailable("; ".join(errors) or "no rates")
        rates["USD"] = 1.0
        return {"base": "USD", "rates": rates, "updated_at": iso(updated), "next_update": iso(next_update),
                "sources": sources, "warnings": errors}

    # ---------------------------------------------------------------- public
    def latest(self, force=False):
        cached, fetched_at = self._load("latest")
        fresh = cached and time.time() - fetched_at < self.ttl
        if fresh and not force:
            return {**cached, "fetched_at": iso(fetched_at), "stale": False}
        with self.lock:
            cached, fetched_at = self._load("latest")          # another request may have just refreshed
            if cached and not force and time.time() - fetched_at < self.ttl:
                return {**cached, "fetched_at": iso(fetched_at), "stale": False}
            try:
                data = self._download()
                self._store("latest", data)
                return {**data, "fetched_at": iso(time.time()), "stale": False}
            except RatesUnavailable as e:
                if cached:                                     # offline: keep using the last good rates
                    return {**cached, "fetched_at": iso(fetched_at), "stale": True, "error": str(e)}
                raise

    def convert(self, amount, src, dst, rates=None):
        r = (rates or self.latest())["rates"]
        if src not in r or dst not in r:
            raise KeyError(src if src not in r else dst)
        return amount * r[dst] / r[src]

    def history(self, src, dst, days=30, today=None):
        """[(date, rate)] for 1 src in dst. Uses daily files of currency-api (cached forever)."""
        today = today or date.today()
        step = 1 if days <= 31 else 3 if days <= 93 else 7
        wanted = [today - timedelta(days=d) for d in range(days, -1, -step)]
        if wanted[-1] != today:
            wanted.append(today)
        cache = {}
        missing = []
        for d in wanted:
            data, _ = self._load(f"hist:{d.isoformat()}")
            if data:
                cache[d] = data
            else:
                missing.append(d)

        def get(d):
            try:
                rates, _ = self._from_fawaz(d.isoformat())
                return d, rates
            except Exception:
                return d, None

        if missing:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for d, rates in pool.map(get, missing):
                    if rates:
                        cache[d] = rates
                        if d < today:                            # today's file may still change
                            self._store(f"hist:{d.isoformat()}", rates)
        points = []
        for d in sorted(cache):
            r = cache[d]
            if src in r and dst in r:
                points.append((d.isoformat(), r[dst] / r[src]))
        return points
