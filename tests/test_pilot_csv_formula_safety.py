"""Offline regressions for pilot CSV spreadsheet-formula safety.

These synthetic inputs are NOT pilot outcomes or human evaluations.
"""
import csv
import io
import json

import pytest

from scripts import audit_pilot_runs_csv as auditor
from scripts import summarize_pilot as producer


DANGEROUS = (
    "=1+1", "+SUM(1,1)", "-2+3", "@SUM(1,1)",
    "  =HYPERLINK(\"https://invalid.example\")",
    "\t+1+1", "\n@SUM(1,1)", "\ufeff=1",
    "\u200b@SUM(1,1)", "\u202e=1", "\u202f-1+2",
)


@pytest.mark.parametrize("value", DANGEROUS)
def test_pilot_export_rejects_formula_like_metadata_before_csv_render(value):
    with pytest.raises(ValueError, match="formula-like CSV cell"):
        producer._render_csv([{
            "variant_id": "D6", "task_id": "pilot-01",
            "smart_model": value,
        }])


@pytest.mark.parametrize("value", DANGEROUS)
def test_independent_source_auditor_rejects_unsafe_raw_task_id(value):
    with pytest.raises(ValueError, match="formula-like CSV source cell in task_id"):
        auditor._expected_row(
            "D6", value, {"run_id": "run-01"},
            "run-01", "pilot-set", {},
        )


@pytest.mark.parametrize("column", [
    "task_set_id", "task_id", "run_id", "usage_accounting_status",
    "verification_status", "smart_model", "fast_model",
])
def test_source_auditor_checks_all_untrusted_text_columns(column):
    trace = {"run_id": "run-01"}
    arm, task, stem, task_set = "D6", "pilot-01", "run-01", "pilot-set"
    if column == "task_id":
        task = "=1"
    elif column == "task_set_id":
        task_set = "=1"
    elif column == "run_id":
        trace["run_id"] = "=1"
        stem = "=1"
    else:
        trace[column] = "=1"
    with pytest.raises(ValueError, match="formula-like CSV source cell"):
        auditor._expected_row(arm, task, trace, stem, task_set, {})


def test_safe_hyphenated_model_names_and_embedded_operators_keep_exact_bytes():
    rows = [{"task_id": "pilot-01", "smart_model": "gpt-4o-mini",
             "verification_status": "complete+verified",
             "usage_accounting_status": "provided (no = formula)",
             "fast_model": "x@provider"}]
    text = producer._render_csv(rows)
    result = list(csv.DictReader(io.StringIO(text, newline="")))
    assert result == rows
    source = auditor._expected_row(
        "D6", "pilot-01",
        {"run_id": "run-01", "smart_model": "gpt-4o-mini",
         "fast_model": "x@provider",
         "verification_status": "complete+verified"},
        "run-01", "pilot-set", {},
    )
    assert source["smart_model"] == "gpt-4o-mini"


def test_publish_fails_closed_without_creating_canonical_outputs(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(producer, "OUTPUT_JSON", tmp_path / "pilot_summary.json")
    monkeypatch.setattr(producer, "OUTPUT_CSV", tmp_path / "pilot_runs.csv")
    with pytest.raises(ValueError, match="formula-like CSV cell"):
        producer._publish_pilot_outputs(
            {"schema_version": 5},
            [{"task_id": "pilot-01", "run_id": "\u200b=1+1"}],
        )
    assert list(tmp_path.iterdir()) == []


def test_full_v5_csv_auditor_does_not_certify_formula_from_its_own_source(
    tmp_path,
):
    path = tmp_path / "pilot_runs.csv"
    path.write_text(",".join(auditor.COLUMNS) + "\n", encoding="utf-8")
    pricing = tmp_path / "prices.json"
    pricing.write_text(json.dumps({"models": {}}), encoding="utf-8")
    errors = auditor.audit_pilot_runs_csv(
        path, {("D6", "=1+1"): {"run_id": "run-01"}},
        {("D6", "=1+1"): "run-01"},
        ["D6"], ["=1+1"], "pilot-set", pricing,
    )
    assert any("formula-like CSV source cell in task_id" in e for e in errors)
