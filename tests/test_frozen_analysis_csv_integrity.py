"""Synthetic-only regression tests for independent frozen CSV integrity audit."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts import audit_frozen_analysis_csv_inputs as audit


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def matrix(tmp_path):
    main = []
    evaluator = []
    for variant in audit.VARIANTS:
        for ordinal in range(1, 11):
            task = f"synthetic-{ordinal:02d}"
            main.append({
                "variant_id": variant, "task_id": task, "completed": "True",
                "source_budget": "3" if variant == "D3" else "6",
                "successful_sources": "2", "failed_sources": "1",
                "search_calls": "1", "model_calls": "2",
                "total_tokens": "160", "report_words": "15",
                "treatment_cost_usd": "0.2", "latency_seconds": "12.5",
                "posthoc_claims_checked": "8",
                "posthoc_strict_support_rate": "0.75",
                "posthoc_evaluator_cost_usd": "0.031",
            })
            evaluator.append({
                "variant_id": variant, "task_id": task,
                "run_id": f"{variant}-{task}",
                "claims_checked": "8", "supported": "6",
                "partially_supported": "1", "unsupported": "1",
                "contradicted": "0", "strict_support_rate": "0.75",
                "total_tokens": "100", "estimated_cost_usd": "0.031",
                "evidence_status": "retrieved_evidence",
            })
    main_path, support_path = tmp_path / "main.csv", tmp_path / "support.csv"

    def save():
        _write(main_path, main)
        _write(support_path, evaluator)

    save()
    return main, evaluator, save, main_path, support_path


def _check(matrix):
    return audit.audit_frozen_csv_inputs(matrix[3], matrix[4])


def test_valid_synthetic_matrix_is_read_only(matrix):
    before = tuple(path.read_bytes() for path in matrix[3:5])
    result = _check(matrix)
    assert result["status"] == "pass_summary_csv_internal_consistency_only"
    assert result["paired_cells"] == 40
    assert result["frozen_analysis_recomputed"] is False
    assert result["original_executions_independently_authenticated"] is False
    assert result["human_validation_performed"] is False
    assert tuple(path.read_bytes() for path in matrix[3:5]) == before


def test_retained_canonical_csvs_pass_internal_preflight():
    # This checks tracked summary bytes only, not missing original trace custody.
    receipt = audit.audit_frozen_csv_inputs()
    assert receipt["paired_cells"] == 40
    assert receipt["original_executions_independently_authenticated"] is False


@pytest.mark.parametrize("value", [
    "2.5", "7.99999999999999999", "8.0000000000000000001",
    "NaN", "Infinity", "-Infinity", "1e309", "9007199254740993", "broken",
])
def test_exact_count_parser_rejects_nonintegral_nonfinite_or_unsafe(value):
    with pytest.raises(audit.InputIntegrityError):
        audit._int({"claims_checked": value}, "claims_checked", label="synthetic")


@pytest.mark.parametrize("column,value", [
    ("claims_checked", "13"),
    ("supported", "6.5"),
    ("supported", "-1"),
    ("contradicted", "-1"),
    ("strict_support_rate", "0.97"),
    ("estimated_cost_usd", "nan"),
    ("total_tokens", "-1"),
    ("run_id", ""),
])
def test_synthetic_evaluator_corruption_rejected(matrix, column, value):
    _, evaluator, save, _, _ = matrix
    evaluator[0][column] = value
    save()
    with pytest.raises(audit.InputIntegrityError):
        _check(matrix)


@pytest.mark.parametrize("column,value", [
    ("source_budget", "6"),
    ("successful_sources", "4"),
    ("failed_sources", "-1"),
    ("model_calls", "2.5"),
    ("report_words", "nan"),
    ("search_calls", "inf"),
    ("treatment_cost_usd", "nan"),
    ("latency_seconds", "-0.01"),
    ("posthoc_claims_checked", "9"),
    ("posthoc_strict_support_rate", "0.9"),
    ("posthoc_evaluator_cost_usd", "0.9"),
    ("completed", "False"),
])
def test_synthetic_treatment_corruption_rejected(matrix, column, value):
    main, _, save, _, _ = matrix
    main[0][column] = value
    save()
    with pytest.raises(audit.InputIntegrityError):
        _check(matrix)


def test_evaluator_negative_count_cancellation_cannot_pass(matrix):
    _, evaluator, save, _, _ = matrix
    evaluator[0]["supported"] = "-1"
    evaluator[0]["unsupported"] = "8"
    save()
    with pytest.raises(audit.InputIntegrityError, match="category"):
        _check(matrix)


def test_duplicate_cell_cannot_displace_independent_task(matrix):
    _, evaluator, save, _, _ = matrix
    evaluator[1]["task_id"] = evaluator[0]["task_id"]
    save()
    with pytest.raises(audit.InputIntegrityError, match="duplicate"):
        _check(matrix)


@pytest.mark.parametrize("contents,term", [
    ("variant_id,task_id,variant_id\nD3,item,D6\n", "duplicate CSV headers"),
    ("variant_id,task_id\nD3,item,extra\n", "missing or extra CSV cells"),
    ("variant_id,task_id\nD3\n", "missing or extra CSV cells"),
    ("variant_id,task_id\n\"unclosed\n", "malformed CSV"),
])
def test_malformed_csv_fails_closed(tmp_path, contents, term):
    path = tmp_path / "malformed.csv"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(audit.InputIntegrityError, match=term):
        audit._read_csv(path, label="synthetic")
