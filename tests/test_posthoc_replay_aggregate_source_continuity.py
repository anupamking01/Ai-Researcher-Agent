"""Synthetic, offline aggregate-publication evidence continuity tests.

All measurements are fixture records; no evaluator or treatment is invoked.
"""
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _cell(tmp_path, *, run_id="synthetic-01", task_id="main-01", sources=1):
    folder = tmp_path / "outputs" / run_id
    folder.mkdir(parents=True)
    (folder / "research_report.md").write_text(
        f"Report for {run_id}\n", encoding="utf-8"
    )
    if sources:
        (folder / "research-query-01.txt").write_text(
            "synthetic evidence", encoding="utf-8"
        )
    trace = {
        "question": f"Question for {run_id}",
        "successful_source_count": sources,
    }
    prepared = evaluator._prepare_evaluator_input(
        trace, "D3", task_id, run_id, root=tmp_path
    )
    record = {
        "variant_id": "D3",
        "task_id": task_id,
        "run_id": run_id,
        "evidence_status": prepared["evidence_status"],
        "input_fingerprints": prepared["input_fingerprints"],
    }
    expected = ("D3", tmp_path / f"{run_id}.json", trace, task_id, run_id)
    return expected, record, folder


def _check(tmp_path, expected, rows):
    return evaluator._require_final_evaluator_source_continuity(
        expected, rows, root=tmp_path
    )


def test_all_cached_sources_unchanged_can_publish(tmp_path):
    expected, cached, _folder = _cell(tmp_path)
    assert _check(tmp_path, [expected], [cached]) is None


def test_cached_report_changed_after_preflight_cannot_publish(tmp_path):
    expected, cached, folder = _cell(tmp_path)
    (folder / "research_report.md").write_text(
        "Changed source\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="refusing aggregate publication"):
        _check(tmp_path, [expected], [cached])


def test_cached_evidence_same_length_mutation_cannot_publish(tmp_path):
    expected, cached, folder = _cell(tmp_path)
    evidence_file = folder / "research-query-01.txt"
    evidence_file.write_text(
        "X" * len(evidence_file.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Evaluator source changed after preflight"):
        _check(tmp_path, [expected], [cached])


def test_zero_source_cached_record_rejects_later_evidence(tmp_path):
    expected, cached, folder = _cell(tmp_path, sources=0)
    assert cached["evidence_status"] == "zero_successful_sources"
    (folder / "research-query-01.txt").write_text(
        "unexpected evidence", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="contradicts zero successful sources"):
        _check(tmp_path, [expected], [cached])


def test_zero_source_cached_record_still_valid_when_unchanged(tmp_path):
    expected, cached, _folder = _cell(tmp_path, sources=0)
    assert _check(tmp_path, [expected], [cached]) is None


def test_missing_source_fails_before_aggregate(tmp_path):
    expected, cached, folder = _cell(tmp_path)
    (folder / "research-query-01.txt").unlink()
    with pytest.raises(SystemExit, match="Saved evidence missing"):
        _check(tmp_path, [expected], [cached])


def test_late_second_cell_mutation_cannot_escape_all_cached_replay(tmp_path):
    a, ar, _ = _cell(tmp_path, run_id="synthetic-01", task_id="main-01")
    b, br, folder = _cell(tmp_path, run_id="synthetic-02", task_id="main-02")
    (folder / "research_report.md").write_text(
        "Later changed report", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="D3/main-02/synthetic-02"):
        _check(tmp_path, [a, b], [ar, br])


def test_incomplete_measurement_matrix_cannot_pass_final_check(tmp_path):
    a, ar, _ = _cell(tmp_path, run_id="synthetic-01", task_id="main-01")
    b, _br, _ = _cell(tmp_path, run_id="synthetic-02", task_id="main-02")
    with pytest.raises(SystemExit, match="one measurement per treatment"):
        _check(tmp_path, [a, b], [ar])


def test_duplicate_measurement_identity_rejected(tmp_path):
    a, ar, _ = _cell(tmp_path)
    with pytest.raises(SystemExit, match="Duplicate evaluator measurement"):
        _check(tmp_path, [a, a], [ar, ar])


def test_final_guard_runs_before_aggregate_publication():
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts" / "evaluate_posthoc_support.py"
    ).read_text(encoding="utf-8")
    tail = source.split("    rows = sorted(", 1)[1]
    trace_guard = "_require_preflight_treatment_trace_unchanged(trace_path, trace_sha256)"
    full_guard = "_require_final_evaluator_source_continuity(expected, rows)"
    publish = "_publish_aggregate_outputs(summary_path, csv_path, summary, rows)"
    assert tail.index(trace_guard) < tail.index(full_guard) < tail.index(publish)
