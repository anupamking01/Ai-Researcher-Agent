"""Byte-exact treatment-trace continuity in noncanonical replay (offline only).

All inputs are synthetic. No treatment, evaluator, or human rating is run.
"""
import hashlib
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _trace(tmp_path):
    path = tmp_path / "trace.json"
    path.write_bytes(b'{"trace":{"successful_source_count":1},"metadata":"old"}\\n'.replace(b"\\n", b"\n"))
    return path


def _capture(path):
    payload, digest = evaluator._load_json(path, include_sha256=True)
    return payload, digest


def test_optional_source_digest_is_exact_loaded_json_bytes(tmp_path):
    path = _trace(tmp_path)
    payload, digest = _capture(path)
    assert evaluator._load_json(path) == payload
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert evaluator._require_preflight_treatment_trace_unchanged(path, digest) is None


def test_unused_trace_metadata_change_is_not_hidden_by_same_prompt(tmp_path):
    path = _trace(tmp_path)
    _, digest = _capture(path)
    path.write_bytes(path.read_bytes().replace(b'"old"', b'"new"'))
    with pytest.raises(SystemExit, match="Treatment trace changed after preflight"):
        evaluator._require_preflight_treatment_trace_unchanged(path, digest)


def test_whitespace_only_json_change_still_breaks_source_custody(tmp_path):
    path = _trace(tmp_path)
    payload, digest = _capture(path)
    path.write_bytes(path.read_bytes() + b" ")
    assert evaluator._load_json(path) == payload
    with pytest.raises(SystemExit, match="Treatment trace changed after preflight"):
        evaluator._require_preflight_treatment_trace_unchanged(path, digest)


def test_missing_trace_fails_closed(tmp_path):
    path = _trace(tmp_path)
    _, digest = _capture(path)
    path.unlink()
    with pytest.raises(SystemExit, match="Treatment trace must be a regular"):
        evaluator._require_preflight_treatment_trace_unchanged(path, digest)


def test_trace_symlink_substitution_fails_closed(tmp_path):
    path = _trace(tmp_path)
    _, digest = _capture(path)
    original = tmp_path / "other.json"
    original.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(original)
    with pytest.raises(SystemExit, match="Treatment trace must be a regular"):
        evaluator._require_preflight_treatment_trace_unchanged(path, digest)


def test_recheck_still_obeys_json_size_limit(tmp_path, monkeypatch):
    path = _trace(tmp_path)
    _, digest = _capture(path)
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_JSON_BYTES", 8)
    with pytest.raises(SystemExit, match="Treatment trace exceeds maximum 8 bytes"):
        evaluator._require_preflight_treatment_trace_unchanged(path, digest)


def test_trace_rechecks_bracket_provider_call_and_aggregate_publication():
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts" / "evaluate_posthoc_support.py"
    ).read_text(encoding="utf-8")
    pending = source.split("    for item in pending:", 1)[1].split(
        "    rows = sorted(", 1
    )[0]
    guard = "_require_preflight_treatment_trace_unchanged(trace_path, trace_sha256)"
    assert pending.count(guard) == 2
    assert (
        pending.index(guard)
        < pending.index("raw = create_chat_completion(")
        < pending.rindex(guard)
        < pending.index("_publish_evaluation_cache(out_path, record)")
    )
    final = source.split("    rows = sorted(", 1)[1]
    assert "for trace_path, trace_sha256 in trace_sources.values():" in final
    assert final.index(guard) < final.index("_publish_aggregate_outputs(")


def test_source_fingerprint_is_taken_from_parsed_trace_snapshot():
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts" / "evaluate_posthoc_support.py"
    ).read_text(encoding="utf-8")
    main = source.split("def main() -> int:", 1)[1]
    assert "payload, trace_sha256 = _load_json(trace_path, include_sha256=True)" in main
    assert "trace_sources[(variant, task_id, run_id)] = (trace_path, trace_sha256)" in main
