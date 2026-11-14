"""Synthetic source/test matrix contracts for full offline CI coverage."""
from pathlib import Path

import pytest
import yaml

from scripts import select_full_ci_shard as partition


def _make_tree(root, names):
    for name in names:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("def test_example(): assert True\n", encoding="utf-8")


def test_discovery_includes_nested_both_pytest_patterns_and_excludes_other_files(tmp_path):
    _make_tree(tmp_path, [
        "tests/test_alpha.py", "tests/nested/feature_test.py",
        "tests/test_beta.py", "tests/conftest.py", "docs/test_not_collected.py",
    ])
    assert partition.discover_modules(tmp_path) == (
        "tests/nested/feature_test.py", "tests/test_alpha.py", "tests/test_beta.py",
    )


@pytest.mark.parametrize("shards", [1, 2, 3, 8])
def test_every_module_in_exactly_one_shard_independent_of_input_order(shards):
    modules = tuple(f"tests/test_{i:03d}.py" for i in range(31))
    partition.verify_partition(modules, shards=shards)
    actual = [name for i in range(shards) for name in
              partition.select_shard(tuple(reversed(modules)), shard=i, shards=shards)]
    assert sorted(actual) == list(modules)
    assert len(actual) == len(set(actual))


@pytest.mark.parametrize("shard,shards", [
    (-1, 8), (8, 8), (True, 8), (0, 0), (0, 65), (0, True), (0, 1.5),
])
def test_invalid_matrix_values_fail_closed(shard, shards):
    with pytest.raises(ValueError, match="shard"):
        partition.select_shard(("tests/test_one.py",), shard=shard, shards=shards)


def test_duplicate_modules_and_empty_shards_fail_closed():
    with pytest.raises(ValueError, match="unique"):
        partition.verify_partition(("tests/test_one.py", "tests/test_one.py"), shards=1)
    with pytest.raises(ValueError, match="empty shard"):
        partition.verify_partition(("tests/test_one.py",), shards=2)


def test_selector_rejects_symlink_modules(tmp_path):
    _make_tree(tmp_path, ["tests/test_original.py"])
    (tmp_path / "tests" / "test_alias.py").symlink_to("test_original.py")
    with pytest.raises(ValueError, match="must not be a symlink"):
        partition.discover_modules(tmp_path)


def test_nested_symlink_directory_cannot_hide_test_modules(tmp_path):
    _make_tree(tmp_path, [
        "tests/real/test_nested.py", "tests/test_visible.py",
    ])
    (tmp_path / "tests" / "alias").symlink_to(
        "real", target_is_directory=True,
    )
    with pytest.raises(ValueError, match="directory must be real"):
        partition.discover_modules(tmp_path)


def test_broken_directory_alias_cannot_evade_discovery(tmp_path):
    _make_tree(tmp_path, ["tests/test_visible.py"])
    (tmp_path / "tests" / "lost_subtree").symlink_to(
        "no-longer-here", target_is_directory=True,
    )
    with pytest.raises(ValueError, match="must not be a symlink"):
        partition.discover_modules(tmp_path)


def test_support_file_symlink_is_not_ignored_as_non_test(tmp_path):
    _make_tree(tmp_path, ["tests/test_visible.py", "tests/support.py"])
    (tmp_path / "tests" / "helper.py").symlink_to("support.py")
    with pytest.raises(ValueError, match="must not be a symlink"):
        partition.discover_modules(tmp_path)


def test_unreadable_subtree_cannot_be_silently_skipped(tmp_path, monkeypatch):
    _make_tree(tmp_path, ["tests/test_visible.py"])

    def failing_walk(*_args, **kwargs):
        kwargs["onerror"](PermissionError(
            13, "Permission denied", str(tmp_path / "tests" / "private"),
        ))
        yield None  # A generator, so the error fires at traversal time.

    monkeypatch.setattr(partition.os, "walk", failing_walk)
    with pytest.raises(ValueError, match="cannot inspect offline test directory"):
        partition.discover_modules(tmp_path)


def test_ci_matrix_requires_all_shards_and_retained_exact_selection():
    workflow = yaml.load(
        (Path(__file__).resolve().parents[1] / ".github/workflows/tests.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["unit-tests"]
    assert job["strategy"]["fail-fast"] == "false"
    assert [int(x) for x in job["strategy"]["matrix"]["shard"]] == list(range(partition.SHARDS))
    assert job["timeout-minutes"] == "20"
    steps = job["steps"]
    run = next(s for s in steps if s.get("name") == "Run offline unit tests")
    assert run["env"]["VERA_SHARD"] == "${{ matrix.shard }}"
    assert "--verify-partition --shards 8" in run["run"]
    assert '--shard "$VERA_SHARD" --shards 8' in run["run"]
    assert '"${test_modules[@]}"' in run["run"]
    assert "tee -a" in run["run"]
    artifact = next(s for s in steps if s.get("name", "").startswith("Retain source-bound offline test"))
    assert "shard-${{ matrix.shard }}" in artifact["with"]["name"]
    preinstall = next(s for s in steps if s.get("name", "").startswith("Retain pre-install diagnostic"))
    assert "shard-${{ matrix.shard }}" in preinstall["with"]["name"]
    assert preinstall["with"]["if-no-files-found"] == "error"
    assert "vera-offline-test-modules.txt" in artifact["with"]["path"]
    assert artifact["with"]["if-no-files-found"] == "error"


def test_repository_partition_is_complete():
    modules = partition.discover_modules()
    assert "tests/test_full_ci_shard_selection.py" in modules
    partition.verify_partition(modules, shards=partition.SHARDS)
