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
        "not_started": 0,
    }
    assert result["all_recorded_cells_completed"] is True
    assert result["source_manifest_sha256"] == hashlib.sha256(source).hexdigest()
    assert result["plan_file_sha256"] == hashlib.sha256(receipt).hexdigest()
    assert result["execution_log_sha256"] == hashlib.sha256(_bytes(log)).hexdigest()
    assert result["plan_file_external_pin_matched"] is False
    assert result["task_manifest_external_pin_matched"] is False
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


def test_case_only_run_id_alias_cannot_claim_two_independent_runs():
    source, receipt, log = _fixture()
    log["events"][0]["run_id"] = "Future-Run-A"
    log["events"][1]["run_id"] = "future-run-a"
    with pytest.raises(design.DesignError, match="duplicate run ID"):
        audit.audit_execution_log(source, receipt, _bytes(log))


@pytest.mark.parametrize("unsafe_id", [
    "CON", "con.notes", "PRN", "AUX.json", "NUL", "COM1", "lpt9",
    "future-run-00.",
])
def test_windows_device_names_and_trailing_dots_are_not_portable_runs(unsafe_id):
    source, receipt, log = _fixture()
    log["events"][0]["run_id"] = unsafe_id
    with pytest.raises(design.DesignError, match="unsafe or duplicate run ID"):
        audit.audit_execution_log(source, receipt, _bytes(log))


def test_distinct_mixed_case_run_ids_still_pass_recorded_chronology():
    source, receipt, log = _fixture()
    log["events"][0]["run_id"] = "Future-Run-A"
    log["events"][1]["run_id"] = "future-run-b"
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["status"] == "pass_recorded_chronology_only"
    assert result["recorded_cells"] == 40


@pytest.mark.parametrize("mutate,pattern", [
    (lambda l: l["events"][0].update(variant="NOT_A_PLANNED_ARM"), "frozen task-major"),
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


def _mark_unattempted_suffix(log, first_unattempted):
    for event in log["events"][first_unattempted:]:
        event.update({
            "run_id": None, "status": "not_started",
            "started_at_utc": None, "finished_at_utc": None,
        })


@pytest.mark.parametrize("attempted", [1, 4, 39])
def test_interrupted_study_retains_every_planned_cell_without_fake_runs(attempted):
    source, receipt, log = _fixture()
    _mark_unattempted_suffix(log, attempted)
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["status"] == "pass_recorded_chronology_only"
    assert result["recorded_cells"] == 40
    assert result["attempted_cells"] == attempted
    assert result["unattempted_cells"] == 40 - attempted
    assert result["recorded_status_counts"]["completed"] == attempted
    assert result["recorded_status_counts"]["not_started"] == 40 - attempted
    assert result["all_planned_cells_attempted"] is False
    assert result["all_recorded_cells_completed"] is False
    assert result["actual_execution_independently_authenticated"] is False


def test_interrupted_study_retains_attempted_failure_not_as_unattempted():
    source, receipt, log = _fixture()
    log["events"][0]["status"] = "timeout"
    _mark_unattempted_suffix(log, 1)
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["recorded_status_counts"]["timeout"] == 1
    assert result["recorded_status_counts"]["not_started"] == 39
    assert result["attempted_cells"] == 1


@pytest.mark.parametrize("field,value", [
    ("run_id", "invented-run"),
    ("started_at_utc", "2027-03-02T12:00:12Z"),
    ("finished_at_utc", "2027-03-02T12:00:23Z"),
])
def test_not_started_cannot_claim_run_or_execution_timestamps(field, value):
    source, receipt, log = _fixture()
    _mark_unattempted_suffix(log, 2)
    log["events"][2][field] = value
    with pytest.raises(design.DesignError, match="not_started requires null"):
        audit.audit_execution_log(source, receipt, _bytes(log))


def test_gap_before_later_attempt_is_not_an_interrupted_suffix():
    source, receipt, log = _fixture()
    log["events"][1].update({
        "run_id": None, "status": "not_started",
        "started_at_utc": None, "finished_at_utc": None,
    })
    with pytest.raises(design.DesignError, match="attempt after a not_started suffix"):
        audit.audit_execution_log(source, receipt, _bytes(log))


def test_zero_attempts_do_not_pass_execution_audit():
    source, receipt, log = _fixture()
    _mark_unattempted_suffix(log, 0)
    with pytest.raises(design.DesignError, match="no attempted cells"):
        audit.audit_execution_log(source, receipt, _bytes(log))


def test_attempted_cell_with_null_run_id_is_invalid():
    source, receipt, log = _fixture()
    log["events"][1]["run_id"] = None
    with pytest.raises(design.DesignError, match="unsafe or duplicate run ID"):
        audit.audit_execution_log(source, receipt, _bytes(log))


def test_completed_full_study_reports_no_unattempted_cells():
    source, receipt, log = _fixture()
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["attempted_cells"] == 40
    assert result["unattempted_cells"] == 0
    assert result["all_planned_cells_attempted"] is True
    assert result["recorded_status_counts"]["not_started"] == 0


def test_chronology_source_pin_blocks_self_consistent_task_replacement():
    original, _, _ = _fixture()
    changed = json.loads(original)
    changed["tasks"][0]["question"] = "Substituted future task in chronology?"
    substituted = _bytes(changed)
    new_plan = _plan(substituted)
    new_log = _bytes(_log(substituted, new_plan))
    assert audit.audit_execution_log(
        substituted, new_plan, new_log
    )["status"] == "pass_recorded_chronology_only"
    with pytest.raises(design.DesignError, match="task manifest SHA-256 differs"):
        audit.audit_execution_log(
            substituted, new_plan, new_log,
            expected_task_manifest_sha256=hashlib.sha256(original).hexdigest(),
        )
    assert audit.audit_execution_log(
        original, _plan(original), _bytes(_log(original, _plan(original))),
        expected_task_manifest_sha256=hashlib.sha256(original).hexdigest(),
    )["task_manifest_external_pin_matched"] is True


def test_chronology_cli_checks_preexecution_task_source_pin(tmp_path, monkeypatch, capsys):
    source, receipt, log = _fixture()
    manifest = tmp_path / "tasks.json"
    plan = tmp_path / "plan.json"
    events = tmp_path / "events.json"
    manifest.write_bytes(source)
    plan.write_bytes(receipt)
    events.write_bytes(_bytes(log))
    monkeypatch.setattr(sys, "argv", [
        "verify_counterbalanced_replication_execution.py",
        "--task-manifest", str(manifest), "--plan-file", str(plan),
        "--execution-log", str(events),
        "--expected-task-manifest-sha256", hashlib.sha256(source).hexdigest(),
    ])
    assert audit.main() == 0
    receipt_out = json.loads(capsys.readouterr().out)
    assert receipt_out["task_manifest_external_pin_matched"] is True
    assert receipt_out["actual_execution_independently_authenticated"] is False

def test_arm_level_and_primary_pair_counts_for_fully_recorded_synthetic_log():
    source, receipt, log = _fixture()
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["recorded_status_counts_by_variant"] == {
        variant: {
            "completed": 10, "failed": 0, "timeout": 0,
            "cancelled": 0, "not_started": 0,
        }
        for variant in design.VARIANTS
    }
    assert result["recorded_fully_completed_task_count"] == 10
    assert result["recorded_completed_primary_pair_task_counts"] == {
        "D6_minus_D3": 10, "P6_minus_D6": 10, "P6V_minus_P6": 10,
    }
    assert result["actual_execution_independently_authenticated"] is False


def test_one_logged_timeout_changes_only_affected_primary_pair_coverage():
    source, receipt, log = _fixture()
    next(event for event in log["events"] if event["variant"] == "P6V")[
        "status"
    ] = "timeout"
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["recorded_status_counts_by_variant"]["P6V"] == {
        "completed": 9, "failed": 0, "timeout": 1,
        "cancelled": 0, "not_started": 0,
    }
    assert result["recorded_fully_completed_task_count"] == 9
    assert result["recorded_completed_primary_pair_task_counts"] == {
        "D6_minus_D3": 10, "P6_minus_D6": 10, "P6V_minus_P6": 9,
    }
    assert result["all_planned_cells_attempted"] is True
    assert result["all_recorded_cells_completed"] is False


def test_interrupted_log_exposes_variant_skew_and_missing_paired_tasks():
    source, receipt, log = _fixture()
    # One entire task attempted, with the D6 arm failed; all later tasks
    # explicitly unstarted. Aggregate completed count alone hides this skew.
    next(event for event in log["events"][:4] if event["variant"] == "D6")[
        "status"
    ] = "failed"
    for event in log["events"][4:]:
        event.update({
            "run_id": None, "status": "not_started",
            "started_at_utc": None, "finished_at_utc": None,
        })
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["attempted_cells"] == 4
    assert result["unattempted_cells"] == 36
    for variant in design.VARIANTS:
        counts = result["recorded_status_counts_by_variant"][variant]
        assert counts["not_started"] == 9
        assert counts["failed"] == (1 if variant == "D6" else 0)
        assert counts["completed"] == (0 if variant == "D6" else 1)
    assert result["recorded_fully_completed_task_count"] == 0
    assert result["recorded_completed_primary_pair_task_counts"] == {
        "D6_minus_D3": 0, "P6_minus_D6": 0, "P6V_minus_P6": 1,
    }
    assert result["all_recorded_cells_completed"] is False
    assert result["scientific_outcomes_validated"] is False


def test_complete_log_retains_planned_position_and_pair_order_balance():
    """Full Williams design has 2/3 slot exposures and 5:5 precedence."""
    source, receipt, log = _fixture()
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    attempted = result["recorded_attempted_position_counts_by_variant"]
    completed = result["recorded_completed_position_counts_by_variant"]
    assert attempted == completed
    for arm in design.VARIANTS:
        assert set(completed[arm]) == {"1", "2", "3", "4"}
        assert sorted(completed[arm].values()) == [2, 2, 3, 3]
        assert sum(completed[arm].values()) == 10
    for contrast, counts in result[
        "recorded_completed_primary_pair_order_counts"
    ].items():
        assert counts == {"left_before_right": 5, "right_before_left": 5}
        assert sum(counts.values()) == result[
            "recorded_completed_primary_pair_task_counts"
        ][contrast]


def test_failed_arm_removes_one_realized_exposure_and_precedence_not_attempt():
    source, receipt, log = _fixture()
    schedule = design.build_plan(source)["schedule"]
    row = next(
        row for row in schedule
        if row["arm_order"].index("D3") < row["arm_order"].index("D6")
    )
    event = next(
        event for event in log["events"]
        if event["task_id"] == row["task_id"] and event["variant"] == "D6"
    )
    event["status"] = "timeout"
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    slot = str(row["arm_order"].index("D6") + 1)
    attempted = result["recorded_attempted_position_counts_by_variant"]["D6"]
    completed = result["recorded_completed_position_counts_by_variant"]["D6"]
    assert attempted[slot] == completed[slot] + 1
    assert sum(attempted.values()) == 10
    assert sum(completed.values()) == 9
    assert result["recorded_completed_primary_pair_order_counts"]["D6_minus_D3"] == {
        "left_before_right": 5, "right_before_left": 4,
    }
    assert result["recorded_completed_primary_pair_order_counts"]["P6V_minus_P6"] == {
        "left_before_right": 5, "right_before_left": 5,
    }
    for contrast, counts in result[
        "recorded_completed_primary_pair_order_counts"
    ].items():
        assert sum(counts.values()) == result[
            "recorded_completed_primary_pair_task_counts"
        ][contrast]


def test_interruption_exposes_surviving_position_and_order_imbalance():
    source, receipt, log = _fixture()
    schedule = design.build_plan(source)["schedule"]
    _mark_unattempted_suffix(log, 5)
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    first_order = schedule[0]["arm_order"]
    second_first = schedule[1]["arm_order"][0]
    for arm in design.VARIANTS:
        expected = {str(position): int(first_order[position - 1] == arm)
                    for position in range(1, 5)}
        if second_first == arm:
            expected["1"] += 1
        assert result["recorded_attempted_position_counts_by_variant"][arm] == expected
        assert result["recorded_completed_position_counts_by_variant"][arm] == expected
    assert result["unattempted_cells"] == 35
    assert result["recorded_fully_completed_task_count"] == 1
    for contrast, (left, right) in {
        "D6_minus_D3": ("D6", "D3"),
        "P6_minus_D6": ("P6", "D6"),
        "P6V_minus_P6": ("P6V", "P6"),
    }.items():
        direction = (
            "left_before_right"
            if first_order.index(left) < first_order.index(right)
            else "right_before_left"
        )
        counts = result["recorded_completed_primary_pair_order_counts"][contrast]
        assert counts[direction] == 1
        assert sum(counts.values()) == 1


def test_missingness_cannot_be_hidden_by_aggregate_completed_count():
    source, receipt, log = _fixture()
    schedule = design.build_plan(source)["schedule"]
    # Different completed-cell patterns can share the same overall 38/40.
    # Realized pairwise precedence discloses *which* order was lost.
    first = schedule[0]
    second = schedule[1]
    for row in (first, second):
        event = next(
            event for event in log["events"]
            if event["task_id"] == row["task_id"]
            and event["variant"] == "P6"
        )
        event["status"] = "failed"
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert result["recorded_status_counts"]["completed"] == 38
    assert result["recorded_fully_completed_task_count"] == 8
    assert sum(result["recorded_completed_position_counts_by_variant"]["P6"].values()) == 8
    assert sum(result["recorded_attempted_position_counts_by_variant"]["P6"].values()) == 10
    for contrast, counts in result[
        "recorded_completed_primary_pair_order_counts"
    ].items():
        assert sum(counts.values()) == result[
            "recorded_completed_primary_pair_task_counts"
        ][contrast]


def test_full_prospective_run_exposes_planned_first_order_predecessors():
    source, receipt, log = _fixture()
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    expected = {
        arm: {prior: 0 for prior in design.VARIANTS if prior != arm}
        for arm in design.VARIANTS
    }
    for row in design.build_plan(source)["schedule"]:
        for prior, arm in zip(row["arm_order"], row["arm_order"][1:]):
            expected[arm][prior] += 1
    assert result["planned_immediate_predecessor_counts_by_variant"] == expected
    assert result["recorded_attempted_immediate_predecessor_counts_by_variant"] == expected
    assert result["recorded_completed_immediate_predecessor_counts_by_variant"] == expected
    assert result["recorded_completed_after_noncompleted_predecessor_counts_by_variant"] == {
        arm: 0 for arm in design.VARIANTS
    }
    assert sum(sum(row.values()) for row in expected.values()) == 30
    assert result["actual_execution_independently_authenticated"] is False


def test_predecessor_timeout_excludes_completed_pair_not_attempted_exposure():
    source, receipt, log = _fixture()
    first, successor = design.build_plan(source)["schedule"][0]["arm_order"][:2]
    log["events"][0]["status"] = "timeout"
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    planned = result["planned_immediate_predecessor_counts_by_variant"]
    attempted = result["recorded_attempted_immediate_predecessor_counts_by_variant"]
    completed = result["recorded_completed_immediate_predecessor_counts_by_variant"]
    assert attempted == planned
    assert completed[successor][first] == planned[successor][first] - 1
    assert sum(sum(row.values()) for row in completed.values()) == 29
    assert result["recorded_completed_after_noncompleted_predecessor_counts_by_variant"] == {
        arm: int(arm == successor) for arm in design.VARIANTS
    }
    assert result["recorded_status_counts"]["timeout"] == 1


def test_failed_successor_removes_both_completed_adjacent_pairs_without_erasing_attempt():
    source, receipt, log = _fixture()
    first, middle, third = design.build_plan(source)["schedule"][0]["arm_order"][:3]
    log["events"][1]["status"] = "failed"
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    planned = result["planned_immediate_predecessor_counts_by_variant"]
    assert result["recorded_attempted_immediate_predecessor_counts_by_variant"] == planned
    complete = result["recorded_completed_immediate_predecessor_counts_by_variant"]
    assert complete[middle][first] == planned[middle][first] - 1
    assert complete[third][middle] == planned[third][middle] - 1
    assert sum(sum(row.values()) for row in complete.values()) == 28
    assert result["recorded_completed_after_noncompleted_predecessor_counts_by_variant"][third] == 1


def test_interrupted_study_does_not_invent_unattempted_predecessor_exposure():
    source, receipt, log = _fixture()
    _mark_unattempted_suffix(log, 5)
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    row = design.build_plan(source)["schedule"][0]["arm_order"]
    expected = {
        arm: {prior: 0 for prior in design.VARIANTS if prior != arm}
        for arm in design.VARIANTS
    }
    for prior, arm in zip(row, row[1:]):
        expected[arm][prior] += 1
    assert sum(sum(v.values()) for v in expected.values()) == 3
    assert result["recorded_attempted_immediate_predecessor_counts_by_variant"] == expected
    assert result["recorded_completed_immediate_predecessor_counts_by_variant"] == expected
    assert sum(sum(v.values()) for v in result[
        "planned_immediate_predecessor_counts_by_variant"
    ].values()) == 30
    assert result["recorded_completed_after_noncompleted_predecessor_counts_by_variant"] == {
        arm: 0 for arm in design.VARIANTS
    }
    assert result["recorded_status_counts"]["not_started"] == 35


@pytest.mark.parametrize("contrast", (
    "D6_minus_D3", "P6_minus_D6", "P6V_minus_P6",
))
@pytest.mark.parametrize("left_first", (True, False))
def test_primary_contrast_direction_uses_named_subtraction_operands(
    contrast, left_first,
):
    """A non-balanced completed subset must preserve the operand orientation."""
    source, receipt, log = _fixture()
    left, right = contrast.split("_minus_")
    schedule = design.build_plan(source)["schedule"]
    selected = next(
        row for row in schedule
        if (row["arm_order"].index(left) < row["arm_order"].index(right))
        == left_first
    )
    # Remove all but one completed pair from this contrast.  The full 5:5
    # schedule would mask an accidental swap of left/right direction labels.
    for event in log["events"]:
        if event["task_id"] != selected["task_id"] and event["variant"] == left:
            event["status"] = "failed"
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    expected_direction = "left_before_right" if left_first else "right_before_left"
    other_direction = "right_before_left" if left_first else "left_before_right"
    counts = result["recorded_completed_primary_pair_order_counts"][contrast]
    assert counts == {expected_direction: 1, other_direction: 0}
    distance_us = (
        abs(selected["arm_order"].index(left) - selected["arm_order"].index(right))
        * 12_000_000
    )
    timing = result["recorded_completed_primary_pair_start_separation_us"][contrast]
    assert timing[expected_direction] == {
        "count": 1,
        "minimum_microseconds": distance_us,
        "maximum_microseconds": distance_us,
        "total_microseconds": distance_us,
    }
    assert timing[other_direction] == {
        "count": 0,
        "minimum_microseconds": None,
        "maximum_microseconds": None,
        "total_microseconds": 0,
    }


def test_complete_chronology_reports_exact_primary_pair_start_time_separation():
    source, receipt, log = _fixture()
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    separation = result["recorded_completed_primary_pair_start_separation_us"]
    for contrast, (left, right) in {
        "D6_minus_D3": ("D6", "D3"),
        "P6_minus_D6": ("P6", "D6"),
        "P6V_minus_P6": ("P6V", "P6"),
    }.items():
        expected = {"left_before_right": [], "right_before_left": []}
        for row in design.build_plan(source)["schedule"]:
            order = row["arm_order"]
            direction = (
                "left_before_right"
                if order.index(left) < order.index(right)
                else "right_before_left"
            )
            expected[direction].append(
                abs(order.index(right) - order.index(left)) * 12_000_000
            )
        for direction, values in expected.items():
            observed = separation[contrast][direction]
            assert observed == {
                "count": len(values),
                "minimum_microseconds": min(values),
                "maximum_microseconds": max(values),
                "total_microseconds": sum(values),
            }
        assert sum(v["count"] for v in separation[contrast].values()) == 10
    assert result["actual_execution_independently_authenticated"] is False


def test_large_gap_is_visible_without_changing_completed_pair_coverage():
    source, receipt, log = _fixture()
    baseline = audit.audit_execution_log(source, receipt, _bytes(log))
    from datetime import datetime
    for event in log["events"][1:]:
        for key in ("started_at_utc", "finished_at_utc"):
            stamp = datetime.fromisoformat(event[key].replace("Z", "+00:00"))
            event[key] = _utc(stamp + timedelta(hours=1))
    log["finished_at_utc"] = _utc(
        datetime.fromisoformat(log["finished_at_utc"].replace("Z", "+00:00"))
        + timedelta(hours=1)
    )
    altered = audit.audit_execution_log(source, receipt, _bytes(log))
    assert (altered["recorded_completed_primary_pair_task_counts"]
            == baseline["recorded_completed_primary_pair_task_counts"])
    first_arm = design.build_plan(source)["schedule"][0]["arm_order"][0]
    pairs = {
        "D6_minus_D3": {"D6", "D3"},
        "P6_minus_D6": {"P6", "D6"},
        "P6V_minus_P6": {"P6V", "P6"},
    }
    for contrast, arms in pairs.items():
        old = baseline["recorded_completed_primary_pair_start_separation_us"][contrast]
        new = altered["recorded_completed_primary_pair_start_separation_us"][contrast]
        old_total = sum(value["total_microseconds"] for value in old.values())
        new_total = sum(value["total_microseconds"] for value in new.values())
        assert new_total - old_total == (
            3_600_000_000 if first_arm in arms else 0
        )


def test_failed_primary_arm_excludes_its_timing_not_other_pairs():
    source, receipt, log = _fixture()
    baseline = audit.audit_execution_log(source, receipt, _bytes(log))
    first_d6 = next(event for event in log["events"] if event["variant"] == "D6")
    first_d6["status"] = "timeout"
    altered = audit.audit_execution_log(source, receipt, _bytes(log))
    for contrast in ("D6_minus_D3", "P6_minus_D6", "P6V_minus_P6"):
        lag = altered["recorded_completed_primary_pair_start_separation_us"][contrast]
        assert sum(value["count"] for value in lag.values()) == (
            altered["recorded_completed_primary_pair_task_counts"][contrast]
        )
        assert sum(value["count"] for value in lag.values()) == (
            10 if contrast == "P6V_minus_P6" else 9
        )
        if contrast == "P6V_minus_P6":
            assert lag == baseline[
                "recorded_completed_primary_pair_start_separation_us"
            ][contrast]


def test_no_completed_primary_pairs_yield_null_extrema_not_invented_zeros():
    source, receipt, log = _fixture()
    _mark_unattempted_suffix(log, 1)
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    for directions in result[
        "recorded_completed_primary_pair_start_separation_us"
    ].values():
        for metrics in directions.values():
            assert metrics == {
                "count": 0, "minimum_microseconds": None,
                "maximum_microseconds": None, "total_microseconds": 0,
            }


def test_fractional_start_times_retain_microsecond_precision():
    source, receipt, log = _fixture()
    baseline = audit.audit_execution_log(source, receipt, _bytes(log))
    first = log["events"][0]
    first["started_at_utc"] = first["started_at_utc"].replace(
        "Z", ".123456Z"
    )
    first["finished_at_utc"] = first["finished_at_utc"].replace(
        "Z", ".123456Z"
    )
    altered = audit.audit_execution_log(source, receipt, _bytes(log))
    first_arm = design.build_plan(source)["schedule"][0]["arm_order"][0]
    for contrast, arms in {
        "D6_minus_D3": {"D6", "D3"},
        "P6_minus_D6": {"P6", "D6"},
        "P6V_minus_P6": {"P6V", "P6"},
    }.items():
        old = baseline["recorded_completed_primary_pair_start_separation_us"][contrast]
        new = altered["recorded_completed_primary_pair_start_separation_us"][contrast]
        old_total = sum(value["total_microseconds"] for value in old.values())
        new_total = sum(value["total_microseconds"] for value in new.values())
        assert new_total - old_total == (-123456 if first_arm in arms else 0)


def test_full_recorded_chronology_exposes_cross_task_boundary_exposures():
    """Nine task-to-task boundaries are distinct from thirty within-task pairs."""
    source, receipt, log = _fixture()
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    schedule = design.build_plan(source)["schedule"]
    expected = {
        successor: {predecessor: 0 for predecessor in design.VARIANTS}
        for successor in design.VARIANTS
    }
    for left, right in zip(schedule, schedule[1:]):
        expected[right["arm_order"][0]][left["arm_order"][-1]] += 1
    for key in (
        "planned_cross_task_transition_counts_by_variant",
        "recorded_attempted_cross_task_transition_counts_by_variant",
        "recorded_completed_cross_task_transition_counts_by_variant",
    ):
        assert result[key] == expected
        assert sum(map(sum, (row.values() for row in result[key].values()))) == 9
    assert result[
        "recorded_completed_after_noncompleted_cross_task_predecessor_counts_by_variant"
    ] == {arm: 0 for arm in design.VARIANTS}
    assert result["recorded_attempted_cross_task_boundary_gap_us"] == {
        "count": 9,
        "minimum_microseconds": 1_000_000,
        "maximum_microseconds": 1_000_000,
        "total_microseconds": 9_000_000,
    }
    assert result["actual_execution_independently_authenticated"] is False


def test_interrupted_log_preserves_planned_but_not_attempted_cross_task_boundaries():
    source, receipt, log = _fixture()
    baseline = audit.audit_execution_log(source, receipt, _bytes(log))
    _mark_unattempted_suffix(log, 4)
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    assert (result["planned_cross_task_transition_counts_by_variant"]
            == baseline["planned_cross_task_transition_counts_by_variant"])
    for key in (
        "recorded_attempted_cross_task_transition_counts_by_variant",
        "recorded_completed_cross_task_transition_counts_by_variant",
    ):
        assert sum(sum(row.values()) for row in result[key].values()) == 0
    assert result["recorded_attempted_cross_task_boundary_gap_us"] == {
        "count": 0,
        "minimum_microseconds": None,
        "maximum_microseconds": None,
        "total_microseconds": 0,
    }
    assert result["all_recorded_cells_completed"] is False


def test_failed_boundary_predecessor_does_not_count_as_completed_cross_task_pair():
    source, receipt, log = _fixture()
    baseline = audit.audit_execution_log(source, receipt, _bytes(log))
    preceding_arm = log["events"][3]["variant"]
    successor_arm = log["events"][4]["variant"]
    log["events"][3]["status"] = "timeout"
    changed = audit.audit_execution_log(source, receipt, _bytes(log))
    key = "recorded_completed_cross_task_transition_counts_by_variant"
    assert (changed[key][successor_arm][preceding_arm]
            == baseline[key][successor_arm][preceding_arm] - 1)
    assert sum(sum(row.values()) for row in changed[key].values()) == 8
    assert sum(sum(row.values()) for row in changed[
        "recorded_attempted_cross_task_transition_counts_by_variant"
    ].values()) == 9
    assert changed[
        "recorded_completed_after_noncompleted_cross_task_predecessor_counts_by_variant"
    ][successor_arm] == 1
    assert (changed["recorded_attempted_cross_task_boundary_gap_us"]
            == baseline["recorded_attempted_cross_task_boundary_gap_us"])


def test_cross_task_boundary_gap_captures_a_long_pause_without_changing_coverage():
    source, receipt, log = _fixture()
    baseline = audit.audit_execution_log(source, receipt, _bytes(log))
    # Delay task two and all later tasks by exactly one hour: the pause
    # belongs only to the boundary between task one and task two.
    for event in log["events"][4:]:
        for key in ("started_at_utc", "finished_at_utc"):
            event[key] = _utc(
                datetime.fromisoformat(event[key].replace("Z", "+00:00"))
                + timedelta(hours=1)
            )
    log["finished_at_utc"] = _utc(
        datetime.fromisoformat(log["finished_at_utc"].replace("Z", "+00:00"))
        + timedelta(hours=1)
    )
    changed = audit.audit_execution_log(source, receipt, _bytes(log))
    assert (changed["recorded_completed_cross_task_transition_counts_by_variant"]
            == baseline["recorded_completed_cross_task_transition_counts_by_variant"])
    before = baseline["recorded_attempted_cross_task_boundary_gap_us"]
    after = changed["recorded_attempted_cross_task_boundary_gap_us"]
    assert before["count"] == after["count"] == 9
    assert after["total_microseconds"] - before["total_microseconds"] == 3_600_000_000
    assert after["maximum_microseconds"] == 3_601_000_000
    assert changed["scientific_outcomes_validated"] is False


@pytest.mark.parametrize("source_kind", ("task_manifest", "plan_receipt", "execution_log"))
def test_chronology_cli_rejects_hardlinked_input_at_each_boundary(
    source_kind, tmp_path, monkeypatch, capsys,
):
    # All three candidate file types use the shared descriptor-held reader.
    source, receipt, log = _fixture()
    paths = {
        "task_manifest": tmp_path / "tasks.json",
        "plan_receipt": tmp_path / "plan.json",
        "execution_log": tmp_path / "chronology.json",
    }
    for path, raw in zip(
        paths.values(), (source, receipt, _bytes(log)), strict=True
    ):
        path.write_bytes(raw)
    alias = tmp_path / "other_writable_path.json"
    alias.hardlink_to(paths[source_kind])
    monkeypatch.setattr(sys, "argv", [
        "verify_counterbalanced_replication_execution.py",
        "--task-manifest", str(paths["task_manifest"]),
        "--plan-file", str(paths["plan_receipt"]),
        "--execution-log", str(paths["execution_log"]),
    ])
    with pytest.raises(SystemExit) as exc:
        audit.main()
    assert exc.value.code == 2
    assert "exactly one filesystem link" in capsys.readouterr().err
    assert alias.exists()


def test_cross_task_pause_exposure_is_disaggregated_by_successor_arm():
    """Whole-study gap summaries can hide condition-specific time exposure."""
    source, receipt, log = _fixture()
    result = audit.audit_execution_log(source, receipt, _bytes(log))
    grouped = result["recorded_attempted_cross_task_boundary_gap_by_successor_us"]
    expected_counts = {arm: 0 for arm in design.VARIANTS}
    schedule = design.build_plan(source)["schedule"]
    for row in schedule[1:]:
        expected_counts[row["arm_order"][0]] += 1
    assert set(grouped) == set(design.VARIANTS)
    for arm in design.VARIANTS:
        count = expected_counts[arm]
        assert grouped[arm] == {
            "count": count,
            "minimum_microseconds": 1_000_000 if count else None,
            "maximum_microseconds": 1_000_000 if count else None,
            "total_microseconds": count * 1_000_000,
        }
    assert sum(item["count"] for item in grouped.values()) == 9
    assert sum(item["total_microseconds"] for item in grouped.values()) == (
        result["recorded_attempted_cross_task_boundary_gap_us"]["total_microseconds"]
    )
    assert result["actual_execution_independently_authenticated"] is False


def test_interrupted_study_does_not_invent_arm_specific_cross_task_pauses():
    source, receipt, log = _fixture()
    _mark_unattempted_suffix(log, 4)
    grouped = audit.audit_execution_log(source, receipt, _bytes(log))[
        "recorded_attempted_cross_task_boundary_gap_by_successor_us"
    ]
    for arm in design.VARIANTS:
        assert grouped[arm] == {
            "count": 0, "minimum_microseconds": None,
            "maximum_microseconds": None, "total_microseconds": 0,
        }


def test_long_cross_task_pause_is_attributed_to_the_actual_next_arm():
    source, receipt, log = _fixture()
    baseline = audit.audit_execution_log(source, receipt, _bytes(log))
    next_arm = design.build_plan(source)["schedule"][1]["arm_order"][0]
    # Delay all executions after the first task; just the first boundary
    # gains the additional hour, and no completed pair is reclassified.
    for event in log["events"][4:]:
        for clock in ("started_at_utc", "finished_at_utc"):
            event[clock] = _utc(
                datetime.fromisoformat(event[clock].replace("Z", "+00:00"))
                + timedelta(hours=1)
            )
    log["finished_at_utc"] = _utc(
        datetime.fromisoformat(log["finished_at_utc"].replace("Z", "+00:00"))
        + timedelta(hours=1)
    )
    changed = audit.audit_execution_log(source, receipt, _bytes(log))
    field = "recorded_attempted_cross_task_boundary_gap_by_successor_us"
    for arm in design.VARIANTS:
        old, new = baseline[field][arm], changed[field][arm]
        assert new["count"] == old["count"]
        assert new["total_microseconds"] - old["total_microseconds"] == (
            3_600_000_000 if arm == next_arm else 0
        )
        assert new["maximum_microseconds"] == (
            3_601_000_000 if arm == next_arm else old["maximum_microseconds"]
        )
    assert changed["recorded_completed_cross_task_transition_counts_by_variant"] == (
        baseline["recorded_completed_cross_task_transition_counts_by_variant"]
    )


def test_failed_boundary_predecessor_does_not_remove_recorded_pause():
    source, receipt, log = _fixture()
    baseline = audit.audit_execution_log(source, receipt, _bytes(log))
    log["events"][3]["status"] = "timeout"
    changed = audit.audit_execution_log(source, receipt, _bytes(log))
    field = "recorded_attempted_cross_task_boundary_gap_by_successor_us"
    assert changed[field] == baseline[field]
    assert changed["recorded_completed_cross_task_transition_counts_by_variant"] != (
        baseline["recorded_completed_cross_task_transition_counts_by_variant"]
    )
    assert changed["actual_execution_independently_authenticated"] is False
