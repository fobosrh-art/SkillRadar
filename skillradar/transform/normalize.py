"""Field-level normalisation rules (pure functions, unit-tested).

Principle: normalise representation, never invent values. Unknown inputs are kept
as-is (and logged as issues) rather than guessed.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .text import norm_key

# ---------------------------------------------------------------- city / location
BAKU_ALIASES = {"baki", "baku", "баку", "baky", "baki seheri", "baku city", "г баку", "город баку"}
COUNTRY_TOKENS = {"azerbaijan", "azerbaycan", "азербайджан", "az", "aze", "azerbaijan republic"}


def normalize_city(location: str | None, city: str | None = None) -> str | None:
    """'Bakı', 'Bakı, Azərbaycan', 'Баку', 'Baku, Azerbaijan' -> 'Baku'. Anything else: returned unchanged."""
    for value in (city, location):
        if not value:
            continue
        parts = [norm_key(p) for p in re.split(r"[,/;|]", value)]
        parts = [p for p in parts if p and p not in COUNTRY_TOKENS]
        if parts and all(p in BAKU_ALIASES for p in parts):
            return "Baku"
    raw = city or location
    return raw.strip() if raw else None


# ---------------------------------------------------------------- dates
def parse_ts(value) -> datetime | None:
    if value in (None, ""):
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


# ---------------------------------------------------------------- currency / salary
CURRENCY_MAP = {"azn": "AZN", "manat": "AZN", "₼": "AZN",
                "usd": "USD", "$": "USD", "dollar": "USD", "eur": "EUR", "€": "EUR", "rub": "RUB", "₽": "RUB"}
KNOWN_CURRENCIES = {"AZN", "USD", "EUR", "RUB", "GBP", "TRY"}


def normalize_currency(value) -> str | None:
    if value in (None, ""):
        return None
    s = str(value).strip()
    return CURRENCY_MAP.get(s.lower(), s.upper())


# Amounts below this are placeholders, not pay (observed: salary_from=1, salary_to=1 on vakansiya_biz).
MIN_PLAUSIBLE_AMOUNT = 10


def parse_amount(value) -> float | None:
    """Numbers or numeric strings ('1 200', '1200.50').
    0 / negative / placeholder (< MIN_PLAUSIBLE_AMOUNT) / unparsable -> None (= not stated, never imputed)."""
    if value is None or isinstance(value, bool) or value == "":   # note: 1 == True in Python
        return None
    if isinstance(value, (int, float)):
        num = float(value)
    else:
        s = re.sub(r"[\s ]", "", str(value)).replace(",", ".")
        if not re.fullmatch(r"\d+(\.\d+)?", s):
            return None
        num = float(s)
    return num if num >= MIN_PLAUSIBLE_AMOUNT else None


# ---------------------------------------------------------------- employment type
EMPLOYMENT_MAP = {
    "full time": "full_time", "fulltime": "full_time", "tam stat": "full_time", "tam is gunu": "full_time",
    "полная занятость": "full_time", "part time": "part_time", "yarim stat": "part_time",
    "natamam is gunu": "part_time", "частичная занятость": "part_time", "contractor": "contract",
    "contract": "contract", "muqavile": "contract", "internship": "internship", "intern": "internship",
    "tecrube": "internship", "стажировка": "internship", "volunteer": "volunteer", "konullu": "volunteer",
    "temporary": "temporary", "muveqqeti": "temporary", "freelance": "freelance", "serbest": "freelance",
    "remote": "remote",
}


def normalize_employment(value) -> str | None:
    if value in (None, ""):
        return None
    key = norm_key(str(value).replace("_", " ").replace("-", " "))
    return EMPLOYMENT_MAP.get(key, "other")


PLACEHOLDER_LABELS = {"career levels undefined", "undefined", "null", "none", "n a", "-"}


def clean_label(value) -> str | None:
    if value in (None, ""):
        return None
    s = str(value).strip()
    return None if norm_key(s) in PLACEHOLDER_LABELS else s


# ---------------------------------------------------------------- company
LEGAL_FORMS = {"mmc", "asc", "qsc", "aasc", "llc", "ltd", "limited", "inc", "jsc", "ojsc", "cjsc", "ooo", "оао",
               "ооо", "зао", "пао", "plc", "gmbh", "ag", "sa", "bv", "co", "corp", "corporation", "ik", "fi",
               "mmc nin", "filiali", "branch"}


def company_key(name: str | None) -> str | None:
    """Comparable key: folded, punctuation removed, legal-form tokens dropped."""
    if not name:
        return None
    tokens = [t for t in norm_key(name).split() if t not in LEGAL_FORMS]
    key = " ".join(tokens)
    return key or norm_key(name) or None


def title_key(title: str | None) -> str | None:
    if not title:
        return None
    return norm_key(title) or None
