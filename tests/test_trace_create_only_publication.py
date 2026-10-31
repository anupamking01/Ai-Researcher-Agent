"""Offline trace-publication provenance and create-only regression tests."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os

import pytest

from logic.experiment import ExperimentConfig, save_run_trace


def _config(tmp_path, *, variant="D3"):
    return ExperimentConfig(
        variant_id=variant,
        planning_mode="direct",
        source_budget=3,
        verification_mode="none",
        trace_root=str(tmp_path / "traces"),
    )


def _write(config, *, run_id="run-001", source_count=2):
    return save_run_trace(
        trace={"run_id": run_id, "source_count": source_count},
        config=config,
        run_id=run_id,
    )


def test_creates_complete_json_and_cleans_staging_file(tmp_path):
    config = _config(tmp_path)
    path = Path(_write(config))
    assert path == tmp_path / "traces" / "D3" / "run-001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["experiment"]["variant_id"] == "D3"
    assert payload["trace"]["source_count"] == 2
    assert path.stat().st_nlink == 1
    assert list(path.parent.iterdir()) == [path]


def test_duplicate_run_id_fails_without_mutating_original(tmp_path):
    config = _config(tmp_path)
    path = Path(_write(config))
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        _write(config, source_count=999)
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


def test_distinct_run_ids_remain_separate(tmp_path):
    config = _config(tmp_path)
    first = Path(_write(config, run_id="run-one"))
    second = Path(_write(config, run_id="run-two"))
    assert first != second
    assert first.is_file() and second.is_file()


@pytest.mark.parametrize(
    "run_id",
    ["", ".", "..", "../escape", "nested/run", r"..\\escape", ".hidden", "x" * 129],
)
def test_unsafe_run_identifiers_fail_before_creating_folders(tmp_path, run_id):
    config = _config(tmp_path)
    with pytest.raises(ValueError, match="run_id"):
        _write(config, run_id=run_id)
    assert not (tmp_path / "traces").exists()


@pytest.mark.parametrize(
    "variant",
    ["../outside", "nested/name", r"D3\\outside", ".hidden", "D.3", "Dü", "x" * 129],
)
def test_unsafe_variant_identifiers_fail_before_creating_folders(tmp_path, variant):
    config = _config(tmp_path, variant=variant)
    with pytest.raises(ValueError, match="variant_id"):
        _write(config)
    assert not (tmp_path / "traces").exists()


def test_root_directory_symlink_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "traces").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="trace_root"):
        _write(_config(tmp_path))
    assert list(outside.iterdir()) == []


def test_variant_directory_symlink_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "traces"
    root.mkdir()
    (root / "D3").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="variant directory"):
        _write(_config(tmp_path))
    assert list(outside.iterdir()) == []


def test_existing_symlink_trace_does_not_follow_or_overwrite(tmp_path):
    config = _config(tmp_path)
    variant_root = tmp_path / "traces" / "D3"
    variant_root.mkdir(parents=True)
    protected = tmp_path / "protected.json"
    protected.write_bytes(b"original evidence")
    (variant_root / "run-001.json").symlink_to(protected)
    with pytest.raises(FileExistsError):
        _write(config)
    assert protected.read_bytes() == b"original evidence"
    assert len(list(variant_root.iterdir())) == 1


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), object()])
def test_unserializable_or_nonfinite_trace_fails_before_creating_folders(tmp_path, bad):
    config = _config(tmp_path)
    with pytest.raises((TypeError, ValueError)):
        save_run_trace(
            trace={"run_id": "run-001", "latency_seconds": bad},
            config=config,
            run_id="run-001",
        )
    assert not (tmp_path / "traces").exists()


def test_staging_file_removed_if_publication_fails(tmp_path, monkeypatch):
    config = _config(tmp_path)

    def deny_link(*args, **kwargs):
        raise OSError("synthetic publication failure")

    monkeypatch.setattr(os, "link", deny_link)
    with pytest.raises(OSError, match="synthetic publication failure"):
        _write(config)
    assert list((tmp_path / "traces" / "D3").iterdir()) == []


def test_concurrent_same_id_has_exactly_one_winner(tmp_path):
    config = _config(tmp_path)

    def attempt(index):
        try:
            return _write(config, source_count=index)
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [11, 22]))
    assert sum(result is not None for result in results) == 1
    root = tmp_path / "traces" / "D3"
    files = list(root.iterdir())
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["trace"]["source_count"] in {11, 22}
