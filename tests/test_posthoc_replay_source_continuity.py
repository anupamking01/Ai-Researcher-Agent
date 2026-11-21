"""Offline synthetic preflight-to-publication source-continuity regression tests."""
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _fixture(tmp_path, *, sources=1):
    run_id = "synthetic-run"
    folder = tmp_path / "outputs" / run_id
    folder.mkdir(parents=True)
    (folder / "research_report.md").write_text("Synthetic report\n", encoding="utf-8")
    if sources:
        (folder / "research-query-01.txt").write_text(
            "synthetic evidence", encoding="utf-8"
        )
    trace = {"question": "Synthetic question", "successful_source_count": sources}
    prepared = evaluator._prepare_evaluator_input(
        trace, "D3", "main-01", run_id, root=tmp_path
    )
    item = {**prepared, "variant": "D3", "task_id": "main-01", "run_id": run_id}
    return item, trace, folder


def _check(item, trace, root):
    return evaluator._require_preflight_evaluator_input_unchanged(
        item, trace=trace, root=root
    )


def test_unchanged_report_evidence_and_prompt_are_accepted(tmp_path):
    item, trace, _folder = _fixture(tmp_path)
    assert _check(item, trace, tmp_path) is None


def test_report_replacement_after_preflight_rejected(tmp_path):
    item, trace, folder = _fixture(tmp_path)
    (folder / "research_report.md").write_text(
        "Changed report\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="Evaluator source changed after preflight"):
        _check(item, trace, tmp_path)


def test_same_length_evidence_rewrite_after_preflight_rejected(tmp_path):
    item, trace, folder = _fixture(tmp_path)
    old = (folder / "research-query-01.txt").read_text(encoding="utf-8")
    (folder / "research-query-01.txt").write_text(
        "X" * len(old), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="Evaluator source changed after preflight"):
        _check(item, trace, tmp_path)


def test_added_query_source_after_preflight_rejected(tmp_path):
    item, trace, folder = _fixture(tmp_path)
    (folder / "research-query-02.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(SystemExit, match="Evaluator source changed after preflight"):
        _check(item, trace, tmp_path)


def test_missing_query_source_fails_closed(tmp_path):
    item, trace, folder = _fixture(tmp_path)
    (folder / "research-query-01.txt").unlink()
    with pytest.raises(SystemExit, match="Saved evidence missing"):
        _check(item, trace, tmp_path)


def test_preflight_prompt_mismatch_is_not_refreshed(tmp_path):
    item, trace, _folder = _fixture(tmp_path)
    item["prompt"] += " altered prompt"
    with pytest.raises(SystemExit, match="Evaluator source changed after preflight"):
        _check(item, trace, tmp_path)


def test_valid_zero_source_sentinel_remains_accepted(tmp_path):
    item, trace, _folder = _fixture(tmp_path, sources=0)
    assert item["evidence_status"] == "zero_successful_sources"
    assert _check(item, trace, tmp_path) is None


def test_zero_source_new_evidence_rejected_without_reclassification(tmp_path):
    item, trace, folder = _fixture(tmp_path, sources=0)
    (folder / "research-query-01.txt").write_text("new", encoding="utf-8")
    with pytest.raises(SystemExit, match="contradicts zero successful sources"):
        _check(item, trace, tmp_path)


def test_two_rechecks_bracket_provider_call_and_cache_write():
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts" / "evaluate_posthoc_support.py"
    ).read_text(encoding="utf-8")
    body = source.split("    for item in pending:", 1)[1]
    guard = "_require_preflight_evaluator_input_unchanged(item, trace=original_trace)"
    assert body.count(guard) == 2
    assert (
        body.index(guard)
        < body.index("raw = create_chat_completion(")
        < body.rindex(guard)
        < body.index("_publish_evaluation_cache(out_path, record)")
    )
