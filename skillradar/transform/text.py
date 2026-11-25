"""Text normalisation shared by dedup, company keys and skill matching.

`fold()` lower-cases and strips diacritics **character by character** so the folded
string has exactly the same length as the original: a match found at [start:end]
in the folded text points to the same characters in the original text. This is
what lets us store exact evidence ("matched_text") for every extracted skill.
"""
from __future__ import annotations

import html
import re
import unicodedata

# Azerbaijani / Turkish letters that str.lower()/NFKD do not fold to the ASCII form we want.
_SPECIAL = {
    "İ": "i", "I": "i", "ı": "i", "Ə": "e", "ə": "e", "Ş": "s", "ş": "s", "Ç": "c", "ç": "c",
    "Ğ": "g", "ğ": "g", "Ö": "o", "ö": "o", "Ü": "u", "ü": "u", "ё": "е", "Ё": "е",
    "’": "'", "‘": "'", "–": "-", "—": "-", " ": " ",
}


def _fold_char(ch: str) -> str:
    c = _SPECIAL.get(ch)
    if c is not None:
        return c
    c = ch.lower()
    if len(c) != 1:
        c = c[0]
    decomposed = unicodedata.normalize("NFKD", c)
    return decomposed[0] if decomposed else c


def fold(text: str | None) -> str:
    if not text:
        return ""
    return "".join(_fold_char(ch) for ch in text)


# word tokens; keeps "c++", "c#", "node.js", "1c" as single tokens
TOKEN_RE = re.compile(r"\w+(?:\+\+|#|(?:\.\w+)+)?", re.UNICODE)


def tokenize(folded: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(folded)]


def norm_key(text: str | None) -> str:
    """Folded, punctuation-free, single-spaced key used for comparisons."""
    return " ".join(t for t, _, _ in tokenize(fold(text)))


def clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    t = html.unescape(str(text)).replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t or None


def detect_lang(text: str) -> str:
    """Very small heuristic, used only for reporting (never for filtering)."""
    if not text:
        return "unknown"
    cyr = len(re.findall(r"[а-яА-ЯёЁ]", text))
    az = len(re.findall(r"[əğışçöüƏĞİŞÇÖÜ]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cyr > 20 and cyr > latin:
        return "ru"
    if az >= 3:
        return "az"
    if latin > 20:
        return "en"
    return "unknown"
