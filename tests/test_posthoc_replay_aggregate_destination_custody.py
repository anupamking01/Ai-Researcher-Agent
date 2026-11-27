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


@pytest.mark.parametrize(
    "field, convert",
    [
        ("can_replace_original_evaluator_evidence", int),
        ("historical_archive_custody_authenticated", int),
        ("original_actions_evaluator_recovery_run_id", float),
        ("original_actions_treatment_run_id", float),
    ],
)
def test_numeric_alias_cannot_authorize_noncanonical_replacement(
    tmp_path, field, convert
):
    """A digest-valid pair must carry the exact JSON marker types."""
    summary, csv = _destinations(tmp_path)
    record = _write_pair(summary, csv)
    marker = record["replay_provenance"]
    original = marker[field]
    marker[field] = convert(original)
    assert marker[field] == original  # The old Python equality check passed.
    assert type(marker[field]) is not type(original)
    summary.write_text(json.dumps(record), encoding="utf-8")
    before = summary.read_bytes(), csv.read_bytes()
    with pytest.raises(SystemExit, match="lacks matching explicit noncanonical"):
        _snapshot(summary, csv)
    assert (summary.read_bytes(), csv.read_bytes()) == before


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
        < main.index("from agent.llm_utils import ")
        < main.index("_require_noncanonical_aggregate_destinations_unchanged(")
        < main.index("_publish_aggregate_outputs(")
    )


@pytest.mark.parametrize("reader", ["verify", "destination_snapshot"])
@pytest.mark.parametrize("oversize", [False, True])
def test_digest_valid_aggregate_csv_has_exact_byte_ceiling(
    tmp_path, monkeypatch, reader, oversize
):
    """A correctly digested CSV must not bypass the aggregate read limit.

    Both read paths are offline; no historical outputs or evaluator calls.
    """
    summary, csv = _destinations(tmp_path)
    csv_bytes = b"variant_id,task_id\\nD3,main-01\\n"
    _write_pair(summary, csv, csv=csv_bytes)
    cap = len(csv_bytes) - int(oversize)
    monkeypatch.setattr(evaluator, "MAX_EVALUATOR_AGGREGATE_CSV_BYTES", cap)
    read_pair = (
        (lambda: evaluator._verify_aggregate_outputs(summary, csv))
        if reader == "verify"
        else (lambda: _snapshot(summary, csv))
    )
    if oversize:
        with pytest.raises(
            SystemExit, match=r"post-hoc aggregate CSV exceeds maximum|"
            r"Existing post-hoc aggregate CSV exceeds maximum"
        ):
            read_pair()
    else:
        read_pair()


@pytest.mark.parametrize(
    "artifact, limit_name",
    [
        ("summary", "MAX_EVALUATOR_JSON_BYTES"),
        ("CSV", "MAX_EVALUATOR_AGGREGATE_CSV_BYTES"),
    ],
)
@pytest.mark.parametrize("oversize", [False, True])
def test_aggregate_writer_matches_reader_byte_ceiling(
    tmp_path, monkeypatch, artifact, limit_name, oversize
):
    """An unreadable candidate must not replace an existing aggregate pair."""
    summary_path, csv_path = _destinations(tmp_path)
    candidate = {
        "study_id": evaluator.STUDY_ID,
        "replay_provenance": evaluator._noncanonical_evaluator_replay_provenance(),
        "synthetic_metadata": "é" * 50,
    }
    rows = [{"variant_id": "D3", "task_id": "main-01", "run_id": "synthetic"}]
    evaluator._publish_aggregate_outputs(summary_path, csv_path, candidate, rows)
    expected = summary_path.read_bytes(), csv_path.read_bytes()
    exact_size = len(expected[0 if artifact == "summary" else 1])

    _write_pair(summary_path, csv_path)
    before = summary_path.read_bytes(), csv_path.read_bytes()
    monkeypatch.setattr(evaluator, limit_name, exact_size - int(oversize))
    if oversize:
        def fail_if_staged(*args, **kwargs):
            pytest.fail("oversized generation must fail before any staging")

        monkeypatch.setattr(evaluator, "_stage_durable_output", fail_if_staged)
        with pytest.raises(
            SystemExit, match=f"aggregate {artifact} exceeds maximum publication size"
        ):
            evaluator._publish_aggregate_outputs(summary_path, csv_path, candidate, rows)
        assert (summary_path.read_bytes(), csv_path.read_bytes()) == before
    else:
        digest = evaluator._publish_aggregate_outputs(
            summary_path, csv_path, candidate, rows
        )
        assert (summary_path.read_bytes(), csv_path.read_bytes()) == expected
        evaluator._verify_aggregate_outputs(
            summary_path, csv_path, intended_summary_sha256=digest
        )
