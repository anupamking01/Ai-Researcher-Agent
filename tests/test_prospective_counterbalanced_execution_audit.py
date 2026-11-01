"""Offline synthetic tests: future VERA chronology, not experimental outcomes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import sys

import pytest

from scripts import plan_counterbalanced_replication as design
from scripts import verify_counterbalanced_replication_execution as audit


def _manifest():
    return json.dumps({
        "schema_version": 1,
        "task_set_id": "independent-future-tasks-2027",
        "frozen_before_execution": True,
        "tasks": [
            {"id": f"unseen-{i:02d}", "category": "research",
             "question": f"Freshly chosen future research question {i}?"}
            for i in range(10)
        ],
    }, sort_keys=True, separators=(",", ":")).encode()


def _plan(source):
    return (json.dumps(design.build_plan(source), sort_keys=True, indent=2)
            + "\n").encode()


def _utc(when):
    return when.isoformat().replace("+00:00", "Z")


def _log(source, receipt):
    schedule = design.build_plan(source)["schedule"]
    t0 = datetime(2027, 3, 2, 12, 0, tzinfo=timezone.utc)
    events = []
    current = t0
    for row in schedule:
        for variant in row["arm_order"]:
            events.append({
                "task_id": row["task_id"], "variant": variant,
                "run_id": f"replication-{len(events):02d}",
                "status": "completed",
                "started_at_utc": _utc(current),
                "finished_at_utc": _utc(current + timedelta(seconds=11)),
            })
            current += timedelta(seconds=12)
    return {
        "schema_version": 1,
        "classification": audit.LOG_CLASSIFICATION,
        "task_set_id": design.build_plan(source)["task_set_id"],
        "source_manifest_sha256": hashlib.sha256(source).hexdigest(),
        "plan_file_sha256": hashlib.sha256(receipt).hexdigest(),
        "started_at_utc": _utc(t0),
        "finished_at_utc": _utc(current),
        "events": events,
    }


def _bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _fixture():
    source = _manifest()
    receipt = _plan(source)
    return source, receipt, _log(source, receipt)


def test_exact_schedule_and_chronology_only_with_explicit_limits():
    source, receipt, log = _fixture()
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["status"] == "pass_recorded_chronology_only"
    assert result["recorded_cells"] == 40
    assert result["recorded_status_counts"] == {
        "completed": 40, "failed": 0, "timeout": 0, "cancelled": 0,
    }
    assert result["all_recorded_cells_completed"] is True
    assert result["source_manifest_sha256"] == hashlib.sha256(source).hexdigest()
    assert result["plan_file_sha256"] == hashlib.sha256(receipt).hexdigest()
    assert result["execution_log_sha256"] == hashlib.sha256(_bytes(log)).hexdigest()
    assert result["plan_file_external_pin_matched"] is False
    assert result["execution_log_external_pin_matched"] is False
    assert result["actual_execution_independently_authenticated"] is False
    assert result["scientific_outcomes_validated"] is False
    assert result["historical_2026_study_validated"] is False
    assert result["human_validation_performed"] is False


@pytest.mark.parametrize("status", ["failed", "timeout", "cancelled"])
def test_failed_and_incomplete_attempts_retained_without_positive_outcome_claim(status):
    source, receipt, log = _fixture()
    log["events"][3]["status"] = status
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["recorded_status_counts"][status] == 1
    assert result["recorded_status_counts"]["completed"] == 39
    assert result["all_recorded_cells_completed"] is False


@pytest.mark.parametrize("mutate,pattern", [
    (lambda l: l["events"][0].update(variant="P6V"), "frozen task-major"),
    (lambda l: l["events"][0].update(task_id="unseen-08"), "frozen task-major"),
    (lambda l: l["events"].__setitem__(slice(0, 2), list(reversed(l["events"][:2]))), "frozen task-major"),
    (lambda l: l["events"].pop(), "all 40 planned"),
    (lambda l: l["events"].append(l["events"][-1].copy()), "all 40 planned"),
    (lambda l: l["events"][1].update(run_id=l["events"][0]["run_id"]), "duplicate run ID"),
    (lambda l: l["events"][1].update(run_id="../unsafe"), "unsafe or duplicate"),
    (lambda l: l["events"][1].update(status="invalid"), "unknown status"),
    (lambda l: l["events"][1].update(status=True), "unknown status"),
    (lambda l: l["events"][1].update(result_score=5), "exact event schema"),
    (lambda l: l.update(observed_support=0.99), "exact audit schema"),
    (lambda l: l.update(schema_version=True), "schema version"),
    (lambda l: l.update(classification="confirmatory_success"), "invalid classification"),
    (lambda l: l.update(source_manifest_sha256="0" * 64), "source_manifest_sha256"),
    (lambda l: l.update(plan_file_sha256="0" * 64), "plan_file_sha256"),
])
def test_schedule_lineage_identity_and_ambiguous_claims_fail_closed(mutate, pattern):
    source, receipt, log = _fixture()
    mutate(log)
    with pytest.raises(design.DesignError, match=pattern):
        audit.audit_execution_log(source, receipt, _bytes(log))


@pytest.mark.parametrize("mutate,pattern", [
    (lambda l: l["events"][1].update(started_at_utc=l["events"][0]["started_at_utc"]), "overlapping"),
    (lambda l: l["events"][0].update(finished_at_utc=l["events"][0]["started_at_utc"]), "nonpositive"),
    (lambda l: l["events"][0].update(started_at_utc="2027-03-02T12:00:00+03:00"), "explicit UTC"),
    (lambda l: l["events"][0].update(started_at_utc="2027-03-02T12:00:00"), "explicit UTC"),
    (lambda l: l["events"][0].update(started_at_utc="2027-02-30T12:00:00Z"), "real UTC"),
    (lambda l: l["events"][0].update(started_at_utc="2027-03-02T12:00:00.1234567Z"), "explicit UTC"),
    (lambda l: l.update(started_at_utc="2027-03-02T12:00:01Z"), "overlapping"),
    (lambda l: l.update(finished_at_utc="2027-03-02T12:00:02Z"), "outside study window"),
    (lambda l: l.update(finished_at_utc=l["started_at_utc"]), "invalid duration"),
])
def test_utc_and_global_nonoverlap_contract(mutate, pattern):
    source, receipt, log = _fixture()
    mutate(log)
    with pytest.raises(design.DesignError, match=pattern):
        audit.audit_execution_log(source, receipt, _bytes(log))


@pytest.mark.parametrize("raw,pattern", [
    (b"", "outside supported range"),
    (b"x" * (audit.MAX_EXECUTION_LOG_BYTES + 1), "outside supported range"),
    (b"not json", "unambiguous UTF-8 JSON"),
    (b"[]", "exact audit schema"),
    (b'{"schema_version":1,"schema_version":1}', "duplicate"),
    (b'{"schema_version":NaN}', "nonstandard"),
    (b'{"schema_version":1e999}', "not finite"),
    (b'{"schema_version":' + b"9" * 129 + b"}", "unbounded"),
])
def test_untrusted_execution_log_inputs_fail_closed(raw, pattern):
    source, receipt, _ = _fixture()
    with pytest.raises(design.DesignError, match=pattern):
        audit.audit_execution_log(source, receipt, raw)


def test_external_fingerprints_reject_self_consistent_replacement_and_bad_pins():
    source, receipt, log = _fixture()
    original_log = _bytes(log)
    log_sha = hashlib.sha256(original_log).hexdigest()
    plan_sha = hashlib.sha256(receipt).hexdigest()
    verified = audit.audit_execution_log(
        source, receipt, original_log,
        expected_plan_file_sha256=plan_sha,
        expected_execution_log_sha256=log_sha,
    )
    assert verified["plan_file_external_pin_matched"] is True
    assert verified["execution_log_external_pin_matched"] is True
    log["events"][0]["status"] = "failed"
    with pytest.raises(design.DesignError, match="does not match exact"):
        audit.audit_execution_log(
            source, receipt, _bytes(log),
            expected_execution_log_sha256=log_sha,
        )
    with pytest.raises(design.DesignError, match="differs from supplied external pin"):
        audit.audit_execution_log(
            source, receipt, original_log,
            expected_plan_file_sha256="0" * 64,
        )
    for invalid in ("", "A" * 64, "0" * 63, 7, True):
        with pytest.raises(design.DesignError, match="64 lowercase"):
            audit.audit_execution_log(
                source, receipt, original_log,
                expected_execution_log_sha256=invalid,
            )


def test_changed_manifest_and_changed_plan_receipt_fail_before_chronology():
    source, receipt, log = _fixture()
    changed = json.loads(source)
    changed["tasks"][0]["question"] = "Entirely new question?"
    with pytest.raises(design.DesignError, match="recomputed manifest-bound"):
        audit.audit_execution_log(_bytes(changed), receipt, _bytes(log))
    altered_receipt = json.loads(receipt)
    altered_receipt["schedule"][0]["arm_order"].reverse()
    with pytest.raises(design.DesignError, match="recomputed manifest-bound"):
        audit.audit_execution_log(source, _bytes(altered_receipt), _bytes(log))


def test_cli_is_read_only_and_rejects_unsafe_log_path(tmp_path, monkeypatch, capsys):
    source, receipt, log = _fixture()
    manifest = tmp_path / "manifest.json"
    schedule = tmp_path / "plan.json"
    log_path = tmp_path / "execution.json"
    manifest.write_bytes(source)
    schedule.write_bytes(receipt)
    log_path.write_bytes(_bytes(log))
    monkeypatch.setattr(sys, "argv", [
        "verify_counterbalanced_replication_execution.py",
        "--task-manifest", str(manifest),
        "--plan-file", str(schedule),
        "--execution-log", str(log_path),
    ])
    assert audit.main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["recorded_cells"] == 40
    assert "events" not in summary
    assert sorted(tmp_path.iterdir()) == sorted([manifest, schedule, log_path])
    alias = tmp_path / "log_alias.json"
    alias.symlink_to(log_path)
    monkeypatch.setattr(sys, "argv", [
        "verify_counterbalanced_replication_execution.py",
        "--task-manifest", str(manifest),
        "--plan-file", str(schedule),
        "--execution-log", str(alias),
    ])
    with pytest.raises(SystemExit) as exc:
        audit.main()
    assert exc.value.code == 2
    assert "bounded regular non-symlink" in capsys.readouterr().err
