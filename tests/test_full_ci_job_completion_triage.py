"""Synthetic offline CI job metadata; no GitHub, treatments or ratings."""
import json

import pytest

from scripts.audit_full_ci_job_completion import audit_jobs, audit_run_envelope, load_jobs_json, main

SHA = "a" * 40
RUN = 12345
ATTEMPT = 2

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


def _steps(labels):
    return [
        {"name": label, "status": "completed", "conclusion": "success", "number": n}
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
            "name": f"unit-tests ({shard})",
            "status": "completed" if conclusion else "in_progress",
            "conclusion": conclusion,
            "steps": _steps(SHARD_STEPS),
            "started_at": "2026-11-23T00:00:00Z",
            "completed_at": "2026-11-23T00:10:00Z",
        })
    jobs.append({
        "id": 17, "run_id": RUN, "run_attempt": ATTEMPT,
        "head_sha": SHA, "name": "replay-complete-shard-set",
        "status": "completed" if replay else "in_progress",
        "conclusion": replay,
        "steps": _steps(REPLAY_STEPS),
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
    assert result["other_incomplete_shards"] == [0]
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
    payload = _inventory()
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
        payload["jobs"][index]["steps"] = _steps(names)
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
