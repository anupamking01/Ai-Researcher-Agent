"""Offline regression tests for protecting historical aggregate output files.

All fixtures are synthetic; no provider, historical treatment, or human data.
"""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import evaluate_posthoc_support as evaluator


def _destinations(tmp_path):
    root = tmp_path / "outputs"
    root.mkdir()
    return root / "posthoc_support_summary.json", root / "posthoc_support_runs.csv"


def _write_pair(summary_path, csv_path, *, noncanonical=True, csv=b"variant_id,task_id\n"):
    summary = {
        "study_id": evaluator.STUDY_ID,
        "posthoc_support_runs_sha256": hashlib.sha256(csv).hexdigest(),
    }
    if noncanonical:
        summary["replay_provenance"] = evaluator._noncanonical_evaluator_replay_provenance()
    csv_path.write_bytes(csv)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return summary


def _snapshot(summary_path, csv_path):
    return evaluator._snapshot_noncanonical_aggregate_destinations(
        summary_path, csv_path
    )


def test_empty_noncanonical_aggregate_destinations_are_safe(tmp_path):
    summary, csv = _destinations(tmp_path)
    assert _snapshot(summary, csv) is None
    assert evaluator._require_noncanonical_aggregate_destinations_unchanged(
        summary, csv, None
    ) is None


def test_only_explicitly_bound_noncanonical_pair_can_be_refreshed(tmp_path):
    summary, csv = _destinations(tmp_path)
    _write_pair(summary, csv)
    original = _snapshot(summary, csv)
    assert original == (
        hashlib.sha256(summary.read_bytes()).hexdigest(),
        hashlib.sha256(csv.read_bytes()).hexdigest(),
    )
    assert evaluator._require_noncanonical_aggregate_destinations_unchanged(
        summary, csv, original
    ) is None


def test_original_frozen_style_pair_is_preserved(tmp_path):
    summary, csv = _destinations(tmp_path)
    _write_pair(summary, csv, noncanonical=False)
    before = summary.read_bytes(), csv.read_bytes()
    with pytest.raises(SystemExit, match="lacks matching explicit noncanonical"):
        _snapshot(summary, csv)
    assert (summary.read_bytes(), csv.read_bytes()) == before


@pytest.mark.parametrize("missing", ["summary", "csv"])
def test_orphaned_aggregate_artifact_blocks_replay(tmp_path, missing):
    summary, csv = _destinations(tmp_path)
    _write_pair(summary, csv)
    (summary if missing == "summary" else csv).unlink()
    with pytest.raises(SystemExit, match="pair is incomplete"):
        _snapshot(summary, csv)


def test_noncanonical_summary_cannot_authorize_unbound_csv_bytes(tmp_path):
    summary, csv = _destinations(tmp_path)
    _write_pair(summary, csv)
    csv.write_bytes(csv.read_bytes() + b"unexpected\n")
    with pytest.raises(SystemExit, match="does not bind the retained CSV"):
        _snapshot(summary, csv)


def test_forged_original_replacement_permission_cannot_authorize_overwrite(tmp_path):
    summary, csv = _destinations(tmp_path)
    record = _write_pair(summary, csv)
    record["replay_provenance"]["can_replace_original_evaluator_evidence"] = True
    summary.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(SystemExit, match="lacks matching explicit noncanonical"):
        _snapshot(summary, csv)


def test_byte_equivalent_summary_rewrite_is_detected_at_publication(tmp_path):
    summary, csv = _destinations(tmp_path)
    _write_pair(summary, csv)
    original = _snapshot(summary, csv)
    summary.write_bytes(summary.read_bytes() + b" ")
    with pytest.raises(SystemExit, match="destinations changed after preflight"):
        evaluator._require_noncanonical_aggregate_destinations_unchanged(
            summary, csv, original
        )


def test_new_aggregate_appearing_during_replay_is_not_replaced(tmp_path):
    summary, csv = _destinations(tmp_path)
    original = _snapshot(summary, csv)
    _write_pair(summary, csv)
    with pytest.raises(SystemExit, match="destinations changed after preflight"):
        evaluator._require_noncanonical_aggregate_destinations_unchanged(
            summary, csv, original
        )


def test_symlinked_prior_summary_is_not_treated_as_safe(tmp_path):
    summary, csv = _destinations(tmp_path)
    _write_pair(summary, csv)
    alternate = tmp_path / "alternate.json"
    alternate.write_bytes(summary.read_bytes())
    summary.unlink()
    summary.symlink_to(alternate)
    with pytest.raises(SystemExit, match="regular non-symlink"):
        _snapshot(summary, csv)


def test_aggregate_destinations_are_checked_before_provider_calls_and_publication():
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "evaluate_posthoc_support.py"
    ).read_text(encoding="utf-8")
    main = source.split("def main() -> int:", 1)[1]
    assert (
        main.index("aggregate_destination_snapshot = _snapshot_noncanonical_aggregate_destinations(")
        < main.index("from agent.llm_utils import UsageTracker")
        < main.index("_require_noncanonical_aggregate_destinations_unchanged(")
        < main.index("_publish_aggregate_outputs(summary_path, csv_path, summary, rows)")
    )
