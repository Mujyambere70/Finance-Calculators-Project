# CalcWise — Finance Calculators (Python + Flask)

A real-life finance calculator website: **investment, home loan (bond), personal/car loan (EMI), savings goal and
retirement** calculators with live results, charts, full repayment schedules, saved calculations, share links,
CSV export and print / PDF — plus a **live currency converter for every currency in the world**, a full
**scientific calculator** and **generators** (authenticator OTP, passwords, emails, phone and passport numbers).

> This project started as the **Finance Calculator** capstone of the HyperionDev Software Engineering Bootcamp —
> a console program with an investment calculator and a bond repayment calculator. It was rebuilt as a web app;
> the original formulas are still used and covered by tests. The improved console program is in `console_version/`.
>
> Designed and developed by **Jean Michel Mujyambere** · [github.com/Mujyambere70](https://github.com/Mujyambere70)

## How to run / Как запустить

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS / Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```
Open **http://127.0.0.1:5000**. The database `calcwise.db` (saved calculations) is created automatically.

Console version (no Flask needed): `python console_version/finance_calculators.py`

## Calculators / Калькуляторы

| Calculator | You enter | You get |
|---|---|---|
| **Investment** | initial deposit, monthly deposit, rate, years, simple / compound, how often interest is added (yearly … daily), inflation | final value, deposits vs interest, value in today's money, effective yearly rate, comparison simple ↔ compound, year-by-year table and chart |
| **Home loan (bond)** | house price, deposit, rate, period in years **or** months, extra monthly payment, first payment month, property tax, insurance, monthly income | monthly repayment, total monthly cost, total interest, payoff date, interest and months saved by extra payments, **affordability check** (28 % / 36 % rule), yearly and monthly amortization schedule |
| **Loan / EMI** | amount, rate, months (quick buttons 12-84), processing fee | EMI, total interest, fee, total repaid, **real APR including the fee**, donut chart, schedule |
| **Savings goal** | goal, money you already have, time, interest | amount to save per month and per week, interest earned, date the goal is reached |
| **Retirement** | ages, savings, monthly contribution, returns before / after retirement, inflation, income wanted | savings at retirement, monthly income it can pay (also in today's money), savings needed, shortfall and extra monthly saving needed, age when money runs out |

**Every calculator also has:**
- results that update while you type (Python API `/api/calc/<name>`), clear error message next to the wrong field
- **157 currencies — every currency used in the world today** (ISO 4217, from the Unicode CLDR data) plus Bitcoin,
  Ether and Tether, grouped by region with flags: **East Africa first** (RWF, KES, UGX, TZS, BIF, SSP, CDF, SOS, ETB,
  ERN, DJF, SDG, MWK, ZMW, ZWG, MZN, MGA, MUR, SCR, KMF), then the rest of Africa, Middle East, Asia, Europe,
  the Americas, Oceania and crypto. Shillings, francs, yen… are shown without cents, as in real life.
- under every answer: **"≈ the same amount in another currency"** with today's live rate

**My calculations** — save any calculation with a name, open it later to change it (update or save as new),
rename, delete one or delete all. They belong to your browser through a private cookie (no sign-up);
other visitors cannot see or change them.

## Currency converter with live rates / Конвертер валют

Open **/converter**.

- Convert any amount between any two of the 157 currencies, swap with one click, quick pairs
  (USD→RWF, RWF→KES, KES→UGX, UGX→TZS, EUR→RWF, RUB→RWF…)
- **1 X = … Y** and **1 Y = … X**, the time the rates were published and when the next update comes
- **History chart** for 7 days, 1 month, 3 months or 1 year with low, high and % change
- **"Your amount in other currencies"** — your own list, add or remove currencies (remembered in the browser)
- **Table of all currencies** with search (country, name or code) and region filters
- The page **checks for new rates every 5 minutes** and when you come back to the tab; a green dot shows "Live",
  orange shows "Offline – last saved rates"

**Where the rates come from (free, no API key):**

| Source | What | Updates |
|---|---|---|
| [ExchangeRate-API](https://www.exchangerate-api.com) open access — `open.er-api.com/v6/latest/USD` | ~160 official currencies | once a day |
| [currency-api](https://github.com/fawazahmed0/exchange-api) by Fawaz Ahmed — jsDelivr + Cloudflare mirror | 200+ incl. crypto, **daily history** | once a day |

`rates.py` downloads both and merges them (the official source wins, the other fills gaps like Bitcoin).
If one source is down, the other is enough. The server downloads again **at most once an hour** (set `FX_TTL` in seconds),
so it never hits the sources' rate limits; results are saved in SQLite, so **without internet the last saved rates
are still used**. History days are cached forever (old rates never change).

> Free sources publish **mid-market rates once a day** — real money changers and banks add their margin.
> For second-by-second trading rates you need a paid API key; `rates.py` is built so another source can be added easily.

## Scientific calculator / Научный калькулятор

Open **/scientific**. A keypad like a real Casio-style calculator plus full keyboard typing.

- **Functions:** sin, cos, tan and their inverses (**2nd**), hyperbolic (**hyp**) and inverse hyperbolic, ln, log (any base:
  `log(8, 2)`), log₂, eˣ, 10ˣ, x², x³, xʸ, √, ∛, ʸ√x (`root(x, n)`), 1/x, n! (also for decimals through the gamma function),
  nCr, nPr, |x|, mod, %, gcd, lcm, round, floor, ceil, min, max, hypot
- **Constants:** π, e, τ, φ · **EXP** (×10ⁿ, e.g. `1.5E3`) · **Ans** (last answer) · **memory** MC, MR, M+, M−
- **Angle modes:** DEG / RAD / GRAD
- **Correct maths rules:** `2^3^2 = 512` (powers from the right), `-2^2 = -4`, implicit multiplication `2π`, `3(4+5)`, `2sin(30)`
- **Live preview** while typing, then **=** saves it to the **history** (click an old line to use it again)
- Extra results: **fraction** (0.75 → 3/4), **binary, octal, hexadecimal** for whole numbers
- **Clear error messages** instead of crashes: "Division by zero", "Square root of a negative number is not real",
  "A ')' is missing", "tan is not defined here (cos = 0)"…
- Floating-point noise removed: `0.1 + 0.2 = 0.3`, `sin(180°) = 0`

How it works: `scientific.py` reads the expression with a **recursive-descent parser** (tokenizer → expression →
term → unary → power → postfix → primary). It never uses `eval()`, so typed text can never run code.

## Generators / Генераторы

Open **/generators** (tabs: OTP · Password · Email · Phone number · Passport number). Every list can be copied
one by one, copied all at once or downloaded as CSV. All randomness comes from Python's `secrets` module.

| Generator | What it does |
|---|---|
| **Authenticator (TOTP / HOTP)** | Real 2-step-verification codes - the same maths as Google / Microsoft Authenticator (RFC 6238, RFC 4226). Random 160-bit setup key, QR code + `otpauth://` link to add it to your phone, live 30 s countdown, previous / next code, SHA1 / SHA256 / SHA512, 6 or 8 digits, and **"Check a code from your app"** (accepts ±1 step for clock drift). Tested with the official RFC test vectors. |
| **One-time codes** | SMS / email style codes: numbers, letters + numbers, easy-to-read (no 0/O, 1/I), letters, hex; 4-12 characters; shows how many combinations exist |
| **Password** | Random passwords (4-64 chars, choose groups, avoid look-alikes, always at least one of every group), **passphrases** (`Maple-Rocket-Quiet42-Harbor-Lime`) and **PINs** (skips 0000, 1234, 1111…). Strength in bits and time to crack. **"How strong is my password?"** checks your own password **in the browser only** - it is never sent. |
| **Email** | 11 types: first.last, name + number, initials, first_last, nickname, random, role (info@, support@…), plus-address (name+tag@), subdomain, student id, work - or a mix. Domains: safe test domains (example.com, *.test - reserved, never reach a person), popular providers, or your own domain. Names from many countries. |
| **Phone number** | **All 246 countries and territories** with the right calling code. Mobile or landline; international (+250 788 123 456), national (0788 123 456) and E.164 (+250788123456). Real mobile prefixes for 100+ countries (East Africa, Europe, Asia, the Americas…). Optional **fictional range** that never belongs to a real person (USA/Canada 555-01xx, UK 07700 900xxx). If `phonenumbers` (Google libphonenumber) is installed, every number is validated against the official plan and shows the operator. |
| **Passport number** | Number **format** for every country, for testing booking / visa forms: published format for 39 countries (USA, UK, Germany, China, India, Russia…), "approximate" for some, the ICAO 9303 general format for the rest. Not a document. |

> Emails, phone and passport numbers are **test data** for developers and students - never use them to pretend to be
> someone or on real documents. Random phone numbers may belong to real people: don't call or text them.

## Formulas / Формулы

| | Formula |
|---|---|
| Simple interest (original) | `A = P (1 + r t)` |
| Compound interest (original, yearly) | `A = P (1 + r)^t`, in general `A = P (1 + r/n)^(n t)` |
| Bond / loan repayment (original) | `x = i P / (1 − (1 + i)^−n)`, `i` = yearly rate / 12, `n` = months |
| Savings goal | `PMT = (Goal − PV (1+i)^n) · i / ((1+i)^n − 1)` |
| APR | the rate at which the money actually received (loan − fee) equals the present value of all EMIs (found by bisection) |
| Real value | `value / (1 + inflation)^years` |

## Tests

```bash
python -m unittest discover -s tests -v      # 75 tests
```
`test_generators.py` checks the authenticator with the RFC 4226 / RFC 6238 test vectors, every password rule,
every email type, a phone and passport number for every country and the API; `test_rates.py` checks the live rates with a fake internet (both sources, one source down, mirror, cache, offline,
history), `test_scientific.py` the scientific engine, `test_calculators.py` checks the maths (including the 3 original formulas, schedules that add up,
extra payments, APR, goal reached exactly, retirement gap) and `test_app.py` checks pages, the API,
CSRF protection and that saved calculations are private.

## Project structure

```
fincalc/
├── app.py              Flask: pages, JSON API, saved calculations (SQLite), CSRF, owner cookie
├── calculators.py      all finance maths (no web code) - investment, bond, loan, savings_goal, retirement
├── scientific.py       safe scientific expression parser and evaluator (no eval)
├── generators.py       OTP/TOTP/HOTP, passwords, emails, phone + passport numbers (no web code)
├── countries.py        246 countries: flag, region, calling code
├── rates.py            live exchange rates: 2 sources, merge, fallback, SQLite cache, history
├── currencies.py       157 currencies (code, name, symbol, countries, flag, region, decimals) from CLDR
├── forms.py            fields, defaults, help texts and explanations of every calculator
├── templates/          base, index, calculator (one template for all 5), converter, scientific, generators, saved, about, error
├── static/
│   ├── style.css       responsive design, print styles
│   ├── app.js          live calculation, SVG charts, tables, CSV, share link, save dialog, currency
│   ├── sci.js          scientific keypad, keyboard, memory, history
│   ├── gen.js          generators page: tabs, live authenticator, QR, strength checker, CSV
│   ├── conv.js         converter: live rates, auto refresh, history chart, favourites, table
│   └── img/            logo.png, favicon.png
├── console_version/    improved console program (uses calculators.py) + original_capstone.py
├── screenshots/
└── tests/
```

## Security
CSRF token on every form and API call · input validated on the server · parameterised SQL ·
auto-escaped HTML · saved calculations filtered by a random private owner id (HTTP-only cookie) ·
only known fields are stored.

*CalcWise gives estimates for planning and learning — it is not financial advice.*
