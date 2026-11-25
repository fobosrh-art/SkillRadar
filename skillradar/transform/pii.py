"""Personal-data anonymisation applied at ingestion (raw file -> Bronze table).

* Dedicated contact fields (contact_email, contact_phone, facts.contact_email) are
  removed and replaced by presence flags.
* E-mail addresses and phone numbers inside free text are replaced by [EMAIL] / [PHONE].
* Identifier/URL fields are never rewritten (some native ids contain long digit runs).
"""
from __future__ import annotations

import re
from typing import Any

# \w is Unicode-aware: also catches internationalised addresses such as hr@nümunəşirkət.az
EMAIL_RE = re.compile(r"[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[^\W\d_]{2,}")
# obfuscated / broken addresses such as "account ant @nümunə.az" (observed in real data):
# a bare "@domain.tld" plus at most one preceding word. "@handle" without a dot is left alone.
BROKEN_EMAIL_RE = re.compile(r"(?:[\w.%+\-]+\s)?@[\w\-]+(?:\.[\w\-]+)*\.[^\W\d_]{2,}")
# a run of digits with phone separators; validated by digit count below
PHONE_CANDIDATE_RE = re.compile(r"(?<![\w])\+?\(?\d[\d\s\-().]{7,}\d(?![\w])")
PHONE_MIN_DIGITS, PHONE_MAX_DIGITS = 9, 13

CONTACT_KEYS = {"contact_email", "contact_phone", "contact_name", "contact_person"}
SKIP_KEYS = {"id", "url", "source_url", "company_logo", "slug", "source", "posted_at", "deadline_at",
             "first_seen_at", "ingested_at", "deactivated_at"}


def _phone_sub(m: re.Match) -> str:
    digits = sum(ch.isdigit() for ch in m.group(0))
    if PHONE_MIN_DIGITS <= digits <= PHONE_MAX_DIGITS:
        return "[PHONE]"
    return m.group(0)


def redact_text(text: str) -> tuple[str, int]:
    count = 0
    new, n = EMAIL_RE.subn("[EMAIL]", text)
    count += n
    new, n = BROKEN_EMAIL_RE.subn("[EMAIL]", new)
    count += n
    redacted = PHONE_CANDIDATE_RE.sub(_phone_sub, new)
    count += redacted.count("[PHONE]") - new.count("[PHONE]")
    return redacted, count


def contains_pii(text: str | None) -> bool:
    if not text:
        return False
    return redact_text(text)[1] > 0


def anonymize_record(record: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return (anonymised deep copy, number of redactions)."""
    total = 0

    def walk(obj: Any, key: str | None = None) -> Any:
        nonlocal total
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in CONTACT_KEYS:
                    if v not in (None, ""):
                        total += 1
                    out[f"{k}_present"] = v not in (None, "")
                    continue
                out[k] = walk(v, k)
            return out
        if isinstance(obj, list):
            return [walk(v, key) for v in obj]
        if isinstance(obj, str) and key not in SKIP_KEYS:
            red, n = redact_text(obj)
            total += n
            return red
        return obj

    return walk(record), total
