from skillradar.transform.silver import normalize_record
from skillradar.quality.checks import check_salaries


def test_reviewed_invalid_salary_range():
    rec = {
        "source": "work_az",
        "title": "Sales Specialist",
        "salary_from": 1500,
        "salary_to": 600,
        "salary_currency": "AZN",
        "city": "Baku",
    }

    row, issues = normalize_record(rec, "work_az:9478", 1)

    assert row["salary_from"] is None
    assert row["salary_to"] is None
    assert row["has_salary"] == 0
    assert row["salary_currency"] is None
    assert check_salaries([row]).passed

    assert any(
        issue[2] == "reviewed_invalid_salary_range_treated_as_not_stated"
        for issue in issues
    )

    other, _ = normalize_record(rec, "work_az:9999", 2)
    assert not check_salaries([other]).passed
