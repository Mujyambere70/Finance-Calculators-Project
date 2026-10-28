"""
scientific.py - a safe scientific calculator engine (no eval()).

The expression is read by a small recursive-descent parser:

    expression := term   (('+' | '-') term)*
    term       := unary  (('*' | '/' | 'mod') unary  |  implicit multiplication)*
    unary      := ('+' | '-') unary  |  power
    power      := postfix ('^' unary)?          # right to left: 2^3^2 = 2^9
    postfix    := primary ('!' | '%')*          # 5! = 120,  50% = 0.5
    primary    := number | constant | function '(' arguments ')' | '(' expression ')' | '|' expression '|'

So it understands things like:  2sin(30)+√16,  3(4+5),  2π r  (with r stored),  5!,  -2^2 = -4,
log(1000), log(8, 2), nCr(10, 3), 1.5e3, |−7|, 20% * 150.
Angles follow the DEG / RAD / GRAD mode.
"""

import math
import re

MAX_LENGTH = 300
MAX_FACTORIAL = 170          # 171! is bigger than the largest float


class SciError(ValueError):
    """A message for the user, e.g. 'Division by zero'."""


# ------------------------------------------------------------------ tokenizer

TOKEN = re.compile(r"""
    \s*(?:
      (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
    | (?P<name>[A-Za-z_][A-Za-z_0-9]*|π|τ|φ|√|∛)
    | (?P<op>\*\*|[-+*/^!%(),|×÷−])
    )""", re.X)

ALIASES = {"×": "*", "÷": "/", "−": "-", "**": "^", "π": "pi", "τ": "tau", "φ": "phi", "√": "sqrt", "∛": "cbrt"}


def tokenize(text):
    text = text.strip()
    if not text:
        raise SciError("Type an expression.")
    if len(text) > MAX_LENGTH:
        raise SciError("Expression is too long.")
    pos, out = 0, []
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "":
                break
            raise SciError(f"I don't understand '{text[pos:].strip()[:10]}'.")
        kind = m.lastgroup
        value = m.group(kind)
        if kind == "num":
            out.append(("num", float(value)))
        else:
            value = ALIASES.get(value, value)
            out.append(("name" if kind == "name" and value not in ("sqrt", "cbrt") else
                        "name" if kind == "name" else "op", value))
        pos = m.end()
    return out


# ------------------------------------------------------------------ the functions

def _fact(x):
    if x != int(x) or x < 0:
        # gamma function for non-integers: x! = Γ(x + 1)
        if x < 0 and x == int(x):
            raise SciError("Factorial of a negative whole number is not defined.")
        return math.gamma(x + 1)
    if x > MAX_FACTORIAL:
        raise SciError(f"Factorial is too large (max {MAX_FACTORIAL}!).")
    return float(math.factorial(int(x)))


def _whole(x, what):
    if x != int(x) or x < 0:
        raise SciError(f"{what} needs whole numbers ≥ 0.")
    return int(x)


def _ncr(n, r):
    n, r = _whole(n, "nCr"), _whole(r, "nCr")
    if r > n:
        raise SciError("In nCr, r cannot be bigger than n.")
    return float(math.comb(n, r))


def _npr(n, r):
    n, r = _whole(n, "nPr"), _whole(r, "nPr")
    if r > n:
        raise SciError("In nPr, r cannot be bigger than n.")
    return float(math.perm(n, r))


def _log(x, base=10):
    if x <= 0:
        raise SciError("log is defined only for numbers > 0.")
    if base <= 0 or base == 1:
        raise SciError("The base of log must be > 0 and not 1.")
    return math.log(x, base)


def _root(x, n):
    if n == 0:
        raise SciError("The 0th root does not exist.")
    if x < 0:
        if n == int(n) and int(n) % 2 == 1:
            return -((-x) ** (1 / n))
        raise SciError("Even root of a negative number is not real.")
    return x ** (1 / n)


class Angles:
    FACTOR = {"deg": math.pi / 180, "rad": 1.0, "grad": math.pi / 200}

    def __init__(self, mode):
        if mode not in self.FACTOR:
            raise SciError("Angle mode must be DEG, RAD or GRAD.")
        self.k = self.FACTOR[mode]

    def to_rad(self, x):
        return x * self.k

    def from_rad(self, x):
        return x / self.k


def make_functions(angles):
    def trig(f, name):
        def g(x):
            r = angles.to_rad(x)
            if name == "tan" and abs(math.cos(r)) < 1e-15:
                raise SciError("tan is not defined here (cos = 0).")
            return round(f(r), 14)          # sin(180°) = 0, not 1.2e-16
        return g

    def inverse(f, name, lo=-1, hi=1):
        def g(x):
            if not lo <= x <= hi:
                raise SciError(f"{name} needs a value between {lo} and {hi}.")
            return angles.from_rad(f(x))
        return g

    def checked(f, name, test, message):
        def g(*a):
            if not test(*a):
                raise SciError(message)
            return f(*a)
        return g

    return {
        # name: (function, number of arguments: int or (min, max))
        "sin": (trig(math.sin, "sin"), 1), "cos": (trig(math.cos, "cos"), 1), "tan": (trig(math.tan, "tan"), 1),
        "asin": (inverse(math.asin, "asin"), 1), "acos": (inverse(math.acos, "acos"), 1),
        "atan": (lambda x: angles.from_rad(math.atan(x)), 1),
        "sinh": (math.sinh, 1), "cosh": (math.cosh, 1), "tanh": (math.tanh, 1), "asinh": (math.asinh, 1),
        "acosh": (checked(math.acosh, "acosh", lambda x: x >= 1, "acosh needs a value ≥ 1."), 1),
        "atanh": (checked(math.atanh, "atanh", lambda x: -1 < x < 1, "atanh needs a value between -1 and 1."), 1),
        "sqrt": (checked(math.sqrt, "√", lambda x: x >= 0, "Square root of a negative number is not real."), 1),
        "cbrt": (lambda x: _root(x, 3), 1), "root": (_root, 2),
        "ln": (checked(math.log, "ln", lambda x: x > 0, "ln is defined only for numbers > 0."), 1),
        "log": (_log, (1, 2)), "log2": (lambda x: _log(x, 2), 1),
        "exp": (math.exp, 1), "abs": (abs, 1), "fact": (_fact, 1),
        "nCr": (_ncr, 2), "nPr": (_npr, 2),
        "floor": (math.floor, 1), "ceil": (math.ceil, 1),
        "round": (lambda x, n=0: round(x, int(n)), (1, 2)),
        "gcd": (lambda a, b: float(math.gcd(_whole(abs(a), "gcd"), _whole(abs(b), "gcd"))), 2),
        "lcm": (lambda a, b: float(math.lcm(_whole(abs(a), "lcm"), _whole(abs(b), "lcm"))), 2),
        "min": (min, (1, 20)), "max": (max, (1, 20)),
        "hypot": (math.hypot, 2),
    }


CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau, "phi": (1 + 5 ** 0.5) / 2}


# ------------------------------------------------------------------ parser

class Parser:
    def __init__(self, tokens, angle="deg", variables=None):
        self.t, self.i = tokens, 0
        self.funcs = make_functions(Angles(angle))
        self.vars = {**CONSTANTS, **{k: float(v) for k, v in (variables or {}).items()}}

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else (None, None)

    def take(self, value=None):
        tok = self.peek()
        if value is not None and tok[1] != value:
            raise SciError(f"Expected '{value}'.")
        self.i += 1
        return tok

    def parse(self):
        value = self.expression()
        if self.peek()[0] is not None:
            tok = self.peek()[1]
            raise SciError("A ')' is missing its '('." if tok == ")" else f"Unexpected '{tok}'.")
        return value

    def expression(self):
        v = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            r = self.term()
            v = v + r if op == "+" else v - r
        return v

    def starts_value(self):
        kind, val = self.peek()
        return kind in ("num", "name") or val == "("

    def term(self):
        v = self.unary()
        while True:
            kind, val = self.peek()
            if val in ("*", "/") or (kind == "name" and val == "mod"):
                self.take()
                r = self.unary()
                if val == "*":
                    v *= r
                else:
                    if r == 0:
                        raise SciError("Division by zero.")
                    v = v / r if val == "/" else math.fmod(v, r)
            elif self.starts_value():                       # 2π, 3(4+5), 2sin(30)
                v *= self.unary()
            else:
                return v

    def unary(self):
        if self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            v = self.unary()
            return -v if op == "-" else v
        return self.power()

    def power(self):
        base = self.postfix()
        if self.peek()[1] == "^":
            self.take()
            exp = self.unary()
            if base == 0 and exp < 0:
                raise SciError("0 to a negative power is division by zero.")
            if base < 0 and exp != int(exp):
                raise SciError("A negative number to a fractional power is not real.")
            try:
                return math.pow(base, exp)
            except OverflowError:
                raise SciError("The result is too large.")
        return base

    def postfix(self):
        v = self.primary()
        while self.peek()[1] in ("!", "%"):
            v = _fact(v) if self.take()[1] == "!" else v / 100
        return v

    def primary(self):
        kind, val = self.take()
        if kind is None:
            raise SciError("The expression is not complete.")
        if kind == "num":
            return val
        if val == "(":
            v = self.expression()
            if self.peek()[1] != ")":
                raise SciError("A ')' is missing.")
            self.take(")")
            return v
        if val == "|":
            v = self.expression()
            self.take("|")
            return abs(v)
        if kind == "name":
            if val in self.funcs:
                return self.call(val)
            if val in self.vars:
                return self.vars[val]
            raise SciError(f"Unknown name '{val}'.")
        raise SciError(f"Unexpected '{val}'.")

    def call(self, name):
        fn, count = self.funcs[name]
        if self.peek()[1] != "(":                       # sin 30, √9  (one argument, no brackets)
            if count != 1 and count != (1, 2):
                raise SciError(f"{name} needs brackets: {name}(…).")
            args = [self.unary()]
        else:
            self.take("(")
            args = [self.expression()]
            while self.peek()[1] == ",":
                self.take()
                args.append(self.expression())
            if self.peek()[1] != ")":
                raise SciError("A ')' is missing.")
            self.take(")")
        lo, hi = (count, count) if isinstance(count, int) else count
        if not lo <= len(args) <= hi:
            raise SciError(f"{name} needs {lo if lo == hi else f'{lo} to {hi}'} number(s).")
        try:
            return float(fn(*args))
        except SciError:
            raise
        except OverflowError:
            raise SciError("The result is too large.")
        except (ValueError, ZeroDivisionError):
            raise SciError(f"{name} is not defined for this value.")


# ------------------------------------------------------------------ public API

def tidy(x):
    """Remove floating-point noise (0.1 + 0.2 = 0.3, not 0.30000000000000004). Whole numbers stay exact."""
    if not math.isfinite(x) or x == int(x):
        return x + 0.0
    return float(f"{x:.15g}")


def format_number(x):
    if math.isnan(x):
        raise SciError("The result is not a number.")
    if math.isinf(x):
        raise SciError("The result is too large.")
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    if abs(x) >= 1e15 or abs(x) < 1e-6:
        mant, exp = f"{x:.10e}".split("e")
        return f"{mant.rstrip('0').rstrip('.')}×10^{int(exp)}"
    return f"{x:.12g}"


def evaluate(expression, angle="deg", variables=None):
    """Returns {'value': float, 'display': str}. Raises SciError with a friendly message."""
    tokens = tokenize(expression)
    try:
        value = Parser(tokens, angle, variables).parse()
    except RecursionError:
        raise SciError("The expression is nested too deeply.")
    except OverflowError:
        raise SciError("The result is too large.")
    value = tidy(value)
    return {"value": value, "display": format_number(value)}


def convert(value, kind):
    """Extra results shown under the answer: fraction, hex, binary, degrees/radians."""
    out = {}
    if value == int(value) and abs(value) < 2 ** 53:
        n = int(value)
        out["hex"] = ("-" if n < 0 else "") + hex(abs(n))[2:].upper()
        out["bin"] = ("-" if n < 0 else "") + bin(abs(n))[2:]
        out["oct"] = ("-" if n < 0 else "") + oct(abs(n))[2:]
    else:
        from fractions import Fraction
        f = Fraction(value).limit_denominator(10000)
        if abs(float(f) - value) < 1e-10 and f.denominator != 1:
            out["fraction"] = f"{f.numerator}/{f.denominator}"
    return out
