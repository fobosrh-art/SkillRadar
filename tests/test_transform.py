"""Unit tests for normalisation, PII anonymisation, dedup and the skill matcher."""
from skillradar.skills.matcher import LabelIndex, build_esco_entries, make_entry
from skillradar.transform.dedup import DedupCandidate, find_cross_source_duplicates
from skillradar.transform.normalize import (company_key, normalize_city, normalize_currency, normalize_employment,
                                            parse_amount, parse_ts, to_iso)
from skillradar.transform.pii import anonymize_record, redact_text
from skillradar.transform.text import fold


# ------------------------------------------------------------------ normalisation
def test_city_variants_normalised_to_baku():
    for v in ["Bakı", "Bakı, Azərbaycan", "Баку", "Baku, Azerbaijan", "BAKU", " bakı "]:
        assert normalize_city(v) == "Baku", v


def test_non_baku_city_kept_unchanged():
    assert normalize_city("Sumqayıt") == "Sumqayıt"
    assert normalize_city("Bakı Bank, Sumqayıt") != "Baku"


def test_currency_and_amounts():
    assert normalize_currency("azn") == "AZN"
    assert normalize_currency("₼") == "AZN"
    assert normalize_currency(None) is None
    assert parse_amount("1 200") == 1200.0
    assert parse_amount(0) is None          # 0 = not stated, not a salary of zero
    assert parse_amount("negotiable") is None


def test_dates_to_utc_iso():
    assert to_iso(parse_ts("2026-12-24T23:59:59+04:00")) == "2026-12-24T19:59:59Z"
    assert parse_ts("not a date") is None


def test_employment_type_mapping():
    assert normalize_employment("FULL_TIME") == normalize_employment("Full-time") == "full_time"
    assert normalize_employment("CONTRACTOR") == "contract"
    assert normalize_employment(None) is None   # missing stays missing
    assert normalize_employment("Növbəli") == "other"


def test_company_key_strips_legal_forms():
    assert company_key("Bank Respublika ASC") == company_key("bank respublika") == "bank respublika"
    assert company_key("Doydum MMC") == company_key("Doydum")
    assert company_key(None) is None


def test_fold_preserves_length_for_offsets():
    s = "İngilis dili, Mühasibat UÇOTU, Английский"
    assert len(fold(s)) == len(s)
    assert fold("Məsuliyyətli") == "mesuliyyetli"


# ------------------------------------------------------------------ PII
def test_redacts_email_and_phone_but_not_salary_or_dates():
    text, n = redact_text("Əlaqə: 0550000102, (012) 555-01-02, hr@x.az. Maaş 1500-2000 AZN, 24.12.2026")
    assert n == 3
    assert "0550000102" not in text and "hr@x.az" not in text and "555-01-02" not in text
    assert "1500-2000" in text and "24.12.2026" in text


def test_redacts_internationalised_email_domains():
    # regression: found by the HTTP leak scan of the real dataset
    text, n = redact_text("CV göndərin: hr@nümunəşirkət.az və ya info@şirkət.com.az")
    assert n == 2 and "@" not in text
    text, n = redact_text("CV-lərini account ant @nümunə.az ünvanına, Instagram: @skillradar")
    assert n == 1 and "nümunə" not in text and "@skillradar" in text


def test_anonymize_record_drops_contact_fields_keeps_ids():
    rec = {"id": "hh1_az:139796960", "contact_email": "a@b.com", "contact_phone": "(050) 111-22-33",
           "facts": {"contact_email": "c@d.com"}, "description": "zəng edin 050 111 22 33"}
    out, n = anonymize_record(rec)
    assert out["id"] == "hh1_az:139796960"
    assert "contact_email" not in out and out["contact_email_present"] is True
    assert out["facts"] == {"contact_email_present": True}
    assert "[PHONE]" in out["description"]
    assert n == 4


# ------------------------------------------------------------------ dedup
def _c(job_id, source, title="satis meneceri", company="doydum", day="2026-11-24", seen="2026-11-20"):
    return DedupCandidate(job_id, source, title, company, day, seen)


def test_cross_source_duplicate_linked_to_earliest_seen():
    links = find_cross_source_duplicates([_c("holo:1", "holo", seen="2026-11-22"), _c("boss:1", "boss")])
    assert links == {"holo:1": ("boss:1", links["holo:1"][1])}


def test_dedup_is_conservative():
    assert find_cross_source_duplicates([_c("boss:1", "boss"), _c("boss:2", "boss")]) == {}     # same source
    assert find_cross_source_duplicates([_c("a:1", "a", company=None), _c("b:1", "b", company=None)]) == {}
    assert find_cross_source_duplicates([_c("a:1", "a"), _c("b:1", "b", day="2026-11-01")]) == {}  # > 3 days
    assert find_cross_source_duplicates([_c("a:1", "a"), _c("b:1", "b", title="muhasib")]) == {}


# ------------------------------------------------------------------ matcher
def _index():
    entries = [e for e in [
        make_entry("u:excel", "excel", "alias", "en"),
        make_entry("u:eng", "ingilis dil*", "alias", "az"),
        make_entry("u:eng", "английск*", "alias", "ru"),
        make_entry("u:sales", "satış*", "alias", "az"),
        make_entry("u:sql", "SQL", "preferred", "en"),
        make_entry("u:pm", "project management", "preferred", "en"),
        make_entry("u:mgmt", "management", "preferred", "en"),
    ] if e]
    return LabelIndex(entries)


def test_matcher_stems_and_evidence_offsets():
    text = "Tələblər: İngilis dilini bilmək, Excel-də işləmək, satışda təcrübə, английского языка"
    matches = _index().find(text)
    uris = [m.entry.uri for m in matches]
    assert uris.count("u:eng") == 2 and "u:excel" in uris and "u:sales" in uris
    for m in matches:
        assert text[m.start:m.end] == m.matched_text       # evidence points to original characters
    assert any(m.matched_text == "İngilis dilini" for m in matches)


def test_matcher_short_labels_case_sensitive_and_longest_wins():
    idx = _index()
    assert [m.entry.uri for m in idx.find("SQL and Project Management")] == ["u:sql", "u:pm"]
    assert idx.find("sql in lower case") == []


def test_esco_single_word_alt_and_ambiguous_alt_dropped():
    rows = [("u:1", "project management", "security\nPM tools"), ("u:2", "securities", "PM tools")]
    entries, stats = build_esco_entries(rows, stopwords=set())
    labels = {e.label for e in entries}
    assert "security" not in labels           # single-word alt -> dropped
    assert "PM tools" not in labels           # alt shared by two concepts -> ambiguous
    assert stats["dropped_ambiguous_alt"] == 1


def test_reviewed_false_positive_labels_are_excluded():
    rows = [("u:land", "land planner", "planning engineer\nspatial planner"), ("u:hist", "history", "")]
    entries, stats = build_esco_entries(rows, stopwords={"history"}, excluded_labels={"planning engineer"})
    labels = {e.label for e in entries}
    assert "planning engineer" not in labels and "history" not in labels and "spatial planner" in labels
    idx = LabelIndex(entries)
    assert idx.find("Planning Engineer, deployment history") == []


def test_no_text_is_not_absence():
    assert _index().find(None) == [] and _index().find("") == []
