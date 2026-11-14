"""Closed-world local evaluator-cache inventory (synthetic, offline).

The standalone noncanonical replay must not reuse a cherry-picked subset of
cached evaluator JSON files while ignoring extra local measurement records.
"""
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _seed(root: Path, *, variants=("D3", "D6", "P6", "P6V"), count=10):
    for variant in variants:
        arm = root / variant
        arm.mkdir(parents=True)
        for index in range(count):
            (arm / f"main-{index + 1:02d}.json").write_text(
                "{}", encoding="utf-8"
            )
    return root


def test_absent_cache_root_means_no_previous_measurements(tmp_path):
    assert evaluator._inventory_evaluator_cache_tree(tmp_path / "absent") == set()


def test_complete_40_cache_inventory_is_included(tmp_path):
    root = _seed(tmp_path / "cache")
    files = evaluator._inventory_evaluator_cache_tree(root)
    assert len(files) == 40
    assert {p.parent.name for p in files} == set(evaluator.VARIANTS)


def test_partial_cache_is_allowed_for_resumption(tmp_path):
    root = _seed(tmp_path / "cache", variants=("D3",), count=2)
    files = evaluator._inventory_evaluator_cache_tree(root)
    assert len(files) == 2


@pytest.mark.parametrize("unexpected", ["rogue.json", ".hidden", "backup", "P6_extra"])
def test_unknown_root_entries_are_not_silently_omitted(tmp_path, unexpected):
    root = _seed(tmp_path / "cache", variants=("D3",), count=1)
    target = root / unexpected
    if unexpected == "backup":
        target.mkdir()
    else:
        target.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="unselected evaluator cache"):
        evaluator._inventory_evaluator_cache_tree(root)


@pytest.mark.parametrize("unexpected", ["main-01.json.bak", ".temp", "nested"])
def test_nonjson_or_nested_cache_entries_are_not_ignored(tmp_path, unexpected):
    root = _seed(tmp_path / "cache", variants=("D3",), count=1)
    target = root / "D3" / unexpected
    if unexpected == "nested":
        target.mkdir()
        (target / "main-02.json").write_text("{}", encoding="utf-8")
    else:
        target.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="unselected evaluator cache"):
        evaluator._inventory_evaluator_cache_tree(root)


def test_symlinked_cached_json_is_rejected(tmp_path):
    root = _seed(tmp_path / "cache", variants=("D3",), count=1)
    (root / "D3" / "main-02.json").symlink_to(root / "D3" / "main-01.json")
    with pytest.raises(SystemExit, match="nonregular cache"):
        evaluator._inventory_evaluator_cache_tree(root)


def test_symlinked_variant_directory_is_rejected(tmp_path):
    root = _seed(tmp_path / "cache", variants=("D3",), count=1)
    (root / "D6").symlink_to(root / "D3", target_is_directory=True)
    with pytest.raises(SystemExit, match="nonregular variant directory"):
        evaluator._inventory_evaluator_cache_tree(root)


def test_symlinked_cache_root_is_rejected_even_if_directory_exists(tmp_path):
    root = _seed(tmp_path / "cache", variants=("D3",), count=1)
    (tmp_path / "alias").symlink_to(root, target_is_directory=True)
    with pytest.raises(SystemExit, match="cache root is a symlink"):
        evaluator._inventory_evaluator_cache_tree(tmp_path / "alias")


def test_cache_root_cannot_be_an_existing_regular_file(tmp_path):
    root = tmp_path / "cache"
    root.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="cache root must be a directory"):
        evaluator._inventory_evaluator_cache_tree(root)


def test_more_than_ten_entries_per_variant_is_rejected(tmp_path):
    root = _seed(tmp_path / "cache", variants=("D3",), count=11)
    with pytest.raises(SystemExit, match="more than ten evaluator cache entries"):
        evaluator._inventory_evaluator_cache_tree(root)


def test_resume_preflight_rejects_ignored_backup_before_preparing_inputs(
    tmp_path, monkeypatch
):
    root = _seed(tmp_path / "cache", variants=("D3",), count=1)
    (root / "D3" / "main-02.json.bak").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evaluator, "EVAL_ROOT", root)
    with pytest.raises(SystemExit, match="unselected evaluator cache"):
        evaluator._preflight_evaluator_resume(
            [], pricing={}, evaluator_model=evaluator.FROZEN_EVALUATOR_MODEL,
            evaluator_temperature=evaluator.FROZEN_EVALUATOR_TEMPERATURE,
        )


def test_spend_helper_uses_the_same_closed_world_inventory(tmp_path, monkeypatch):
    root = _seed(tmp_path / "cache", variants=("D3",), count=1)
    (root / "other").mkdir()
    monkeypatch.setattr(evaluator, "EVAL_ROOT", root)
    with pytest.raises(SystemExit, match="unselected evaluator cache"):
        evaluator._existing_evaluator_cost(
            {}, expected_evaluator_model=evaluator.FROZEN_EVALUATOR_MODEL,
            expected_temperature=evaluator.FROZEN_EVALUATOR_TEMPERATURE,
        )


def test_unexpected_json_cell_keeps_separate_expected_path_guard(
    tmp_path, monkeypatch
):
    root = _seed(tmp_path / "cache", variants=("D3",), count=1)
    monkeypatch.setattr(evaluator, "EVAL_ROOT", root)
    with pytest.raises(SystemExit, match="Unexpected cached post-hoc evaluation"):
        evaluator._preflight_evaluator_resume(
            [], pricing={}, evaluator_model=evaluator.FROZEN_EVALUATOR_MODEL,
            evaluator_temperature=evaluator.FROZEN_EVALUATOR_TEMPERATURE,
        )


def test_cache_inventory_runs_before_any_model_import():
    source = Path(evaluator.__file__).read_text(encoding="utf-8")
    assert (
        source.index("existing_paths = _inventory_evaluator_cache_tree(EVAL_ROOT)")
        < source.index("from agent.llm_utils import UsageTracker")
    )
