"""Integration tests: pages, JSON API and saved calculations."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from forms import CALCS  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(os.path.join(self.tmp.name, "t.db"))
        self.c = self.new_client()

    def tearDown(self):
        self.tmp.cleanup()

    def new_client(self):
        c = self.app.test_client()
        c.get("/")                                  # gets the owner cookie
        with c.session_transaction() as s:
            s["csrf"] = "tok"
        return c

    def api(self, url, body, client=None):
        return (client or self.c).post(url, json=body, headers={"X-CSRF-Token": "tok"})

    def save(self, name="My plan", client=None, **extra):
        body = {"kind": "investment", "name": name, "inputs": {"principal": "50000", "rate": "7", "years": "5"}, **extra}
        return self.api("/api/saved", body, client).get_json()


class TestPages(Base):
    def test_pages(self):
        for url in ["/", "/about", "/saved"] + [f"/calculator/{k}" for k in CALCS]:
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertEqual(self.c.get("/calculator/nope").status_code, 404)

    def test_share_link_fills_form(self):
        html = self.c.get("/calculator/loan?amount=777000&months=60").get_data(as_text=True)
        self.assertIn('value="777000"', html)

    def test_author_credit(self):
        self.assertIn("Jean Michel Mujyambere", self.c.get("/").get_data(as_text=True))


class TestApi(Base):
    def test_every_calculator_with_defaults(self):
        for kind, calc in CALCS.items():
            data = {f["name"]: f.get("default", "") for f in calc["fields"]}
            r = self.api(f"/api/calc/{kind}", data)
            self.assertEqual(r.status_code, 200, kind)
            self.assertIn("summary", r.get_json())

    def test_field_error(self):
        r = self.api("/api/calc/bond", {"price": "", "rate": 9, "term": 20})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(list(r.get_json()["errors"]), ["price"])

    def test_csrf_required(self):
        r = self.c.post("/api/calc/loan", json={"amount": 1000, "rate": 10, "months": 12})
        self.assertEqual(r.status_code, 400)

    def test_unknown_calculator(self):
        self.assertEqual(self.api("/api/calc/magic", {}).status_code, 404)


class TestSaved(Base):
    def test_save_open_update_rename_delete(self):
        d = self.save()
        self.assertTrue(d["ok"])
        self.assertIn("My plan", self.c.get("/saved").get_data(as_text=True))
        html = self.c.get(f"/calculator/investment?saved={d['id']}").get_data(as_text=True)
        self.assertIn('value="50000"', html)
        u = self.save(name="My plan v2", id=d["id"])
        self.assertTrue(u["updated"])
        self.c.post(f"/saved/{d['id']}/rename", data={"name": "Retirement fund", "csrf_token": "tok"})
        self.assertIn("Retirement fund", self.c.get("/saved").get_data(as_text=True))
        self.c.post(f"/saved/{d['id']}/delete", data={"csrf_token": "tok"})
        self.assertNotIn("Retirement fund", self.c.get("/saved").get_data(as_text=True))

    def test_invalid_inputs_not_saved(self):
        r = self.api("/api/saved", {"kind": "investment", "inputs": {"principal": "x", "rate": "7", "years": "5"}})
        self.assertEqual(r.status_code, 400)

    def test_other_people_cannot_see_or_change_mine(self):
        d = self.save(name="Private plan")
        other = self.new_client()
        self.assertNotIn("Private plan", other.get("/saved").get_data(as_text=True))
        self.assertNotIn('value="50000"', other.get(f"/calculator/investment?saved={d['id']}").get_data(as_text=True))
        self.assertEqual(other.post(f"/saved/{d['id']}/delete", data={"csrf_token": "tok"}).status_code, 404)
        self.assertEqual(self.api("/api/saved", {"kind": "investment", "id": d["id"], "inputs": {"principal": "1", "rate": "1", "years": "1"}},
                                  other).status_code, 404)
        self.assertIn("Private plan", self.c.get("/saved").get_data(as_text=True))

    def test_delete_all(self):
        self.save("A")
        self.save("B")
        self.c.post("/saved/delete-all", data={"csrf_token": "tok"})
        html = self.c.get("/saved").get_data(as_text=True)
        self.assertIn("Nothing saved yet", html)

    def test_unknown_fields_are_dropped(self):
        d = self.save(inputs={"principal": "1000", "rate": "5", "years": "2", "evil": "<script>"})
        html = self.c.get(f"/calculator/investment?saved={d['id']}").get_data(as_text=True)
        self.assertNotIn("<script>alert", html)


if __name__ == "__main__":
    unittest.main()
