"""
forms.py - what each calculator asks for (labels, defaults, help text) and the explanations
shown under it. The page is built from this, so adding a field means changing only this file.
"""

from currencies import CURRENCY_LIST, REGION_ORDER

# grouped by region for the currency menus: {region: [currency, ...]}
CURRENCY_GROUPS = {r: [c for c in CURRENCY_LIST if c["region"] == r] for r in REGION_ORDER}
CURRENCY_GROUPS = {r: sorted(cs, key=lambda c: c["code"]) for r, cs in CURRENCY_GROUPS.items() if cs}
CURRENCY_GROUPS["North America & Caribbean"].sort(key=lambda c: c["code"] != "USD")     # USD first
CURRENCY_GROUPS["Europe"].sort(key=lambda c: c["code"] not in ("EUR", "GBP"))
CURRENCIES = {c["code"]: f'{c["name"]} ({c["symbol"]})' for c in CURRENCY_LIST}
CURRENCY_LOCALES = {c["code"]: c["locale"] for c in CURRENCY_LIST}
CURRENCY_INFO = {c["code"]: c for c in CURRENCY_LIST}

COMPOUNDING = [("annually", "Once a year"), ("semi-annually", "Twice a year"), ("quarterly", "Every quarter"),
               ("monthly", "Every month"), ("daily", "Every day")]


def money(name, label, default, help="", required=True):
    return {"name": name, "label": label, "type": "money", "default": default, "help": help, "required": required}


def percent(name, label, default, help="", step="0.05"):
    return {"name": name, "label": label, "type": "percent", "default": default, "help": help, "step": step}


CALCS = {
    "investment": {
        "title": "Investment calculator",
        "short": "Investment",
        "icon": "📈",
        "color": "#10b981",
        "tagline": "How much will my money grow with simple or compound interest?",
        "fields": [
            money("principal", "Initial deposit", 100000, "Money you invest today."),
            money("monthly_deposit", "Monthly deposit", 5000, "Added at the end of every month. 0 = none.", False),
            percent("rate", "Interest rate (per year)", 8),
            {"name": "years", "label": "Number of years", "type": "number", "default": 10, "min": 1, "max": 100,
             "step": "1", "suffix": "years"},
            {"name": "interest_type", "label": "Interest type", "type": "segmented", "default": "compound",
             "options": [("compound", "Compound"), ("simple", "Simple")]},
            {"name": "compounding", "label": "Interest is added", "type": "select", "default": "annually",
             "options": COMPOUNDING, "show_if": "interest_type=compound"},
            percent("inflation", "Inflation (optional)", 5, "Shows what the money will be worth in today's prices."),
        ],
        "explain": [
            ("Simple interest", "Interest is paid only on the money you put in: <code>A = P × (1 + r × t)</code>."),
            ("Compound interest", "Interest also earns interest: <code>A = P × (1 + r/n)<sup>n×t</sup></code>, "
                                  "where <i>n</i> is how often interest is added in a year."),
            ("Real value", "Prices grow every year (inflation). The real value shows what your money can buy "
                           "in today's prices."),
        ],
    },
    "bond": {
        "title": "Home loan (bond) calculator",
        "short": "Home loan",
        "icon": "🏠",
        "color": "#3b82f6",
        "tagline": "What is my monthly repayment and how much interest will I pay?",
        "fields": [
            money("price", "House price", 5000000),
            money("deposit", "Deposit (down payment)", 1000000, "Banks usually want 10-20 % of the price.", False),
            percent("rate", "Interest rate (per year)", 8.5),
            {"name": "term", "label": "Repayment period", "type": "number", "default": 20, "min": 1, "max": 600,
             "step": "1", "unit_field": "term_unit"},
            {"name": "term_unit", "label": "Unit", "type": "hidden", "default": "years"},
            money("extra", "Extra payment every month", 0, "Pay a little more to finish early and save interest.", False),
            {"name": "start", "label": "First payment", "type": "month", "default": ""},
            money("property_tax", "Property tax per year", 0, "Optional - adds to your monthly cost.", False),
            money("insurance", "Home insurance per year", 0, "Optional.", False),
            money("income", "Your monthly income (after tax)", 0, "Optional - we check if the loan is affordable.", False),
        ],
        "explain": [
            ("Monthly repayment", "<code>x = (i × P) / (1 − (1 + i)<sup>−n</sup>)</code> where <i>P</i> is the "
                                  "loan, <i>i</i> the monthly rate (yearly rate ÷ 12) and <i>n</i> the number of months."),
            ("Affordability", "A common rule: keep the total monthly home cost below <b>28 %</b> of your income. "
                              "Up to 36 % is a stretch, above that is risky."),
            ("Extra payments", "Every extra payment reduces the loan balance directly, so the next interest "
                               "is smaller and the loan ends earlier."),
        ],
    },
    "loan": {
        "title": "Personal & car loan (EMI) calculator",
        "short": "Loan / EMI",
        "icon": "🚗",
        "color": "#f59e0b",
        "tagline": "What is my EMI and what does the loan really cost with fees?",
        "fields": [
            money("amount", "Loan amount", 500000),
            percent("rate", "Interest rate (per year)", 11.5),
            {"name": "months", "label": "Loan period", "type": "number", "default": 48, "min": 1, "max": 480,
             "step": "1", "suffix": "months", "presets": [12, 24, 36, 48, 60, 84]},
            percent("fee", "Processing fee", 1.5, "Charged once, usually 0.5-3 % of the loan.", "0.1"),
        ],
        "explain": [
            ("EMI", "Equated Monthly Instalment - the same amount every month. Early EMIs are mostly interest, "
                    "later ones mostly repay the loan."),
            ("APR", "The Annual Percentage Rate includes the processing fee, because you receive less money "
                    "but repay the full loan. Compare loans by APR, not by the advertised rate."),
        ],
    },
    "savings-goal": {
        "title": "Savings goal calculator",
        "short": "Savings goal",
        "icon": "🎯",
        "color": "#8b5cf6",
        "tagline": "How much must I save every month to reach my goal?",
        "fields": [
            money("target", "Goal amount", 300000, "e.g. a laptop, a car, a wedding, university fees."),
            money("current", "Money you already have", 20000, "", False),
            {"name": "years", "label": "Time to reach the goal", "type": "number", "default": 2, "min": 0.25,
             "max": 60, "step": "0.25", "suffix": "years"},
            percent("rate", "Interest on savings (per year)", 6),
        ],
        "explain": [
            ("Formula", "<code>Monthly = (Goal − Now × (1+i)<sup>n</sup>) × i / ((1+i)<sup>n</sup> − 1)</code>"),
            ("Tip", "Set up an automatic transfer on salary day - saving first is easier than saving what is left."),
        ],
    },
    "retirement": {
        "title": "Retirement planner",
        "short": "Retirement",
        "icon": "🌴",
        "color": "#ef4444",
        "tagline": "Will my savings be enough when I stop working?",
        "fields": [
            {"name": "age", "label": "Current age", "type": "number", "default": 26, "min": 15, "max": 90, "step": "1", "suffix": "years"},
            {"name": "retire_age", "label": "Retirement age", "type": "number", "default": 60, "min": 30, "max": 100, "step": "1", "suffix": "years"},
            {"name": "life_expectancy", "label": "Plan money until age", "type": "number", "default": 85, "min": 50, "max": 120, "step": "1", "suffix": "years"},
            money("savings", "Savings today", 100000, "", False),
            money("monthly", "Monthly contribution", 10000, "", False),
            percent("return_before", "Return before retirement", 10, "Stocks / mutual funds: often 8-12 %."),
            percent("return_after", "Return after retirement", 6, "Safer investments: often 5-7 %."),
            percent("inflation", "Inflation", 5),
            money("income_wanted", "Monthly income you want (today's money)", 50000, "", False),
        ],
        "explain": [
            ("How it works", "First your savings grow until retirement. Then you take the same amount every "
                             "month until the plan age, while the rest keeps earning the after-retirement return."),
            ("Inflation", "The income you want is in today's money. With inflation it will need to be "
                          "much larger in the future - the planner includes this."),
        ],
    },
}
