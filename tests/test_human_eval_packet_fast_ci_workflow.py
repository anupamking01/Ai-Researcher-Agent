"""Contract tests for the independently executable blinded-packet CI lane.

This lane is narrower than full pytest and cannot authenticate historical
source reports, validate human annotations or certify scientific findings.
"""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/human-eval-packet-fast-ci.yml"
PACKET_SCRIPTS = (
    "scripts/build_human_eval_packet.py",
    "scripts/verify_human_eval_packet.py",
    "scripts/export_human_eval_annotator_bundle.py",
    "scripts/freeze_human_eval_ratings.py",
    "scripts/verify_human_eval_submission_preflight.py",
    "scripts/verify_human_eval_counterbalanced_handoff.py",
    "scripts/verify_human_eval_counterbalanced_submission_pair.py",
    "scripts/verify_human_eval_counterbalanced_freeze_link.py",
    "scripts/verify_human_eval_automated_run_lineage.py",
    "scripts/verify_human_eval_automated_handoff.py",
    "scripts/audit_human_eval_archive_readiness.py",
    "scripts/triage_historical_archive_candidates.py",
    "scripts/verify_historical_archive_triage_receipt.py",
    "scripts/preflight_recovered_artifact_zip.py",
    "scripts/audit_historical_artifact_job_logs.py",
    "scripts/verify_published_main_study_inputs.py",
    "scripts/validate_main_study_inputs.py",
    "scripts/validate_numeric_inputs.py",
    "scripts/verify_research_artifact_manifest.py",
    "scripts/fingerprint_research_artifacts.py",
    "scripts/verify_frozen_main_study_tasks.py",
)
PACKET_MODULES = (
    "tests/test_human_eval.py",
    "tests/test_human_eval_submission_preflight.py",
    "tests/test_human_eval_packet_capture_bounds.py",
    "tests/test_human_eval_packet_record_boundaries.py",
    "tests/test_human_eval_packet_source_numeric_integrity.py",
    "tests/test_human_eval_packet_verification.py",
    "tests/test_human_eval_packet_window_custody.py",
    "tests/test_human_eval_annotator_bundle_contract.py",
    "tests/test_human_eval_annotator_export_capture_bounds.py",
    "tests/test_human_eval_annotator_export.py",
    "tests/test_human_eval_counterbalanced_handoff.py",
    "tests/test_human_eval_counterbalanced_submission_pair.py",
    "tests/test_human_eval_counterbalanced_freeze_link.py",
    "tests/test_human_eval_automated_run_lineage.py",
    "tests/test_human_eval_automated_handoff.py",
    "tests/test_human_eval_archive_readiness.py",
    "tests/test_human_eval_expected_recovery_paths.py",
    "tests/test_historical_archive_candidate_triage.py",
    "tests/test_historical_archive_triage_receipt_replay.py",
    "tests/test_historical_archive_triage_receipt_schema_preflight.py",
    "tests/test_human_eval_packet_fast_ci_workflow.py",
)
SCOPE = (
    "bash scripts/run_offline_pytest_firewalled.sh "
    + " ".join(PACKET_MODULES)
    + ' 2>&1 | tee "$RUNNER_TEMP/vera-human-packet-tests.log"'
)


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_packet_lane_is_narrow_pinned_and_offline():
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in workflow["on"]
    job = workflow["jobs"]["packet-regressions"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert 0 < int(job["timeout-minutes"]) <= 12
    steps = job["steps"]
    checkout = next(s for s in steps if s["name"] == "Checkout source without credentials")
    assert checkout["with"]["persist-credentials"] == "false"
    setup = next(s for s in steps if s["name"] == "Pin offline Python interpreter")
    assert setup["with"]["python-version"] == "3.11.17"
    assert setup["with"]["pip-version"] == "26.2.1"
    install = next(s for s in steps if s["name"] == "Install pinned packet-test dependencies only")
    command = " ".join(install["run"].splitlines())
    for value in (
        "set -euo pipefail", "--no-deps", "--only-binary=:all:",
        "--retries 1 --timeout 15",
        "--constraint requirements-ci.lock --constraint requirements.txt",
        "pytest pluggy iniconfig packaging PyYAML markdown-it-py mdurl",
        "python -m pip check",
    ):
        assert value in command
    assert "-r requirements.txt" not in command
    compile_step = next(s for s in steps if s["name"] == "Compile packet implementation and regressions")
    for path in (*PACKET_SCRIPTS, *PACKET_MODULES, "tests/human_eval_test_support.py"):
        assert path in compile_step["run"]
    test = next(s for s in steps if s["name"] == "Run firewalled blinded-packet regressions")
    assert test["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert test["run"].strip().splitlines() == ["set -euo pipefail", SCOPE]
    for event in ("push", "pull_request"):
        paths = workflow["on"][event]["paths"]
        for required in (
            *PACKET_SCRIPTS,
            *PACKET_MODULES,
            "tests/human_eval_test_support.py",
            ".github/workflows/human-eval-packet-fast-ci.yml",
            "scripts/run_offline_pytest_firewalled.sh",
            "requirements.txt",
            "requirements-ci.lock",
        ):
            assert required in paths


def test_packet_lane_checks_source_and_replays_receipt_before_publication():
    steps = _workflow()["jobs"]["packet-regressions"]["steps"]
    names = [step["name"] for step in steps]
    ordered = (
        "Verify runtime and source before installing dependencies",
        "Install pinned packet-test dependencies only",
        "Verify source immediately before packet tests",
        "Run firewalled blinded-packet regressions",
        "Verify runtime and source after packet tests",
        "Bind exact-commit packet-test evidence",
        "Replay packet-test evidence before retention",
        "Retain source-bound packet regression evidence",
    )
    assert [names.index(name) for name in ordered] == sorted(names.index(name) for name in ordered)
    for name in (ordered[0], ordered[2], ordered[4]):
        assert '--checkout-sha "$GITHUB_SHA"' in steps[names.index(name)]["run"]
    receipt = steps[names.index(ordered[5])]["run"]
    replay = steps[names.index(ordered[6])]["run"]
    assert "python -m scripts.verify_ci_test_evidence" in receipt
    assert replay.splitlines()[0].strip() == "set -euo pipefail"
    assert "python -m scripts.verify_retained_ci_test_evidence" in replay
    for key, val in (
        ("--checkout-sha", "$GITHUB_SHA"), ("--run-id", "$GITHUB_RUN_ID"),
        ("--run-attempt", "$GITHUB_RUN_ATTEMPT"), ("--event", "$GITHUB_EVENT_NAME"),
    ):
        assert f'{key} "{val}"' in replay
    upload = steps[names.index(ordered[-1])]["with"]
    assert upload["if-no-files-found"] == "error"
    assert upload["retention-days"] == "90"
    assert "vera-human-packet-tests.log" in upload["path"]
    assert "vera-human-packet-test-receipt.json" in upload["path"]
