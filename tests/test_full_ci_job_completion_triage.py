"""Synthetic offline CI job metadata; no GitHub, treatments or ratings."""
import json

import pytest

from scripts.audit_full_ci_job_completion import audit_jobs, load_jobs_json, main

SHA = "a" * 40
RUN = 12345
ATTEMPT = 2


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
        })
    jobs.append({
        "id": 17, "run_id": RUN, "run_attempt": ATTEMPT,
        "head_sha": SHA, "name": "replay-complete-shard-set",
        "status": "completed" if replay else "in_progress",
        "conclusion": replay,
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
