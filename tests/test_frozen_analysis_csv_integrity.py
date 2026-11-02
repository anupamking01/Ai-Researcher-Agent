"""Synthetic-only regression tests for independent frozen CSV integrity audit."""
from __future__ import annotations

import csv
import os
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
    # Non-original task IDs are intentional in synthetic arithmetic fixtures.
    return audit.audit_frozen_csv_inputs(
        matrix[3], matrix[4], require_original_task_set=False
    )


def test_valid_synthetic_matrix_is_read_only(matrix):
    before = tuple(path.read_bytes() for path in matrix[3:5])
    result = _check(matrix)
    assert result["status"] == "pass_summary_csv_internal_consistency_only"
    assert result["paired_cells"] == 40
    assert result["frozen_analysis_recomputed"] is False
    assert result["original_executions_independently_authenticated"] is False
    assert result["human_validation_performed"] is False
    assert result["frozen_task_ids_match_original_source"] is False
    assert result["original_task_manifest_sha256"] is None
    assert tuple(path.read_bytes() for path in matrix[3:5]) == before


def test_retained_canonical_csvs_pass_internal_preflight():
    # This checks tracked summary bytes only, not missing original trace custody.
    receipt = audit.audit_frozen_csv_inputs()
    assert receipt["paired_cells"] == 40
    assert receipt["original_executions_independently_authenticated"] is False
    assert receipt["frozen_task_ids_match_original_source"] is True
    assert receipt["original_task_manifest_sha256"] == (
        "5701df80036edb354f4f7d1efc409ea8f554a215f8c37da9d1a0b8ed01fdfd5f"
    )


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


def _set_synthetic_zero_source(matrix):
    """Configure one coherent zero-evidence cell without touching original data."""
    main, evaluator, save, _, _ = matrix
    main[0]["successful_sources"] = "0"
    main[0]["failed_sources"] = "3"
    main[0]["posthoc_strict_support_rate"] = "0"
    evaluator[0].update({
        "evidence_status": "zero_successful_sources",
        "supported": "0",
        "partially_supported": "0",
        "unsupported": "8",
        "contradicted": "0",
        "strict_support_rate": "0",
    })
    save()


def test_zero_source_sentinel_with_all_unsupported_claims_is_valid(matrix):
    _set_synthetic_zero_source(matrix)
    assert _check(matrix)["paired_cells"] == 40


@pytest.mark.parametrize("labels,rate", [
    ((1, 0, 7, 0), "0.125"),
    ((0, 1, 7, 0), "0"),
    ((0, 0, 7, 1), "0"),
])
def test_zero_source_disallows_coherently_rewritten_non_unsupported_labels(
    matrix, labels, rate,
):
    _set_synthetic_zero_source(matrix)
    main, evaluator, save, _, _ = matrix
    for key, count in zip(
        ("supported", "partially_supported", "unsupported", "contradicted"),
        labels,
    ):
        evaluator[0][key] = str(count)
    evaluator[0]["strict_support_rate"] = rate
    main[0]["posthoc_strict_support_rate"] = rate
    save()
    with pytest.raises(audit.InputIntegrityError, match="non-unsupported labels"):
        _check(matrix)


@pytest.mark.parametrize("status", ["", "retrieved_evidence", "unknown"])
def test_zero_source_requires_explicit_frozen_evidence_sentinel(matrix, status):
    _set_synthetic_zero_source(matrix)
    _, evaluator, save, _, _ = matrix
    evaluator[0]["evidence_status"] = status
    save()
    with pytest.raises(audit.InputIntegrityError, match="lacks evidence sentinel"):
        _check(matrix)


def test_nonzero_source_rejects_zero_evidence_sentinel(matrix):
    _, evaluator, save, _, _ = matrix
    evaluator[0]["evidence_status"] = "zero_successful_sources"
    save()
    with pytest.raises(audit.InputIntegrityError, match="contradicts sources"):
        _check(matrix)


def _relabel_all_cells(matrix, prefix: str) -> None:
    # Edit both CSVs consistently: pair/cardinality checks alone cannot catch
    # a wholesale task substitution with ten new, equally balanced task IDs.
    for rows in matrix[:2]:
        for row in rows:
            row["task_id"] = row["task_id"].replace("synthetic-", prefix)
    matrix[2]()


def test_original_source_anchor_accepts_pinned_task_ids_in_synthetic_counts(matrix):
    _relabel_all_cells(matrix, "main-")
    before = tuple(path.read_bytes() for path in matrix[3:5])
    receipt = audit.audit_frozen_csv_inputs(matrix[3], matrix[4])
    assert receipt["frozen_task_ids_match_original_source"] is True
    assert receipt["original_task_manifest_sha256"] == (
        "5701df80036edb354f4f7d1efc409ea8f554a215f8c37da9d1a0b8ed01fdfd5f"
    )
    assert tuple(path.read_bytes() for path in matrix[3:5]) == before


def test_coherent_forty_cell_task_substitution_fails_original_source_gate(matrix):
    _relabel_all_cells(matrix, "other-")
    # All arithmetic, category partitions and cross-CSV pairs remain valid.
    assert _check(matrix)["paired_cells"] == 40
    with pytest.raises(audit.InputIntegrityError, match="pinned original treatment task set"):
        audit.audit_frozen_csv_inputs(matrix[3], matrix[4])


@pytest.mark.parametrize("corruption", ["missing", "rewritten"])
def test_original_task_manifest_missing_or_rewritten_fails_closed(
    matrix, tmp_path, monkeypatch, corruption,
):
    _relabel_all_cells(matrix, "main-")
    monkeypatch.setattr(audit, "REPO_ROOT", tmp_path)
    if corruption == "rewritten":
        source = tmp_path / "experiments" / "main_budget_tasks.json"
        source.parent.mkdir()
        source.write_text('{"tasks":[]}', encoding="utf-8")
    with pytest.raises(audit.InputIntegrityError, match="source failed verification"):
        audit.audit_frozen_csv_inputs(matrix[3], matrix[4])


@pytest.mark.parametrize("input_index", [3, 4])
def test_audit_rejects_symlinked_csv_even_with_identical_valid_bytes(
    matrix, input_index, tmp_path,
):
    source = matrix[input_index]
    original = tmp_path / "unlinked_original.csv"
    original.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(original)
    with pytest.raises(audit.InputIntegrityError, match="stable CSV|non-symlink"):
        _check(matrix)


def test_audit_rejects_symlinked_parent_directory(matrix, tmp_path):
    source = matrix[3]
    parent_alias = tmp_path / "linked_parent"
    parent_alias.symlink_to(source.parent, target_is_directory=True)
    with pytest.raises(audit.InputIntegrityError, match="symlinked parent"):
        audit._read_csv(parent_alias / source.name, label="synthetic")


def test_audit_rejects_nonregular_fifo_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO test requires POSIX")
    path = tmp_path / "pretend.csv"
    os.mkfifo(path)
    with pytest.raises(audit.InputIntegrityError, match="non-symlink regular"):
        audit._read_csv(path, label="synthetic")


def test_audit_rejects_oversized_csv_before_parsing(tmp_path):
    path = tmp_path / "oversized.csv"
    path.write_bytes(b"a" * (audit.MAX_INPUT_BYTES + 1))
    with pytest.raises(audit.InputIntegrityError, match="exceeds input limit"):
        audit._read_csv(path, label="synthetic")


def test_audit_detects_same_byte_path_swap_during_capture(matrix, monkeypatch, tmp_path):
    source = matrix[3]
    replacement = tmp_path / "same_bytes.csv"
    replacement.write_bytes(source.read_bytes())
    original_read = os.read
    moved = False

    def swap_then_read(fd, count):
        nonlocal moved
        if not moved:
            os.replace(replacement, source)
            moved = True
        return original_read(fd, count)

    monkeypatch.setattr(audit.os, "read", swap_then_read)
    with pytest.raises(audit.InputIntegrityError, match="changed during bounded CSV capture"):
        audit._read_csv(source, label="synthetic")
    assert moved


def test_audit_detects_inplace_rewrite_during_capture(matrix, monkeypatch):
    source = matrix[3]
    original_read = os.read
    changed = False

    def rewrite_then_read(fd, count):
        nonlocal changed
        if not changed:
            with source.open("r+b") as stream:
                stream.seek(0)
                stream.write(b"X")
                stream.flush()
                os.fsync(stream.fileno())
            changed = True
        return original_read(fd, count)

    monkeypatch.setattr(audit.os, "read", rewrite_then_read)
    with pytest.raises(audit.InputIntegrityError, match="changed during bounded CSV capture"):
        audit._read_csv(source, label="synthetic")
    assert changed
