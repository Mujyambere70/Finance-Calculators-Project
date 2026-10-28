"""
generators.py - test-data and security generators (no web code):

    otp_codes()        one-time codes (numbers, letters, hex …)
    TOTP / HOTP        real authenticator-app codes (RFC 6238 / RFC 4226), the same maths as
                       Google Authenticator, Microsoft Authenticator, Authy …
    passwords()        strong random passwords, passphrases and PINs + strength (entropy)
    emails()           email addresses of many types (name, initials, role, plus-address …)
    phones()           phone numbers for every country (mobile / landline, 3 formats)
    passports()        passport-NUMBER formats for test forms (not documents)

All randomness comes from the `secrets` module (cryptographically secure).
Generated emails, phone and passport numbers are TEST DATA for filling and testing forms.
"""

import base64
import hashlib
import hmac
import math
import secrets
import string
import struct
import time
import unicodedata
from urllib.parse import quote, urlencode

from countries import COUNTRIES, COUNTRY_LIST

try:  # optional: Google's libphonenumber (pip install phonenumbers) - exact rules for every region
    import phonenumbers
    from phonenumbers import PhoneNumberFormat, PhoneNumberType, carrier, geocoder
except ImportError:  # the built-in rules below are used instead
    phonenumbers = None

rng = secrets.SystemRandom()
MAX_COUNT = 100


class GenError(ValueError):
    """Wrong option. `field` names the input so the page can show the message next to it."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def _int(opts, key, default, lo, hi, label):
    try:
        v = int(opts.get(key, default))
    except (TypeError, ValueError):
        raise GenError(key, f"{label} must be a whole number.")
    if not lo <= v <= hi:
        raise GenError(key, f"{label} must be between {lo} and {hi}.")
    return v


def _bool(opts, key, default=False):
    v = opts.get(key, default)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "yes")


def _count(opts):
    return _int(opts, "count", 10, 1, MAX_COUNT, "How many")


# =========================================================================== strength
def crack_time(bits, guesses_per_second=1e10):
    """Average time for a fast offline attack (10 billion guesses a second) to find it."""
    seconds = 2 ** (bits - 1) / guesses_per_second
    for unit, size in (("centuries", 3.15e9), ("years", 3.15e7), ("days", 86400), ("hours", 3600), ("minutes", 60)):
        if seconds >= size:
            n = seconds / size
            if unit == "centuries" and n > 1e6:
                return "millions of centuries"
            return f"{n:,.0f} {unit}"
    return "less than a minute" if seconds >= 1 else "instantly"


def strength(bits):
    label = ("Very weak" if bits < 28 else "Weak" if bits < 40 else "Fair" if bits < 60
             else "Strong" if bits < 80 else "Very strong")
    return {"bits": round(bits, 1), "label": label, "crack": crack_time(bits)}


# =========================================================================== OTP codes
OTP_SETS = {
    "numeric": string.digits,
    "alphanumeric": string.ascii_uppercase + string.digits,
    "letters": string.ascii_uppercase,
    "hex": "0123456789ABCDEF",
    "safe": "ACDEFGHJKMNPQRTUVWXY34679",  # no 0/O, 1/I/L, 2/Z, 5/S, 8/B - easy to read and type
}


def otp_codes(opts):
    kind = opts.get("type", "numeric")
    if kind not in OTP_SETS:
        raise GenError("type", "Unknown code type.")
    length = _int(opts, "length", 6, 4, 12, "Code length")
    minutes = _int(opts, "valid", 5, 1, 60, "Valid for")
    chars = OTP_SETS[kind]
    items = []
    for _ in range(_count(opts)):
        code = "".join(secrets.choice(chars) for _ in range(length))
        if kind == "numeric" and _bool(opts, "no_leading_zero") and code[0] == "0":
            code = secrets.choice("123456789") + code[1:]
        group = 3 if length in (6, 9, 12) else 4 if length in (8, 12) else 0
        shown = "-".join(code[i:i + group] for i in range(0, length, group)) if group and _bool(opts, "group") else code
        items.append({"value": shown, "raw": code})
    bits = length * math.log2(len(chars))
    return {"items": items, "info": {"combinations": f"{len(chars) ** length:,}", "valid_minutes": minutes,
                                     "guess": f"1 in {len(chars) ** length:,}", "bits": round(bits, 1)}}


# =========================================================================== TOTP / HOTP
ALGOS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


def new_secret(nbytes=20):
    """160-bit random secret in Base32 (what authenticator apps call the 'setup key')."""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode().rstrip("=")


def _key(secret):
    s = secret.replace(" ", "").replace("-", "").upper()
    if not s or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=" for c in s):
        raise GenError("secret", "The secret must be Base32 (letters A-Z and digits 2-7).")
    try:
        return base64.b32decode(s + "=" * (-len(s) % 8))
    except Exception:
        raise GenError("secret", "This is not a valid Base32 secret.")


def hotp(key, counter, digits=6, algorithm="SHA1"):
    """RFC 4226: HMAC of the 8-byte counter -> dynamic truncation -> last `digits` digits."""
    mac = hmac.new(key, struct.pack(">Q", counter), ALGOS[algorithm]).digest()
    offset = mac[-1] & 0x0F
    number = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** digits).zfill(digits)


def totp(key, at=None, period=30, digits=6, algorithm="SHA1"):
    """RFC 6238: HOTP with counter = number of `period`-second steps since 1970."""
    at = time.time() if at is None else at
    return hotp(key, int(at // period), digits, algorithm)


def _otp_opts(opts):
    digits = _int(opts, "digits", 6, 6, 8, "Digits")
    period = _int(opts, "period", 30, 15, 120, "Period")
    algorithm = str(opts.get("algorithm", "SHA1")).upper()
    if algorithm not in ALGOS:
        raise GenError("algorithm", "Algorithm must be SHA1, SHA256 or SHA512.")
    return digits, period, algorithm


def totp_state(opts, now=None):
    """Current, previous and next code + seconds left + otpauth:// link for authenticator apps."""
    secret = str(opts.get("secret") or "").strip() or new_secret()
    key = _key(secret)
    digits, period, algorithm = _otp_opts(opts)
    now = time.time() if now is None else now
    mode = opts.get("mode", "totp")
    issuer = (str(opts.get("issuer") or "CalcWise").strip() or "CalcWise")[:40]
    account = (str(opts.get("account") or "demo@example.com").strip() or "demo@example.com")[:60]
    clean = secret.replace(" ", "").upper().rstrip("=")
    params = {"secret": clean, "issuer": issuer, "algorithm": algorithm, "digits": digits}
    if mode == "hotp":
        counter = _int(opts, "counter", 0, 0, 10 ** 12, "Counter")
        params["counter"] = counter
        codes = [{"counter": c, "code": hotp(key, c, digits, algorithm)} for c in range(counter, counter + 5)]
        result = {"mode": "hotp", "code": codes[0]["code"], "next_codes": codes, "counter": counter}
    else:
        params["period"] = period
        step = int(now // period)
        result = {"mode": "totp", "code": hotp(key, step, digits, algorithm),
                  "previous": hotp(key, step - 1, digits, algorithm), "next": hotp(key, step + 1, digits, algorithm),
                  "remaining": period - int(now % period), "period": period, "step": step}
    label = quote(f"{issuer}:{account}")
    result.update(secret=clean, secret_grouped=" ".join(clean[i:i + 4] for i in range(0, len(clean), 4)),
                  digits=digits, algorithm=algorithm, issuer=issuer, account=account,
                  uri=f"otpauth://{'hotp' if mode == 'hotp' else 'totp'}/{label}?{urlencode(params)}")
    return result


def totp_verify(opts, now=None):
    """Check a code typed from an authenticator app. Accepts one step before/after (clock drift)."""
    key = _key(str(opts.get("secret") or ""))
    digits, period, algorithm = _otp_opts(opts)
    code = "".join(ch for ch in str(opts.get("code", "")) if ch.isdigit())
    if len(code) != digits:
        raise GenError("code", f"Type the {digits}-digit code.")
    now = time.time() if now is None else now
    if opts.get("mode") == "hotp":
        counter = _int(opts, "counter", 0, 0, 10 ** 12, "Counter")
        for c in range(counter, counter + 10):  # look-ahead window
            if hmac.compare_digest(hotp(key, c, digits, algorithm), code):
                return {"valid": True, "message": f"Correct - code for counter {c}.", "counter": c}
        return {"valid": False, "message": "Wrong code."}
    step = int(now // period)
    for drift in (0, -1, 1):
        if hmac.compare_digest(hotp(key, step + drift, digits, algorithm), code):
            when = {0: "current", -1: "previous (just expired)", 1: "next"}[drift]
            return {"valid": True, "message": f"Correct - this is the {when} code.", "drift": drift}
    return {"valid": False, "message": "Wrong or expired code."}


# =========================================================================== passwords
SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?/~"
AMBIGUOUS = set("Il1O0o|`'\"")

WORDS = """able acid aged also area army away baby back bake ball band bank barn base bath bean bear beat bell belt
bench best bike bird bite blue boat body bone book boot born boss bowl brave bread brick brief bring broad brown
brush build bulb bunch burn busy cabin cake calm camel camp canal candy cane card care cargo carry cart case cash
cast cave chain chair chalk charm chart chase cheap check cheek chef chess chest chief child chip city clap class
clay clean clear clerk cliff climb clock cloud clown coach coal coast coat cocoa code coffee coin cold color comet
cook cool coral corn couch count cover cow crab craft crane crash cream creek crew crisp crop crowd crown cube cup
curve daily dance dark date dawn deal deep deer desk dial diary dice dime dish dive dock doll dolphin door dove
draft dragon drama dream dress drift drill drink drive drum duck dune dust eager eagle early earth easel east easy
echo edge eight elbow elder elk ember empty end enjoy equal escape even event exact exit extra fable face fact
fair faith fame fancy farm fast fault feast fence ferry fever field fifty film final find fire firm fish five
flag flame flash fleet flight float flock flood floor flour flower fluid flute focus foam fog fold folk food foot
force forest fork form fort fox frame fresh frog front frost fruit fuel fund funny gate gear gecko gem giant gift
girl glad glass globe glove glow goat gold golf good goose grace grain grand grape grass gravy great green grid
grill group grow guard guess guide guitar habit hair half hall happy harbor hard harp hawk hazel heart heat hedge
helmet herb hero hill hobby holiday honey hood hook hope horn horse host hotel hour house humor hunt hurry ice
icon idea igloo image inch index ink inner input iron island ivory jacket jaguar jam jar jazz jeans jelly jewel
job join joke jolly judge juice jump jungle junior kayak keen kettle key kick kind king kite kiwi knee knife knot
koala label lace ladder lake lamp land lane laser late laugh lava lawn layer lazy leaf lemon lens level light
lilac lime linen lion list little live llama lobby local lock lodge logic lone long loop lotus loud love lucky
lunar lunch lungs magic magnet mail major mango maple march market mask match maze meadow medal melon memo menu
merry metal meter middle mild milk mill mind mint minute mirror mixer model modern moment money monkey month moon
moose morning moss motor mountain mouse movie mud mug museum music mystery nail name napkin narrow nature navy
near neat neck needle nest net never new next nice night noble noise north note novel number nurse nut oak oasis
ocean october odd offer office olive omega onion open opera orange orbit orchid order organ otter outer oval oven
owl owner oyster pace paddle page paint palm panda panel paper parade park party pasta path patio peace peach
pearl pedal pencil pepper piano pickle pilot pine pink pipe pizza place plain planet plant plate plaza plum poem
point polar pond pony pool poppy porch pot powder power prize proud pulse pump puppy purple puzzle quack queen
quest quick quiet quilt quiz rabbit radar radio rain ramp ranch rapid raven razor ready rebel recipe red reef
relax remote rhythm ribbon rice ride ridge ring ripple river road robin robot rocket rocky roof room root rope
rose rough round royal ruby rugby ruler rumor safari sail salad salt sand satin sauce scale scarf scene school
science scoop scout screen sea seal season seed seven shadow shark sheep shelf shell shine ship shirt shoe shore
short shrub silk silver simple siren sister sketch skill sky sled sleep slice slope small smile smoke snack snail
snow soap soccer sock sofa soft solar solid sonic soup south space spark spice spider spike spoon sport spring
spruce square squid stable stage stamp star steam steel stem stone storm story stove straw stream street strong
sugar summer sun super swamp swan sweet swift swim table tail talent tango tank tea teach team tennis tent thunder
ticket tiger timber tiny toast today token tomato tool topic torch tower toy track trail train tree trend tribe
trick trophy truck trust tulip tuna tunnel turtle twelve twin uncle under unit upper urban usual valley value
vapor velvet venus verse vest video view violet violin visit vivid voice volcano vote wagon walnut walrus wave
wealth weather west whale wheat wheel whistle wide wild willow wind window wing winter wise wolf wonder wood wool
world yacht yard year yellow yoga young zebra zero zigzag zone""".split()


def _password(length, sets, exclude_ambiguous):
    pools = [[c for c in s if not (exclude_ambiguous and c in AMBIGUOUS)] for s in sets]
    pools = [p for p in pools if p]
    every = [c for p in pools for c in p]
    chars = [secrets.choice(p) for p in pools][:length]          # at least one from every chosen group
    chars += [secrets.choice(every) for _ in range(length - len(chars))]
    rng.shuffle(chars)
    return "".join(chars), len(every)


def passwords(opts):
    mode = opts.get("mode", "password")
    n = _count(opts)
    items = []
    if mode == "password":
        length = _int(opts, "length", 16, 4, 128, "Length")
        symbols = str(opts.get("symbols_set") or SYMBOLS)
        sets = []
        if _bool(opts, "upper", True): sets.append(string.ascii_uppercase)
        if _bool(opts, "lower", True): sets.append(string.ascii_lowercase)
        if _bool(opts, "digits", True): sets.append(string.digits)
        if _bool(opts, "symbols", True): sets.append(symbols)
        if not sets:
            raise GenError("upper", "Choose at least one group of characters.")
        if length < len(sets):
            raise GenError("length", f"Length must be at least {len(sets)} to use every chosen group.")
        for _ in range(n):
            pw, pool = _password(length, sets, _bool(opts, "no_ambiguous"))
            items.append({"value": pw, **strength(length * math.log2(pool))})
    elif mode == "passphrase":
        words = _int(opts, "words", 5, 3, 12, "Words")
        sep = str(opts.get("separator", "-"))[:3]
        cap, num = _bool(opts, "capitalize", True), _bool(opts, "number", True)
        for _ in range(n):
            ws = [secrets.choice(WORDS) for _ in range(words)]
            if cap:
                ws = [w.capitalize() for w in ws]
            bits = words * math.log2(len(WORDS))
            if num:
                i = secrets.randbelow(words)
                ws[i] += str(secrets.randbelow(100))
                bits += math.log2(100 * words)
            items.append({"value": sep.join(ws), **strength(bits)})
    elif mode == "pin":
        length = _int(opts, "length", 6, 4, 12, "PIN length")
        bad = {"0" * length, "1234567890"[:length], "0123456789"[:length], "9876543210"[:length]}
        for _ in range(n):
            while True:
                pin = "".join(secrets.choice(string.digits) for _ in range(length))
                if pin not in bad and len(set(pin)) > 2:  # skip 0000, 1234, 1111 …
                    break
            items.append({"value": pin, **strength(length * math.log2(10))})
    else:
        raise GenError("mode", "Unknown password type.")
    return {"items": items, "info": {"wordlist": len(WORDS)}}


# =========================================================================== emails
FIRST = """Jean Aline Eric Grace Diane Patrick Claudine Olivier Divine Kevin Wanjiru Otieno Achieng Kamau Njeri
Nakato Mukasa Amani Neema Baraka Zawadi Ivan Olga Anna Dmitry Natalia Sergei Priya Rahul Aisha Fatima Omar
Yusuf Li Wei Mei Yuki Hiro Maria Carlos Lucia Pedro John Emma Liam Sophie Lucas Chloe Amara Kwame Zainab
Chidi Ama Kofi Sara Noah Mia Elena Marco Leila Hassan Tariq Ngozi Thabo Lerato Sipho Ines Hugo Clara""".split()
LAST = """Uwimana Habimana Niyonzima Mugisha Ndayisaba Uwase Mukamana Nshimiyimana Kamau Odhiambo Mwangi Otieno
Okello Namubiru Mushi Mwakyusa Ivanov Petrova Smirnov Kuznetsova Sharma Patel Khan Singh Wang Chen Zhang Tanaka
Sato Garcia Silva Santos Lopez Smith Johnson Brown Williams Müller Schmidt Martin Dubois Rossi Bianchi Mensah
Okafor Diallo Traoré Nkosi Dlamini Haddad Rahman Novak Kowalski Andersen Nielsen Costa Fernández""".split()
ADJ = "sunny happy swift brave calm clever bright lucky quiet bold cosmic green blue golden silver wild".split()
NOUN = "river tiger eagle panda falcon cloud rocket lion maple ocean comet forest pixel wave star".split()
ROLES = "info support sales admin hr billing contact hello noreply team careers office accounts help".split()

SAFE_DOMAINS = ["example.com", "example.org", "example.net", "mail.test", "company.test", "school.test"]
PROVIDER_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "proton.me", "mail.ru", "yandex.ru"]
EMAIL_TYPES = {
    "name": "first.last", "name_number": "firstlast + number", "initial": "f.last", "underscore": "first_last",
    "username": "nickname + number", "random": "random letters", "role": "role (info@, support@ …)",
    "plus": "plus address (name+tag@)", "subdomain": "name@mail.sub.domain", "student": "student id",
    "work": "work (f.last@company)", "mixed": "mix of all types",
}


def _ascii(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if c.isascii() and c.isalnum()).lower()


def _domain_ok(d):
    labels = d.split(".")
    return (3 < len(d) <= 253 and len(labels) >= 2 and labels[-1].isalpha() and len(labels[-1]) >= 2 and
            all(lab and len(lab) <= 63 and lab[0] != "-" and lab[-1] != "-" and
                all(c.isalnum() or c == "-" for c in lab) for lab in labels))


def emails(opts):
    kind = opts.get("type", "mixed")
    if kind not in EMAIL_TYPES:
        raise GenError("type", "Unknown email type.")
    source = opts.get("domains", "safe")
    custom = str(opts.get("domain") or "").strip().lower().lstrip("@")
    if source == "custom":
        if not _domain_ok(custom):
            raise GenError("domain", "Type a domain like mycompany.com")
        domains = [custom]
    elif source == "providers":
        domains = PROVIDER_DOMAINS
    else:
        domains = SAFE_DOMAINS
    seen, items = set(), []
    kinds = [k for k in EMAIL_TYPES if k != "mixed"]
    n = _count(opts)
    while len(items) < n:
        k = secrets.choice(kinds) if kind == "mixed" else kind
        first, last = secrets.choice(FIRST), secrets.choice(LAST)
        f, l = _ascii(first), _ascii(last)
        dom = secrets.choice(domains)
        num = secrets.randbelow(99) + 1
        local = {
            "name": f"{f}.{l}",
            "name_number": secrets.choice([f"{f}{l}{num}", f"{f}.{l}{1960 + secrets.randbelow(50)}", f"{f}{num}"]),
            "initial": secrets.choice([f"{f[0]}.{l}", f"{f[0]}{l}", f"{f}{l[0]}"]),
            "underscore": f"{f}_{l}",
            "username": f"{secrets.choice(ADJ)}{secrets.choice(NOUN)}{num}",
            "random": "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10)),
            "role": secrets.choice(ROLES),
            "plus": f"{f}.{l}+{secrets.choice(['news', 'shop', 'test', 'bank', 'work', 'promo'])}{num}",
            "subdomain": f"{f}.{l}",
            "student": f"s{2020 + secrets.randbelow(7)}{secrets.randbelow(10 ** 5):05d}",
            "work": f"{f[0]}.{l}",
        }[k]
        if k == "subdomain":
            dom = f"{secrets.choice(['mail', 'staff', 'dept', 'hq'])}.{dom}"
        elif k == "student":
            dom = f"students.{dom}"
        email = f"{local}@{dom}"
        if email in seen:
            continue
        seen.add(email)
        items.append({"value": email, "type": EMAIL_TYPES[k], "name": "" if k in ("role", "random", "username", "student")
                      else f"{first} {last}"})
    return {"items": items, "info": {"domains": domains}}


# =========================================================================== phone numbers
# ISO  national-number-length  mobile-prefixes  grouping  [trunk]       (checked against national numbering plans)
PHONE_RULES = """
RW 9 78,79,72,73 3-3-3|KE 9 70,71,72,74,75,76,79,11,10 3-6|UG 9 70,71,74,75,76,77,78 3-6|TZ 9 61,62,65,67,68,69,71,73,74,75,76,77,78 3-3-3
BI 8 61,62,68,69,71,72,75,76,77,79 2-2-2-2|SS 9 91,92,95,97,98 3-3-3|CD 9 81,82,83,84,85,89,90,91,97,99 3-3-3
SO 9 61,62,63,65,68,69,71,77,90 2-3-4|ET 9 91,92,93,94,96,97,98,99,70 2-3-4|ER 7 7 1-3-3|DJ 8 77 2-2-2-2|SD 9 90,91,92,96,99,11,12 2-3-4
MW 9 88,99,98,89 3-3-3|ZM 9 95,96,97,76,77 3-3-3|ZW 9 71,73,77,78 2-3-4|MZ 9 82,83,84,85,86,87 2-3-4|MG 9 32,33,34,38 2-2-3-2
MU 8 5 4-4|SC 7 2 1-3-3|KM 7 3 3-2-2
NG 10 803,806,813,816,703,706,802,808,812,708,805,807,815,905,809,817,818,909,701,902,901,904,907,912 3-3-4
GH 9 20,23,24,26,27,28,50,53,54,55,56,57,59 2-3-4|ZA 9 60,61,62,63,64,65,66,67,68,71,72,73,74,76,78,79,81,82,83,84 2-3-4
EG 10 10,11,12,15 3-3-4|MA 9 6,7 3-2-2-2|DZ 9 5,6,7 3-2-2-2|TN 8 2,5,9 2-3-3 -|CM 9 6 3-3-3 -|SN 9 70,75,76,77,78 2-3-2-2 -
CI 10 01,05,07 2-2-2-2-2 -|AO 9 91,92,93,94,95,99 3-3-3 -
GB 10 7 4-6|IE 9 83,85,86,87,89 2-3-4|FR 9 6,7 1-2-2-2-2|DE 11 151,152,157,159,160,162,163,170,171,172,173,174,175,176,177,178,179 3-8
IT 10 32,33,34,35,36,37,38,39 3-3-4 -|ES 9 6,7 3-3-3 -|PT 9 91,92,93,96 3-3-3 -|NL 9 6 1-8|BE 9 46,47,48,49 3-2-2-2
CH 9 75,76,77,78,79 2-3-2-2|AT 10 650,660,664,676,680,681,688,699 3-7|PL 9 50,51,53,57,60,66,69,72,73,78,79,88 3-3-3 -
SE 9 70,72,73,76,79 2-3-2-2|NO 8 4,9 3-2-3 -|DK 8 2,3,4,5,6,7,8,9 2-2-2-2 -|FI 9 40,41,44,45,50 2-3-4
RU 10 9 3-3-2-2 8|KZ 10 70,74,77 3-3-2-2 8|UA 9 50,63,66,67,68,73,93,95,96,97,98,99 2-3-2-2|BY 9 25,29,33,44 2-3-2-2 8
UZ 9 90,91,93,94,95,97,98,99,33,88 2-3-2-2 -|TR 10 50,53,54,55 3-3-2-2|GR 10 69 3-3-4 -|RO 9 7 3-3-3|CZ 9 6,7 3-3-3 -
IN 10 6,7,8,9 5-5|PK 10 30,31,32,33,34 3-7|BD 10 13,14,15,16,17,18,19 4-6|LK 9 70,71,72,74,75,76,77,78 2-3-4|NP 10 98,97 3-7 -
CN 11 130,131,132,133,134,135,136,137,138,139,150,151,152,153,155,156,157,158,159,166,177,180,181,182,183,185,186,187,188,189,199 3-4-4 -
HK 8 5,6,9 4-4 -|TW 9 9 3-3-3|JP 10 70,80,90 2-4-4|KR 10 10 2-4-4
PH 10 905,906,915,916,917,926,927,935,936,945,955,956,975,977,995,997,908,918,919,920,921,928,929,939,947,949,961,998,999 3-3-4
ID 11 811,812,813,821,822,852,853,855,856,857,858,877,878,881,895,896,897,898,899,838,831 3-4-4|MY 9 12,13,14,16,17,19 2-3-4
SG 8 8,9 4-4 -|TH 9 6,8,9 2-3-4|VN 9 3,5,7,8,9 2-3-4|AE 9 50,52,54,55,56,58 2-3-4|SA 9 50,53,54,55,56,57,58,59 2-3-4
QA 8 3,5,6,7 4-4 -|KW 8 5,6,9 4-4 -|IL 9 50,52,53,54,55,58 2-3-4|IR 10 91,92,93,99,90 3-3-4|IQ 10 75,77,78,79 3-3-4
JO 9 77,78,79 1-4-4|LB 8 70,71,76,78,79,81 2-3-3|AU 9 4 3-3-3|NZ 9 21,22,27 2-3-4
BR 11 119,219,319,419,519,619,719,819,859,919 2-5-4|MX 10 55,33,81,22,44,99 2-4-4 -|AR 11 911,9351,9341,9261,9221 1-2-4-4
CO 10 30,31,32,35 3-3-4 -|CL 9 9 1-4-4 -|PE 9 9 3-3-3 -|VE 10 412,414,416,424,426 3-7|EC 9 9 2-3-4|CU 8 5 1-3-4
"""
# Countries below: correct calling code and usual length; mobile prefixes are approximate.
PHONE_APPROX = """AF 9 7|AL 9 6|AD 6 3,4,6 -|AM 8 9,7,4,5|AW 7 5,6,7,9 -|AZ 9 50,51,55,70,77|BH 8 3 -|BZ 7 6 -|BJ 10 01 -
BT 8 17,77 -|BO 8 6,7 -|BA 8 6|BW 8 7 -|BN 7 7,8 -|BG 9 87,88,89,98|BF 8 6,7 -|KH 9 1,6,7,8,9|CV 7 9,5 -|CF 8 7 -|TD 8 6,9 -
CG 9 06,05,04 -|CK 5 5,7 -|CR 8 6,7,8 -|HR 9 91,92,95,97,98,99|CW 8 9 -|CY 8 9 -|SV 8 6,7 -|GQ 9 222,551 -|EE 8 5 -|SZ 8 7 -
FK 5 5,6 -|FO 6 2,5,7,9 -|FJ 7 7,8,9 -|GF 9 694|PF 8 87,89 -|GA 8 06,07 -|GM 7 7,3,2,5,6,9 -|GE 9 5|GI 8 5 -|GL 6 2,4,5 -
GP 9 690|GT 8 3,4,5 -|GN 9 6 -|GW 9 95,96 -|GY 7 6 -|HT 8 3,4 -|HN 8 3,9 -|HU 9 20,30,31,50,70 06|IS 7 6,7,8 -|LA 10 20
LV 8 2 -|LS 8 5,6 -|LR 9 77,88|LY 9 91,92,94|LI 7 7 -|LT 8 6 8|LU 9 6 -|MO 8 6 -|MV 7 7,9 -|ML 8 6,7 -|MT 8 79,99 -|MH 7 4,5 -
MQ 9 696|MR 8 2,3,4 -|YT 9 639|FM 7 3,9 -|MD 8 6,7|MC 8 6 -|MN 8 8,9 -|ME 8 6|MM 9 9|NA 9 81,85|NR 7 5 -|NC 6 7,8,9 -|NI 8 8 -
NE 8 9 -|NU 4 1,3,4 -|NF 6 3,5 -|KP 10 191,195|MK 8 7|OM 8 9,7 -|PW 7 7,6 -|PS 9 59,56|PA 8 6 -|PG 8 7 -|PY 9 9|RE 9 692,693
BL 9 690|SH 4 5,6 -|PM 6 4,5 -|MF 9 690|WS 7 7 -|SM 10 66 -|ST 7 9 -|RS 9 6|SL 8 7,3|SK 9 9|SI 8 30,31,40,41,51,64,68,69,70,71
SB 7 7,8 -|SR 7 8 -|SY 9 9|TJ 9 9 -|TL 8 7 -|TG 8 9,7 -|TK 4 7 -|TO 7 7,8 -|TM 8 6 8|TV 6 9 -|UY 8 9|VU 7 5,7 -|VA 10 3 -
WF 6 8 -|YE 9 7|XK 8 4|KG 9 5,7,2|KI 8 7 -|EH 9 6,7|AX 10 4|SJ 8 4,9 -|IO 7 3 -|CX 9 4|CC 9 4|PN 9 4|BQ 7 3,4 -|GG 10 7
JE 10 7|IM 10 7|AC 4 4 -|TA 4 8 -"""

NANP_AREAS = {"US": "201 202 205 206 212 213 214 215 301 303 305 310 312 404 415 503 512 602 617 646 702 713 718 808 917",
              "CA": "204 250 306 403 416 418 506 514 587 604 613 647 709 780 902 905",
              "DO": "809 829 849", "PR": "787 939", "JM": "876 658"}
DEFAULT_GROUPS = {4: "4", 5: "5", 6: "3-3", 7: "3-4", 8: "4-4", 9: "3-3-3", 10: "3-3-4", 11: "3-4-4", 12: "4-4-4"}


def _parse_rules(text, exact):
    """Exact lines: ISO length prefixes grouping [trunk].  Approximate lines: ISO length prefixes [trunk]."""
    rules = {}
    for chunk in text.replace("\n", "|").split("|"):
        parts = chunk.split()
        if not parts:
            continue
        iso, length, prefixes, rest = parts[0], int(parts[1]), parts[2].split(","), parts[3:]
        groups = rest.pop(0) if exact else DEFAULT_GROUPS.get(length, "3-3-4")
        trunk = rest[0] if rest else "0"
        rules[iso] = {"len": length, "mobile": prefixes, "groups": groups, "trunk": "" if trunk == "-" else trunk,
                      "exact": exact}
    return rules


RULES = {**_parse_rules(PHONE_APPROX, False), **_parse_rules(PHONE_RULES, True)}


def _group(nsn, pattern):
    out, i = [], 0
    for size in map(int, pattern.split("-")):
        out.append(nsn[i:i + size])
        i += size
    if i < len(nsn):
        out[-1] += nsn[i:]
    return " ".join(p for p in out if p)


def _digits(n):
    return "".join(secrets.choice(string.digits) for _ in range(n))


def _nanp(iso, dial, kind, safe):
    """US, Canada and the Caribbean: +1 area-code exchange-number, e.g. (415) 555-0123."""
    area = secrets.choice(NANP_AREAS[iso].split()) if iso in NANP_AREAS else dial[1:]
    if safe:
        exchange, line = "555", "01" + _digits(2)      # 555-0100 … 555-0199 is reserved for fiction
    else:
        exchange = secrets.choice("23456789") + _digits(2)
        if exchange[1:] == "11":
            exchange = exchange[0] + "21"
        line = _digits(4)
    nsn = area + exchange + line
    return {"e164": f"+1{nsn}", "international": f"+1 {area}-{exchange}-{line}",
            "national": f"({area}) {exchange}-{line}", "type": "mobile or landline"}


def _phone_builtin(iso, kind, safe):
    c = COUNTRIES[iso]
    dial = c["dial"]
    if dial.startswith("1"):
        return _nanp(iso, dial, kind, safe)
    r = RULES.get(iso) or {"len": 8, "mobile": ["9"], "groups": "4-4", "trunk": "0", "exact": False}
    if iso == "GB" and safe:
        nsn = "7700900" + _digits(3)                  # Ofcom drama range 07700 900000 - 900999
    elif kind == "landline":
        first = secrets.choice([d for d in "23456" if not any(p.startswith(d) for p in r["mobile"])] or ["2"])
        nsn = first + _digits(r["len"] - 1)
    else:
        prefix = secrets.choice(r["mobile"])
        nsn = prefix + _digits(r["len"] - len(prefix))
    grouped = _group(nsn, r["groups"])
    if iso in ("BR",):
        national = f"({nsn[:2]}) {nsn[2:7]}-{nsn[7:]}"
    elif iso in ("RU", "KZ", "BY"):
        national = f"8 ({nsn[:3]}) {nsn[3:6]}-{nsn[6:8]}-{nsn[8:]}" if len(nsn) == 10 else f"8 {grouped}"
    else:
        national = (r["trunk"] + " " if len(r["trunk"]) > 1 else r["trunk"]) + grouped
    return {"e164": f"+{dial}{nsn}", "international": f"+{dial} {grouped}", "national": national,
            "type": kind}


def _phone_lib(iso, kind):
    """Exact numbers with Google's libphonenumber when it is installed."""
    want = PhoneNumberType.MOBILE if kind == "mobile" else PhoneNumberType.FIXED_LINE
    ex = phonenumbers.example_number_for_type(iso, want) or phonenumbers.example_number_for_type(iso, PhoneNumberType.FIXED_LINE_OR_MOBILE)
    if ex is None:
        return None
    nsn = phonenumbers.national_significant_number(ex)
    ok_types = (want, PhoneNumberType.FIXED_LINE_OR_MOBILE)
    for keep in (max(2, len(nsn) // 2), 3, 2, 1):
        for _ in range(40):
            cand = nsn[:keep] + _digits(len(nsn) - keep)
            num = phonenumbers.parse(f"+{ex.country_code}{cand}")
            if phonenumbers.is_valid_number_for_region(num, iso) and phonenumbers.number_type(num) in ok_types:
                return {"e164": phonenumbers.format_number(num, PhoneNumberFormat.E164),
                        "international": phonenumbers.format_number(num, PhoneNumberFormat.INTERNATIONAL),
                        "national": phonenumbers.format_number(num, PhoneNumberFormat.NATIONAL),
                        "type": kind, "operator": carrier.name_for_number(num, "en") or "",
                        "area": geocoder.description_for_number(num, "en") or ""}
    return None


def phone_quality(iso):
    if phonenumbers is not None:
        return "exact"
    if COUNTRIES[iso]["dial"].startswith("1") or RULES.get(iso, {}).get("exact"):
        return "real prefixes"
    return "approximate"


def phones(opts):
    iso = str(opts.get("country", "RW")).upper()
    kind = opts.get("kind", "mobile")
    if kind not in ("mobile", "landline"):
        raise GenError("kind", "Choose mobile or landline.")
    if iso != "ALL" and iso not in COUNTRIES:
        raise GenError("country", "Choose a country.")
    safe = _bool(opts, "safe")
    items = []
    for _ in range(_count(opts)):
        code = secrets.choice(COUNTRY_LIST)["code"] if iso == "ALL" else iso
        p = None
        if phonenumbers is not None and not safe:
            try:
                p = _phone_lib(code, kind)
            except Exception:
                p = None
        p = p or _phone_builtin(code, kind, safe)
        c = COUNTRIES[code]
        p.update(country=c["name"], flag=c["flag"], iso=code, dial="+" + c["dial"], value=p["international"],
                 quality="exact" if "operator" in p else "fictional (safe)" if safe and (code in ("GB",) or c["dial"].startswith("1"))
                 else phone_quality(code))
        items.append(p)
    return {"items": items, "info": {"library": phonenumbers is not None,
                                     "safe_available": iso in ("US", "CA", "GB") or COUNTRIES.get(iso, {}).get("dial", "").startswith("1")}}


# =========================================================================== passport numbers
# Pattern letters:  A = letter   9 = digit   X = letter or digit   L = letter except Q X Z
#                   D = German set (C F G H J K L M N P R T V W X Y Z 0-9)   N = letter/digit without O   {..} = fixed text
PASSPORT_FORMATS = {
    # known public formats
    "US": (["999999999", "A99999999"], "known"), "GB": (["999999999"], "known"), "CA": (["AA999999"], "known"),
    "AU": (["A9999999", "AA9999999"], "known"), "NZ": (["AA999999"], "known"), "IE": (["AA9999999"], "known"),
    "FR": (["99AA99999"], "known"), "DE": (["{C}DDDDDDDD"], "known"), "IT": (["AA9999999"], "known"),
    "ES": (["AAA999999"], "known"), "NL": (["AANNNNNN9"], "known"), "BE": (["AA999999"], "known"),
    "CH": (["A9999999"], "known"), "AT": (["A9999999"], "known"), "PL": (["AA9999999"], "known"),
    "SE": (["99999999"], "known"), "FI": (["AA9999999"], "known"), "DK": (["999999999"], "known"),
    "RU": (["99 9999999"], "known"), "UA": (["AA999999"], "known"), "BY": (["AA9999999"], "known"),
    "KZ": (["{N}99999999"], "known"), "UZ": (["AA9999999"], "known"), "TR": (["A99999999"], "known"),
    "IN": (["L9999999"], "known"), "PK": (["AA9999999"], "known"), "LK": (["A9999999"], "known"),
    "CN": (["{E}99999999", "{EA}9999999"], "known"), "JP": (["AA9999999"], "known"),
    "KR": (["{M}99999999", "{M}999A9999"], "known"), "SG": (["A9999999A"], "known"), "MY": (["A99999999"], "known"),
    "PH": (["A9999999A"], "known"), "TH": (["AA9999999"], "known"), "VN": (["A99999999"], "known"),
    "NG": (["A99999999"], "known"), "ZA": (["A99999999"], "known"), "BR": (["AA999999"], "known"),
    "AR": (["AAA999999"], "known"),
    # format seen in practice, not officially published
    "RW": (["{PC}9999999"], "approximate"), "KE": (["{AK}9999999", "{A}9999999"], "approximate"),
    "UG": (["{A}99999999"], "approximate"), "TZ": (["{AB}999999"], "approximate"), "PT": (["A999999"], "approximate"),
    "NO": (["99999999"], "approximate"), "BD": (["AA9999999"], "approximate"), "NP": (["99999999"], "approximate"),
    "ID": (["A9999999"], "approximate"), "AE": (["999999999"], "approximate"), "SA": (["A9999999"], "approximate"),
    "IL": (["99999999"], "approximate"), "EG": (["A99999999"], "approximate"), "GH": (["{G}9999999"], "approximate"),
    "MX": (["A99999999"], "approximate"), "CO": (["AA999999"], "approximate"), "CL": (["A99999999"], "approximate"),
}
GENERIC_PASSPORT = ["AA9999999"]  # ICAO 9303 allows up to 9 letters/digits
TOKEN_SETS = {"A": string.ascii_uppercase, "9": string.digits, "X": string.ascii_uppercase + string.digits,
              "L": "ABCDEFGHIJKLMNOPRSTUVWY", "D": "CFGHJKLMNPRTVWXYZ0123456789",
              "N": "ABCDEFGHIJKLMNPQRSTUVWXYZ0123456789"}


def _from_pattern(pattern):
    out, fixed = [], False
    for ch in pattern:
        if ch == "{":
            fixed = True
        elif ch == "}":
            fixed = False
        elif fixed or ch not in TOKEN_SETS:
            out.append(ch)
        else:
            out.append(secrets.choice(TOKEN_SETS[ch]))
    return "".join(out)


def describe_pattern(pattern):
    """'AA9999999' -> '2 letters + 7 digits'."""
    words = {"A": "letter", "9": "digit", "X": "letter/digit", "L": "letter", "D": "letter/digit", "N": "letter/digit"}
    parts, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "{":
            j = pattern.index("}", i)
            parts.append(f'"{pattern[i + 1:j]}"')
            i = j + 1
            continue
        if ch == " ":
            i += 1
            continue
        j = i
        while j < len(pattern) and pattern[j] == ch:
            j += 1
        n = j - i
        word = words.get(ch, ch)
        if n > 1:
            word = "/".join(w + "s" for w in word.split("/"))
        parts.append(f"{n} {word}")
        i = j
    return " + ".join(parts)


def passports(opts):
    iso = str(opts.get("country", "RW")).upper()
    if iso != "ALL" and iso not in COUNTRIES:
        raise GenError("country", "Choose a country.")
    items = []
    for _ in range(_count(opts)):
        code = secrets.choice(COUNTRY_LIST)["code"] if iso == "ALL" else iso
        patterns, quality = PASSPORT_FORMATS.get(code, (GENERIC_PASSPORT, "generic"))
        pattern = secrets.choice(patterns)
        c = COUNTRIES[code]
        items.append({"value": _from_pattern(pattern), "country": c["name"], "flag": c["flag"], "iso": code,
                      "format": describe_pattern(pattern), "quality": quality})
    return {"items": items, "info": {"known": sum(1 for v in PASSPORT_FORMATS.values() if v[1] == "known")}}


# =========================================================================== dispatcher
TOOLS = {"otp": otp_codes, "password": passwords, "email": emails, "phone": phones, "passport": passports}


def generate(tool, opts):
    if tool not in TOOLS:
        raise GenError("tool", "Unknown generator.")
    return TOOLS[tool](opts or {})
