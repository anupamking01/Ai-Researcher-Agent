"""Closed-world, bounded evaluator trace-tree inventory (synthetic/offline only).

This guard prevents a direct noncanonical replay from silently omitting
misnamed, nested or symlinked experimental source files.
"""
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _seed(root: Path, *, variants=("D3", "D6", "P6", "P6V"), cells=10):
    for variant in variants:
        directory = root / variant
        directory.mkdir(parents=True)
        for number in range(cells):
            (directory / f"trace-{number:02d}.json").write_text(
                "{}", encoding="utf-8"
            )
    return root


def test_exact_forty_file_tree_is_accepted_in_stable_order(tmp_path):
    root = _seed(tmp_path / "traces")
    inventory = evaluator._inventory_evaluator_treatment_trace_tree(root)
    assert set(inventory) == set(evaluator.VARIANTS)
    assert sum(len(paths) for paths in inventory.values()) == 40
    for variant in evaluator.VARIANTS:
        assert [p.name for p in inventory[variant]] == [
            f"trace-{number:02d}.json" for number in range(10)
        ]


def test_synthetic_partial_tree_is_left_to_separate_cardinality_gate(tmp_path):
    root = _seed(tmp_path / "traces", variants=("D3",), cells=1)
    inventory = evaluator._inventory_evaluator_treatment_trace_tree(
        root, variants=("D3", "D6")
    )
    assert len(inventory["D3"]) == 1
    assert inventory["D6"] == []


@pytest.mark.parametrize("unexpected", ["rogue.json", ".hidden", "README.md", "extra-dir"])
def test_unexpected_root_entries_are_not_silently_ignored(tmp_path, unexpected):
    root = _seed(tmp_path / "traces", variants=("D3",), cells=1)
    target = root / unexpected
    if unexpected == "extra-dir":
        target.mkdir()
    else:
        target.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="unselected treatment trace files"):
        evaluator._inventory_evaluator_treatment_trace_tree(
            root, variants=("D3", "D6")
        )


@pytest.mark.parametrize("unexpected", ["wrong.txt", ".hidden.json.bak", "nested"])
def test_nonselected_variant_entries_block_replay(tmp_path, unexpected):
    root = _seed(tmp_path / "traces", variants=("D3",), cells=1)
    target = root / "D3" / unexpected
    if unexpected == "nested":
        target.mkdir()
        (target / "alternate.json").write_text("{}", encoding="utf-8")
    else:
        target.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="unselected treatment trace files"):
        evaluator._inventory_evaluator_treatment_trace_tree(root, variants=("D3",))


def test_symlinked_trace_cannot_be_ignored_by_json_glob(tmp_path):
    root = _seed(tmp_path / "traces", variants=("D3",), cells=1)
    (root / "D3" / "other.json").symlink_to(root / "D3" / "trace-00.json")
    with pytest.raises(SystemExit, match="nonregular trace"):
        evaluator._inventory_evaluator_treatment_trace_tree(root, variants=("D3",))


def test_symlinked_variant_directory_is_rejected(tmp_path):
    root = _seed(tmp_path / "traces", variants=("D3",), cells=1)
    (root / "D6").symlink_to(root / "D3", target_is_directory=True)
    with pytest.raises(SystemExit, match="nonregular variant directory"):
        evaluator._inventory_evaluator_treatment_trace_tree(
            root, variants=("D3", "D6")
        )


def test_symlinked_trace_root_is_rejected(tmp_path):
    root = _seed(tmp_path / "traces", variants=("D3",), cells=1)
    alias = tmp_path / "trace-alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(SystemExit, match="root must be a regular non-symlink"):
        evaluator._inventory_evaluator_treatment_trace_tree(
            alias, variants=("D3",)
        )


def test_missing_trace_root_is_rejected(tmp_path):
    with pytest.raises(SystemExit, match="root must be a regular non-symlink"):
        evaluator._inventory_evaluator_treatment_trace_tree(
            tmp_path / "missing", variants=("D3",)
        )


def test_overfull_variant_tree_is_bounded_before_sorting(tmp_path):
    root = _seed(tmp_path / "traces", variants=("D3",), cells=11)
    with pytest.raises(SystemExit, match="more than ten treatment trace entries"):
        evaluator._inventory_evaluator_treatment_trace_tree(
            root, variants=("D3",)
        )


def test_overfull_root_tree_is_bounded_before_sorting(tmp_path):
    root = _seed(tmp_path / "traces", variants=("D3",), cells=1)
    (root / "P6").mkdir()
    (root / "extra").mkdir()
    with pytest.raises(SystemExit, match="more root entries than frozen variants"):
        evaluator._inventory_evaluator_treatment_trace_tree(
            root, variants=("D3", "P6")
        )


def test_inventory_precedes_trace_parse_and_model_import():
    source = (Path(evaluator.__file__)).read_text(encoding="utf-8")
    assert (
        source.index("trace_files = _inventory_evaluator_treatment_trace_tree(")
        < source.index("payload = _load_json(trace_path)")
        < source.index("from agent.llm_utils import UsageTracker")
    )
