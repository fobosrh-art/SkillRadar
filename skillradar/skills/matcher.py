"""Explainable dictionary matcher (ESCO labels + curated multilingual aliases).

How it works (for the defense):
  1. Every label is folded (lower-case, diacritics removed, see text.fold) and tokenised.
  2. Exact labels go into a hash map keyed by their token tuple -> O(1) lookup per n-gram.
     Scanning a text is O(tokens x max_label_len) - no regex per label, no ML model.
  3. Alias tokens ending in '*' are stems (Azerbaijani/Russian suffixes: "satışda", "английского").
     They are indexed by the first 3 letters of their first token to keep the candidate list tiny.
  4. Overlapping matches are resolved greedily: longest span wins.
  5. Short labels (<= 4 chars, e.g. SQL, SAP, HSE) must appear in UPPER CASE in the original
     text, which prevents matching ordinary words.
Every match keeps the exact original substring and character offsets as evidence.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..transform.text import fold, tokenize

RESOURCES = Path(__file__).with_name("resources")
SHORT_LABEL_LEN = 4
MAX_LABEL_TOKENS = 6


@dataclass(frozen=True)
class Entry:
    uri: str
    label: str
    label_type: str          # preferred | alt | alias
    lang: str
    tokens: tuple[str, ...]
    stems: tuple[bool, ...]  # True where token is a prefix stem ('*')
    case_sensitive: bool


@dataclass(frozen=True)
class Match:
    entry: Entry
    start: int
    end: int
    matched_text: str


def make_entry(uri: str, label: str, label_type: str, lang: str) -> Entry | None:
    folded_tokens: list[str] = []
    stem_flags: list[bool] = []
    for word in label.split():
        is_stem = word.endswith("*")
        sub = [x for x, _, _ in tokenize(fold(word.rstrip("*")))]   # "sürücü-ekspeditor" -> 2 tokens
        folded_tokens += sub
        stem_flags += [False] * (len(sub) - 1) + [is_stem] if sub else []
    stems = tuple(stem_flags)
    if not folded_tokens or len(folded_tokens) > MAX_LABEL_TOKENS:
        return None
    if any(s and len(tok) < 3 for tok, s in zip(folded_tokens, stems)):
        return None                    # stems shorter than 3 letters are too ambiguous ("dil*" is ok)
    compact = "".join(folded_tokens)
    return Entry(uri, label.rstrip("*").replace("*", ""), label_type, lang, tuple(folded_tokens), stems,
                 case_sensitive=len(compact) <= SHORT_LABEL_LEN)


class LabelIndex:
    def __init__(self, entries: list[Entry]):
        self.exact: dict[tuple[str, ...], Entry] = {}
        self.stemmed: dict[str, list[Entry]] = defaultdict(list)
        self.max_len = 1
        for e in entries:
            if any(e.stems):
                self.stemmed[e.tokens[0][:3]].append(e)
            else:
                self.exact.setdefault(e.tokens, e)
            self.max_len = max(self.max_len, len(e.tokens))

    def __len__(self) -> int:
        return len(self.exact) + sum(len(v) for v in self.stemmed.values())

    @staticmethod
    def _case_ok(e: Entry, original: str) -> bool:
        return not e.case_sensitive or original == original.upper() and any(c.isalpha() for c in original)

    def find(self, text: str | None) -> list[Match]:
        if not text:
            return []
        toks = tokenize(fold(text))
        words = [t for t, _, _ in toks]
        found: list[Match] = []
        for i in range(len(words)):
            for n in range(min(self.max_len, len(words) - i), 0, -1):
                e = self.exact.get(tuple(words[i:i + n]))
                if e:
                    s, end = toks[i][1], toks[i + n - 1][2]
                    if self._case_ok(e, text[s:end]):
                        found.append(Match(e, s, end, text[s:end]))
            for e in self.stemmed.get(words[i][:3], ()):
                n = len(e.tokens)
                if i + n > len(words):
                    continue
                if all(words[i + k].startswith(e.tokens[k]) if e.stems[k] else words[i + k] == e.tokens[k]
                       for k in range(n)):
                    s, end = toks[i][1], toks[i + n - 1][2]
                    if self._case_ok(e, text[s:end]):
                        found.append(Match(e, s, end, text[s:end]))
        # longest-span-first, non-overlapping
        found.sort(key=lambda m: (-(m.end - m.start), m.start))
        taken: list[tuple[int, int]] = []
        result = []
        for m in found:
            if any(m.start < e and s < m.end for s, e in taken):
                continue
            taken.append((m.start, m.end))
            result.append(m)
        return sorted(result, key=lambda m: m.start)


def split_labels(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split("\n") if x.strip()]


def load_aliases(filename: str, pref_to_uri: dict[str, str]) -> tuple[list[Entry], list[str]]:
    """Curated aliases; an alias is accepted only if its ESCO preferred label exists."""
    entries, rejected = [], []
    with open(RESOURCES / filename, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            uri = pref_to_uri.get(row["esco_preferred_label"].strip().lower())
            if not uri:
                rejected.append(f"{row['alias']} -> {row['esco_preferred_label']} (not in ESCO)")
                continue
            e = make_entry(uri, row["alias"].strip(), "alias", row["lang"].strip())
            if e:
                entries.append(e)
            else:
                rejected.append(f"{row['alias']} (invalid alias pattern)")
    return entries, rejected


def build_esco_entries(rows, stopwords: set[str], excluded_labels: set[str] | None = None) -> tuple[list[Entry], dict]:
    """rows: (uri, preferred_label, alt_labels). Ambiguous alt labels are dropped.
    excluded_labels: folded multi-word labels observed to map real job text to the wrong concept."""
    excluded_labels = excluded_labels or set()
    pref: dict[tuple, Entry] = {}
    alts: dict[tuple, list[Entry]] = defaultdict(list)
    stats = {"labels_considered": 0, "dropped_stopword_or_short": 0, "dropped_single_word_alt": 0,
             "dropped_ambiguous_alt": 0}
    for uri, pref_label, alt_labels in rows:
        for label, kind in [(pref_label, "preferred")] + [(a, "alt") for a in split_labels(alt_labels)]:
            stats["labels_considered"] += 1
            e = make_entry(uri, label, kind, "en")
            if e is None:
                continue
            if " ".join(e.tokens) in excluded_labels:
                stats["dropped_reviewed_false_positive"] = stats.get("dropped_reviewed_false_positive", 0) + 1
                continue
            if len(e.tokens) == 1 and (e.tokens[0] in stopwords or e.tokens[0].isdigit()):
                stats["dropped_stopword_or_short"] += 1
                continue
            # ESCO single-word ALT labels often point to a broader/odd concept ("security" -> securities,
            # "standard" -> scaffolding components). Keep only short acronyms (CRM, HR, CCTV).
            if kind == "alt" and len(e.tokens) == 1 and not e.case_sensitive:
                stats["dropped_single_word_alt"] += 1
                continue
            if kind == "preferred":
                pref.setdefault(e.tokens, e)
            else:
                alts[e.tokens].append(e)
    entries = list(pref.values())
    for toks, cands in alts.items():
        if toks in pref:
            continue
        if len({c.uri for c in cands}) > 1:
            stats["dropped_ambiguous_alt"] += 1
            continue
        entries.append(cands[0])
    stats["entries"] = len(entries)
    return entries, stats
