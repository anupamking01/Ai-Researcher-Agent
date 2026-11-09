"""Synthetic main-study CSV formula safety checks; no experiments rerun."""

import csv
import io

import pytest

from scripts import audit_main_study_numeric_inputs as audit


def _export(fields, row):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


@pytest.mark.parametrize("label,column,value", [
    (audit.MAIN_PATH, "treatment_cost_usd", "+1.25"),
    (audit.MAIN_PATH, "treatment_cost_usd", "-0.0"),
    (audit.MAIN_PATH, "treatment_cost_usd", "\u2003+1.25"),
    (audit.MAIN_PATH, "cost_status", '=HYPERLINK("https://invalid.example")'),
    (audit.MAIN_PATH, "cost_status", "\t@SUM(1,1)"),
    (audit.SUPPORT_PATH, "run_id", "\u200b=1+1"),
    (audit.SUPPORT_PATH, "run_id", "\ufeff+1"),
    (audit.SUPPORT_PATH, "evidence_status", "\n@SUM(1,1)"),
    (audit.SUPPORT_PATH, "strict_support_rate", "\u202f+0.5"),
])
def test_rejects_formula_like_exported_cells(label, column, value):
    raw = _export(["variant_id", "task_id", column], {
        "variant_id": "D3", "task_id": "main-01", column: value,
    })
    with pytest.raises(audit.NumericInputError, match="formula-like CSV cell"):
        audit._parse_csv(raw, label)


def test_rejects_formula_like_extra_header():
    raw = _export(["variant_id", "task_id", "=unused"], {
        "variant_id": "D3", "task_id": "main-01", "=unused": "safe",
    })
    with pytest.raises(audit.NumericInputError, match="formula-like CSV header"):
        audit._parse_csv(raw, audit.MAIN_PATH)


def test_rejects_missing_unused_metadata():
    raw = b"variant_id,task_id,cost_status\nD3,main-01\n"
    with pytest.raises(audit.NumericInputError, match="missing or surplus CSV fields"):
        audit._parse_csv(raw, audit.MAIN_PATH)


def test_rejects_surplus_csv_field():
    raw = b"variant_id,task_id\nD3,main-01,extra\n"
    with pytest.raises(audit.NumericInputError, match="missing or surplus CSV fields"):
        audit._parse_csv(raw, audit.MAIN_PATH)


def test_safe_embedded_operators_blank_values_and_numbers_preserved():
    raw = _export(
        ["variant_id", "task_id", "cost_status", "evidence_status", "total_tokens"],
        {"variant_id": "D3", "task_id": "main-01",
         "cost_status": "estimated+uncached@provider", "evidence_status": "",
         "total_tokens": "1.25"},
    )
    rows = audit._parse_csv(raw, "synthetic")
    assert rows[0]["cost_status"] == "estimated+uncached@provider"
    assert rows[0]["evidence_status"] == ""
    assert rows[0]["total_tokens"] == "1.25"


def test_numeric_equivalence_alone_does_not_certify_spreadsheet_safety():
    assert audit._number({"n": "+1.25"}, "n", "synthetic") == audit._number(
        {"n": "1.25"}, "n", "synthetic"
    )
    raw = _export(["variant_id", "task_id", "n"], {
        "variant_id": "D3", "task_id": "main-01", "n": "+1.25"
    })
    with pytest.raises(audit.NumericInputError, match="formula-like CSV cell"):
        audit._parse_csv(raw, "synthetic")
