"""Tests for the scientific calculator engine and its API."""

import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from scientific import SciError, convert, evaluate  # noqa: E402


def val(expr, angle="deg", **v):
    return evaluate(expr, angle, v)["value"]


class TestArithmetic(unittest.TestCase):
    def test_order_of_operations(self):
        cases = {"2+3*4": 14, "(2+3)*4": 20, "2^3^2": 512, "-2^2": -4, "(-2)^2": 4, "10-4-3": 3, "100/10/5": 2,
                 "2×3÷4": 1.5, "7−10": -3, "10 mod 3": 1, "20%*150": 30, "1.5E3/3": 500, ".5+.25": 0.75}
        for expr, expected in cases.items():
            with self.subTest(expr=expr):
                self.assertAlmostEqual(val(expr), expected)

    def test_implicit_multiplication(self):
        self.assertAlmostEqual(val("3(4+5)"), 27)
        self.assertAlmostEqual(val("2π"), 2 * math.pi, places=9)
        self.assertAlmostEqual(val("(1+1)(2+2)"), 8)
        self.assertAlmostEqual(val("2sin(30)"), 1)

    def test_floating_noise_removed(self):
        self.assertEqual(val("0.1+0.2"), 0.3)
        self.assertEqual(val("sin(180)"), 0)
        self.assertEqual(evaluate("1/3")["display"], "0.333333333333")


class TestFunctions(unittest.TestCase):
    def test_trig_in_degrees_radians_grads(self):
        self.assertAlmostEqual(val("sin(30)"), 0.5)
        self.assertAlmostEqual(val("cos(pi)", "rad"), -1)
        self.assertAlmostEqual(val("sin(100)", "grad"), 1)
        self.assertAlmostEqual(val("asin(1)"), 90)
        self.assertAlmostEqual(val("atan(1)", "rad"), math.pi / 4, places=9)
        self.assertAlmostEqual(val("sinh(1)"), math.sinh(1), places=9)

    def test_logs_roots_powers(self):
        self.assertAlmostEqual(val("log(1000)"), 3)
        self.assertAlmostEqual(val("log(8, 2)"), 3)
        self.assertAlmostEqual(val("ln(e^2)"), 2)
        self.assertAlmostEqual(val("log2(1024)"), 10)
        self.assertAlmostEqual(val("√16+∛27"), 7)
        self.assertAlmostEqual(val("∛-8"), -2)
        self.assertAlmostEqual(val("root(625, 4)"), 5)
        self.assertAlmostEqual(val("2^0.5"), math.sqrt(2), places=9)
        self.assertAlmostEqual(val("4^(-1)"), 0.25)

    def test_factorial_and_combinatorics(self):
        self.assertEqual(val("5!"), 120)
        self.assertEqual(val("3!!"), 720)
        self.assertAlmostEqual(val("0.5!"), math.sqrt(math.pi) / 2, places=9)
        self.assertEqual(val("nCr(10, 3)"), 120)
        self.assertEqual(val("nPr(5, 2)"), 20)
        self.assertEqual(val("gcd(12, 18) + lcm(4, 6)"), 18)

    def test_other_functions_and_variables(self):
        self.assertEqual(val("|−7|+abs(-3)"), 10)
        self.assertEqual(val("max(3, 9, 4) - min(3, 9, 4)"), 6)
        self.assertEqual(val("floor(2.7)+ceil(2.1)+round(2.567, 2)"), 7.57)
        self.assertEqual(val("hypot(3, 4)"), 5)
        self.assertEqual(val("Ans*2", Ans=21), 42)
        self.assertEqual(val("M+1", M=4), 5)


class TestErrors(unittest.TestCase):
    def test_friendly_errors(self):
        cases = {"1/0": "Division by zero", "sqrt(-1)": "not real", "log(0)": "> 0", "(2+3": "missing",
                 "2+": "not complete", "tan(90)": "cos = 0", "abc": "Unknown name", "171!": "too large",
                 "asin(2)": "between", "2)": "'('", "1e300*1e300": "too large", "": "Type an expression",
                 "(-8)^(1/3)": "not real", "nCr(3, 5)": "bigger", "log(5, 1)": "base", "2 $ 3": "understand",
                 "sin(1, 2)": "needs 1"}
        for expr, part in cases.items():
            with self.subTest(expr=expr):
                with self.assertRaises(SciError) as e:
                    evaluate(expr)
                self.assertIn(part, str(e.exception))

    def test_no_code_execution(self):
        for expr in ["__import__('os')", "open('x')", "().__class__", "exit()"]:
            with self.assertRaises(SciError):
                evaluate(expr)

    def test_too_long(self):
        with self.assertRaises(SciError):
            evaluate("1+" * 200 + "1")


class TestDisplay(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(evaluate("2^40")["display"], "1099511627776")
        self.assertEqual(evaluate("2^70")["display"], "1.1805916207×10^21")
        self.assertEqual(evaluate("1/10^9")["display"], "1×10^-9")

    def test_extras(self):
        self.assertEqual(convert(255.0, "deg")["hex"], "FF")
        self.assertEqual(convert(10.0, "deg")["bin"], "1010")
        self.assertEqual(convert(0.75, "deg")["fraction"], "3/4")


class TestScientificApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = create_app(os.path.join(self.tmp.name, "t.db")).test_client()
        self.c.get("/")
        with self.c.session_transaction() as s:
            s["csrf"] = "tok"

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, body):
        return self.c.post("/api/scientific", json=body, headers={"X-CSRF-Token": "tok"})

    def test_page_and_api(self):
        self.assertEqual(self.c.get("/scientific").status_code, 200)
        r = self.post({"expr": "sin(pi/6)", "angle": "RAD"})
        self.assertAlmostEqual(r.get_json()["value"], 0.5)
        r = self.post({"expr": "Ans + M", "ans": 2, "memory": 3})
        self.assertEqual(r.get_json()["value"], 5)

    def test_api_error(self):
        r = self.post({"expr": "1/0"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "Division by zero.")
        self.assertEqual(self.post({"expr": "1", "angle": "turns"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
