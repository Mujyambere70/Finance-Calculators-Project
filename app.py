"""
CalcWise - finance calculators web app (Flask).

Run:  pip install -r requirements.txt
      python app.py      ->  http://127.0.0.1:5000

The maths is in calculators.py. The page sends the form to /api/calc/<kind> while you type
and draws the answer, the chart and the schedule. Calculations can be saved, renamed and deleted
("My calculations"); they belong to your browser (a private cookie), no sign-up needed.
"""

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

from calculators import CalcError, calculate
from scientific import SciError, convert, evaluate
from forms import CALCS, CURRENCIES, CURRENCY_GROUPS, CURRENCY_INFO, CURRENCY_LOCALES
from rates import RatesUnavailable, RateService
from countries import COUNTRY_LIST
from generators import (EMAIL_TYPES, PASSPORT_FORMATS, GenError, generate, phonenumbers as PHONE_LIB,
                        totp_state, totp_verify)

BASE = os.path.dirname(os.path.abspath(__file__))
OWNER_COOKIE = "cw_owner"

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    inputs     TEXT NOT NULL,
    summary    TEXT NOT NULL,
    currency   TEXT NOT NULL DEFAULT 'INR',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_owner ON saved(owner, updated_at);
"""


def create_app(db_path=None, rate_fetch=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["DB"] = db_path or os.path.join(BASE, "calcwise.db")

    @contextmanager
    def db():
        con = sqlite3.connect(app.config["DB"])
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    with db() as con:
        con.executescript(SCHEMA)
    fx = RateService(app.config["DB"], **({"fetch": rate_fetch} if rate_fetch else {}))
    app.fx = fx

    def now():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ---------------------------------------------------------------- owner cookie + CSRF
    @app.before_request
    def before():
        g.owner = request.cookies.get(OWNER_COOKIE)
        g.new_owner = not g.owner or len(g.owner) != 32
        if g.new_owner:
            g.owner = secrets.token_hex(16)
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        if request.method == "POST":
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not token or not secrets.compare_digest(token, session["csrf"]):
                if request.path.startswith("/api/"):
                    return jsonify(error="Page expired - please reload."), 400
                abort(400)

    @app.after_request
    def after(resp):
        if g.get("new_owner"):
            resp.set_cookie(OWNER_COOKIE, g.owner, max_age=3 * 365 * 24 * 3600, httponly=True, samesite="Lax")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.context_processor
    def globals_():
        with db() as con:
            n = con.execute("SELECT COUNT(*) FROM saved WHERE owner = ?", (g.owner,)).fetchone()[0]
        return {"CALCS": CALCS, "CURRENCIES": CURRENCIES, "CURRENCY_GROUPS": CURRENCY_GROUPS,
                "CURRENCY_LOCALES": CURRENCY_LOCALES, "csrf_token": session.get("csrf", ""), "saved_count": n,
                "year": datetime.now().year}

    # ---------------------------------------------------------------- pages
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/calculator/<kind>")
    def calculator(kind):
        if kind not in CALCS:
            abort(404)
        values = {f["name"]: f.get("default", "") for f in CALCS[kind]["fields"]}
        if "start" in values and not values["start"]:          # first repayment: next month
            today = datetime.now()
            values["start"] = f"{today.year + today.month // 12}-{today.month % 12 + 1:02d}"
        values.update({k: v for k, v in request.args.items() if k in values})   # shareable links
        saved_item = None
        if request.args.get("saved", "").isdigit():
            with db() as con:
                row = con.execute("SELECT * FROM saved WHERE id = ? AND owner = ? AND kind = ?",
                                  (int(request.args["saved"]), g.owner, kind)).fetchone()
            if row:
                saved_item = dict(row)
                values.update(json.loads(row["inputs"]))
        return render_template("calculator.html", kind=kind, calc=CALCS[kind], values=values, saved=saved_item)

    @app.route("/saved")
    def saved_list():
        with db() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM saved WHERE owner = ? ORDER BY updated_at DESC",
                                                 (g.owner,))]
        for r in rows:
            r["summary"] = json.loads(r["summary"])
        return render_template("saved.html", rows=rows)

    # ---------------------------------------------------------------- currency converter + live rates
    @app.route("/converter")
    def converter():
        return render_template("converter.html", INFO=CURRENCY_INFO)

    @app.route("/api/rates")
    def api_rates():
        try:
            data = fx.latest(force=request.args.get("refresh") == "1" and app.config.get("TESTING", False))
        except RatesUnavailable as e:
            return jsonify(error="Live rates are not available right now. Please check your internet connection.",
                           detail=str(e)), 503
        resp = jsonify(data)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/api/rates/history")
    def api_rates_history():
        src, dst = request.args.get("from", "USD").upper(), request.args.get("to", "EUR").upper()
        try:
            days = min(max(int(request.args.get("days", 30)), 7), 365)
        except ValueError:
            days = 30
        if src not in CURRENCY_INFO and src != "USD" or dst not in CURRENCY_INFO and dst != "USD":
            return jsonify(error="Unknown currency."), 400
        points = fx.history(src, dst, days)
        if not points:
            return jsonify(error="History is not available right now.", points=[]), 503
        return jsonify(points=points, source="currency-api (Fawaz Ahmed)")

    @app.route("/scientific")
    def scientific():
        return render_template("scientific.html")

    @app.route("/api/scientific", methods=["POST"])
    def api_scientific():
        body = request.get_json(silent=True) or {}
        variables = {}
        for name in ("ans", "Ans", "M"):
            try:
                variables[name] = float(body.get(name.lower() if name != "M" else "memory", 0) or 0)
            except (TypeError, ValueError):
                variables[name] = 0.0
        try:
            r = evaluate(str(body.get("expr", "")), str(body.get("angle", "deg")).lower(), variables)
        except SciError as e:
            return jsonify(error=str(e)), 400
        r["extras"] = convert(r["value"], body.get("angle"))
        return jsonify(r)

    # ---------------------------------------------------------------- generators
    GEN_TOOLS = {"otp": "OTP & authenticator", "password": "Password", "email": "Email",
                 "phone": "Phone number", "passport": "Passport number"}

    @app.route("/generators")
    @app.route("/generators/<tool>")
    def generators(tool="otp"):
        if tool not in GEN_TOOLS:
            abort(404)
        groups = {}
        for c in COUNTRY_LIST:
            groups.setdefault(c["region"], []).append(c)
        order = [r for r in CURRENCY_GROUPS if r in groups]
        return render_template("generators.html", tool=tool, TOOLS=GEN_TOOLS, EMAIL_TYPES=EMAIL_TYPES,
                               COUNTRY_GROUPS={r: groups[r] for r in order}, n_countries=len(COUNTRY_LIST),
                               passport_known=sum(1 for v in PASSPORT_FORMATS.values() if v[1] == "known"),
                               phone_lib=PHONE_LIB is not None)

    @app.route("/api/generate/<tool>", methods=["POST"])
    def api_generate(tool):
        opts = request.get_json(silent=True) or {}
        try:
            if tool == "totp":
                return jsonify(totp_state(opts))
            if tool == "totp-verify":
                return jsonify(totp_verify(opts))
            return jsonify(generate(tool, opts))
        except GenError as e:
            status = 404 if e.field == "tool" else 400
            return jsonify(error=str(e), field=e.field), status

    @app.route("/about")
    def about():
        return render_template("about.html")

    # ---------------------------------------------------------------- API
    def run(kind, data):
        try:
            return calculate(kind, data), None
        except CalcError as e:
            return None, {e.field: e.message}

    @app.route("/api/calc/<kind>", methods=["POST"])
    def api_calc(kind):
        if kind not in CALCS:
            return jsonify(error="Unknown calculator."), 404
        result, errors = run(kind, request.get_json(silent=True) or {})
        if errors:
            return jsonify(errors=errors), 400
        return jsonify(result)

    def clean_inputs(kind, data):
        names = {f["name"] for f in CALCS[kind]["fields"]}
        return {k: str(v)[:40] for k, v in (data or {}).items() if k in names}

    @app.route("/api/saved", methods=["POST"])
    def api_save():
        body = request.get_json(silent=True) or {}
        kind = body.get("kind")
        if kind not in CALCS:
            return jsonify(error="Unknown calculator."), 400
        name = " ".join(str(body.get("name") or "").split())[:60] or f"{CALCS[kind]['title']} {datetime.now():%d %b %H:%M}"
        inputs = clean_inputs(kind, body.get("inputs"))
        currency = body.get("currency") if body.get("currency") in CURRENCIES else "RWF"
        result, errors = run(kind, inputs)
        if errors:
            return jsonify(errors=errors), 400
        with db() as con:
            n = con.execute("SELECT COUNT(*) FROM saved WHERE owner = ?", (g.owner,)).fetchone()[0]
            if body.get("id") and str(body["id"]).isdigit():         # update my existing calculation
                cur = con.execute("UPDATE saved SET name = ?, inputs = ?, summary = ?, currency = ?, updated_at = ? "
                                  "WHERE id = ? AND owner = ?", (name, json.dumps(inputs), json.dumps(result["summary"]),
                                                                 currency, now(), int(body["id"]), g.owner))
                if cur.rowcount == 0:
                    return jsonify(error="Calculation not found."), 404
                return jsonify(ok=True, id=int(body["id"]), name=name, updated=True)
            if n >= 200:
                return jsonify(error="You can keep up to 200 calculations. Delete some old ones first."), 400
            cur = con.execute("INSERT INTO saved (owner, kind, name, inputs, summary, currency, created_at, updated_at) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (g.owner, kind, name, json.dumps(inputs),
                                                                  json.dumps(result["summary"]), currency, now(), now()))
            return jsonify(ok=True, id=cur.lastrowid, name=name, updated=False)

    @app.route("/saved/<int:sid>/rename", methods=["POST"])
    def saved_rename(sid):
        name = " ".join((request.form.get("name") or "").split())[:60]
        if len(name) < 2:
            flash("Name must have at least 2 characters.", "error")
        else:
            with db() as con:
                if con.execute("UPDATE saved SET name = ?, updated_at = ? WHERE id = ? AND owner = ?",
                               (name, now(), sid, g.owner)).rowcount == 0:
                    abort(404)
            flash("Renamed.", "success")
        return redirect(url_for("saved_list"))

    @app.route("/saved/<int:sid>/delete", methods=["POST"])
    def saved_delete(sid):
        with db() as con:
            if con.execute("DELETE FROM saved WHERE id = ? AND owner = ?", (sid, g.owner)).rowcount == 0:
                abort(404)
        flash("Calculation deleted.", "success")
        return redirect(url_for("saved_list"))

    @app.route("/saved/delete-all", methods=["POST"])
    def saved_delete_all():
        with db() as con:
            n = con.execute("DELETE FROM saved WHERE owner = ?", (g.owner,)).rowcount
        flash(f"{n} calculations deleted.", "success")
        return redirect(url_for("saved_list"))

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, text="This page does not exist."), 404

    @app.errorhandler(400)
    def bad(e):
        return render_template("error.html", code=400, text="This form expired. Please go back and reload the page."), 400

    return app


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
