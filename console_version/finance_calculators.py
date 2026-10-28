"""
Finance Calculator - console version (improved HyperionDev capstone).

Uses the same maths as the web app (calculators.py), so both always give the same answers.
Run from the project folder:  python console_version/finance_calculators.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calculators import CalcError, calculate  # noqa: E402

MENU = {
    "investment": "the money you will have after investing (simple or compound interest)",
    "bond": "the monthly repayment of a home loan",
    "loan": "the EMI and real cost (APR) of a personal or car loan",
    "goal": "how much to save each month to reach a savings goal",
}


def ask(prompt, allowed=None):
    """Ask until the answer is not empty (and is one of `allowed`, if given)."""
    while True:
        answer = input(prompt).strip().lower()
        if answer and (allowed is None or answer in allowed):
            return answer
        print(f"  Please type one of: {', '.join(allowed)}" if allowed else "  Please type a value.")


def ask_and_calculate(kind, questions, fixed=None):
    """Ask every question; if the calculator rejects a value, ask only that one again."""
    data = dict(fixed or {})
    for field, prompt in questions:
        data[field] = ask(prompt)
    while True:
        try:
            return calculate(kind, data)
        except CalcError as e:
            print("  " + e.message)
            prompt = dict(questions).get(e.field, f"{e.field}: ")
            data[e.field] = ask(prompt)


def money(x):
    return f"{x:,.2f}"


def main():
    print("=" * 62)
    print("  FINANCE CALCULATOR")
    print("=" * 62)
    for key, text in MENU.items():
        print(f"  {key:<11}- {text}")
    choice = ask("\nEnter one of the options above: ", MENU)

    if choice == "investment":
        kind = ask("Enter 'simple' or 'compound' interest: ", ("simple", "compound"))
        r = ask_and_calculate("investment", [
            ("principal", "Amount you are depositing: "),
            ("rate", "Interest rate per year (e.g. 8 for 8%): "),
            ("years", "Number of years you plan on investing: "),
        ], {"interest_type": kind, "monthly_deposit": 0})
        s = r["summary"]
        print(f"\nThe total amount after {r['schedule'][-1]['year']} years with {kind} interest is: {money(s['final_value'])}")
        print(f"Interest earned: {money(s['total_interest'])}")

    elif choice == "bond":
        r = ask_and_calculate("bond", [
            ("price", "Present value of the house: "),
            ("rate", "Annual interest rate (e.g. 8.5): "),
            ("term", "Number of months for bond repayment: "),
        ], {"term_unit": "months", "deposit": 0})
        s = r["summary"]
        print(f"\nThe monthly bond repayment is: {money(s['monthly_payment'])}")
        print(f"Total interest over {s['months']} months: {money(s['total_interest'])}")

    elif choice == "loan":
        r = ask_and_calculate("loan", [
            ("amount", "Loan amount: "), ("rate", "Interest rate per year: "),
            ("months", "Loan period in months: "), ("fee", "Processing fee in % (0 if none): "),
        ])
        s = r["summary"]
        print(f"\nMonthly EMI: {money(s['monthly_payment'])}  |  total cost: {money(s['total_cost'])}  |  APR: {s['apr']}%")

    else:
        r = ask_and_calculate("savings-goal", [
            ("target", "Goal amount: "), ("current", "Money you already have: "),
            ("years", "Years to reach the goal: "), ("rate", "Interest on savings per year: "),
        ])
        print(f"\nSave {money(r['summary']['monthly_saving'])} every month to reach your goal.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")
