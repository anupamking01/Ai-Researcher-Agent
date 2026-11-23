"""Synthetic offline CI job metadata; no GitHub, treatments or ratings."""
import json

import pytest

from scripts.audit_full_ci_job_completion import audit_jobs, load_jobs_json, main

SHA = "a" * 40
RUN = 12345
ATTEMPT = 2

# Independent from implementation constants: tests fail if required step names
# are silently removed from the auditor.
SHARD_STEPS = (
    "Verify exact checkout before dependency-free diagnostic gate",
    "Run dependency-free diagnostic invariants before pip installation",
    "Bind dependency-free test transcript to commit and run",
    "Independently replay dependency-free evidence before retention",
    "Retain pre-install diagnostic evidence (90 days)",
    "Verify exact source checkout before tests",
    "Run offline unit tests",
    "Verify exact source checkout after tests",
    "Bind exact-commit offline test evidence",
    "Replay exact-commit offline test evidence before upload",
    "Retain source-bound offline test evidence (90 days)",
)
REPLAY_STEPS = (
    "Download current-attempt shard evidence",
    "Stage exact-attempt shard directories",
    "Download exact-attempt pre-install diagnostic evidence",
    "Stage complete early diagnostic evidence set",
    "Independently replay all sixteen downloaded shard receipts",
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
        })
    jobs.append({
        "id": 17, "run_id": RUN, "run_attempt": ATTEMPT,
        "head_sha": SHA, "name": "replay-complete-shard-set",
        "status": "completed" if replay else "in_progress",
        "conclusion": replay,
        "steps": _steps(REPLAY_STEPS),
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


def test_cli_exit_codes_are_explicit(tmp_path, capsys):
    path = tmp_path / "jobs.json"
    args = ["--jobs-json", str(path), "--run-id", str(RUN),
            "--run-attempt", str(ATTEMPT), "--commit", SHA]
    path.write_text(json.dumps(_inventory()), encoding="utf-8")
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["full_job_gate_completed"] is True
    path.write_text(json.dumps(_inventory({6: "cancelled"}, "skipped")), encoding="utf-8")
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
