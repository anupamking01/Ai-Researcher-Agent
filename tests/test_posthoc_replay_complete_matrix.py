"""Offline, synthetic full-matrix preflight for noncanonical evaluator replay.

No treatment, evaluator, network, or original historical archive is used.
"""
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _task_questions():
    return {f"main-{number:02d}": f"question {number}" for number in range(1, 11)}


def _matrix():
    return [
        (
            variant,
            Path("synthetic") / variant / f"{task_id}.json",
            {},
            task_id,
            f"synthetic-{variant}-{task_id}",
        )
        for variant in evaluator.VARIANTS
        for task_id in _task_questions()
    ]


def test_complete_frozen_40_cell_matrix_accepted_without_provider_calls():
    assert len(_matrix()) == 40
    assert evaluator._require_complete_frozen_treatment_matrix(
        _matrix(), _task_questions()
    ) is None


@pytest.mark.parametrize("index", [0, 12, 39])
def test_missing_treatment_cell_blocks_replay(index):
    rows = _matrix()
    rows.pop(index)
    with pytest.raises(SystemExit, match="incomplete or ambiguous.*missing="):
        evaluator._require_complete_frozen_treatment_matrix(rows, _task_questions())


def test_empty_matrix_blocks_replay():
    with pytest.raises(SystemExit, match="incomplete or ambiguous.*missing="):
        evaluator._require_complete_frozen_treatment_matrix([], _task_questions())


def test_duplicate_cell_cannot_replace_missing_cell():
    rows = _matrix()
    duplicate = rows[0]
    rows[-1] = (duplicate[0], duplicate[1], duplicate[2], duplicate[3], "fresh-run")
    with pytest.raises(SystemExit, match="duplicate_cells="):
        evaluator._require_complete_frozen_treatment_matrix(rows, _task_questions())


def test_reused_run_id_cannot_make_two_reports_independent():
    rows = _matrix()
    last = rows[-1]
    rows[-1] = (*last[:-1], rows[0][-1])
    with pytest.raises(SystemExit, match="reused_run_ids="):
        evaluator._require_complete_frozen_treatment_matrix(rows, _task_questions())


@pytest.mark.parametrize("replacement", [
    ("UNKNOWN", "main-01"),
    ("P6", "main-99"),
])
def test_unexpected_variant_or_task_rejected(replacement):
    rows = _matrix()
    last = rows[-1]
    rows[-1] = (replacement[0], last[1], last[2], replacement[1], last[4])
    with pytest.raises(SystemExit, match="unexpected="):
        evaluator._require_complete_frozen_treatment_matrix(rows, _task_questions())


@pytest.mark.parametrize("wrong_ids", [
    {f"main-{number:02d}" for number in range(1, 10)},
    {f"main-{number:02d}" for number in range(2, 12)},
    {f"main-{number:02d}" for number in range(1, 11)} | {"main-11"},
])
def test_modified_task_contract_cannot_redefine_expected_matrix(wrong_ids):
    with pytest.raises(SystemExit, match="exactly the ten frozen"):
        evaluator._require_complete_frozen_treatment_matrix(
            _matrix(), {task_id: "question" for task_id in wrong_ids}
        )


def test_main_calls_matrix_guard_before_any_model_import():
    source = (
        Path(__file__).resolve().parents[1] /
        "scripts" / "evaluate_posthoc_support.py"
    ).read_text(encoding="utf-8")
    assert (
        source.index("_require_complete_frozen_treatment_matrix(expected, expected_questions)")
        < source.index("from agent.llm_utils import UsageTracker")
    )
    assert "Refusing evaluator replay: incomplete treatment trace" in source
    assert "unselected treatment trace files" in source
