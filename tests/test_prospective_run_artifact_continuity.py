"""Synthetic-only tests for prospective recorded source-to-run continuity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import shutil
import sys

import pytest

from scripts import plan_counterbalanced_replication as design
from scripts import verify_counterbalanced_replication_execution as chronology
from scripts import verify_prospective_run_artifacts as evidence


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _file_claim(path, raw):
    return {"path": path, "size_bytes": len(raw), "sha256": _digest(raw)}


def _fixture(tmp_path):
    source = _bytes({
        "schema_version": 1, "task_set_id": "new-2027-independent-questions",
        "frozen_before_execution": True,
        "tasks": [
            {"id": f"new-{i:02d}", "category": "research",
             "question": f"Future independently selected question {i}?"}
            for i in range(10)
        ],
    })
    question_hashes = {
        task["id"]: _digest(task["question"].encode("utf-8"))
        for task in json.loads(source)["tasks"]
    }
    plan = (json.dumps(design.build_plan(source), sort_keys=True, indent=2)
            + "\n").encode()
    start = datetime(2027, 4, 1, 10, 0, tzinfo=timezone.utc)
    events = []
    for row in design.build_plan(source)["schedule"]:
        for variant in row["arm_order"]:
            ordinal = len(events)
            begun = start + timedelta(seconds=ordinal * 13)
            ended = begun + timedelta(seconds=11)
            events.append({
                "task_id": row["task_id"], "variant": variant,
                "run_id": f"trial-{ordinal:02d}", "status": "completed",
                "started_at_utc": begun.isoformat().replace("+00:00", "Z"),
                "finished_at_utc": ended.isoformat().replace("+00:00", "Z"),
            })
    log = {
        "schema_version": 1, "classification": chronology.LOG_CLASSIFICATION,
        "task_set_id": "new-2027-independent-questions",
        "source_manifest_sha256": _digest(source),
        "plan_file_sha256": _digest(plan),
        "started_at_utc": events[0]["started_at_utc"],
        "finished_at_utc": (start + timedelta(seconds=40 * 13)).isoformat().replace(
            "+00:00", "Z"
        ), "events": events,
    }
    root = tmp_path / "evidence"
    (root / "traces").mkdir(parents=True)
    (root / "reports").mkdir()
    cells = []
    for event in events:
        run_id = event["run_id"]
        report = f"Future synthetic report for {run_id}\n".encode()
        report_path = f"reports/{run_id}.md"
        (root / report_path).write_bytes(report)
        trace = _bytes({
            "run_id": run_id, "task_id": event["task_id"],
            "variant": event["variant"], "status": event["status"],
            "started_at_utc": event["started_at_utc"],
            "finished_at_utc": event["finished_at_utc"],
            "report_sha256": _digest(report),
            "task_question_sha256": question_hashes[event["task_id"]],
            "treatment_controls": dict(
                design.PROSPECTIVE_TREATMENT_CONTROLS_V1[event["variant"]]
            ),
            "synthetic_marker": "not a real experiment",
        })
        trace_path = f"traces/{run_id}.json"
        (root / trace_path).write_bytes(trace)
        cells.append({
            "task_id": event["task_id"], "variant": event["variant"],
            "run_id": run_id, "status": "completed",
            "trace": _file_claim(trace_path, trace),
            "report": _file_claim(report_path, report),
        })
    index = {
        "schema_version": 1,
        "classification": evidence.INDEX_CLASSIFICATION,
        "task_set_id": log["task_set_id"],
        "execution_log_sha256": _digest(_bytes(log)),
        "cells": cells,
    }
    return source, plan, log, index, root


def _audit(fixture, *, log=None, index=None, **pins):
    source, plan, original_log, original_index, root = fixture
    return evidence.audit_run_artifacts(
        source, plan, _bytes(log if log is not None else original_log),
        _bytes(index if index is not None else original_index), root, **pins,
    )


def test_complete_synthetic_matrix_binds_all_traces_reports_and_events(tmp_path):
    fixture = _fixture(tmp_path)
    source, plan, log, index, root = fixture
    result = _audit(
        fixture,
        expected_task_manifest_sha256=_digest(source),
        expected_plan_file_sha256=_digest(plan),
        expected_execution_log_sha256=_digest(_bytes(log)),
        expected_evidence_index_sha256=_digest(_bytes(index)),
    )
    assert result["status"] == "pass_local_artifact_continuity_only"
    assert result["attempted_cells"] == 40
    assert result["unattempted_cells"] == 0
    assert result["verified_attempted_traces"] == 40
    assert result["verified_reports"] == 40
    assert result["all_planned_cells_completed"] is True
    assert result["artifact_bytes_equal_supplied_fingerprints"] is True
    assert result["trace_question_fingerprints_match_frozen_manifest"] is True
    assert result["trace_treatment_controls_match_frozen_design"] is True
    assert result["evidence_index_external_pin_matched"] is True
    assert result["recorded_execution_independently_authenticated"] is False
    assert result["scientific_outcomes_validated"] is False
    assert result["historical_2026_study_validated"] is False
    assert result["human_validation_performed"] is False
    assert len(list((root / "traces").iterdir())) == 40


def _mark_unattempted(fixture, start_index):
    _, _, log, index, _ = fixture
    for event, cell in zip(log["events"][start_index:],
                           index["cells"][start_index:], strict=True):
        event.update({
            "status": "not_started", "run_id": None,
            "started_at_utc": None, "finished_at_utc": None,
        })
        cell.update({
            "status": "not_started", "run_id": None,
            "trace": None, "report": None,
        })
    index["execution_log_sha256"] = _digest(_bytes(log))


def test_interrupted_run_retains_unattempted_cells_without_fake_evidence(tmp_path):
    fixture = _fixture(tmp_path)
    _mark_unattempted(fixture, 4)
    result = _audit(fixture)
    assert result["attempted_cells"] == 4
    assert result["unattempted_cells"] == 36
    assert result["verified_attempted_traces"] == 4
    assert result["verified_reports"] == 4
    assert result["all_planned_cells_completed"] is False


def test_failed_attempt_preserves_trace_without_inventing_report(tmp_path):
    fixture = _fixture(tmp_path)
    _, _, log, index, root = fixture
    log["events"][0]["status"] = "failed"
    index["cells"][0]["status"] = "failed"
    index["cells"][0]["report"] = None
    path = root / index["cells"][0]["trace"]["path"]
    trace = json.loads(path.read_bytes())
    trace["status"] = "failed"
    trace["report_sha256"] = None
    raw = _bytes(trace)
    path.write_bytes(raw)
    index["cells"][0]["trace"] = _file_claim(
        index["cells"][0]["trace"]["path"], raw
    )
    index["execution_log_sha256"] = _digest(_bytes(log))
    result = _audit(fixture)
    assert result["recorded_status_counts"]["failed"] == 1
    assert result["verified_attempted_traces"] == 40
    assert result["verified_reports"] == 39
    assert result["all_planned_cells_completed"] is False


@pytest.mark.parametrize("mutate,pattern", [
    (lambda x: x["cells"][0].update(variant="DUMMY"), "differs from recorded event"),
    (lambda x: x["cells"][0].update(run_id="wrong-run"), "differs from recorded event"),
    (lambda x: x["cells"].pop(), "retain all 40"),
    (lambda x: x.update(classification="independently_validated"), "invalid classification"),
    (lambda x: x.update(execution_log_sha256="0" * 64), "exact execution log"),
    (lambda x: x["cells"][0].update(report=None), "lacks a report"),
    (lambda x: x["cells"][0].update(trace=None), "lacks a trace"),
    (lambda x: x["cells"][0]["report"].update(size_bytes=True), "invalid file fingerprint"),
    (lambda x: x["cells"][0]["trace"].update(path="../escape"), "safe relative"),
])
def test_wrong_event_structure_or_claims_fail_closed(tmp_path, mutate, pattern):
    fixture = _fixture(tmp_path)
    mutate(fixture[3])
    with pytest.raises(design.DesignError, match=pattern):
        _audit(fixture)


def test_trace_identity_cannot_be_rewritten_even_with_updated_index_digest(tmp_path):
    fixture = _fixture(tmp_path)
    _, _, _, index, root = fixture
    item = index["cells"][0]
    path = root / item["trace"]["path"]
    trace = json.loads(path.read_bytes())
    trace["run_id"] = "different-claimed-run"
    raw = _bytes(trace)
    path.write_bytes(raw)
    item["trace"] = _file_claim(item["trace"]["path"], raw)
    with pytest.raises(design.DesignError, match="does not bind to recorded event"):
        _audit(fixture)



@pytest.mark.parametrize("field,revised", [
    ("started_at_utc", "2027-04-01T10:00:01Z"),
    ("finished_at_utc", "2027-04-01T10:00:12Z"),
])
def test_rewritten_ledger_timestamps_cannot_rebind_original_trace(
    tmp_path, field, revised
):
    fixture = _fixture(tmp_path)
    _, _, log, index, _ = fixture
    log["events"][0][field] = revised
    index["execution_log_sha256"] = _digest(_bytes(log))
    chronology.audit_execution_log(fixture[0], fixture[1], _bytes(log))
    with pytest.raises(design.DesignError, match=f"{field} does not bind to recorded chronology"):
        _audit(fixture)


@pytest.mark.parametrize("field,revised", [
    ("started_at_utc", None),
    ("finished_at_utc", 0),
    ("started_at_utc", "2027-04-01T10:00:02Z"),
    ("finished_at_utc", "2027-04-01T10:00:10Z"),
])
def test_trace_timestamp_missing_or_rewritten_with_rehashed_index_still_fails(
    tmp_path, field, revised
):
    fixture = _fixture(tmp_path)
    _, _, _, index, root = fixture
    claim = index["cells"][0]["trace"]
    path = root / claim["path"]
    trace = json.loads(path.read_bytes())
    if revised is None:
        trace.pop(field)
    else:
        trace[field] = revised
    altered = _bytes(trace)
    path.write_bytes(altered)
    index["cells"][0]["trace"] = _file_claim(claim["path"], altered)
    with pytest.raises(design.DesignError, match=f"{field} does not bind to recorded chronology"):
        _audit(fixture)


def test_swapped_report_cannot_be_rebound_without_trace_change(tmp_path):
    fixture = _fixture(tmp_path)
    _, _, _, index, root = fixture
    item = index["cells"][0]
    new_raw = (root / index["cells"][1]["report"]["path"]).read_bytes()
    (root / item["report"]["path"]).write_bytes(new_raw)
    item["report"] = _file_claim(item["report"]["path"], new_raw)
    with pytest.raises(design.DesignError, match="does not bind the supplied report"):
        _audit(fixture)


def test_missing_and_changed_artifacts_fail_even_if_manifest_is_present(tmp_path):
    fixture = _fixture(tmp_path)
    _, _, _, index, root = fixture
    report_path = root / index["cells"][0]["report"]["path"]
    report_path.write_text("Modified after inventory\n")
    with pytest.raises(design.DesignError, match="differs from supplied artifact bytes"):
        _audit(fixture)
    report_path.unlink()
    with pytest.raises(design.DesignError, match="could not be safely opened"):
        _audit(fixture)


def test_duplicate_path_is_rejected_as_reused_source(tmp_path):
    fixture = _fixture(tmp_path)
    _, _, _, index, _ = fixture
    index["cells"][1]["report"] = dict(index["cells"][0]["report"])
    with pytest.raises(design.DesignError, match="reuses an artifact path"):
        _audit(fixture)


def test_hardlink_and_symlink_artifact_aliases_are_rejected(tmp_path):
    fixture = _fixture(tmp_path)
    _, _, _, index, root = fixture
    first_path = root / index["cells"][0]["trace"]["path"]
    alias = root / "traces" / "hardlink.json"
    os.link(first_path, alias)
    with pytest.raises(design.DesignError, match="no hardlink aliases"):
        _audit(fixture)
    alias.unlink()
    second_path = root / index["cells"][0]["trace"]["path"]
    original = second_path.read_bytes()
    second_path.unlink()
    second_path.symlink_to(root / index["cells"][1]["trace"]["path"])
    with pytest.raises(design.DesignError, match="could not be safely opened"):
        _audit(fixture)


def test_symlinked_root_or_parent_directory_rejected(tmp_path):
    fixture = _fixture(tmp_path)
    source, plan, log, index, root = fixture
    linked = tmp_path / "alias"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(design.DesignError, match="could not be safely opened"):
        evidence.audit_run_artifacts(source, plan, _bytes(log), _bytes(index), linked)
    parent = root / "traces"
    renamed = root / "trace_source"
    parent.rename(renamed)
    parent.symlink_to(renamed, target_is_directory=True)
    with pytest.raises(design.DesignError, match="could not be safely opened"):
        _audit(fixture)


def test_external_index_pin_detects_coherently_rewritten_inventory(tmp_path):
    fixture = _fixture(tmp_path)
    _, _, _, index, root = fixture
    old_pin = _digest(_bytes(index))
    path = root / index["cells"][0]["report"]["path"]
    altered = b"Alternative synthetic report\n"
    path.write_bytes(altered)
    index["cells"][0]["report"] = _file_claim(index["cells"][0]["report"]["path"], altered)
    trace_path = root / index["cells"][0]["trace"]["path"]
    trace = json.loads(trace_path.read_bytes())
    trace["report_sha256"] = _digest(altered)
    trace_bytes = _bytes(trace)
    trace_path.write_bytes(trace_bytes)
    index["cells"][0]["trace"] = _file_claim(index["cells"][0]["trace"]["path"], trace_bytes)
    assert _audit(fixture)["status"] == "pass_local_artifact_continuity_only"
    with pytest.raises(design.DesignError, match="does not match exact"):
        _audit(fixture, expected_evidence_index_sha256=old_pin)


@pytest.mark.parametrize("raw,pattern", [
    (b"", "outside supported range"),
    (b"[" + b"x" * (evidence.MAX_INDEX_BYTES + 1), "outside supported range"),
    (b"not-json", "unambiguous UTF-8 JSON"),
    (b'{"schema_version":1,"schema_version":1}', "duplicate"),
    (b'{"schema_version":NaN}', "nonstandard"),
])
def test_untrusted_inventory_bytes_are_bounded_and_unambiguous(tmp_path, raw, pattern):
    source, plan, log, _, root = _fixture(tmp_path)
    with pytest.raises(design.DesignError, match=pattern):
        evidence.audit_run_artifacts(source, plan, _bytes(log), raw, root)


def test_no_attempted_trace_may_be_missing_or_substituted(tmp_path):
    fixture = _fixture(tmp_path)
    _mark_unattempted(fixture, 3)
    fixture[3]["cells"][3]["trace"] = dict(fixture[3]["cells"][0]["trace"])
    with pytest.raises(design.DesignError, match="invents source evidence"):
        _audit(fixture)


def test_cli_is_read_only_and_prints_no_artifact_content(tmp_path, monkeypatch, capsys):
    fixture = _fixture(tmp_path)
    source, plan, log, index, root = fixture
    paths = [tmp_path / n for n in ("tasks.json", "plan.json", "log.json", "index.json")]
    for path, data in zip(paths, (source, plan, _bytes(log), _bytes(index)), strict=True):
        path.write_bytes(data)
    monkeypatch.setattr(sys, "argv", [
        "verify_prospective_run_artifacts.py",
        "--task-manifest", str(paths[0]),
        "--plan-file", str(paths[1]),
        "--execution-log", str(paths[2]),
        "--evidence-index", str(paths[3]),
        "--artifact-root", str(root),
    ])
    assert evidence.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["verified_attempted_traces"] == 40
    assert "cells" not in receipt and "synthetic_marker" not in str(receipt)
    assert all(path.exists() for path in paths)


@pytest.mark.parametrize("corruption", [
    "missing", "null", "boolean", "other_task", "wrong_hash",
])
def test_trace_question_binding_rejects_rehashed_wrong_source_claim(
    tmp_path, corruption
):
    # The inventory can be rehashed around a changed trace, yet it must not
    # silently certify a trace claiming a different question for the same ID.
    fixture = _fixture(tmp_path)
    source, _, _, index, root = fixture
    claim = index["cells"][0]["trace"]
    path = root / claim["path"]
    trace = json.loads(path.read_bytes())
    if corruption == "missing":
        trace.pop("task_question_sha256")
    elif corruption == "null":
        trace["task_question_sha256"] = None
    elif corruption == "boolean":
        trace["task_question_sha256"] = True
    elif corruption == "other_task":
        other_question = json.loads(source)["tasks"][1]["question"]
        trace["task_question_sha256"] = _digest(other_question.encode("utf-8"))
    else:
        trace["task_question_sha256"] = "0" * 64
    changed = _bytes(trace)
    path.write_bytes(changed)
    index["cells"][0]["trace"] = _file_claim(claim["path"], changed)
    with pytest.raises(design.DesignError, match="question fingerprint differs"):
        _audit(fixture)


def test_frozen_prospective_controls_match_existing_four_arm_definitions():
    # Detect drift away from the actual four-arm treatment definitions.
    from logic.experiment import ExperimentConfig

    assert set(design.PROSPECTIVE_TREATMENT_CONTROLS_V1) == set(design.VARIANTS)
    for variant, expected in design.PROSPECTIVE_TREATMENT_CONTROLS_V1.items():
        current = ExperimentConfig.from_variant(variant)
        assert {field: getattr(current, field) for field in expected} == expected


@pytest.mark.parametrize("variant,alteration", [
    ("D3", ("source_budget", 6)),
    ("D6", ("source_budget", 3)),
    ("P6", ("planning_mode", "direct")),
    ("P6V", ("verification_mode", "none")),
    ("D3", ("planning_mode", "planner")),
    ("P6V", ("source_budget", True)),
    ("D6", ("source_budget", 6.0)),
    ("P6", ("missing", None)),
    ("D3", ("null", None)),
    ("D6", ("extra", "unexpected")),
])
def test_wrong_recorded_intervention_rejected_even_after_trace_rehash(
    tmp_path, variant, alteration
):
    # Rehashing a candidate index must not legitimize a mislabeled
    # planned treatment's recorded intervention configuration.
    fixture = _fixture(tmp_path)
    index, root = fixture[3], fixture[4]
    cell = next(c for c in index["cells"] if c["variant"] == variant)
    claim = cell["trace"]
    path = root / claim["path"]
    trace = json.loads(path.read_bytes())
    field, value = alteration
    if field == "missing":
        trace.pop("treatment_controls")
    elif field == "null":
        trace["treatment_controls"] = None
    elif field == "extra":
        trace["treatment_controls"]["extra_factor"] = value
    else:
        trace["treatment_controls"][field] = value
    changed = _bytes(trace)
    path.write_bytes(changed)
    cell["trace"] = _file_claim(claim["path"], changed)
    with pytest.raises(design.DesignError, match="frozen treatment-control|frozen variant"):
        _audit(fixture)


def test_artifact_root_replacement_between_reads_fails(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    root = fixture[4]
    original = evidence._validate_file_claim
    swapped = False

    def replace_after_first(*args, **kwargs):
        nonlocal swapped
        result = original(*args, **kwargs)
        if not swapped:
            moved = tmp_path / 'original-retained-root'
            root.rename(moved)
            shutil.copytree(moved, root)
            swapped = True
        return result

    monkeypatch.setattr(evidence, '_validate_file_claim', replace_after_first)
    with pytest.raises(design.DesignError, match='artifact root changed during verification'):
        _audit(fixture)
    assert swapped


def test_artifact_root_mutation_between_reads_fails(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    root = fixture[4]
    original = evidence._validate_file_claim
    changed = False

    def mutate_after_first(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            (root / 'unexpected-new-entry').write_bytes(b'unexpected')
            changed = True
        return result

    monkeypatch.setattr(evidence, '_validate_file_claim', mutate_after_first)
    with pytest.raises(design.DesignError, match='artifact root changed during verification'):
        _audit(fixture)
    assert changed
