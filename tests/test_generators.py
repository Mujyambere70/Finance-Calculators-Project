"""Generators: OTP / authenticator (RFC test vectors), passwords, emails, phones, passports + the web API."""

import os
import re
import string
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generators as G  # noqa: E402
from app import create_app  # noqa: E402
from countries import COUNTRIES, COUNTRY_LIST  # noqa: E402


class TestAuthenticator(unittest.TestCase):
    SHA1 = b"12345678901234567890"

    def test_rfc4226_hotp_vectors(self):
        want = ["755224", "287082", "359152", "969429", "338314", "254676", "287922", "162583", "399871", "520489"]
        self.assertEqual([G.hotp(self.SHA1, c) for c in range(10)], want)

    def test_rfc6238_totp_vectors(self):
        sha256 = b"12345678901234567890123456789012"
        sha512 = b"1234567890" * 6 + b"1234"
        cases = [(59, "94287082", "46119246", "90693936"), (1111111109, "07081804", "68084774", "25091201"),
                 (1234567890, "89005924", "91819424", "93441116"), (20000000000, "65353130", "77737706", "47863826")]
        for t, s1, s256, s512 in cases:
            self.assertEqual(G.totp(self.SHA1, t, digits=8), s1)
            self.assertEqual(G.totp(sha256, t, digits=8, algorithm="SHA256"), s256)
            self.assertEqual(G.totp(sha512, t, digits=8, algorithm="SHA512"), s512)

    def test_state_uri_and_verify(self):
        st = G.totp_state({"account": "jean@example.com", "issuer": "CalcWise"}, now=1000)
        self.assertEqual(len(st["secret"]), 32)                       # 160-bit Base32
        self.assertTrue(st["uri"].startswith("otpauth://totp/CalcWise%3Ajean%40example.com?secret="))
        self.assertEqual(st["remaining"], 20)                         # 1000 s -> 10 s into a 30 s step
        opts = {"secret": st["secret"]}
        self.assertTrue(G.totp_verify({**opts, "code": st["code"]}, now=1000)["valid"])
        self.assertTrue(G.totp_verify({**opts, "code": st["previous"]}, now=1000)["valid"])   # clock drift
        self.assertFalse(G.totp_verify({**opts, "code": st["code"]}, now=1100)["valid"])      # expired
        with self.assertRaises(G.GenError):
            G.totp_verify({**opts, "code": "12"})
        with self.assertRaises(G.GenError):
            G.totp_state({"secret": "not base32!"})

    def test_hotp_mode(self):
        st = G.totp_state({"mode": "hotp", "secret": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", "counter": 0})
        self.assertEqual(st["code"], "755224")                       # same key as RFC 4226 in Base32
        self.assertIn("counter=0", st["uri"])
        r = G.totp_verify({"mode": "hotp", "secret": st["secret"], "counter": 0, "code": "359152"})
        self.assertEqual(r["counter"], 2)


class TestCodesAndPasswords(unittest.TestCase):
    def test_otp_codes(self):
        r = G.otp_codes({"type": "numeric", "length": 6, "count": 50})
        self.assertEqual(len(r["items"]), 50)
        self.assertTrue(all(re.fullmatch(r"\d{6}", i["value"]) for i in r["items"]))
        self.assertEqual(r["info"]["combinations"], "1,000,000")
        safe = G.otp_codes({"type": "safe", "length": 8, "count": 30})["items"]
        self.assertFalse(any(set(i["value"]) & set("0O1IL2Z5S8B") for i in safe))
        grouped = G.otp_codes({"length": 6, "group": True, "count": 1})["items"][0]
        self.assertRegex(grouped["value"], r"^\d{3}-\d{3}$")
        with self.assertRaises(G.GenError):
            G.otp_codes({"length": 30})

    def test_password_rules(self):
        items = G.passwords({"length": 12, "count": 40, "no_ambiguous": True})["items"]
        for it in items:
            pw = it["value"]
            self.assertEqual(len(pw), 12)
            self.assertTrue(any(c.isupper() for c in pw) and any(c.islower() for c in pw)
                            and any(c.isdigit() for c in pw) and any(c in G.SYMBOLS for c in pw))
            self.assertFalse(set(pw) & G.AMBIGUOUS)
        only_digits = G.passwords({"length": 8, "upper": False, "lower": False, "symbols": False, "count": 5})["items"]
        self.assertTrue(all(i["value"].isdigit() for i in only_digits))
        with self.assertRaises(G.GenError):
            G.passwords({"upper": False, "lower": False, "digits": False, "symbols": False})

    def test_passphrase_pin_and_strength(self):
        p = G.passwords({"mode": "passphrase", "words": 6, "separator": "-", "count": 1})["items"][0]
        self.assertEqual(len(p["value"].split("-")), 6)
        self.assertGreater(p["bits"], 60)
        for it in G.passwords({"mode": "pin", "length": 4, "count": 100})["items"]:
            self.assertNotIn(it["value"], ("0000", "1234", "1111"))
        self.assertEqual(G.strength(20)["label"], "Very weak")
        self.assertEqual(G.strength(100)["label"], "Very strong")
        self.assertEqual(len(set(G.WORDS)), len(G.WORDS))


class TestTestData(unittest.TestCase):
    EMAIL = re.compile(r"^[a-z0-9._+]+@([a-z0-9-]+\.)+[a-z]{2,}$")

    def test_emails_every_type(self):
        for kind in G.EMAIL_TYPES:
            for it in G.emails({"type": kind, "count": 20})["items"]:
                self.assertRegex(it["value"], self.EMAIL)
                self.assertTrue(it["value"].split("@")[1].split(".")[-1] in ("com", "org", "net", "test"))
        r = G.emails({"type": "role", "domains": "custom", "domain": "MyFirm.co.rw", "count": 5})
        self.assertTrue(all(i["value"].endswith("@myfirm.co.rw") for i in r["items"]))
        self.assertEqual(len({i["value"] for i in G.emails({"count": 100})["items"]}), 100)  # no duplicates
        with self.assertRaises(G.GenError):
            G.emails({"domains": "custom", "domain": "not a domain"})

    def test_phone_every_country(self):
        self.assertGreaterEqual(len(COUNTRY_LIST), 240)
        for c in COUNTRY_LIST:
            p = G.phones({"country": c["code"], "count": 1})["items"][0]
            self.assertTrue(p["e164"].startswith("+" + c["dial"][:1]), c["code"])
            self.assertTrue(re.fullmatch(r"\+\d{6,15}", p["e164"]), (c["code"], p["e164"]))   # E.164 max 15 digits

    def test_phone_real_formats(self):
        rw = G.phones({"country": "RW", "count": 30})["items"]
        self.assertTrue(all(re.fullmatch(r"\+2507[2389]\d{7}", p["e164"]) for p in rw))
        self.assertTrue(all(re.fullmatch(r"07\d{2} \d{3} \d{3}", p["national"]) for p in rw))
        ru = G.phones({"country": "RU", "count": 1})["items"][0]
        self.assertRegex(ru["national"], r"^8 \(9\d\d\) \d{3}-\d{2}-\d{2}$")
        us = G.phones({"country": "US", "safe": True, "count": 20})["items"]
        self.assertTrue(all(re.search(r"555-01\d\d$", p["national"]) for p in us))
        gb = G.phones({"country": "GB", "safe": True, "count": 1})["items"][0]
        self.assertTrue(gb["e164"].startswith("+447700900"))
        land = G.phones({"country": "KE", "kind": "landline", "count": 10})["items"]
        self.assertFalse(any(p["e164"].startswith("+2547") for p in land))

    def test_passports(self):
        de = G.passports({"country": "DE", "count": 30})["items"]
        self.assertTrue(all(re.fullmatch(r"C[CFGHJKLMNPRTVWXYZ0-9]{8}", p["value"]) for p in de))
        us = G.passports({"country": "US", "count": 30})["items"]
        self.assertTrue(all(re.fullmatch(r"[A-Z0-9]\d{8}", p["value"]) for p in us))
        self.assertEqual(G.passports({"country": "IN", "count": 1})["items"][0]["format"], "1 letter + 7 digits")
        self.assertEqual(G.passports({"country": "CD", "count": 1})["items"][0]["quality"], "generic")
        for c in COUNTRY_LIST:
            v = G.passports({"country": c["code"], "count": 1})["items"][0]["value"].replace(" ", "")
            self.assertTrue(5 <= len(v) <= 9 and v.isalnum(), c["code"])


class TestApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = create_app(os.path.join(self.tmp.name, "t.db")).test_client()
        self.c.get("/")
        with self.c.session_transaction() as s:
            s["csrf"] = "tok"

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, tool, body, token="tok"):
        return self.c.post(f"/api/generate/{tool}", json=body, headers={"X-CSRF-Token": token})

    def test_pages(self):
        for t in ["", "/otp", "/password", "/email", "/phone", "/passport"]:
            r = self.c.get("/generators" + t)
            self.assertEqual(r.status_code, 200, t)
            self.assertIn(b"test data", r.data)
        self.assertEqual(self.c.get("/generators/nope").status_code, 404)

    def test_api(self):
        for tool in ["otp", "password", "email", "phone", "passport"]:
            r = self.post(tool, {"count": 3})
            self.assertEqual(r.status_code, 200, tool)
            self.assertEqual(len(r.get_json()["items"]), 3)
        st = self.post("totp", {}).get_json()
        self.assertEqual(len(st["code"]), 6)
        self.assertTrue(self.post("totp-verify", {"secret": st["secret"], "code": st["code"]}).get_json()["valid"])

    def test_errors_and_csrf(self):
        r = self.post("password", {"length": 500})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["field"], "length")
        self.assertEqual(self.post("phone", {"count": 1000}).status_code, 400)
        self.assertEqual(self.post("nothing", {}).status_code, 404)
        self.assertEqual(self.post("otp", {}, token="bad").status_code, 400)


if __name__ == "__main__":
    unittest.main()
