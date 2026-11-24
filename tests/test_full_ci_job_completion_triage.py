"""Synthetic offline CI job metadata; no GitHub, treatments or ratings."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.audit_full_ci_job_completion import audit_artifact_inventory, audit_jobs, audit_run_envelope, load_jobs_json, main

SHA = "a" * 40
RUN = 12345
ATTEMPT = 2
REPO = "example/vera"
RUN_URL = f"https://api.github.com/repos/{REPO}/actions/runs/{RUN}"

# Independent from implementation constants: tests fail if required step names
# are silently removed from the auditor.
SHARD_STEPS = (
    "Checkout repository",
    "Set up Python",
    "Verify pinned CI Python runtime before tests",
    "Verify pinned Python before dependency-free diagnostic gate",
    "Verify exact checkout before dependency-free diagnostic gate",
    "Run dependency-free diagnostic invariants before pip installation",
    "Verify exact checkout after dependency-free diagnostic gate",
    "Bind dependency-free test transcript to commit and run",
    "Independently replay dependency-free evidence before retention",
    "Retain pre-install diagnostic evidence (90 days)",
    "Install application and test dependencies",
    "Verify installed CI dependencies before tests",
    "Compile research code",
    "Verify exact source checkout before tests",
    "Run offline unit tests",
    "Verify exact source checkout after tests",
    "Verify installed CI dependencies after tests",
    "Verify pinned CI Python runtime after tests",
    "Bind exact-commit offline test evidence",
    "Replay exact-commit offline test evidence before upload",
    "Retain source-bound offline test evidence (90 days)",
)
REPLAY_STEPS = (
    "Checkout exact tested sources for full-set replay",
    "Set up pinned Python for full-set replay",
    "Verify Python and checkout before full-set replay",
    "Install exact pinned replay dependencies",
    "Verify pinned replay dependencies",
    "Download current-attempt shard evidence",
    "Stage exact-attempt shard directories",
    "Download exact-attempt pre-install diagnostic evidence",
    "Stage complete early diagnostic evidence set",
    "Independently replay all sixteen downloaded shard receipts",
    "Verify exact checkout after full-set replay",
    "Retain verified sixteen-shard replay (90 days)",
)


def _steps(labels, timestamp="2026-11-23T00:00:00Z"):
    return [
        {"name": label, "status": "completed", "conclusion": "success", "number": n,
         "started_at": timestamp, "completed_at": timestamp}
        for n, label in enumerate(labels, start=1)
    ]


def _inventory(shard_overrides=None, replay="success"):
    shard_overrides = shard_overrides or {}
    jobs = []
    for shard in range(16):
        conclusion = shard_overrides.get(shard, "success")
        jobs.append({
            "id": shard + 1,
            "run_id": RUN,
            "run_attempt": ATTEMPT,
            "head_sha": SHA,
            "workflow_name": "tests", "run_url": RUN_URL,
            "name": f"unit-tests ({shard})",
            "status": "completed" if conclusion else "in_progress",
            "conclusion": conclusion,
            "steps": _steps(SHARD_STEPS),
            "started_at": "2026-11-23T00:00:00Z",
            "completed_at": "2026-11-23T00:10:00Z",
        })
    jobs.append({
        "id": 17, "run_id": RUN, "run_attempt": ATTEMPT,
        "workflow_name": "tests", "run_url": RUN_URL,
        "head_sha": SHA, "name": "replay-complete-shard-set",
        "status": "completed" if replay else "in_progress",
        "conclusion": replay,
        "steps": _steps(REPLAY_STEPS, "2026-11-23T00:11:00Z"),
        "started_at": "2026-11-23T00:11:00Z",
        "completed_at": "2026-11-23T00:12:00Z",
    })
    return {"total_count": len(jobs), "jobs": jobs}


def _audit(payload):
    return audit_jobs(payload, run_id=RUN, run_attempt=ATTEMPT, commit=SHA)


def test_metadata_complete_does_not_claim_replay_artifact_verification():
    result = _audit(_inventory())
    assert result["full_job_gate_completed"] is True
    assert result["successful_shards"] == list(range(16))
    assert result["retained_evidence_verified_by_this_tool"] is False
    assert result["research_result_or_human_validation"] is False


def test_cancelled_shard_is_not_promoted_even_if_tests_finished_in_job_logs():
    result = _audit(_inventory({6: "cancelled", 13: "cancelled"}, "skipped"))
    assert result["full_job_gate_completed"] is False
    assert result["cancelled_shards"] == [6, 13]
    assert result["replay_job_conclusion"] == "skipped"
    assert 6 not in result["successful_shards"]


def test_successful_shards_without_replay_are_not_complete():
    assert _audit(_inventory(replay="skipped"))["full_job_gate_completed"] is False
    assert _audit(_inventory(replay=None))["full_job_gate_completed"] is False


def test_pending_and_failed_shards_remain_separate():
    result = _audit(_inventory({0: None, 5: "failure", 8: "timed_out"}, replay=None))
    assert result["pending_shards"] == [0]
    assert result["other_incomplete_shards"] == []
    assert result["failed_shards"] == [5, 8]
    assert result["full_job_gate_completed"] is False


@pytest.mark.parametrize("mutation,pattern", [
    (lambda p: p["jobs"][0].update(head_sha="b" * 40), "mixed run"),
    (lambda p: p["jobs"][0].update(run_attempt=1), "mixed run"),
    (lambda p: p["jobs"].append(dict(p["jobs"][0])), "total_count"),
    (lambda p: p.update(total_count=18), "total_count"),
    (lambda p: p["jobs"][0].update(name="unit-tests (17)"), "unexpected CI job"),
    (lambda p: p["jobs"].pop(), "total_count"),
    (lambda p: p["jobs"][0].update(conclusion="success", status="in_progress"), "unfinished job"),
])
def test_inconsistent_or_mixed_inventories_fail_closed(mutation, pattern):
    payload = _inventory()
    mutation(payload)
    with pytest.raises(ValueError, match=pattern):
        _audit(payload)


def test_missing_shard_classified_not_success():
    payload = _inventory(replay="skipped")
    payload["jobs"].pop(4)
    payload["total_count"] = len(payload["jobs"])
    result = _audit(payload)
    assert result["missing_shards"] == [4]
    assert result["full_job_gate_completed"] is False


def test_duplicate_job_name_rejected_even_with_distinct_job_ids():
    payload = _inventory()
    payload["jobs"][1]["name"] = payload["jobs"][0]["name"]
    with pytest.raises(ValueError, match="duplicate or malformed"):
        _audit(payload)


def test_loaded_job_json_rejects_duplicate_keys_and_nonfinite_numbers(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text('{"total_count":0,"total_count":1,"jobs":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate jobs JSON key"):
        load_jobs_json(path)
    path.write_text('{"total_count":NaN,"jobs":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="nonstandard JSON number"):
        load_jobs_json(path)



@pytest.mark.parametrize("nested", [
    '{"jobs":' + '[' * 40 + '0' + ']' * 40 + ',"total_count":0}',
    '{"jobs":' + '{"child":' * 40 + '0' + '}' * 40 + ',"total_count":0}',
])
def test_jobs_json_rejects_excessive_nesting_before_decoding(tmp_path, monkeypatch, nested):
    path = tmp_path / "jobs.json"
    path.write_text(nested, encoding="utf-8")

    def should_not_decode(*args, **kwargs):
        raise AssertionError("deep JSON must be rejected before json.loads")

    monkeypatch.setattr("scripts.audit_full_ci_job_completion.json.loads", should_not_decode)
    with pytest.raises(ValueError, match="nesting limit"):
        load_jobs_json(path)


def test_jobs_json_depth_scanner_ignores_brackets_in_escaped_strings(tmp_path):
    path = tmp_path / "jobs.json"
    payload = {
        "total_count": 0,
        "jobs": [],
        "note": ('[{"quoted": "[[]]"}]' * 80),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_jobs_json(path) == payload


@pytest.mark.parametrize("invalid", [
    '{"jobs":[]}}',
    '{"jobs":[],"total_count":0',
    '{"jobs":[],"note":"unfinished}',
])
def test_jobs_json_rejects_unbalanced_containers_or_strings(tmp_path, invalid):
    path = tmp_path / "jobs.json"
    path.write_text(invalid, encoding="utf-8")
    with pytest.raises(ValueError, match="container or string|unmatched closing"):
        load_jobs_json(path)


def _run_snapshot(status="completed", conclusion="success"):
    return {
        "id": RUN, "run_attempt": ATTEMPT, "head_sha": SHA,
        "name": "tests", "path": ".github/workflows/tests.yml",
        "url": RUN_URL, "repository": {"full_name": REPO},
        "event": "pull_request", "status": status, "conclusion": conclusion,
    }


def test_jobs_json_excessive_nesting_has_explicit_invalid_cli_exit(tmp_path, capsys):
    path = tmp_path / "deep.json"
    path.write_text('[' * 40 + '0' + ']' * 40, encoding="utf-8")
    run_path = tmp_path / "workflow-run.json"
    run_path.write_text(json.dumps(_run_snapshot()), encoding="utf-8")
    result = main([
        "--jobs-json", str(path), "--run-json", str(run_path),
        "--run-id", str(RUN),
        "--run-attempt", str(ATTEMPT),
        "--commit", SHA,
    ])
    assert result == 2
    assert "nesting limit" in capsys.readouterr().err


def test_cli_exit_codes_are_explicit(tmp_path, capsys):
    path = tmp_path / "jobs.json"
    run_path = tmp_path / "workflow-run.json"
    run_path.write_text(json.dumps(_run_snapshot()), encoding="utf-8")
    args = ["--jobs-json", str(path), "--run-json", str(run_path),
            "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--commit", SHA]
    path.write_text(json.dumps(_inventory()), encoding="utf-8")
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["full_job_gate_completed"] is True
    path.write_text(json.dumps(_inventory({6: "cancelled"}, "skipped")), encoding="utf-8")
    run_path.write_text(json.dumps(_run_snapshot(conclusion="cancelled")), encoding="utf-8")
    assert main(args) == 1
    assert json.loads(capsys.readouterr().out)["cancelled_shards"] == [6]

def test_successful_shard_cannot_omit_offline_pytest():
    payload = _inventory()
    payload["jobs"][3]["steps"] = [s for s in payload["jobs"][3]["steps"] if s["name"] != "Run offline unit tests"]
    with pytest.raises(ValueError, match="missing required successful step"):
        _audit(payload)


@pytest.mark.parametrize("step_name", [
    "Verify exact source checkout before tests",
    "Replay exact-commit offline test evidence before upload",
    "Retain source-bound offline test evidence (90 days)",
])
def test_successful_shard_must_not_skip_essential_evidence_step(step_name):
    payload = _inventory()
    step = next(s for s in payload["jobs"][6]["steps"] if s["name"] == step_name)
    step.update(status="completed", conclusion="skipped")
    with pytest.raises(ValueError, match="required step did not succeed"):
        _audit(payload)


def test_missing_successful_job_steps_inventory_is_invalid():
    payload = _inventory()
    del payload["jobs"][0]["steps"]
    with pytest.raises(ValueError, match="no steps inventory"):
        _audit(payload)


def test_duplicate_job_steps_fail_closed():
    payload = _inventory()
    payload["jobs"][0]["steps"].append(dict(payload["jobs"][0]["steps"][0]))
    with pytest.raises(ValueError, match="duplicate job step"):
        _audit(payload)


@pytest.mark.parametrize("step_name", [
    "Independently replay all sixteen downloaded shard receipts",
    "Retain verified sixteen-shard replay (90 days)",
])
def test_replay_job_success_requires_actual_replay_and_upload(step_name):
    payload = _inventory()
    step = next(s for s in payload["jobs"][-1]["steps"] if s["name"] == step_name)
    step.update(status="completed", conclusion="skipped")
    with pytest.raises(ValueError, match="required step did not succeed"):
        _audit(payload)


def test_cancelled_jobs_can_be_triaged_without_full_steps():
    payload = _inventory({9: "cancelled"}, replay="skipped")
    del payload["jobs"][9]["steps"]
    del payload["jobs"][-1]["steps"]
    result = _audit(payload)
    assert result["cancelled_shards"] == [9]
    assert result["full_job_gate_completed"] is False


def test_optional_failure_diagnostic_may_be_skipped():
    payload = _inventory()
    payload["jobs"][0]["steps"].append({
        "name": "Retain unverified diagnostics on CI failure or cancellation (90 days)",
        "status": "completed", "conclusion": "skipped", "number": 99
    })
    assert _audit(payload)["full_job_gate_completed"] is True

@pytest.mark.parametrize(
    "status,conclusion",
    [
        ("completed", "success"),
        ("completed", "failure"),
        ("completed", "cancelled"),
        ("in_progress", None),
    ],
)
def test_green_shard_rejects_executed_failure_only_diagnostics(status, conclusion):
    # The workflow uses failure() || cancelled() for this step.
    # It must not appear to execute within an otherwise successful shard.
    payload = _inventory()
    payload["jobs"][0]["steps"].append({
        "name": "Retain unverified diagnostics on CI failure or cancellation (90 days)",
        "status": status, "conclusion": conclusion, "number": 99,
    })
    with pytest.raises(ValueError, match="failure-only diagnostics must be skipped"):
        _audit(payload)


@pytest.mark.parametrize(
    "job_index,label",
    [
        (0, "Set up job"),
        (0, "Post Set up Python"),
        (0, "Complete job"),
        (-1, "Set up job"),
        (-1, "Post Set up pinned Python for full-set replay"),
        (-1, "Complete job"),
    ],
)
@pytest.mark.parametrize("status,conclusion", [
    ("completed", "skipped"),
    ("completed", "failure"),
    ("in_progress", None),
])
def test_green_job_rejects_incomplete_provider_housekeeping(
    job_index, label, status, conclusion
):
    payload = _inventory()
    payload["jobs"][job_index]["steps"].append({
        "name": label, "status": status, "conclusion": conclusion, "number": 99,
    })
    with pytest.raises(ValueError, match="provider housekeeping step did not succeed"):
        _audit(payload)


@pytest.mark.parametrize("job_index,first,second", [
    (0, "Run offline unit tests", "Bind exact-commit offline test evidence"),
    (5, "Replay exact-commit offline test evidence before upload",
        "Retain source-bound offline test evidence (90 days)"),
    (-1, "Independently replay all sixteen downloaded shard receipts",
        "Retain verified sixteen-shard replay (90 days)"),
])
def test_green_jobs_cannot_reorder_required_execution_gates(job_index, first, second):
    payload = _inventory()
    steps = payload["jobs"][job_index]["steps"]
    first_step = next(step for step in steps if step["name"] == first)
    second_step = next(step for step in steps if step["name"] == second)
    first_step["name"], second_step["name"] = second_step["name"], first_step["name"]
    with pytest.raises(ValueError, match="required evidence steps out of execution order"):
        _audit(payload)


@pytest.mark.parametrize("bad_number", [None, True, 0, -3, "2", 2.5])
def test_green_jobs_require_strictly_increasing_integer_step_numbers(bad_number):
    payload = _inventory()
    payload["jobs"][0]["steps"][1]["number"] = bad_number
    with pytest.raises(ValueError, match="malformed or out-of-order step number"):
        _audit(payload)


def test_green_replay_rejects_repeated_step_number():
    payload = _inventory()
    payload["jobs"][-1]["steps"][2]["number"] = 2
    with pytest.raises(ValueError, match="malformed or out-of-order step number"):
        _audit(payload)


def test_green_job_allows_provider_cleanup_step_number_gaps():
    payload = _inventory()
    payload["jobs"][0]["steps"].append({
        "name": "Post Checkout repository", "status": "completed",
        "conclusion": "success", "number": 45,
    })
    assert _audit(payload)["full_job_gate_completed"] is True



@pytest.mark.parametrize(
    ("job_index", "unreviewed_label"),
    [
        (0, "Execute unreviewed experiment runner"),
        (7, "Run offline unit tests (unreviewed retry)"),
        (-1, "Recompute historical evaluators"),
        (-1, "Post unexpected third-party action"),
    ],
)
def test_green_jobs_reject_unreviewed_extra_execution_steps(job_index, unreviewed_label):
    # A completely successful mandatory chain must not certify additional
    # user-controlled workflow steps that were never reviewed in tests.yml.
    payload = _inventory()
    steps = payload["jobs"][job_index]["steps"]
    steps.insert(1, {
        "name": unreviewed_label,
        "status": "completed",
        "conclusion": "success",
        "number": 0,
    })
    for number, step in enumerate(steps, start=1):
        step["number"] = number
    with pytest.raises(ValueError, match="unexpected successful-job step"):
        _audit(payload)


def test_known_provider_setup_and_post_steps_remain_acceptable():
    # These labels come from the real provider job-step metadata, rather
    # than from the workflow's user-defined steps.
    payload = _inventory()
    for index, post_steps in (
        (0, ("Post Set up Python", "Post Checkout repository")),
        (-1, ("Post Set up pinned Python for full-set replay",
              "Post Checkout exact tested sources for full-set replay")),
    ):
        steps = payload["jobs"][index]["steps"]
        names = ["Set up job", *(step["name"] for step in steps), *post_steps, "Complete job"]
        payload["jobs"][index]["steps"] = _steps(
            names, payload["jobs"][index]["started_at"]
        )
    assert _audit(payload)["full_job_gate_completed"] is True

def test_cancelled_job_still_classifiable_with_incomplete_step_numbers():
    payload = _inventory({4: "cancelled"}, replay="skipped")
    payload["jobs"][4]["steps"][0].pop("number")
    assert _audit(payload)["cancelled_shards"] == [4]


@pytest.mark.parametrize("step_name", [
    "Checkout repository",
    "Set up Python",
    "Verify pinned CI Python runtime before tests",
    "Verify pinned Python before dependency-free diagnostic gate",
    "Verify exact checkout after dependency-free diagnostic gate",
    "Install application and test dependencies",
    "Verify installed CI dependencies before tests",
    "Compile research code",
    "Verify installed CI dependencies after tests",
    "Verify pinned CI Python runtime after tests",
])
def test_successful_shard_rejects_skipped_execution_prerequisite(step_name):
    # Every unconditional step matters; a green pytest alone is insufficient.
    payload = _inventory()
    step = next(s for s in payload["jobs"][6]["steps"] if s["name"] == step_name)
    step.update(status="completed", conclusion="skipped")
    with pytest.raises(ValueError, match="required step did not succeed"):
        _audit(payload)


@pytest.mark.parametrize("step_name", [
    "Checkout exact tested sources for full-set replay",
    "Set up pinned Python for full-set replay",
    "Verify Python and checkout before full-set replay",
    "Install exact pinned replay dependencies",
    "Verify pinned replay dependencies",
    "Verify exact checkout after full-set replay",
])
def test_successful_replay_rejects_skipped_execution_prerequisite(step_name):
    payload = _inventory()
    step = next(s for s in payload["jobs"][-1]["steps"] if s["name"] == step_name)
    step.update(status="completed", conclusion="skipped")
    with pytest.raises(ValueError, match="required step did not succeed"):
        _audit(payload)


def test_successful_shard_cannot_omit_dependency_install_step():
    payload = _inventory()
    payload["jobs"][4]["steps"] = [s for s in payload["jobs"][4]["steps"]
                                   if s["name"] != "Install application and test dependencies"]
    with pytest.raises(ValueError, match="missing required successful step"):
        _audit(payload)


def test_successful_replay_cannot_omit_checkout_step():
    payload = _inventory()
    payload["jobs"][-1]["steps"] = [s for s in payload["jobs"][-1]["steps"]
                                   if s["name"] != "Checkout exact tested sources for full-set replay"]
    with pytest.raises(ValueError, match="missing required successful step"):
        _audit(payload)


@pytest.mark.parametrize(("job_index", "field", "value", "pattern"), [
    (0, "completed_at", None, "missing or malformed completed_at"),
    (-1, "started_at", "2026-11-23T00:11:00+00:00", "missing or malformed started_at"),
    (8, "started_at", "2026-02-30T00:00:00Z", "invalid started_at"),
    (3, "completed_at", "2026-11-22T23:59:00Z", "completed_at precedes started_at"),
    (-1, "completed_at", "2026-11-23T00:09:00Z", "completed_at precedes started_at"),
])
def test_green_ci_job_gate_rejects_invalid_provider_time_windows(
    job_index, field, value, pattern
):
    payload = _inventory()
    if value is None:
        payload["jobs"][job_index].pop(field)
    else:
        payload["jobs"][job_index][field] = value
    with pytest.raises(ValueError, match=pattern):
        _audit(payload)


def test_green_ci_job_gate_rejects_replay_before_last_shard_finishes():
    payload = _inventory()
    payload["jobs"][12]["completed_at"] = "2026-11-23T00:11:30Z"
    with pytest.raises(ValueError, match="replay started before all successful shards completed"):
        _audit(payload)


def test_green_ci_job_gate_allows_same_second_replay_after_last_shard():
    payload = _inventory()
    payload["jobs"][-1]["started_at"] = "2026-11-23T00:10:00Z"
    assert _audit(payload)["full_job_gate_completed"] is True


def test_incomplete_run_triage_needs_no_cross_job_timestamp_claim():
    payload = _inventory({8: "cancelled"}, replay="skipped")
    for job in payload["jobs"]:
        if job["conclusion"] != "success":
            job.pop("started_at")
            job.pop("completed_at")
    result = _audit(payload)
    assert result["cancelled_shards"] == [8]
    assert result["full_job_gate_completed"] is False


def test_green_ci_cli_rejects_replay_before_shards_as_invalid(tmp_path, capsys):
    payload = _inventory()
    payload["jobs"][-1]["started_at"] = "2026-11-23T00:09:59Z"
    path = tmp_path / "out-of-order-ci.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    run_path = tmp_path / "workflow-run.json"
    run_path.write_text(json.dumps(_run_snapshot()), encoding="utf-8")
    assert main([
        "--jobs-json", str(path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--commit", SHA,
    ]) == 2
    assert "replay started before" in capsys.readouterr().err


def test_matching_workflow_run_is_required_to_certify_all_green_jobs():
    result = audit_run_envelope(
        _run_snapshot(), _audit(_inventory()),
        run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
    )
    assert result["full_workflow_job_gate_completed"] is True
    assert result["retained_evidence_verified_by_this_tool"] is False


@pytest.mark.parametrize("status,conclusion", [
    ("completed", "cancelled"),
    ("completed", "failure"),
    ("completed", "timed_out"),
    ("in_progress", None),
])
def test_green_job_inventory_cannot_upgrade_non_successful_workflow(status, conclusion):
    result = audit_run_envelope(
        _run_snapshot(status, conclusion), _audit(_inventory()),
        run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
    )
    assert result["full_job_gate_completed"] is True
    assert result["full_workflow_job_gate_completed"] is False


@pytest.mark.parametrize("field,value,pattern", [
    ("id", RUN + 1, "mixed ID"),
    ("id", True, "mixed ID"),
    ("run_attempt", 1, "mixed ID"),
    ("head_sha", "b" * 40, "mixed ID"),
    ("name", "evaluator-recovery", "unexpected workflow identity"),
    ("path", ".github/workflows/evaluator-recovery.yml", "unexpected workflow identity"),
    ("event", "schedule", "unexpected workflow trigger"),
    ("status", "unknown", "unsupported workflow status"),
    ("conclusion", "unknown", "unsupported workflow conclusion"),
])
def test_run_envelope_rejects_mixed_or_unrelated_workflows(field, value, pattern):
    snapshot = _run_snapshot()
    snapshot[field] = value
    with pytest.raises(ValueError, match=pattern):
        audit_run_envelope(
            snapshot, _audit(_inventory()),
            run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
        )


@pytest.mark.parametrize("status,conclusion", [
    ("completed", None),
    ("in_progress", "success"),
])
def test_run_envelope_rejects_inconsistent_status_conclusion(status, conclusion):
    with pytest.raises(ValueError, match="inconsistent workflow"):
        audit_run_envelope(
            _run_snapshot(status, conclusion), _audit(_inventory()),
            run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
        )


def test_workflow_success_cannot_hide_failed_jobs():
    with pytest.raises(ValueError, match="contradicts incomplete job"):
        audit_run_envelope(
            _run_snapshot(), _audit(_inventory({7: "cancelled"}, replay="skipped")),
            run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
        )


def test_cancelled_run_and_cancelled_shard_are_valid_incomplete_triage():
    result = audit_run_envelope(
        _run_snapshot(conclusion="cancelled"),
        _audit(_inventory({7: "cancelled"}, replay="skipped")),
        run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
    )
    assert result["cancelled_shards"] == [7]
    assert result["full_workflow_job_gate_completed"] is False


def test_cli_does_not_claim_success_when_workflow_run_is_cancelled(tmp_path, capsys):
    jobs_path, run_path = tmp_path / "jobs.json", tmp_path / "run.json"
    jobs_path.write_text(json.dumps(_inventory()), encoding="utf-8")
    run_path.write_text(json.dumps(_run_snapshot(conclusion="cancelled")), encoding="utf-8")
    result = main([
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--commit", SHA,
    ])
    assert result == 1
    output = json.loads(capsys.readouterr().out)
    assert output["full_job_gate_completed"] is True
    assert output["full_workflow_job_gate_completed"] is False


def test_cli_rejects_duplicate_key_workflow_run_snapshot(tmp_path, capsys):
    jobs_path, run_path = tmp_path / "jobs.json", tmp_path / "run.json"
    jobs_path.write_text(json.dumps(_inventory()), encoding="utf-8")
    run_path.write_text('{"id":1,"id":2}', encoding="utf-8")
    result = main([
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--commit", SHA,
    ])
    assert result == 2
    assert "duplicate jobs JSON key" in capsys.readouterr().err


@pytest.mark.parametrize("job_index", [0, -1])
@pytest.mark.parametrize("mutation,pattern", [
    ({"started_at": None}, "missing or malformed started_at"),
    ({"completed_at": "2026-02-30T00:00:00Z"}, "invalid completed_at"),
    ({"started_at": "2026-11-22T23:59:00Z"}, "outside job time window"),
    ({"completed_at": "2026-11-24T00:00:00Z"}, "outside job time window"),
    ({"completed_at": "2026-11-22T23:59:00Z"}, "completed_at precedes started_at"),
])
def test_complete_gate_requires_valid_step_windows(job_index, mutation, pattern):
    payload = _inventory()
    payload["jobs"][job_index]["steps"][1].update(mutation)
    with pytest.raises(ValueError, match=pattern):
        _audit(payload)


@pytest.mark.parametrize("job_index,overlap_end", [
    (0, "2026-11-23T00:00:01Z"),
    (-1, "2026-11-23T00:11:01Z"),
])
def test_complete_gate_rejects_overlapping_required_steps(job_index, overlap_end):
    payload = _inventory()
    payload["jobs"][job_index]["steps"][0]["completed_at"] = overlap_end
    with pytest.raises(ValueError, match="overlaps previous required step"):
        _audit(payload)


def test_unsuccessful_jobs_do_not_require_step_timing():
    payload = _inventory({2: "cancelled"}, replay="skipped")
    for job in payload["jobs"]:
        if job["conclusion"] != "success":
            for step in job["steps"]:
                step.pop("started_at")
                step.pop("completed_at")
    assert _audit(payload)["cancelled_shards"] == [2]


@pytest.mark.parametrize("incomplete", [False, True])
def test_cli_binds_exact_metadata_snapshot_bytes(tmp_path, capsys, incomplete):
    jobs_path = tmp_path / "jobs.json"
    run_path = tmp_path / "run.json"
    jobs = _inventory({6: "cancelled"}, "skipped") if incomplete else _inventory()
    run = _run_snapshot(conclusion="cancelled" if incomplete else "success")
    args = [
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--commit", SHA,
    ]
    expected_exit = 1 if incomplete else 0

    def invoke(jobs_raw, run_raw):
        jobs_path.write_bytes(jobs_raw)
        run_path.write_bytes(run_raw)
        assert main(args) == expected_exit
        result = json.loads(capsys.readouterr().out)
        assert result["jobs_json_sha256"] == hashlib.sha256(jobs_raw).hexdigest()
        assert result["run_json_sha256"] == hashlib.sha256(run_raw).hexdigest()
        assert result["retained_evidence_verified_by_this_tool"] is False
        return result

    jobs_raw = json.dumps(jobs).encode("utf-8")
    run_raw = json.dumps(run).encode("utf-8")
    first = invoke(jobs_raw, run_raw)
    second = invoke(jobs_raw + b"\n", run_raw)
    third = invoke(jobs_raw, run_raw + b"\n")
    assert first["jobs_json_sha256"] != second["jobs_json_sha256"]
    assert first["run_json_sha256"] == second["run_json_sha256"]
    assert first["jobs_json_sha256"] == third["jobs_json_sha256"]
    assert first["run_json_sha256"] != third["run_json_sha256"]
    for result in (first, second, third):
        result.pop("jobs_json_sha256")
        result.pop("run_json_sha256")
    assert first == second == third


def test_cli_fingerprints_captured_jobs_even_if_path_changes_after_parsing(
    tmp_path, capsys, monkeypatch
):
    import scripts.audit_full_ci_job_completion as auditor

    jobs_path = tmp_path / "jobs.json"
    run_path = tmp_path / "run.json"
    original = json.dumps(_inventory()).encode("utf-8")
    replacement = json.dumps(_inventory({0: "cancelled"}, "skipped")).encode("utf-8")
    jobs_path.write_bytes(original)
    run_path.write_text(json.dumps(_run_snapshot()), encoding="utf-8")
    real_audit = auditor.audit_jobs

    def mutate_after_capture(payload, **kwargs):
        jobs_path.write_bytes(replacement)
        return real_audit(payload, **kwargs)

    monkeypatch.setattr(auditor, "audit_jobs", mutate_after_capture)
    assert main([
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--commit", SHA,
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert jobs_path.read_bytes() == replacement
    assert result["jobs_json_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["jobs_json_sha256"] != hashlib.sha256(replacement).hexdigest()
    assert result["full_workflow_job_gate_completed"] is True


@pytest.mark.parametrize("mutation,pattern", [
    ({"workflow_name": "other"}, "unexpected job workflow"),
    ({"run_url": RUN_URL + "0"}, "unexpected job workflow"),
    ({"run_url": RUN_URL + "?page=1"}, "unexpected job workflow"),
    ({"run_url": RUN_URL.replace(REPO, "other/vera")}, "mixed repository"),
    ({"run_id": float(RUN)}, "mixed run"),
    ({"run_attempt": float(ATTEMPT)}, "mixed run"),
])
def test_job_identity_contradictions_fail_closed_even_for_cancelled_job(mutation, pattern):
    payload = _inventory({3: "cancelled"}, replay="skipped")
    payload["jobs"][3].update(mutation)
    with pytest.raises(ValueError, match=pattern):
        _audit(payload)


def test_uniform_wrong_repository_jobs_cannot_certify_matching_numeric_run():
    payload = _inventory()
    for job in payload["jobs"]:
        job["run_url"] = RUN_URL.replace(REPO, "other/vera")
    with pytest.raises(ValueError, match="repository URLs disagree"):
        audit_run_envelope(
            _run_snapshot(), _audit(payload),
            run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
        )


@pytest.mark.parametrize("mutation,pattern", [
    ({"repository": None}, "invalid repository identity"),
    ({"repository": {"full_name": "other/vera"}}, "repository URLs disagree"),
    ({"url": RUN_URL + "0"}, "repository URLs disagree"),
])
def test_run_envelope_requires_consistent_repository_and_url(mutation, pattern):
    run = _run_snapshot()
    run.update(mutation)
    with pytest.raises(ValueError, match=pattern):
        audit_run_envelope(run, _audit(_inventory()), run_id=RUN, run_attempt=ATTEMPT, commit=SHA)


def test_cross_endpoint_audit_rejects_reused_job_audit_from_another_commit():
    audit = _audit(_inventory())
    audit["commit"] = "b" * 40
    with pytest.raises(ValueError, match="identities disagree"):
        audit_run_envelope(
            _run_snapshot(), audit, run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
        )


def test_valid_incomplete_receipt_preserves_repository_run_identity():
    audit = audit_run_envelope(
        _run_snapshot(conclusion="cancelled"), _audit(_inventory({3: "cancelled"}, "skipped")),
        run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
    )
    assert audit["jobs_run_url"] == RUN_URL
    assert audit["full_workflow_job_gate_completed"] is False


@pytest.mark.parametrize("scope,field", [
    ("jobs", "status"),
    ("jobs", "conclusion"),
    ("run", "event"),
    ("run", "status"),
    ("run", "conclusion"),
])
@pytest.mark.parametrize("value", [[], {}, True, 1])
def test_cli_rejects_nonstring_metadata_enums_without_traceback(
    tmp_path, capsys, scope, field, value
):
    jobs, run = _inventory(), _run_snapshot()
    target = jobs["jobs"][0] if scope == "jobs" else run
    target[field] = value
    jobs_path, run_path = tmp_path / "jobs.json", tmp_path / "run.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    run_path.write_text(json.dumps(run), encoding="utf-8")
    assert main([
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--commit", SHA,
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "CI job completion audit invalid:" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("scope", ["jobs", "run"])
def test_missing_conclusion_is_not_an_explicit_pending_verdict(scope):
    jobs = _inventory({0: None}, replay=None)
    run = _run_snapshot(status="in_progress", conclusion=None)
    assert audit_run_envelope(
        run, _audit(jobs), run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
    )["full_workflow_job_gate_completed"] is False
    target = jobs["jobs"][0] if scope == "jobs" else run
    target.pop("conclusion")
    with pytest.raises(ValueError, match="missing .* conclusion field"):
        audit_run_envelope(
            run, _audit(jobs), run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
        )


@pytest.mark.parametrize("label", ["unit-tests (00)", "unit-tests (01)", "unit-tests (000000)"])
def test_noncanonical_shard_labels_fail_closed_instead_of_aliasing_indices(label):
    jobs = _inventory()
    jobs["jobs"][int(label.removeprefix("unit-tests (").removesuffix(")"))]["name"] = label
    with pytest.raises(ValueError, match="unexpected CI job"):
        _audit(jobs)


@pytest.mark.parametrize("conclusion", ["cancelled", "failure", "timed_out"])
@pytest.mark.parametrize("pending", ["shard", "replay"])
def test_completed_workflow_rejects_unfinished_job_snapshot(conclusion, pending):
    jobs = _inventory({0: None} if pending == "shard" else {},
                      replay=None if pending == "replay" else "skipped")
    with pytest.raises(ValueError, match="completed workflow contradicts unfinished job"):
        audit_run_envelope(
            _run_snapshot(conclusion=conclusion), _audit(jobs),
            run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
        )


def test_pending_and_terminal_other_shards_are_distinct():
    jobs = _inventory({0: None, 1: "skipped", 2: "neutral"}, replay=None)
    result = audit_run_envelope(
        _run_snapshot(status="in_progress", conclusion=None), _audit(jobs),
        run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
    )
    assert result["pending_shards"] == [0]
    assert result["other_incomplete_shards"] == [1, 2]
    assert result["full_workflow_job_gate_completed"] is False


def test_completed_cancelled_run_can_have_missing_or_terminal_other_shards():
    jobs = _inventory({0: "skipped", 1: "neutral", 2: "cancelled"}, replay="skipped")
    jobs["jobs"].pop(3)
    jobs["total_count"] -= 1
    result = audit_run_envelope(
        _run_snapshot(conclusion="cancelled"), _audit(jobs),
        run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
    )
    assert result["pending_shards"] == []
    assert result["other_incomplete_shards"] == [0, 1]
    assert result["missing_shards"] == [3]
    assert result["full_workflow_job_gate_completed"] is False


def test_cli_stale_job_snapshot_emits_no_receipt(tmp_path, capsys):
    jobs_path, run_path = tmp_path / "jobs.json", tmp_path / "run.json"
    jobs_path.write_text(json.dumps(_inventory({0: None}, "skipped")), encoding="utf-8")
    run_path.write_text(json.dumps(_run_snapshot(conclusion="cancelled")), encoding="utf-8")
    assert main([
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--commit", SHA,
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "recapture both snapshots" in captured.err


@pytest.mark.parametrize("event", ["pull_request", "push", "workflow_dispatch"])
@pytest.mark.parametrize("incomplete", [False, True])
def test_metadata_receipt_preserves_head_identity_without_checkout_attestation(
    tmp_path, capsys, event, incomplete
):
    jobs_path, run_path = tmp_path / "jobs.json", tmp_path / "run.json"
    jobs = _inventory({6: "cancelled"}, "skipped") if incomplete else _inventory()
    run = _run_snapshot(conclusion="cancelled" if incomplete else "success")
    run["event"] = event
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    run_path.write_text(json.dumps(run), encoding="utf-8")
    args = ["--jobs-json", str(jobs_path), "--run-json", str(run_path),
            "--run-id", str(RUN), "--run-attempt", str(ATTEMPT)]
    assert main(args + ["--head-sha", SHA]) == (1 if incomplete else 0)
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["workflow_event"] == event
    assert receipt["workflow_head_sha"] == receipt["commit"] == SHA
    assert receipt["tested_checkout_sha_verified_by_this_tool"] is False
    assert main(args + ["--commit", SHA]) == (1 if incomplete else 0)
    assert json.loads(capsys.readouterr().out) == receipt


def test_pr_integration_checkout_cannot_be_substituted_for_rest_head(tmp_path, capsys):
    jobs_path, run_path = tmp_path / "jobs.json", tmp_path / "run.json"
    jobs_path.write_text(json.dumps(_inventory()), encoding="utf-8")
    run_path.write_text(json.dumps(_run_snapshot()), encoding="utf-8")
    integration_checkout = "b" * 40
    assert main([
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT),
        "--head-sha", integration_checkout,
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "workflow head SHA" in captured.err


def test_cross_endpoint_audit_rejects_conflicting_explicit_head_identity():
    audit = _audit(_inventory())
    audit["workflow_head_sha"] = "b" * 40
    with pytest.raises(ValueError, match="identities disagree"):
        audit_run_envelope(
            _run_snapshot(), audit, run_id=RUN, run_attempt=ATTEMPT, commit=SHA,
        )


def test_cli_rejects_ambiguous_head_arguments(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main([
            "--jobs-json", str(tmp_path / "jobs.json"),
            "--run-json", str(tmp_path / "run.json"),
            "--run-id", str(RUN), "--run-attempt", str(ATTEMPT),
            "--head-sha", SHA, "--commit", "b" * 40,
        ])
    assert exc.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("shard_conclusion", [
    None, "failure", "cancelled", "skipped", "timed_out", "action_required", "neutral",
])
def test_successful_replay_rejects_unsuccessful_dependency(shard_conclusion):
    with pytest.raises(ValueError, match="successful full-set replay contradicts"):
        _audit(_inventory({4: shard_conclusion}, replay="success"))


def test_successful_replay_rejects_missing_dependency():
    payload = _inventory()
    payload["jobs"].pop(4)
    payload["total_count"] -= 1
    with pytest.raises(ValueError, match="successful full-set replay contradicts"):
        _audit(payload)


def test_successful_replay_with_cancelled_dependency_emits_no_cli_receipt(tmp_path, capsys):
    jobs_path, run_path = tmp_path / "jobs.json", tmp_path / "run.json"
    jobs_path.write_text(json.dumps(_inventory({4: "cancelled"})), encoding="utf-8")
    run_path.write_text(json.dumps(_run_snapshot(conclusion="cancelled")), encoding="utf-8")
    assert main([
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--head-sha", SHA,
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "successful full-set replay contradicts" in captured.err


def test_cancelled_progress_distinguishes_test_cancellation_from_unreported_boundary():
    payload = _inventory({2: "cancelled", 0: "cancelled"}, replay="skipped")
    for shard, boundary, conclusion in (
        (2, "Run offline unit tests", "cancelled"),
        (0, "Compile research code", None),
    ):
        steps = payload["jobs"][shard]["steps"]
        index = SHARD_STEPS.index(boundary)
        steps[index].update(status="completed" if conclusion else "queued", conclusion=conclusion)
        for step in steps[index + 1:]:
            step.update(status="completed", conclusion="skipped")
        steps.append({"name": "Retain unverified diagnostics on CI failure or cancellation (90 days)",
                      "number": 99, "status": "completed", "conclusion": "success"})
    result = _audit(payload)
    assert result["full_job_gate_completed"] is False
    assert result["cancelled_shard_progress"] == [
        {"shard": 0, "step_inventory_usable": True,
         "last_contiguous_successful_step": "Verify installed CI dependencies before tests",
         "first_unconfirmed_step": "Compile research code",
         "first_unconfirmed_step_conclusion": None,
         "reported_cancelled_required_steps": []},
        {"shard": 2, "step_inventory_usable": True,
         "last_contiguous_successful_step": "Verify exact source checkout before tests",
         "first_unconfirmed_step": "Run offline unit tests",
         "first_unconfirmed_step_conclusion": "cancelled",
         "reported_cancelled_required_steps": ["Run offline unit tests"]},
    ]


def test_cancelled_progress_does_not_bridge_missing_required_step():
    payload = _inventory({5: "cancelled"}, replay="skipped")
    payload["jobs"][5]["steps"].pop(SHARD_STEPS.index("Run offline unit tests"))
    progress = _audit(payload)["cancelled_shard_progress"][0]
    assert progress["last_contiguous_successful_step"] == "Verify exact source checkout before tests"
    assert progress["first_unconfirmed_step"] == "Run offline unit tests"
    assert progress["first_unconfirmed_step_conclusion"] is None


def test_cancelled_progress_all_steps_reported_success_does_not_promote_job():
    result = _audit(_inventory({4: "cancelled"}, replay="skipped"))
    progress = result["cancelled_shard_progress"][0]
    assert progress["last_contiguous_successful_step"] == SHARD_STEPS[-1]
    assert progress["first_unconfirmed_step"] is None
    assert 4 not in result["successful_shards"]
    assert result["full_job_gate_completed"] is False


@pytest.mark.parametrize("mutation", [
    lambda job: job.pop("steps"),
    lambda job: job.update(steps=[]),
    lambda job: job["steps"].append(dict(job["steps"][0])),
    lambda job: job["steps"][0].pop("number"),
    lambda job: job["steps"][0].update(conclusion=[]),
    lambda job: job["steps"][0].update(status="completed", conclusion=None),
    lambda job: job["steps"][0].pop("conclusion"),
    lambda job: job["steps"][0].update(name=SHARD_STEPS[-1]) or job["steps"].pop(),
])
def test_unusable_cancelled_step_inventory_does_not_invent_progress(mutation):
    payload = _inventory({9: "cancelled"}, replay="skipped")
    mutation(payload["jobs"][9])
    result = _audit(payload)
    assert result["cancelled_shards"] == [9]
    assert result["cancelled_shard_progress"] == [
        {"shard": 9, "step_inventory_usable": False,
         "last_contiguous_successful_step": None, "first_unconfirmed_step": None,
         "first_unconfirmed_step_conclusion": None, "reported_cancelled_required_steps": []}
    ]
    assert result["full_job_gate_completed"] is False


def test_successful_inventory_has_no_cancelled_progress():
    assert _audit(_inventory())["cancelled_shard_progress"] == []


@pytest.mark.parametrize("mutation,pattern", [
    (lambda job: job.pop("started_at"), "missing or malformed started_at"),
    (lambda job: job.update(completed_at="2026-11-22T23:59:00Z"), "completed_at precedes started_at"),
    (lambda job: job["steps"][1].pop("completed_at"), "missing or malformed completed_at"),
    (lambda job: job["steps"][1].update(completed_at="2026-11-24T00:00:00Z"), "outside job time window"),
    (lambda job: job["steps"][0].update(completed_at="2026-11-23T00:00:01Z"), "overlaps previous required step"),
])
def test_partial_inventory_rejects_contradictory_successful_shard_timing(mutation, pattern):
    payload = _inventory({8: "cancelled"}, replay="skipped")
    mutation(payload["jobs"][3])
    with pytest.raises(ValueError, match=pattern):
        _audit(payload)


def test_partial_inventory_cli_does_not_issue_receipt_for_invalid_green_shard(tmp_path, capsys):
    jobs = _inventory({8: "cancelled"}, replay="skipped")
    jobs["jobs"][3]["steps"][0].pop("started_at")
    jobs_path = tmp_path / "jobs.json"
    run_path = tmp_path / "run.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    run_path.write_text(json.dumps(_run_snapshot(conclusion="cancelled")), encoding="utf-8")
    assert main([
        "--jobs-json", str(jobs_path), "--run-json", str(run_path),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--head-sha", SHA,
    ]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "missing or malformed started_at" in captured.err


@pytest.mark.parametrize("which", ["jobs", "run"])
@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_cli_rejects_nonregular_metadata_snapshot_without_receipt(tmp_path, capsys, monkeypatch, which, kind):
    jobs_path, run_path = tmp_path / "jobs.json", tmp_path / "run.json"
    jobs_path.write_text(json.dumps(_inventory()), encoding="utf-8")
    run_path.write_text(json.dumps(_run_snapshot()), encoding="utf-8")
    path = jobs_path if which == "jobs" else run_path
    target = tmp_path / "original.json"
    path.rename(target)
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(target)
    else:
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO creation unavailable")
        os.mkfifo(path)
    # Fail promptly even if a regression tries to open a blocking FIFO.
    original_path_open, original_os_open = Path.open, os.open

    def guard_path_open(self, *args, **kwargs):
        assert self != path, "nonregular snapshot opened before preflight"
        return original_path_open(self, *args, **kwargs)

    def guard_os_open(name, *args, **kwargs):
        assert Path(name) != path, "nonregular snapshot opened before preflight"
        return original_os_open(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", guard_path_open)
        patch.setattr(os, "open", guard_os_open)
        status = main([
            "--jobs-json", str(jobs_path), "--run-json", str(run_path),
            "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--head-sha", SHA,
        ])
    assert status == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "regular file" in captured.err


def test_metadata_open_detects_regular_file_replacement(tmp_path, monkeypatch):
    path = tmp_path / "jobs.json"
    path.write_text('{"jobs":[],"total_count":0}', encoding="utf-8")
    replacement = tmp_path / "other.json"
    replacement.write_text('{"jobs":[],"total_count":0}', encoding="utf-8")
    original_open = os.open

    def replace_then_open(name, flags, *args, **kwargs):
        replacement.replace(path)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr("scripts.audit_full_ci_job_completion.os.open", replace_then_open)
    with pytest.raises(ValueError, match="replaced before capture"):
        load_jobs_json(path)


@pytest.mark.skipif(not hasattr(os, "mkfifo") or not hasattr(os, "O_NONBLOCK"),
                    reason="nonblocking POSIX FIFO open unavailable")
def test_metadata_open_rejects_fifo_substituted_after_preflight(tmp_path, monkeypatch):
    path = tmp_path / "jobs.json"
    path.write_text('{"jobs":[],"total_count":0}', encoding="utf-8")
    original_open = os.open

    def replace_then_open(name, flags, *args, **kwargs):
        assert flags & os.O_NONBLOCK
        path.unlink()
        os.mkfifo(path)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr("scripts.audit_full_ci_job_completion.os.open", replace_then_open)
    with pytest.raises(ValueError, match="regular file"):
        load_jobs_json(path)


# Run-wide artifact metadata is separate from exact-attempt job metadata.
def _artifact_run():
    run = _run_snapshot()
    run["repository"]["id"] = 42
    return run


def _artifact(name, artifact_id, expired=False):
    return {
        "id": artifact_id, "name": name, "expired": expired,
        "workflow_run": {"id": RUN, "repository_id": 42, "head_sha": SHA},
    }


def _artifact_inventory():
    names = [
        f"vera-{kind}-shard-{shard}-{RUN}-{ATTEMPT}"
        for kind in ("stdlib-evaluation", "offline-tests") for shard in range(16)
    ] + [f"vera-full-shard-replay-{RUN}-{ATTEMPT}"]
    return {"total_count": len(names), "artifacts": [
        _artifact(name, i) for i, name in enumerate(names, 1)
    ]}


def test_artifact_inventory_complete_does_not_require_failure_diagnostics():
    result = audit_artifact_inventory(_artifact_inventory(), _artifact_run())
    assert result["full_artifact_inventory_listed_unexpired"] is True
    assert result["artifact_inventory"]["unverified_diagnostics"]["missing"] == list(range(16))


def test_artifact_inventory_distinguishes_expired_missing_and_previous_attempt():
    payload = _artifact_inventory()
    payload["artifacts"][16]["expired"] = True
    payload["artifacts"][17]["name"] = f"vera-offline-tests-shard-1-{RUN}-1"
    payload["artifacts"][-1]["name"] = f"vera-full-shard-replay-{RUN}-1"
    payload["artifacts"].append(_artifact(
        f"vera-unverified-failure-shard-1-{RUN}-{ATTEMPT}", 99
    ))
    payload["total_count"] += 1
    result = audit_artifact_inventory(payload, _artifact_run())
    assert result["artifact_inventory"]["offline_tests"]["listed_expired"] == [0]
    assert result["artifact_inventory"]["offline_tests"]["missing"] == [1]
    assert result["artifact_inventory"]["aggregate_replay"]["missing"] == ["replay"]
    assert result["artifact_inventory"]["unverified_diagnostics"]["listed_unexpired"] == [1]
    assert result["excluded_artifact_count"] == 2
    assert result["full_artifact_inventory_listed_unexpired"] is False


@pytest.mark.parametrize("mutation, message", [
    (lambda p: p.update(total_count=100), "paginated"),
    (lambda p: p["artifacts"][0].update(expired=0), "boolean"),
    (lambda p: p["artifacts"][0]["workflow_run"].update(id=999), "mixed workflow run"),
    (lambda p: p["artifacts"][0]["workflow_run"].update(repository_id=99), "mixed workflow run"),
    (lambda p: p["artifacts"][0]["workflow_run"].update(head_sha="b" * 40), "mixed workflow run"),
    (lambda p: p["artifacts"][1].update(id=p["artifacts"][0]["id"]), "duplicate artifact ID"),
    (lambda p: p["artifacts"][1].update(name=p["artifacts"][0]["name"]), "duplicate exact-attempt"),
])
def test_artifact_inventory_rejects_ambiguous_or_foreign_metadata(mutation, message):
    payload = _artifact_inventory()
    mutation(payload)
    with pytest.raises(ValueError, match=message):
        audit_artifact_inventory(payload, _artifact_run())


def test_optional_artifact_cli_gate_preserves_job_verdict_and_fingerprints(tmp_path, capsys):
    jobs = tmp_path / "jobs.json"
    run = tmp_path / "run.json"
    artifacts = tmp_path / "artifacts.json"
    jobs.write_text(json.dumps(_inventory()), encoding="utf-8")
    run.write_text(json.dumps(_artifact_run()), encoding="utf-8")
    payload = _artifact_inventory()
    args = [
        "--jobs-json", str(jobs), "--run-json", str(run), "--artifacts-json", str(artifacts),
        "--run-id", str(RUN), "--run-attempt", str(ATTEMPT), "--head-sha", SHA,
    ]
    artifacts.write_text(json.dumps(payload), encoding="utf-8")
    assert main(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["artifacts_json_sha256"] == hashlib.sha256(artifacts.read_bytes()).hexdigest()
    assert receipt["retained_evidence_verified_by_this_tool"] is False
    payload["artifacts"][-1]["expired"] = True
    artifacts.write_text(json.dumps(payload), encoding="utf-8")
    assert main(args) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["full_workflow_job_gate_completed"] is True
    assert receipt["full_artifact_inventory_listed_unexpired"] is False
    payload["total_count"] += 1
    artifacts.write_text(json.dumps(payload), encoding="utf-8")
    assert main(args) == 2
    assert not capsys.readouterr().out

def test_artifact_identity_handoff_is_stable_and_preserves_unknowns():
    payload = _artifact_inventory()
    first = payload["artifacts"][0]
    first.update(digest="sha256:" + "d" * 64, size_in_bytes=123, expired=True)
    # Equal provider digests are not duplicate artifact identities.
    payload["artifacts"][1].update(digest=first["digest"], size_in_bytes=123)
    payload["artifacts"][2].update(digest=None, size_in_bytes=None)
    payload["artifacts"][3]["name"] = f"vera-stdlib-evaluation-shard-3-{RUN}-1"
    result = audit_artifact_inventory(payload, _artifact_run())
    identities = result["listed_artifact_identities"]
    assert identities[0] == {
        "group": "early_diagnostics", "slot": 0, "name": first["name"],
        "artifact_id": first["id"], "expired": True,
        "provider_declared_digest": first["digest"],
        "provider_declared_size_in_bytes": 123,
    }
    assert identities[1]["artifact_id"] != identities[0]["artifact_id"]
    assert identities[1]["provider_declared_digest"] == first["digest"]
    assert identities[2]["provider_declared_digest"] is None
    assert identities[2]["provider_declared_size_in_bytes"] is None
    assert identities[3]["slot"] == 4
    assert identities[3]["provider_declared_digest"] is None
    assert identities[3]["provider_declared_size_in_bytes"] is None
    assert len(identities) == 32
    assert identities[-1]["group"] == "aggregate_replay"
    assert identities[-1]["slot"] == "replay"
    assert result["full_artifact_inventory_listed_unexpired"] is False
    payload["artifacts"].reverse()
    assert audit_artifact_inventory(payload, _artifact_run()) == result


@pytest.mark.parametrize("field, value", [
    ("digest", "d" * 64),
    ("digest", "sha256:" + "d" * 63),
    ("digest", "sha256:" + "g" * 64),
    ("digest", []),
    ("size_in_bytes", -1),
    ("size_in_bytes", True),
    ("size_in_bytes", "123"),
])
def test_artifact_identity_handoff_rejects_malformed_provider_fields(field, value):
    payload = _artifact_inventory()
    payload["artifacts"][0][field] = value
    with pytest.raises(ValueError, match="invalid provider artifact"):
        audit_artifact_inventory(payload, _artifact_run())
