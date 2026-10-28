"""Unit tests for the finance maths (calculators.py)."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calculators import CalcError, apr, bond, investment, loan, payment, retirement, savings_goal  # noqa: E402


class TestOriginalFormulas(unittest.TestCase):
    """The three formulas of the original capstone program must still give the same answers."""

    def test_simple_interest(self):
        r = investment({"principal": 10000, "rate": 8, "years": 10, "interest_type": "simple"})
        self.assertAlmostEqual(r["summary"]["final_value"], 10000 * (1 + 0.08 * 10), places=2)

    def test_compound_interest_yearly(self):
        r = investment({"principal": 10000, "rate": 8, "years": 10, "interest_type": "compound", "compounding": "annually"})
        self.assertAlmostEqual(r["summary"]["final_value"], 10000 * math.pow(1.08, 10), places=2)

    def test_bond_repayment(self):
        i = 0.085 / 12
        expected = (i * 1_000_000) / (1 - math.pow(1 + i, -240))
        r = bond({"price": 1_000_000, "rate": 8.5, "term": 240, "term_unit": "months"})
        self.assertAlmostEqual(r["summary"]["monthly_payment"], expected, places=2)


class TestInvestment(unittest.TestCase):
    def test_monthly_compounding_is_more(self):
        yearly = investment({"principal": 10000, "rate": 12, "years": 5, "compounding": "annually"})["summary"]["final_value"]
        monthly = investment({"principal": 10000, "rate": 12, "years": 5, "compounding": "monthly"})["summary"]["final_value"]
        self.assertAlmostEqual(monthly, 10000 * (1 + 0.01) ** 60, places=2)
        self.assertGreater(monthly, yearly)

    def test_monthly_deposits_without_interest(self):
        s = investment({"principal": 0, "monthly_deposit": 1000, "rate": 0, "years": 2})["summary"]
        self.assertEqual((s["final_value"], s["total_interest"]), (24000, 0))

    def test_inflation_lowers_real_value(self):
        s = investment({"principal": 10000, "rate": 5, "years": 10, "inflation": 5})["summary"]
        self.assertAlmostEqual(s["real_value"], 10000, places=0)   # growth and inflation cancel out

    def test_schedule_and_comparison(self):
        r = investment({"principal": 5000, "rate": 10, "years": 3})
        self.assertEqual([row["year"] for row in r["schedule"]], [1, 2, 3])
        self.assertEqual(r["summary"]["other_type"]["final_value"], 5000 * 1.3)

    def test_errors(self):
        for data, field in [({"rate": 5, "years": 3}, "principal"), ({"principal": 1, "rate": -1, "years": 3}, "rate"),
                            ({"principal": 1, "rate": 5, "years": 0}, "years"), ({"principal": "abc", "rate": 5, "years": 3}, "principal"),
                            ({"principal": 1, "rate": 5, "years": 2.5}, "years"),
                            ({"principal": 1, "rate": 5, "years": 3, "interest_type": "magic"}, "interest_type"),
                            ({"principal": 0, "monthly_deposit": 0, "rate": 5, "years": 3}, "principal")]:
            with self.subTest(data=data), self.assertRaises(CalcError) as e:
                investment(data)
            self.assertEqual(e.exception.field, field)

    def test_number_with_commas(self):
        s = investment({"principal": "1,00,000", "rate": "8", "years": "1"})["summary"]
        self.assertAlmostEqual(s["final_value"], 108000, places=2)


class TestBondAndLoan(unittest.TestCase):
    def test_schedule_adds_up(self):
        r = bond({"price": 2_000_000, "deposit": 400_000, "rate": 9, "term": 15})
        s = r["summary"]
        self.assertEqual(s["loan_amount"], 1_600_000)
        self.assertEqual(len(r["schedule"]), 180)
        self.assertAlmostEqual(sum(x["principal"] for x in r["schedule"]), 1_600_000, delta=1)
        self.assertAlmostEqual(sum(x["interest"] for x in r["schedule"]), s["total_interest"], delta=1)
        self.assertEqual(r["schedule"][-1]["balance"], 0)
        self.assertEqual(len(r["yearly"]), 15)

    def test_extra_payment_saves_interest(self):
        base = bond({"price": 3_000_000, "rate": 9, "term": 20})["summary"]
        extra = bond({"price": 3_000_000, "rate": 9, "term": 20, "extra": 5000})["summary"]
        self.assertLess(extra["payoff_months"], 240)
        self.assertGreater(extra["interest_saved"], 0)
        self.assertAlmostEqual(base["total_interest"] - extra["total_interest"], extra["interest_saved"], delta=1)

    def test_zero_interest(self):
        self.assertEqual(payment(12000, 0, 12), 1000)

    def test_affordability(self):
        s = bond({"price": 1_000_000, "rate": 10, "term": 10, "income": 100_000})["summary"]
        self.assertEqual(s["affordability"], "good")
        s = bond({"price": 1_000_000, "rate": 10, "term": 10, "income": 30_000})["summary"]
        self.assertEqual(s["affordability"], "risky")

    def test_bond_errors(self):
        with self.assertRaises(CalcError):
            bond({"price": 100, "deposit": 100, "rate": 9, "term": 10})
        with self.assertRaises(CalcError):
            bond({"price": 100, "rate": 9, "term": 10, "start": "not-a-date"})

    def test_start_month(self):
        r = bond({"price": 100000, "rate": 9, "term": 1, "start": "2027-03"})
        self.assertEqual(r["schedule"][0]["date"], "2027-03-01")
        self.assertEqual(r["summary"]["payoff_date"], "2028-02-01")

    def test_apr_includes_fee(self):
        no_fee = loan({"amount": 100000, "rate": 12, "months": 36})["summary"]
        with_fee = loan({"amount": 100000, "rate": 12, "months": 36, "fee": 2})["summary"]
        self.assertAlmostEqual(no_fee["apr"], 12, places=1)
        self.assertGreater(with_fee["apr"], 12)
        self.assertEqual(with_fee["fee"], 2000)

    def test_apr_function(self):
        pay = payment(50000, 0.10, 24)
        self.assertAlmostEqual(apr(50000, pay, 24), 0.10, places=4)


class TestGoalAndRetirement(unittest.TestCase):
    def test_goal_reached_exactly(self):
        r = savings_goal({"target": 100000, "current": 10000, "years": 3, "rate": 6})
        self.assertAlmostEqual(r["schedule"][-1]["balance"], 100000, delta=0.5)

    def test_goal_without_interest(self):
        s = savings_goal({"target": 12000, "years": 1, "rate": 0})["summary"]
        self.assertEqual(s["monthly_saving"], 1000)

    def test_goal_already_reached(self):
        s = savings_goal({"target": 1000, "current": 5000, "years": 1, "rate": 5})["summary"]
        self.assertTrue(s["already_reached"])
        self.assertEqual(s["monthly_saving"], 0)

    def test_retirement_extra_closes_gap(self):
        data = {"age": 30, "retire_age": 60, "life_expectancy": 85, "savings": 100000, "monthly": 5000,
                "return_before": 10, "return_after": 6, "inflation": 5, "income_wanted": 50000}
        s = retirement(data)["summary"]
        self.assertFalse(s["on_track"])
        fixed = retirement({**data, "monthly": 5000 + s["extra_monthly"] + 1})["summary"]
        self.assertTrue(fixed["on_track"])
        self.assertIsNone(fixed["money_lasts_until"])

    def test_retirement_age_rules(self):
        with self.assertRaises(CalcError) as e:
            retirement({"age": 50, "retire_age": 45, "life_expectancy": 80, "return_before": 8, "return_after": 5})
        self.assertEqual(e.exception.field, "retire_age")


if __name__ == "__main__":
    unittest.main()
