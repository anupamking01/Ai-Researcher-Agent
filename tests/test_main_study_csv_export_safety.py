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


def _synthetic_full_schema(label, headers=None):
    """Build one synthetic CSV row; schema checks do not assess measurements."""
    columns = sorted(audit.EXPECTED_CSV_HEADERS[label]) if headers is None else headers
    return _export(columns, {
        column: {"variant_id": "D3", "task_id": "main-01"}.get(column, "0")
        for column in columns
    })


@pytest.mark.parametrize("label", [audit.MAIN_PATH, audit.SUPPORT_PATH])
def test_frozen_csv_headers_are_explicitly_accounted_for(label):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    raw = (root / label).read_bytes()
    parsed = audit._parse_csv(raw, label)
    assert len(parsed) == 40


@pytest.mark.parametrize("label,missing", [
    (audit.MAIN_PATH, "cost_status"),
    (audit.MAIN_PATH, "posthoc_evaluator_cost_usd"),
    (audit.SUPPORT_PATH, "evidence_status"),
    (audit.SUPPORT_PATH, "run_id"),
])
def test_rejects_removed_field_even_if_unchecked_numeric_cells_remain(label, missing):
    columns = sorted(audit.EXPECTED_CSV_HEADERS[label] - {missing})
    with pytest.raises(audit.NumericInputError, match="header schema mismatch.*missing"):
        audit._parse_csv(_synthetic_full_schema(label, columns), label)


@pytest.mark.parametrize("label,shadow", [
    (audit.MAIN_PATH, "provider_billed_cost_usd"),
    (audit.MAIN_PATH, "actual_verified_support_rate"),
    (audit.SUPPORT_PATH, "evidence_authenticated"),
    (audit.SUPPORT_PATH, "human_verified_score"),
])
def test_rejects_shadow_columns_that_could_mislead_export_readers(label, shadow):
    columns = sorted(audit.EXPECTED_CSV_HEADERS[label] | {shadow})
    with pytest.raises(audit.NumericInputError, match="header schema mismatch.*unexpected"):
        audit._parse_csv(_synthetic_full_schema(label, columns), label)


@pytest.mark.parametrize("label,original,alias", [
    (audit.MAIN_PATH, "cost_status", "Cost_status"),
    (audit.MAIN_PATH, "cost_status", " cost_status"),
    (audit.SUPPORT_PATH, "run_id", "run_id "),
])
def test_rejects_noncanonical_header_aliases(label, original, alias):
    columns = sorted((audit.EXPECTED_CSV_HEADERS[label] - {original}) | {alias})
    with pytest.raises(audit.NumericInputError, match="header schema mismatch"):
        audit._parse_csv(_synthetic_full_schema(label, columns), label)


@pytest.mark.parametrize("label", [audit.MAIN_PATH, audit.SUPPORT_PATH])
def test_semantically_equivalent_field_order_remains_accepted(label):
    raw = _synthetic_full_schema(label, list(reversed(sorted(audit.EXPECTED_CSV_HEADERS[label]))))
    rows = audit._parse_csv(raw, label)
    assert rows[0]["variant_id"] == "D3"
