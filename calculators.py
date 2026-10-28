"""
calculators.py - the finance maths of CalcWise (no web code here, so it is easy to test).

Calculators
    investment()    lump sum + optional monthly deposits, simple or compound interest,
                    compounding frequency, inflation-adjusted value, year-by-year table
    bond()          home loan (bond / mortgage): monthly repayment, extra payments,
                    property tax + insurance, affordability check, amortization schedule
    loan()          personal / car loan: EMI, processing fee and the real APR
    savings_goal()  how much to save every month to reach a target
    retirement()    savings at retirement, the monthly income they can pay, and the gap

The two original formulas from the HyperionDev capstone are kept exactly:
    simple interest   A = P (1 + r t)
    compound interest A = P (1 + r) ^ t
    bond repayment    x = (i P) / (1 - (1 + i) ^ (-n))
"""

import math
from datetime import date


class CalcError(ValueError):
    """Wrong input - the message is shown next to the field."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
        self.message = message


# ------------------------------------------------------------------ input helpers

def number(data, field, label, minimum=None, maximum=None, default=None, integer=False):
    raw = data.get(field, default)
    if raw in (None, ""):
        if default is not None:
            return default
        raise CalcError(field, f"{label} is required.")
    try:
        value = float(str(raw).replace(",", "").replace(" ", ""))
    except ValueError:
        raise CalcError(field, f"{label} must be a number.")
    if not math.isfinite(value):
        raise CalcError(field, f"{label} must be a number.")
    if integer:
        if value != int(value):
            raise CalcError(field, f"{label} must be a whole number.")
        value = int(value)
    if minimum is not None and value < minimum:
        raise CalcError(field, f"{label} must be at least {minimum:,g}.")
    if maximum is not None and value > maximum:
        raise CalcError(field, f"{label} must be at most {maximum:,g}.")
    return value


def choice(data, field, label, options, default=None):
    value = str(data.get(field, default) or "").lower()
    if value not in options:
        raise CalcError(field, f"Please choose a valid {label.lower()}.")
    return value


def r2(x):
    return round(x + 0.0, 2)


def add_months(start, months):
    y, m = divmod(start.month - 1 + months, 12)
    return date(start.year + y, m + 1, min(start.day, 28))


COMPOUNDING = {"annually": 1, "semi-annually": 2, "quarterly": 4, "monthly": 12, "daily": 365}
MAX_MONEY = 1e12


# ------------------------------------------------------------------ 1. investment

def investment(data):
    principal = number(data, "principal", "Initial deposit", 0, MAX_MONEY)
    rate = number(data, "rate", "Interest rate", 0, 100) / 100
    years = number(data, "years", "Number of years", 1, 100, integer=True)
    kind = choice(data, "interest_type", "Interest type", ("simple", "compound"), "compound")
    freq = choice(data, "compounding", "Compounding", COMPOUNDING, "annually")
    monthly = number(data, "monthly_deposit", "Monthly deposit", 0, MAX_MONEY, default=0)
    inflation = number(data, "inflation", "Inflation", 0, 50, default=0) / 100
    if principal == 0 and monthly == 0:
        raise CalcError("principal", "Enter an initial deposit or a monthly deposit.")

    n = COMPOUNDING[freq]
    month_rate = (1 + rate / n) ** (n / 12) - 1          # same yearly growth as the chosen compounding
    balance, deposited, simple_interest = principal, principal, 0.0
    rows = []
    for month in range(1, years * 12 + 1):
        if kind == "simple":
            simple_interest += deposited * rate / 12     # interest only on the money deposited
        else:
            balance *= 1 + month_rate
        balance += monthly                                # deposit at the end of the month
        deposited += monthly
        if month % 12 == 0:
            value = deposited + simple_interest if kind == "simple" else balance
            rows.append({"year": month // 12, "deposited": r2(deposited), "interest": r2(value - deposited),
                         "balance": r2(value), "real_value": r2(value / (1 + inflation) ** (month // 12))})
    final = rows[-1]["balance"]
    effective = (1 + rate / n) ** n - 1 if kind == "compound" else rate
    # the same money with the other interest type - shown as a comparison
    other = investment({**data, "interest_type": "simple" if kind == "compound" else "compound",
                        "_compare": "1"}) if not data.get("_compare") else None
    return {
        "summary": {
            "final_value": final,
            "total_deposited": rows[-1]["deposited"],
            "total_interest": rows[-1]["interest"],
            "real_value": rows[-1]["real_value"],
            "effective_rate": r2(effective * 100),
            "growth_multiple": r2(final / rows[-1]["deposited"]) if rows[-1]["deposited"] else 0,
            "other_type": None if other is None else {"type": "simple" if kind == "compound" else "compound",
                                                      "final_value": other["summary"]["final_value"]},
        },
        "sentence": (f"After {years} year{'s' * (years > 1)} with {kind} interest at {rate * 100:g}% a year "
                     f"you will have {{final_value}}: you put in {{total_deposited}} and earn {{total_interest}} interest."),
        "schedule": rows,
    }


# ------------------------------------------------------------------ 2. bond / home loan

def payment(principal, annual_rate, months):
    """Monthly repayment of an amortizing loan (the original capstone formula)."""
    i = annual_rate / 12
    if principal <= 0:
        return 0.0
    if i == 0:
        return principal / months
    return (i * principal) / (1 - (1 + i) ** -months)


def amortize(principal, annual_rate, months, extra=0.0, start=None):
    i = annual_rate / 12
    pay = payment(principal, annual_rate, months)
    balance, rows, total_interest, m = principal, [], 0.0, 0
    start = start or date.today().replace(day=1)
    while balance > 0.005 and m < months:
        m += 1
        interest = balance * i
        principal_part = min(pay + extra - interest, balance)
        if principal_part <= 0:
            raise CalcError("rate", "The repayment does not even cover the interest.")
        balance -= principal_part
        total_interest += interest
        rows.append({"month": m, "date": add_months(start, m - 1).isoformat(), "payment": r2(interest + principal_part),
                     "interest": r2(interest), "principal": r2(principal_part), "balance": r2(max(balance, 0))})
    return pay, rows, total_interest


def yearly(rows):
    out = {}
    for r in rows:
        y = (r["month"] - 1) // 12 + 1
        o = out.setdefault(y, {"year": y, "paid": 0, "interest": 0, "principal": 0, "balance": 0})
        o["paid"] += r["payment"]
        o["interest"] += r["interest"]
        o["principal"] += r["principal"]
        o["balance"] = r["balance"]
    return [{k: r2(v) if k != "year" else v for k, v in o.items()} for o in out.values()]


def bond(data):
    price = number(data, "price", "House price", 1, MAX_MONEY)
    deposit = number(data, "deposit", "Deposit", 0, MAX_MONEY, default=0)
    if deposit >= price:
        raise CalcError("deposit", "The deposit must be smaller than the house price.")
    rate = number(data, "rate", "Interest rate", 0, 50) / 100
    unit = choice(data, "term_unit", "Term unit", ("years", "months"), "years")
    term = number(data, "term", "Repayment period", 1, 600 if unit == "months" else 50, integer=True)
    months = term * 12 if unit == "years" else term
    extra = number(data, "extra", "Extra monthly payment", 0, MAX_MONEY, default=0)
    tax = number(data, "property_tax", "Property tax per year", 0, MAX_MONEY, default=0)
    insurance = number(data, "insurance", "Home insurance per year", 0, MAX_MONEY, default=0)
    income = number(data, "income", "Monthly income", 0, MAX_MONEY, default=0)
    raw_start = str(data.get("start") or "")
    if len(raw_start) == 7:                       # "2026-11" from a month picker
        raw_start += "-01"
    try:
        start = date.fromisoformat(raw_start or date.today().replace(day=1).isoformat())
    except ValueError:
        raise CalcError("start", "Please enter a valid start date.")

    loan_amount = price - deposit
    pay, rows, interest = amortize(loan_amount, rate, months, extra, start)
    base_interest = amortize(loan_amount, rate, months)[2] if extra else interest
    monthly_cost = pay + extra + (tax + insurance) / 12
    ratio = monthly_cost / income * 100 if income else None
    s = {
        "loan_amount": r2(loan_amount),
        "deposit_percent": r2(deposit / price * 100),
        "monthly_payment": r2(pay),
        "monthly_total": r2(monthly_cost),
        "total_interest": r2(interest),
        "total_paid": r2(loan_amount + interest),
        "months": months,
        "payoff_months": len(rows),
        "payoff_date": rows[-1]["date"],
        "interest_saved": r2(base_interest - interest),
        "months_saved": months - len(rows),
        "income_ratio": r2(ratio) if ratio is not None else None,
        "affordability": None if ratio is None else ("good" if ratio <= 28 else "stretch" if ratio <= 36 else "risky"),
    }
    sentence = "Your monthly bond repayment is {monthly_payment}. Over the loan you pay {total_interest} in interest."
    if extra:
        sentence += f" Paying {{extra}} extra a month finishes the loan {s['months_saved']} months early."
    return {"summary": s, "sentence": sentence, "schedule": rows, "yearly": yearly(rows), "extra": r2(extra)}


# ------------------------------------------------------------------ 3. personal / car loan

def apr(amount_received, pay, months):
    """Annual rate at which the money really received is paid back (finds the rate by bisection)."""
    if amount_received <= 0:
        return 0.0
    lo, hi = 0.0, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        i = mid / 12
        pv = pay * months if i == 0 else pay * (1 - (1 + i) ** -months) / i
        lo, hi = (mid, hi) if pv > amount_received else (lo, mid)
    return (lo + hi) / 2


def loan(data):
    amount = number(data, "amount", "Loan amount", 1, MAX_MONEY)
    rate = number(data, "rate", "Interest rate", 0, 60) / 100
    months = number(data, "months", "Loan period", 1, 480, integer=True)
    fee_pct = number(data, "fee", "Processing fee", 0, 10, default=0) / 100
    pay, rows, interest = amortize(amount, rate, months)
    fee = amount * fee_pct
    real = apr(amount - fee, pay, months) * 100
    return {
        "summary": {"monthly_payment": r2(pay), "total_interest": r2(interest), "fee": r2(fee),
                    "total_cost": r2(interest + fee), "total_paid": r2(amount + interest + fee),
                    "apr": r2(real), "interest_share": r2(interest / (amount + interest) * 100) if amount else 0},
        "sentence": "Your EMI is {monthly_payment} for " + f"{months} months" +
                    ". The loan costs {total_cost} in interest and fees - a real yearly rate (APR) of {apr}.",
        "schedule": rows,
        "yearly": yearly(rows),
    }


# ------------------------------------------------------------------ 4. savings goal

def savings_goal(data):
    target = number(data, "target", "Goal amount", 1, MAX_MONEY)
    current = number(data, "current", "Money you already have", 0, MAX_MONEY, default=0)
    years = number(data, "years", "Years", 0.25, 60)
    rate = number(data, "rate", "Interest rate", 0, 50, default=0) / 100
    months = max(1, round(years * 12))
    i = rate / 12
    grown = current * (1 + i) ** months
    if grown >= target:
        need = 0.0
    elif i == 0:
        need = (target - grown) / months
    else:
        need = (target - grown) * i / ((1 + i) ** months - 1)
    balance, rows = current, []
    for m in range(1, months + 1):
        balance = balance * (1 + i) + need
        if months <= 36 or m % 12 == 0 or m == months:     # short goals: every month, long goals: every year
            rows.append({"month": m, "year": r2(m / 12), "deposited": r2(current + need * m), "balance": r2(balance)})
    deposits = need * months
    return {
        "summary": {"monthly_saving": r2(need), "weekly_saving": r2(need * 12 / 52), "total_deposits": r2(deposits),
                    "interest_earned": r2(max(balance - current - deposits, 0)), "months": months,
                    "goal_date": add_months(date.today(), months).isoformat(), "already_reached": need == 0},
        "sentence": ("Your current savings already reach the goal - no extra saving needed." if need == 0 else
                     "Save {monthly_saving} every month (about {weekly_saving} a week) to reach your goal."),
        "schedule": rows,
    }


# ------------------------------------------------------------------ 5. retirement

def retirement(data):
    age = number(data, "age", "Current age", 15, 90, integer=True)
    retire = number(data, "retire_age", "Retirement age", age + 1, 100, integer=True)
    life = number(data, "life_expectancy", "Plan until age", retire + 1, 120, integer=True)
    savings = number(data, "savings", "Current savings", 0, MAX_MONEY, default=0)
    monthly = number(data, "monthly", "Monthly contribution", 0, MAX_MONEY, default=0)
    grow_rate = number(data, "return_before", "Return before retirement", 0, 30) / 100
    after_rate = number(data, "return_after", "Return after retirement", 0, 30) / 100
    inflation = number(data, "inflation", "Inflation", 0, 30, default=0) / 100
    want = number(data, "income_wanted", "Monthly income wanted (today's money)", 0, MAX_MONEY, default=0)

    m_save, m_draw = (retire - age) * 12, (life - retire) * 12
    i, j = grow_rate / 12, after_rate / 12
    balance, rows = savings, []
    for m in range(1, m_save + 1):
        balance = balance * (1 + i) + monthly
        if m % 12 == 0:
            rows.append({"age": age + m // 12, "balance": r2(balance), "phase": "saving"})
    at_retirement = balance
    infl_factor = (1 + inflation) ** (retire - age)
    # level monthly income the pot can pay until the plan age
    income = at_retirement / m_draw if j == 0 else at_retirement * j / (1 - (1 + j) ** -m_draw)
    want_future = want * infl_factor
    needed_pot = want_future * m_draw if j == 0 else want_future * (1 - (1 + j) ** -m_draw) / j
    gap = needed_pot - at_retirement
    extra = 0.0
    if gap > 0:
        extra = gap / m_save if i == 0 else gap * i / ((1 + i) ** m_save - 1)
    pay_out = want_future if want else income
    for m in range(1, m_draw + 1):
        balance = balance * (1 + j) - pay_out
        if m % 12 == 0:
            rows.append({"age": retire + m // 12, "balance": r2(max(balance, 0)), "phase": "retired"})
    runs_out = next((r["age"] for r in rows if r["phase"] == "retired" and r["balance"] <= 0), None)
    return {
        "summary": {"at_retirement": r2(at_retirement), "monthly_income": r2(income),
                    "monthly_income_today": r2(income / infl_factor), "needed_pot": r2(needed_pot) if want else None,
                    "gap": r2(gap) if want else None, "extra_monthly": r2(extra) if want else None,
                    "on_track": (gap <= 0) if want else None, "money_lasts_until": runs_out,
                    "years_saving": retire - age, "years_retired": life - retire},
        "sentence": ("At {retire_age} you will have {at_retirement}. It can pay {monthly_income} a month "
                     "(worth {monthly_income_today} in today's money) until age {life_expectancy}."),
        "schedule": rows,
    }


CALCULATORS = {
    "investment": investment,
    "bond": bond,
    "loan": loan,
    "savings-goal": savings_goal,
    "retirement": retirement,
}


def calculate(kind, data):
    if kind not in CALCULATORS:
        raise KeyError(kind)
    return CALCULATORS[kind](data)
