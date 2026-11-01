"""Synthetic source-count/evidence consistency for noncanonical replay.

No historical treatment runs, evaluator calls or human ratings are generated.
"""

from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _run_files(tmp_path: Path, *, text: str | None) -> None:
    run_dir = tmp_path / "outputs" / "synthetic-run"
    run_dir.mkdir(parents=True)
    (run_dir / "research_report.md").write_text(
        "Synthetic research report\n", encoding="utf-8"
    )
    if text is not None:
        (run_dir / "research-query-01.txt").write_text(
            text, encoding="utf-8"
        )


def _evidence(tmp_path: Path, count=0, *, trace=None):
    if trace is None:
        trace = {"successful_source_count": count}
    return evaluator._evidence_for_trace(
        trace, "D3", "main-01", "synthetic-run", root=tmp_path
    )


def test_zero_source_without_query_files_uses_frozen_sentinel(tmp_path):
    _run_files(tmp_path, text=None)
    assert _evidence(tmp_path) == (
        evaluator.NO_EVIDENCE_SENTINEL, "zero_successful_sources"
    )


def test_zero_source_whitespace_query_file_keeps_sentinel(tmp_path):
    _run_files(tmp_path, text="  \n\t")
    assert _evidence(tmp_path) == (
        evaluator.NO_EVIDENCE_SENTINEL, "zero_successful_sources"
    )


def test_positive_source_count_uses_saved_retrieval_text(tmp_path):
    _run_files(tmp_path, text="Synthetic retrieved source\n")
    assert _evidence(tmp_path, count=1) == (
        "Synthetic retrieved source", "retrieved_evidence"
    )


@pytest.mark.parametrize("count", [0, 0.0])
def test_nonempty_retrieval_cannot_be_relabelled_zero_source(tmp_path, count):
    _run_files(tmp_path, text="Synthetic retrieved source")
    if count == 0.0 and type(count) is float:
        with pytest.raises(SystemExit, match="nonnegative integer"):
            _evidence(tmp_path, count=count)
    else:
        with pytest.raises(SystemExit, match="contradicts zero successful sources"):
            _evidence(tmp_path, count=count)


def test_missing_source_count_cannot_relabel_nonempty_retrieval(tmp_path):
    _run_files(tmp_path, text="Synthetic retrieved source")
    with pytest.raises(SystemExit, match="contradicts zero successful sources"):
        _evidence(tmp_path, trace={})


@pytest.mark.parametrize("text", [None, "", "  \n"])
def test_positive_source_count_requires_nonempty_saved_retrieval(tmp_path, text):
    _run_files(tmp_path, text=text)
    with pytest.raises(SystemExit, match="Saved evidence missing"):
        _evidence(tmp_path, count=1)


@pytest.mark.parametrize("count", [True, False, "0", "1", 1.5, -1, None])
def test_noninteger_or_negative_success_counts_fail_closed(tmp_path, count):
    _run_files(tmp_path, text=None)
    with pytest.raises(SystemExit, match="nonnegative integer"):
        _evidence(tmp_path, count=count)


def test_mismatched_source_count_blocks_resume_preflight_before_model_calls(
    tmp_path, monkeypatch
):
    _run_files(tmp_path, text="Unaccounted synthetic retrieval")
    monkeypatch.setattr(evaluator, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(evaluator, "EVAL_ROOT", tmp_path / "outputs" / "cache")
    expected = [(
        "D3",
        tmp_path / "traces" / "D3" / "synthetic-run.json",
        {
            "run_id": "synthetic-run",
            "question": "Synthetic question",
            "successful_source_count": 0,
        },
        "main-01",
        "synthetic-run",
    )]
    with pytest.raises(SystemExit, match="contradicts zero successful sources"):
        evaluator._preflight_evaluator_resume(
            expected,
            pricing={},
            evaluator_model=evaluator.FROZEN_EVALUATOR_MODEL,
            evaluator_temperature=evaluator.FROZEN_EVALUATOR_TEMPERATURE,
        )
    assert not (tmp_path / "outputs" / "cache").exists()
