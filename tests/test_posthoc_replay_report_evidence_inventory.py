"""Synthetic closed-world report/evidence inventory for noncanonical replay.

No model calls, original treatment reruns, or historical measurements.
"""
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _seed(tmp_path: Path, *, queries=(1,)) -> Path:
    directory = tmp_path / "outputs" / "synthetic-run"
    directory.mkdir(parents=True)
    (directory / "research_report.md").write_text("Synthetic report\n", encoding="utf-8")
    for number in queries:
        (directory / f"research-query-{number:02d}.txt").write_text(
            f"Synthetic evidence {number}\n", encoding="utf-8"
        )
    return directory


def test_full_writer_file_set_accepts_all_queries_in_stable_order(tmp_path):
    directory = _seed(tmp_path, queries=(1, 2, 3, 4))
    (directory / "research_report.pdf").write_bytes(b"%PDF synthetic")
    (directory / "verification.json").write_text("{}", encoding="utf-8")
    assert [p.name for p in evaluator._inventory_evaluator_run_evidence(directory)] == [
        f"research-query-{number:02d}.txt" for number in range(1, 5)
    ]
    assert evaluator._research_context("synthetic-run", root=tmp_path) == (
        "Synthetic evidence 1\n\nSynthetic evidence 2\n\n"
        "Synthetic evidence 3\n\nSynthetic evidence 4"
    )


def test_zero_source_run_with_report_is_still_eligible(tmp_path):
    _seed(tmp_path, queries=())
    assert evaluator._research_context("synthetic-run", root=tmp_path) == ""


@pytest.mark.parametrize("unexpected", [
    "research-query-05.txt", "research-query-1.txt",
    "research-query-00.txt", "research-query-02.txt.bak",
    "alternate-evidence.txt", "research-report.txt",
    ".hidden", "research-query-other.txt",
])
def test_ignored_or_misnamed_source_files_block_replay(tmp_path, unexpected):
    directory = _seed(tmp_path)
    (directory / unexpected).write_text("Alternate evidence", encoding="utf-8")
    with pytest.raises(SystemExit, match="unselected or nonregular report/evidence"):
        evaluator._research_context("synthetic-run", root=tmp_path)


def test_nested_evidence_files_block_replay(tmp_path):
    directory = _seed(tmp_path)
    (directory / "unselected").mkdir()
    (directory / "unselected" / "research-query-02.txt").write_text(
        "Shadow evidence", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="unselected or nonregular report/evidence"):
        evaluator._research_context("synthetic-run", root=tmp_path)


def test_symlinked_unused_optional_pdf_blocks_replay(tmp_path):
    directory = _seed(tmp_path)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF synthetic")
    (directory / "research_report.pdf").symlink_to(outside)
    with pytest.raises(SystemExit, match="unselected or nonregular report/evidence"):
        evaluator._research_context("synthetic-run", root=tmp_path)


def test_symlinked_retrieval_file_blocks_replay(tmp_path):
    directory = _seed(tmp_path)
    (directory / "research-query-02.txt").symlink_to(
        directory / "research-query-01.txt"
    )
    with pytest.raises(SystemExit, match="unselected or nonregular report/evidence"):
        evaluator._research_context("synthetic-run", root=tmp_path)


def test_missing_and_symlinked_run_directories_fail_closed(tmp_path):
    with pytest.raises(SystemExit, match="regular non-symlink directory"):
        evaluator._inventory_evaluator_run_evidence(tmp_path / "absent")
    directory = _seed(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(directory, target_is_directory=True)
    with pytest.raises(SystemExit, match="regular non-symlink directory"):
        evaluator._inventory_evaluator_run_evidence(alias)


@pytest.mark.parametrize("query_numbers", [(2,), (1, 3), (1, 2, 4)])
def test_missing_intermediate_query_blocks_replay(tmp_path, query_numbers):
    directory = _seed(tmp_path, queries=query_numbers)
    with pytest.raises(SystemExit, match="noncontiguous research-query"):
        evaluator._inventory_evaluator_run_evidence(directory)


def test_resume_preflight_rejects_shadow_evidence_before_provider_call(
    tmp_path, monkeypatch
):
    directory = _seed(tmp_path)
    (directory / "alternate-evidence.txt").write_text(
        "Could enter original agent context", encoding="utf-8"
    )
    monkeypatch.setattr(evaluator, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(evaluator, "EVAL_ROOT", tmp_path / "outputs" / "cache")
    expected = [(
        "D3", tmp_path / "traces" / "D3" / "synthetic-run.json",
        {"run_id": "synthetic-run", "question": "Synthetic question",
         "successful_source_count": 1},
        "main-01", "synthetic-run",
    )]
    with pytest.raises(SystemExit, match="unselected or nonregular report/evidence"):
        evaluator._preflight_evaluator_resume(
            expected, pricing={}, evaluator_model=evaluator.FROZEN_EVALUATOR_MODEL,
            evaluator_temperature=evaluator.FROZEN_EVALUATOR_TEMPERATURE,
        )
    assert not (tmp_path / "outputs" / "cache").exists()


def test_inventory_precedes_model_import():
    source = Path(evaluator.__file__).read_text(encoding="utf-8")
    assert (
        source.index("_inventory_evaluator_run_evidence(run_dir)")
        < source.index("from agent.llm_utils import UsageTracker")
    )
