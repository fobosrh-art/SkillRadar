"""Local display translations of ESCO labels (RU/AZ).

* Stored separately from the classifier in skills/resources/label_translations.psv.
* Keyed by the official English preferred label and resolved to ESCO URIs through the Bronze ESCO
  tables at load time; the ESCO data, URIs, matching and analytics are never changed.
* These are SkillRadar's own translations, NOT official ESCO translations (ESCO v1.2.0 has none for RU/AZ).
"""
from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "skills" / "resources" / "label_translations.psv"
TABLES = {"skill": ("bronze_esco_skills", "skill_uri"), "occupation": ("bronze_esco_occupations", "occupation_uri")}


def _read() -> list[tuple[str, str, str, str]]:
    rows = []
    for line in FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        kind, en, ru, az = (p.strip() for p in line.split("|"))
        rows.append((kind, en, ru, az))
    return rows


@lru_cache(maxsize=4)
def load(db_path: str, mtime: float) -> dict:
    """{kind: {uri: {"en", "ru", "az"}}} plus labels that could not be resolved (reported, not guessed)."""
    conn = sqlite3.connect(db_path)
    try:
        out: dict = {"skill": {}, "occupation": {}, "unresolved": []}
        lookup = {}
        for kind, (table, col) in TABLES.items():
            lookup[kind] = {r[1].strip().lower(): r[0] for r in conn.execute(f"SELECT {col}, preferred_label FROM {table}")}
        for kind, en, ru, az in _read():
            uri = lookup.get(kind, {}).get(en.lower())
            if uri:
                out[kind][uri] = {"en": en, "ru": ru, "az": az}
            else:
                out["unresolved"].append(f"{kind}:{en}")
        return out
    finally:
        conn.close()


def translations(db_path: Path) -> dict:
    return load(str(db_path), FILE.stat().st_mtime)


def search_uris(db_path: Path, kind: str, q: str) -> list[str]:
    """URIs whose RU or AZ display label contains q (case-insensitive) - for localised search."""
    ql = q.casefold()
    return [uri for uri, t in translations(db_path)[kind].items()
            if ql in t["ru"].casefold() or ql in t["az"].casefold()]
