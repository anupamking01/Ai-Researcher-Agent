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
            "runtime_context": {
                "runner_commit": "a" * 40,
                "requirements_sha256": "b" * 64,
                "smart_model_id": "gpt-synthetic-smart",
                "fast_model_id": "gpt-synthetic-fast",
                "search_provider_id": "synthetic-search",
                "generation_temperature": 0.0,
                "search_candidate_multiplier": 3,
                "browse_timeout_seconds": 60.0,
                "run_timeout_seconds": 480.0,
                "max_concurrent_browses": 2,
            },
            "source_count": 0,
            "successful_source_count": 0,
            "failed_source_count": 0,
            "scheduled_urls": [],
            "successful_urls": [],
            "failed_urls": [],
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
    assert result["artifact_paths_rechecked_after_full_scan"] == 80
    assert result["artifact_root_inventory_file_count"] == 80
    assert result["artifact_root_inventory_matches_index"] is True
    assert result["artifact_identity_and_bytes_stable_at_final_recheck"] is True
    assert result["all_planned_cells_completed"] is True
    assert result["artifact_bytes_equal_supplied_fingerprints"] is True
    assert result["trace_question_fingerprints_match_frozen_manifest"] is True
    assert result["trace_treatment_controls_match_frozen_design"] is True
    assert result["self_reported_source_ledgers_within_frozen_budgets"] is True
    assert result["evidence_index_external_pin_matched"] is True
    assert result["recorded_execution_independently_authenticated"] is False
    assert result["scientific_outcomes_validated"] is False
    assert result["historical_2026_study_validated"] is False
    assert result["human_validation_performed"] is False
    assert len(list((root / "traces").iterdir())) == 40


def _mark_unattempted(fixture, start_index):
    _, _, log, index, root = fixture
    for event, cell in zip(log["events"][start_index:],
                           index["cells"][start_index:], strict=True):
        # Unattempted cells have no retained output; do not leave artificial
        # candidate runs outside the inventory in the synthetic fixture.
        for kind in ("trace", "report"):
            if cell[kind] is not None:
                (root / cell[kind]["path"]).unlink()
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
    (root / index["cells"][0]["report"]["path"]).unlink()
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
    with pytest.raises(design.DesignError, match="single-link regular files"):
        _audit(fixture)
    alias.unlink()
    second_path = root / index["cells"][0]["trace"]["path"]
    original = second_path.read_bytes()
    second_path.unlink()
    second_path.symlink_to(root / index["cells"][1]["trace"]["path"])
    with pytest.raises(design.DesignError, match="single-link regular files"):
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
    # The initial dedicated-root inventory now rejects the symlink parent.
    with pytest.raises(design.DesignError, match="single-link regular files"):
        _audit(fixture)



@pytest.mark.parametrize("relative", [
    "traces/unindexed-alternative.json",
    "reports/unindexed-alternative.md",
    "traces/additional-attempt/hidden.json",
])
def test_retained_unindexed_attempt_or_report_cannot_be_silently_omitted(
    tmp_path, relative
):
    fixture = _fixture(tmp_path)
    candidate = fixture[4] / relative
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("synthetic alternative evidence", encoding="utf-8")
    with pytest.raises(design.DesignError, match="unindexed or missing evidence"):
        _audit(fixture)


def test_unindexed_symlink_cannot_hide_candidate_evidence(tmp_path):
    fixture = _fixture(tmp_path)
    root = fixture[4]
    (root / "traces" / "hidden-link.json").symlink_to("trial-00.json")
    with pytest.raises(design.DesignError, match="single-link regular files"):
        _audit(fixture)


def test_unindexed_file_appearing_in_nested_directory_mid_audit_is_rejected(
    tmp_path, monkeypatch
):
    fixture = _fixture(tmp_path)
    original = evidence._validate_file_claim
    extra = fixture[4] / "traces" / "late-alternative.json"
    created = False

    def insert_after_first(*args, **kwargs):
        nonlocal created
        result = original(*args, **kwargs)
        if not created:
            extra.write_bytes(b"synthetic late retained attempt")
            created = True
        return result

    monkeypatch.setattr(evidence, "_validate_file_claim", insert_after_first)
    with pytest.raises(design.DesignError, match="unindexed or missing evidence"):
        _audit(fixture)
    assert created


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
    # The full-root inventory now rejects the unexpected retained file
    # before the later root metadata consistency check is reached.
    with pytest.raises(design.DesignError, match='unindexed or missing evidence'):
        _audit(fixture)
    assert changed


def test_early_trace_rewritten_after_check_is_rejected_at_final_sweep(tmp_path, monkeypatch):
    # Mutating a nested trace file does not change the root directory inode.
    fixture = _fixture(tmp_path)
    path = fixture[4] / fixture[3]["cells"][0]["trace"]["path"]
    original = evidence._validate_file_claim
    changed = False

    def rewrite_after_first(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            path.write_bytes(b"rewritten after its first successful hash check")
            changed = True
        return result

    monkeypatch.setattr(evidence, "_validate_file_claim", rewrite_after_first)
    with pytest.raises(design.DesignError, match="previously verified artifact changed"):
        _audit(fixture)
    assert changed


def test_identical_byte_inode_replacement_after_check_is_rejected(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    path = fixture[4] / fixture[3]["cells"][0]["trace"]["path"]
    original = evidence._validate_file_claim
    replaced = False

    def replace_after_first(*args, **kwargs):
        nonlocal replaced
        result = original(*args, **kwargs)
        if not replaced:
            substitute = path.with_name("same-bytes-substitute.json")
            substitute.write_bytes(path.read_bytes())
            os.replace(substitute, path)
            replaced = True
        return result

    monkeypatch.setattr(evidence, "_validate_file_claim", replace_after_first)
    with pytest.raises(design.DesignError, match="previously verified artifact changed"):
        _audit(fixture)
    assert replaced


def test_early_trace_removed_after_check_is_rejected_at_final_sweep(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    path = fixture[4] / fixture[3]["cells"][0]["trace"]["path"]
    original = evidence._validate_file_claim
    removed = False

    def remove_after_first(*args, **kwargs):
        nonlocal removed
        result = original(*args, **kwargs)
        if not removed:
            path.unlink()
            removed = True
        return result

    monkeypatch.setattr(evidence, "_validate_file_claim", remove_after_first)
    with pytest.raises(design.DesignError, match="became inaccessible during audit"):
        _audit(fixture)
    assert removed


def _replace_report_bytes_and_refresh_claims(fixture, raw):
    """Keep the synthetic ledger and trace/index hashes internally consistent."""
    _, _, _, index, root = fixture
    cell = index["cells"][0]
    report_claim = cell["report"]
    (root / report_claim["path"]).write_bytes(raw)
    cell["report"] = _file_claim(report_claim["path"], raw)
    trace_claim = cell["trace"]
    trace_file = root / trace_claim["path"]
    trace = json.loads(trace_file.read_bytes())
    trace["report_sha256"] = _digest(raw)
    trace_raw = _bytes(trace)
    trace_file.write_bytes(trace_raw)
    cell["trace"] = _file_claim(trace_claim["path"], trace_raw)


@pytest.mark.parametrize("recorded_status", ["completed", "failed"])
@pytest.mark.parametrize("bad_report", [
    b" \t\r\n",                      # No substantive textual evidence.
    b"\xff\xfeBinary report",          # Cannot decode as UTF-8.
    b"Readable\x00hidden payload",    # NUL embedded in apparent text.
    b"\xef\xbb\xbf",                 # Only a UTF-8 BOM.
    b"",                              # Zero-byte report.
])
def test_unreadable_or_blank_rehashed_report_rejected(
    tmp_path, recorded_status, bad_report
):
    fixture = _fixture(tmp_path)
    _, _, log, index, root = fixture
    if recorded_status == "failed":
        # Failed attempts may legitimately retain a report; those reports
        # must not bypass the text gate simply because success was not claimed.
        log["events"][0]["status"] = "failed"
        index["cells"][0]["status"] = "failed"
        index["execution_log_sha256"] = _digest(_bytes(log))
        trace_claim = index["cells"][0]["trace"]
        trace_path = root / trace_claim["path"]
        trace = json.loads(trace_path.read_bytes())
        trace["status"] = "failed"
        changed_trace = _bytes(trace)
        trace_path.write_bytes(changed_trace)
        index["cells"][0]["trace"] = _file_claim(trace_claim["path"], changed_trace)
    _replace_report_bytes_and_refresh_claims(fixture, bad_report)
    with pytest.raises(design.DesignError, match="Markdown text|invalid file fingerprint"):
        _audit(fixture)


@pytest.mark.parametrize("extension", ["pdf", "txt"])
def test_nonmarkdown_report_suffix_rejected_with_valid_sha256(tmp_path, extension):
    fixture = _fixture(tmp_path)
    index, root = fixture[3], fixture[4]
    claim = index["cells"][0]["report"]
    old_path = root / claim["path"]
    new_relative = f"reports/trial-00.{extension}"
    old_path.rename(root / new_relative)
    claim["path"] = new_relative
    with pytest.raises(design.DesignError, match=r"requires a \.md Markdown"):
        _audit(fixture)


def test_genuine_nonascii_utf8_markdown_remains_eligible_for_local_audit(tmp_path):
    fixture = _fixture(tmp_path)
    report = "# Síntesis de investigación\n\n日本語の研究ノート。\n".encode("utf-8")
    _replace_report_bytes_and_refresh_claims(fixture, report)
    receipt = _audit(fixture)
    assert receipt["verified_reports"] == 40
    assert receipt["scientific_outcomes_validated"] is False


@pytest.mark.parametrize("malformed_report", [
    99, "reports/trial-00.md", {"path": "reports/trial-00.md"},
    {"path": None, "size_bytes": 20, "sha256": "0" * 64},
])
def test_malformed_report_claim_fails_as_design_error(tmp_path, malformed_report):
    fixture = _fixture(tmp_path)
    fixture[3]["cells"][0]["report"] = malformed_report
    with pytest.raises(design.DesignError, match="exact file fingerprint|invalid file fingerprint"):
        _audit(fixture)


@pytest.mark.parametrize("replacement_report", [
    b"Research report\x1b[31m with terminal escape",
    b"Research report\x01 with hidden C0 control",
    b"Research report\x7f with DEL",
    "Research report\u0085 with C1 control".encode("utf-8"),
    "Research report\u202e with reversed display".encode("utf-8"),
    "Research report\u2066 with directional isolate".encode("utf-8"),
])
def test_report_display_controls_fail_even_when_trace_and_index_are_rehashed(
    tmp_path, replacement_report
):
    # A matching report digest is insufficient when the text presentation can
    # be changed by nonprinting controls or bidirectional formatting commands.
    fixture = _fixture(tmp_path)
    index, root = fixture[3], fixture[4]
    first_cell = index["cells"][0]
    report_claim = first_cell["report"]
    (root / report_claim["path"]).write_bytes(replacement_report)
    first_cell["report"] = _file_claim(report_claim["path"], replacement_report)
    trace_claim = first_cell["trace"]
    trace_path = root / trace_claim["path"]
    trace = json.loads(trace_path.read_bytes())
    trace["report_sha256"] = _digest(replacement_report)
    trace_bytes = _bytes(trace)
    trace_path.write_bytes(trace_bytes)
    first_cell["trace"] = _file_claim(trace_claim["path"], trace_bytes)
    with pytest.raises(
        design.DesignError, match="unsafe control or bidirectional formatting"
    ):
        _audit(fixture)


def test_printable_multilingual_markdown_and_normal_line_controls_remain_valid(tmp_path):
    fixture = _fixture(tmp_path)
    index, root = fixture[3], fixture[4]
    first_cell = index["cells"][0]
    report_claim = first_cell["report"]
    report = "Evidence — research\n\tIndented हिंदी العربية 中文\n".encode("utf-8")
    (root / report_claim["path"]).write_bytes(report)
    first_cell["report"] = _file_claim(report_claim["path"], report)
    trace_claim = first_cell["trace"]
    trace_path = root / trace_claim["path"]
    trace = json.loads(trace_path.read_bytes())
    trace["report_sha256"] = _digest(report)
    trace_bytes = _bytes(trace)
    trace_path.write_bytes(trace_bytes)
    first_cell["trace"] = _file_claim(trace_claim["path"], trace_bytes)
    assert _audit(fixture)["verified_reports"] == 40


def _rewrite_synthetic_source_ledger(fixture, *, cell_number: int, change) -> None:
    """Rehash every synthetic inventory claim after mutating a single trace."""
    _, _, _, index, root = fixture
    cell = index["cells"][cell_number]
    path = root / cell["trace"]["path"]
    trace = json.loads(path.read_bytes())
    change(trace)
    raw = _bytes(trace)
    path.write_bytes(raw)
    cell["trace"] = _file_claim(cell["trace"]["path"], raw)



def test_source_usage_receipt_does_not_infer_actual_exposure_from_budget(tmp_path):
    # Forty completed cells with zero scheduled sources can satisfy upper caps.
    # The receipt must not imply that D3 or D6 actually used their allowances.
    receipt = _audit(_fixture(tmp_path))
    usage = receipt["self_reported_source_usage_by_variant"]
    assert set(usage) == set(design.VARIANTS)
    for variant in design.VARIANTS:
        assert usage[variant] == {
            "attempted_cells": 10,
            "completed_cells": 10,
            "scheduled_source_claims": 0,
            "successful_source_claims": 0,
            "failed_source_claims": 0,
            "at_budget_attempted_cells": 0,
            "zero_scheduled_source_attempts": 10,
            "zero_successful_source_attempts": 10,
        }
    assert receipt["model_or_retrieval_calls_verified"] is False


@pytest.mark.parametrize("variant,scheduled,failed", [
    ("D3", 3, 1),
    ("D6", 2, 0),
    ("P6V", 6, 2),
])
def test_source_usage_receipt_reconciles_partial_and_full_arm_exposure(
    tmp_path, variant, scheduled, failed
):
    fixture = _fixture(tmp_path)
    position = next(
        i for i, cell in enumerate(fixture[3]["cells"])
        if cell["variant"] == variant
    )
    urls = [f"https://synthetic.invalid/{variant}/{i}" for i in range(scheduled)]

    def set_usage(trace):
        trace.update(
            source_count=scheduled,
            successful_source_count=scheduled - failed,
            failed_source_count=failed,
            scheduled_urls=urls,
            successful_urls=urls[:scheduled - failed],
            failed_urls=urls[scheduled - failed:],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=position, change=set_usage)
    receipt = _audit(fixture)
    usage = receipt["self_reported_source_usage_by_variant"][variant]
    assert usage["attempted_cells"] == 10
    assert usage["completed_cells"] == 10
    assert usage["scheduled_source_claims"] == scheduled
    assert usage["successful_source_claims"] == scheduled - failed
    assert usage["failed_source_claims"] == failed
    budget = design.PROSPECTIVE_TREATMENT_CONTROLS_V1[variant]["source_budget"]
    assert usage["at_budget_attempted_cells"] == int(scheduled == budget)
    assert usage["zero_scheduled_source_attempts"] == 9
    assert usage["zero_successful_source_attempts"] == 9


def test_source_usage_receipt_denominators_preserve_failed_and_unattempted(tmp_path):
    fixture = _fixture(tmp_path)
    _mark_unattempted(fixture, 4)
    _, _, log, index, root = fixture
    # Keep the first failed attempt and its (optional) report, rather than
    # excluding an unfavorable outcome from the source-exposure denominator.
    log["events"][0]["status"] = "failed"
    index["cells"][0]["status"] = "failed"
    claim = index["cells"][0]["trace"]
    path = root / claim["path"]
    trace = json.loads(path.read_bytes())
    trace["status"] = "failed"
    changed = _bytes(trace)
    path.write_bytes(changed)
    index["cells"][0]["trace"] = _file_claim(claim["path"], changed)
    index["execution_log_sha256"] = _digest(_bytes(log))

    receipt = _audit(fixture)
    usage = receipt["self_reported_source_usage_by_variant"]
    assert receipt["attempted_cells"] == 4
    assert sum(item["attempted_cells"] for item in usage.values()) == 4
    assert sum(item["completed_cells"] for item in usage.values()) == 3
    assert sum(item["zero_scheduled_source_attempts"] for item in usage.values()) == 4
    assert sum(item["at_budget_attempted_cells"] for item in usage.values()) == 0
    assert all(item["attempted_cells"] == 1 for item in usage.values())

@pytest.mark.parametrize("variant", design.VARIANTS)
def test_recorded_source_budget_at_limit_with_one_failed_url_is_valid(
    tmp_path, variant
):
    fixture = _fixture(tmp_path)
    index = fixture[3]
    number = next(
        i for i, cell in enumerate(index["cells"]) if cell["variant"] == variant
    )
    budget = design.PROSPECTIVE_TREATMENT_CONTROLS_V1[variant]["source_budget"]
    urls = [f"https://synthetic.invalid/{variant}/{i}" for i in range(budget)]

    def set_ledger(trace):
        trace.update(
            source_count=budget,
            successful_source_count=budget - 1,
            failed_source_count=1,
            scheduled_urls=urls,
            successful_urls=urls[:-1],
            failed_urls=urls[-1:],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=number, change=set_ledger)
    receipt = _audit(fixture)
    assert receipt["self_reported_source_ledgers_within_frozen_budgets"] is True
    assert receipt["model_or_retrieval_calls_verified"] is False


@pytest.mark.parametrize("change", [
    lambda t: t.pop("source_count"),
    lambda t: t.update(source_count=True),
    lambda t: t.update(source_count=1.0),
    lambda t: t.update(source_count=-1),
    lambda t: t.update(source_count=7),
    lambda t: t.update(source_count=1),
    lambda t: t.update(successful_source_count=1),
    lambda t: t.update(failed_source_count=-1),
    lambda t: t.pop("scheduled_urls"),
    lambda t: t.update(scheduled_urls=["https://synthetic.invalid/one"]),
    lambda t: t.update(source_count=1, scheduled_urls=[99]),
    lambda t: t.update(source_count=1, scheduled_urls=[" "]),
    lambda t: t.update(source_count=2, scheduled_urls=["u", "u"],
                       successful_source_count=2, successful_urls=["u", "u"]),
    lambda t: t.update(source_count=1, scheduled_urls=["u"],
                       successful_source_count=1, successful_urls=["v"]),
    lambda t: t.update(source_count=2, scheduled_urls=["u", "v"],
                       successful_source_count=1, successful_urls=["u"],
                       failed_source_count=1, failed_urls=["u"]),
    lambda t: t.update(source_count=1, scheduled_urls=[" https://x.invalid"],
                       successful_source_count=1, successful_urls=[" https://x.invalid"]),
    lambda t: t.update(failed_urls="not-a-list"),
])
def test_inconsistent_recorded_source_ledger_rejected_despite_rehashed_trace(
    tmp_path, change
):
    fixture = _fixture(tmp_path)
    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=change)
    with pytest.raises(design.DesignError, match="source ledger"):
        _audit(fixture)


@pytest.mark.parametrize("bad_url", [
    "source without a URI",
    "ftp://synthetic.invalid/record",
    "file:///tmp/not-a-web-source",
    "javascript:alert(1)",
    "/relative/resource",
    "https:/broken.invalid/path",
    "https://",
    "https://user:pass@synthetic.invalid/document",
    "https://synthetic.invalid:0/document",
    "https://synthetic.invalid:99999/document",
    "https://synthetic.invalid:bad/document",
    "https://synthetic.invalid/a b",
    "https://synthetic.invalid/with\\backslash",
    "https://synthetic.invalid/\u200bhidden",
    "https://synthetic.invalid/\u202eoverride",
    "https://[unmatched",
])
def test_nonweb_or_unsafe_source_url_rejected_with_consistent_hashes(
    tmp_path, bad_url
):
    fixture = _fixture(tmp_path)

    def replace_ledger(trace):
        trace.update(
            source_count=1, successful_source_count=1, failed_source_count=0,
            scheduled_urls=[bad_url], successful_urls=[bad_url], failed_urls=[],
        )

    _rewrite_synthetic_source_ledger(
        fixture, cell_number=0, change=replace_ledger
    )
    with pytest.raises(design.DesignError, match="source ledger"):
        _audit(fixture)


@pytest.mark.parametrize("equivalent_urls", [
    ("https://synthetic.invalid/a#first", "https://synthetic.invalid/a#second"),
    ("https://synthetic.invalid", "https://synthetic.invalid/"),
    ("https://synthetic.invalid:443/a", "https://SYNTHETIC.invalid/a"),
    ("http://SYNTHETIC.invalid:80/a", "http://synthetic.invalid/a"),
])
def test_same_fetch_resource_cannot_inflate_scheduled_source_count(
    tmp_path, equivalent_urls
):
    fixture = _fixture(tmp_path)
    urls = list(equivalent_urls)

    def replace_ledger(trace):
        trace.update(
            source_count=2, successful_source_count=2, failed_source_count=0,
            scheduled_urls=urls, successful_urls=urls, failed_urls=[],
        )

    _rewrite_synthetic_source_ledger(
        fixture, cell_number=0, change=replace_ledger
    )
    with pytest.raises(design.DesignError, match="source ledger.*resource"):
        _audit(fixture)


@pytest.mark.parametrize("equivalent_urls", [
    (
        "https://[2001:db8::1]/study",
        "https://[2001:0db8:0000:0000:0000:0000:0000:0001]/study",
    ),
    (
        "https://[::ffff:192.0.2.1]/x",
        "https://[::ffff:c000:201]:443/x#paragraph",
    ),
])
def test_ipv6_address_spelling_aliases_cannot_inflate_source_exposure(
    tmp_path, equivalent_urls
):
    fixture = _fixture(tmp_path)
    urls = list(equivalent_urls)

    def set_ledger(trace):
        trace.update(
            source_count=2, successful_source_count=2, failed_source_count=0,
            scheduled_urls=urls, successful_urls=urls, failed_urls=[],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=set_ledger)
    with pytest.raises(design.DesignError, match="source ledger.*resource"):
        _audit(fixture)


@pytest.mark.parametrize("scheduled, outcome", [
    (
        "https://[2001:db8::1]/study",
        "https://[2001:0db8:0000:0000:0000:0000:0000:0001]/study",
    ),
    (
        "https://[::ffff:192.0.2.1]/x",
        "https://[::ffff:c000:201]:443/x#paragraph",
    ),
])
def test_ipv6_fetch_identity_reconciles_equivalent_outcome_spelling(
    tmp_path, scheduled, outcome
):
    fixture = _fixture(tmp_path)

    def set_ledger(trace):
        trace.update(
            source_count=1, successful_source_count=1, failed_source_count=0,
            scheduled_urls=[scheduled], successful_urls=[outcome], failed_urls=[],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=set_ledger)
    receipt = _audit(fixture)
    assert receipt["self_reported_source_urls_http_and_fetch_distinct"] is True
    assert receipt["model_or_retrieval_calls_verified"] is False


def test_distinct_ipv6_addresses_and_query_strings_remain_distinct(tmp_path):
    fixture = _fixture(tmp_path)
    urls = [
        "https://[2001:db8::1]/study",
        "https://[2001:db8::2]/study",
        "https://[2001:db8::1]/study?edition=2",
    ]

    def set_ledger(trace):
        trace.update(
            source_count=3, successful_source_count=3, failed_source_count=0,
            scheduled_urls=urls, successful_urls=urls, failed_urls=[],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=set_ledger)
    assert _audit(fixture)["self_reported_source_ledgers_within_frozen_budgets"] is True


@pytest.mark.parametrize("nonportable_url", [
    "https://[fe80::1%25eth0]/study",
    "https://[fe80::1%eth0]/study",
])
def test_scoped_ipv6_source_rejected_as_nonportable(tmp_path, nonportable_url):
    fixture = _fixture(tmp_path)

    def set_ledger(trace):
        trace.update(
            source_count=1, successful_source_count=1, failed_source_count=0,
            scheduled_urls=[nonportable_url],
            successful_urls=[nonportable_url], failed_urls=[],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=set_ledger)
    with pytest.raises(design.DesignError, match="source ledger"):
        _audit(fixture)


def test_valid_international_ipv6_and_fragment_urls_remain_distinct(tmp_path):
    fixture = _fixture(tmp_path)
    urls = [
        "https://bücher.example/overview#section",
        "https://[2001:db8::1]/study",
        "https://synthetic.invalid/record?version=1",
    ]

    def replace_ledger(trace):
        trace.update(
            source_count=3, successful_source_count=2, failed_source_count=1,
            scheduled_urls=urls, successful_urls=urls[:2], failed_urls=urls[2:],
        )

    _rewrite_synthetic_source_ledger(
        fixture, cell_number=0, change=replace_ledger
    )
    receipt = _audit(fixture)
    assert receipt["self_reported_source_urls_http_and_fetch_distinct"] is True
    assert receipt["model_or_retrieval_calls_verified"] is False


# Future-replication-only common runtime fidelity checks. These are synthetic
# metadata contracts, not proof that any real model/search requests occurred.
@pytest.mark.parametrize("field,bad_value", [
    ("runner_commit", "not-an-immutable-commit"),
    ("runner_commit", "A" * 40),
    ("requirements_sha256", "Z" * 64),
    ("smart_model_id", ""),
    ("fast_model_id", 22),
    ("search_provider_id", "backend with spaces"),
    ("generation_temperature", True),
    ("generation_temperature", -0.1),
    ("generation_temperature", 2.1),
    ("search_candidate_multiplier", 0),
    ("search_candidate_multiplier", False),
    ("browse_timeout_seconds", 0),
    ("run_timeout_seconds", "480.0"),
    ("max_concurrent_browses", 0),
])
def test_prospective_runtime_context_rejects_bad_rehashed_claim(
    tmp_path, field, bad_value
):
    fixture = _fixture(tmp_path)
    _rewrite_synthetic_source_ledger(
        fixture, cell_number=0,
        change=lambda trace: trace["runtime_context"].update({field: bad_value}),
    )
    with pytest.raises(design.DesignError, match="runtime"):
        _audit(fixture)


@pytest.mark.parametrize("replacement", [None, "not-an-object", {"runner_commit": "a" * 40}])
def test_prospective_runtime_requires_complete_exact_object(tmp_path, replacement):
    fixture = _fixture(tmp_path)
    _rewrite_synthetic_source_ledger(
        fixture, cell_number=0,
        change=lambda trace: trace.update(runtime_context=replacement),
    )
    with pytest.raises(design.DesignError, match="exact common runtime-context fields"):
        _audit(fixture)


def test_prospective_runtime_cannot_invent_extra_fields(tmp_path):
    fixture = _fixture(tmp_path)
    _rewrite_synthetic_source_ledger(
        fixture, cell_number=0,
        change=lambda trace: trace["runtime_context"].update(extra_model="outcome-tuned"),
    )
    with pytest.raises(design.DesignError, match="exact common runtime-context fields"):
        _audit(fixture)


def test_prospective_runtime_drift_rejected_even_if_all_hashes_are_rewritten(tmp_path):
    fixture = _fixture(tmp_path)
    # Both values are valid independently, but non-treatment generation
    # settings may not vary between arms without a recorded protocol deviation.
    _rewrite_synthetic_source_ledger(
        fixture, cell_number=1,
        change=lambda trace: trace["runtime_context"].update(
            generation_temperature=0.25
        ),
    )
    with pytest.raises(design.DesignError, match="runtime context changed"):
        _audit(fixture)


def test_prospective_runtime_prerun_pin_blocks_consistent_relabeling(tmp_path):
    fixture = _fixture(tmp_path)
    first_trace = fixture[4] / fixture[3]["cells"][0]["trace"]["path"]
    context = json.loads(first_trace.read_bytes())["runtime_context"]
    digest = _digest(json.dumps(
        context, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8"))
    result = _audit(fixture, expected_runtime_context_sha256=digest)
    assert result["common_runtime_context_sha256"] == digest
    assert result["common_runtime_context_external_pin_matched"] is True
    assert result["recorded_common_runtime_context_consistent"] is True
    assert result["actual_common_runtime_independently_authenticated"] is False
    assert "synthetic-search" not in str(result)
    with pytest.raises(design.DesignError, match="does not match exact"):
        _audit(fixture, expected_runtime_context_sha256="0" * 64)
    with pytest.raises(design.DesignError, match="64 lowercase"):
        _audit(fixture, expected_runtime_context_sha256="not-a-digest")


def test_prospective_runtime_receipt_is_explicitly_unpinned_without_custody(tmp_path):
    fixture = _fixture(tmp_path)
    result = _audit(fixture)
    assert result["common_runtime_context_sha256"]
    assert result["common_runtime_context_external_pin_matched"] is False
    assert result["recorded_common_runtime_context_consistent"] is True
    assert result["actual_common_runtime_independently_authenticated"] is False

# A fragment or host spelling change does not identify a new HTTP fetch.
# Require outcome partitioning by the same canonical fetch identities used
# by the no-duplicate budget check, while retaining raw URL evidence intact.
@pytest.mark.parametrize("scheduled,outcome", [
    ("https://SYNTHETIC.invalid:443/record#source",
     "https://synthetic.invalid/record#view"),
    ("https://synthetic.invalid", "https://synthetic.invalid/"),
    ("https://bücher.example/overview#section-a",
     "https://xn--bcher-kva.example/overview#section-b"),
    ("http://SYNTHETIC.invalid:80/record",
     "http://synthetic.invalid/record"),
])
@pytest.mark.parametrize("outcome_field", ["successful_urls", "failed_urls"])
def test_equivalent_fetch_resource_outcome_spelling_is_valid(
    tmp_path, scheduled, outcome, outcome_field
):
    fixture = _fixture(tmp_path)

    def change(trace):
        trace.update(
            source_count=1,
            successful_source_count=int(outcome_field == "successful_urls"),
            failed_source_count=int(outcome_field == "failed_urls"),
            scheduled_urls=[scheduled],
            successful_urls=[outcome] if outcome_field == "successful_urls" else [],
            failed_urls=[outcome] if outcome_field == "failed_urls" else [],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=change)
    receipt = _audit(fixture)
    assert receipt["self_reported_source_urls_http_and_fetch_distinct"] is True
    assert receipt["model_or_retrieval_calls_verified"] is False


def test_mixed_alias_outcomes_partition_two_distinct_fetches(tmp_path):
    fixture = _fixture(tmp_path)

    def change(trace):
        trace.update(
            source_count=2, successful_source_count=1, failed_source_count=1,
            scheduled_urls=[
                "https://synthetic.invalid/one#first",
                "https://synthetic.invalid/two?version=1#first",
            ],
            successful_urls=["https://SYNTHETIC.invalid:443/two?version=1#later"],
            failed_urls=["https://synthetic.invalid/one"],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=change)
    assert _audit(fixture)["self_reported_source_ledgers_within_frozen_budgets"] is True


@pytest.mark.parametrize("scheduled,outcome", [
    ("https://synthetic.invalid/item?version=1",
     "https://synthetic.invalid/item?version=2"),
    ("https://synthetic.invalid/item", "http://synthetic.invalid/item"),
    ("https://synthetic.invalid/Item", "https://synthetic.invalid/item"),
])
def test_distinct_fetch_resource_cannot_be_reported_as_scheduled(
    tmp_path, scheduled, outcome
):
    fixture = _fixture(tmp_path)

    def change(trace):
        trace.update(
            source_count=1, successful_source_count=1, failed_source_count=0,
            scheduled_urls=[scheduled], successful_urls=[outcome], failed_urls=[],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=change)
    with pytest.raises(design.DesignError, match="missing, invented or overlapping"):
        _audit(fixture)


def test_aliases_cannot_double_count_one_resource_across_outcomes(tmp_path):
    fixture = _fixture(tmp_path)

    def change(trace):
        trace.update(
            source_count=2, successful_source_count=1, failed_source_count=1,
            scheduled_urls=[
                "https://synthetic.invalid/one",
                "https://synthetic.invalid/two",
            ],
            successful_urls=["https://synthetic.invalid/one#success"],
            failed_urls=["https://SYNTHETIC.invalid:443/one#failure"],
        )

    _rewrite_synthetic_source_ledger(fixture, cell_number=0, change=change)
    with pytest.raises(design.DesignError, match="missing, invented or overlapping"):
        _audit(fixture)


# Synthetic future-replication diagnostics only: do not promote to historical
# treatment-compliance tests or use exposure to filter primary comparisons.
def test_paired_source_exposure_zero_is_not_assumed_to_be_full_budget(tmp_path):
    receipt = _audit(_fixture(tmp_path))
    for contrast in ("D6 - D3", "P6 - D6", "P6V - P6"):
        pairs = receipt["self_reported_paired_source_exposure_by_contrast"][contrast]
        assert pairs == {
            "both_attempted_tasks": 10,
            "both_completed_tasks": 10,
            "scheduled_delta_positive": 0,
            "scheduled_delta_zero": 10,
            "scheduled_delta_negative": 0,
            "scheduled_delta_sum": 0,
            "successful_delta_positive": 0,
            "successful_delta_zero": 10,
            "successful_delta_negative": 0,
            "successful_delta_sum": 0,
        }
    assert receipt["model_or_retrieval_calls_verified"] is False


def test_paired_source_exposure_tracks_within_task_contrast_direction(tmp_path):
    fixture = _fixture(tmp_path)
    first_task_id = fixture[3]["cells"][0]["task_id"]
    for variant, (scheduled, successful) in {
        "D3": (3, 2),
        "D6": (5, 4),
        "P6": (1, 1),
        "P6V": (6, 6),
    }.items():
        position = next(
            n for n, cell in enumerate(fixture[3]["cells"])
            if cell["task_id"] == first_task_id and cell["variant"] == variant
        )
        urls = [f"https://synthetic.invalid/{variant}/{i}" for i in range(scheduled)]

        def set_ledger(trace):
            trace.update(
                source_count=scheduled,
                successful_source_count=successful,
                failed_source_count=scheduled - successful,
                scheduled_urls=urls,
                successful_urls=urls[:successful],
                failed_urls=urls[successful:],
            )

        _rewrite_synthetic_source_ledger(fixture, cell_number=position, change=set_ledger)
    receipt = _audit(fixture)
    comparisons = receipt["self_reported_paired_source_exposure_by_contrast"]
    for contrast, scheduled_delta, successful_delta in (
        ("D6 - D3", 2, 2),
        ("P6 - D6", -4, -3),
        ("P6V - P6", 5, 5),
    ):
        counts = comparisons[contrast]
        assert counts["both_attempted_tasks"] == 10
        assert counts["both_completed_tasks"] == 10
        assert counts["scheduled_delta_sum"] == scheduled_delta
        assert counts["successful_delta_sum"] == successful_delta
        for prefix, delta in (
            ("scheduled", scheduled_delta), ("successful", successful_delta)
        ):
            assert counts[f"{prefix}_delta_positive"] == int(delta > 0)
            assert counts[f"{prefix}_delta_negative"] == int(delta < 0)
            assert counts[f"{prefix}_delta_zero"] == 9
            assert sum(counts[f"{prefix}_delta_{direction}"]
                       for direction in ("negative", "zero", "positive")) == 10


def test_paired_source_exposure_keeps_partial_and_failed_attempts(tmp_path):
    fixture = _fixture(tmp_path)
    _mark_unattempted(fixture, 4)
    _, _, log, index, root = fixture
    failed_variant = log["events"][0]["variant"]
    log["events"][0]["status"] = "failed"
    index["cells"][0]["status"] = "failed"
    claim = index["cells"][0]["trace"]
    trace_path = root / claim["path"]
    trace = json.loads(trace_path.read_bytes())
    trace["status"] = "failed"
    raw = _bytes(trace)
    trace_path.write_bytes(raw)
    index["cells"][0]["trace"] = _file_claim(claim["path"], raw)
    index["execution_log_sha256"] = _digest(_bytes(log))

    receipt = _audit(fixture)
    comparisons = receipt["self_reported_paired_source_exposure_by_contrast"]
    assert receipt["attempted_cells"] == 4
    for contrast, earlier, later in (
        ("D6 - D3", "D3", "D6"),
        ("P6 - D6", "D6", "P6"),
        ("P6V - P6", "P6", "P6V"),
    ):
        counts = comparisons[contrast]
        assert counts["both_attempted_tasks"] == 1
        assert counts["both_completed_tasks"] == int(
            failed_variant not in (earlier, later)
        )
        assert counts["scheduled_delta_zero"] == 1
        assert counts["successful_delta_zero"] == 1
        assert counts["scheduled_delta_sum"] == 0
        assert counts["successful_delta_sum"] == 0
