"""Synthetic, offline evaluator-cache continuity regressions.

The preserved historical evaluator measurements are never opened or rerun.
"""
import hashlib
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _cache(tmp_path, name="main-01.json", content=b'{"synthetic": true}\\n'):
    root = tmp_path / "posthoc_evaluations"
    path = root / "D3" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return root, path, {path: hashlib.sha256(content).hexdigest()}


def _guard(root, sources):
    return evaluator._require_evaluator_cache_source_continuity(
        sources, root=root
    )


def test_unmodified_cached_measurement_has_exact_custody(tmp_path):
    root, _path, snapshot = _cache(tmp_path)
    assert _guard(root, snapshot) is None


def test_missing_empty_cache_root_matches_no_cached_measurements(tmp_path):
    assert _guard(tmp_path / "missing", {}) is None


def test_same_length_measurement_change_is_rejected(tmp_path):
    root, path, snapshot = _cache(tmp_path)
    path.write_bytes(b'{"synthetic": fals}')
    with pytest.raises(SystemExit, match="Evaluator cache changed during replay"):
        _guard(root, snapshot)


def test_semantically_equivalent_json_byte_change_is_rejected(tmp_path):
    root, path, snapshot = _cache(tmp_path)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SystemExit, match="Evaluator cache changed during replay"):
        _guard(root, snapshot)


def test_missing_preflight_cache_is_rejected(tmp_path):
    root, path, snapshot = _cache(tmp_path)
    path.unlink()
    with pytest.raises(SystemExit, match="cache inventory changed"):
        _guard(root, snapshot)


def test_unexpected_valid_cache_is_rejected(tmp_path):
    root, _path, snapshot = _cache(tmp_path)
    (root / "D3" / "main-02.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="cache inventory changed"):
        _guard(root, snapshot)


def test_unselected_backup_file_is_rejected(tmp_path):
    root, _path, snapshot = _cache(tmp_path)
    (root / "D3" / "old-measurement.bak").write_text("backup", encoding="utf-8")
    with pytest.raises(SystemExit, match="unselected evaluator cache"):
        _guard(root, snapshot)


def test_cache_replaced_with_symlink_cannot_pass(tmp_path):
    root, path, snapshot = _cache(tmp_path)
    alternative = tmp_path / "alternative.json"
    alternative.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(alternative)
    with pytest.raises(SystemExit, match="nonregular cache"):
        _guard(root, snapshot)


def test_newly_published_cache_has_exact_serialization_fingerprint(tmp_path):
    path = tmp_path / "posthoc_evaluations" / "D3" / "main-01.json"
    record = {"synthetic": True, "claims_checked": 1}
    raw = evaluator._serialized_evaluation_cache_bytes(record)
    snapshot = {path: hashlib.sha256(raw).hexdigest()}
    evaluator._publish_evaluation_cache(path, record)
    assert path.read_bytes() == raw
    assert _guard(path.parent.parent, snapshot) is None


def test_final_cache_check_precedes_aggregate_publication():
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts" / "evaluate_posthoc_support.py"
    ).read_text(encoding="utf-8")
    tail = source.split("    rows = sorted(", 1)[1]
    assert tail.index(
        "_require_final_evaluator_source_continuity(expected, rows)"
    ) < tail.index(
        "_require_evaluator_cache_source_continuity(cache_source_hashes)"
    ) < tail.index(
        "_publish_aggregate_outputs(summary_path, csv_path, summary, rows)"
    )
