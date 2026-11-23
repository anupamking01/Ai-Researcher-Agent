"""Keep offline CI completion triage independently testable and source-bound.

A passing fast lane tests metadata classification only. It cannot certify
a cancelled sixteen-shard run, historical treatment custody, or human ratings.
"""
from pathlib import Path

import yaml

from scripts.audit_full_ci_job_completion import (
    REQUIRED_REPLAY_STEPS,
    REQUIRED_SHARD_STEPS,
)

ROOT = Path(__file__).resolve().parents[1]
FAST = ".github/workflows/full-ci-job-completion-fast-ci.yml"
FULL = ".github/workflows/tests.yml"
TESTS = (
    "tests/test_full_ci_job_completion_triage.py",
    "tests/test_full_ci_completion_fast_ci_workflow.py",
)
AUDITOR = "scripts/audit_full_ci_job_completion.py"


def _load(path):
    return yaml.load((ROOT / path).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(steps, name):
    matches = [step for step in steps if step["name"] == name]
    assert len(matches) == 1, f"expected one CI step named {name!r}"
    return matches[0]


def test_completion_auditor_fast_lane_is_pinned_offline_and_source_triggered():
    flow = _load(FAST)
    assert flow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in flow["on"]
    for event in ("push", "pull_request"):
        paths = set(flow["on"][event]["paths"])
        assert {FAST, FULL, AUDITOR, *TESTS,
                "scripts/run_offline_pytest_firewalled.sh",
                "scripts/verify_ci_source_checkout.py",
                "scripts/verify_ci_test_evidence.py",
                "scripts/verify_retained_ci_test_evidence.py",
                "requirements.txt", "requirements-ci.lock"} <= paths
    assert flow["on"]["push"]["branches"] == ["research-*"]
    assert set(flow["jobs"]) == {"completion-auditor-regressions"}
    job = flow["jobs"]["completion-auditor-regressions"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert int(job["timeout-minutes"]) <= 12
    steps = job["steps"]
    assert _step(steps, "Checkout source without credentials")["with"]["persist-credentials"] == "false"
    assert _step(steps, "Pin Python interpreter")["with"]["python-version"] == "3.11.17"
    install = _step(steps, "Install pinned, offline test dependencies only")["run"]
    for token in ("--no-deps", "--only-binary=:all:", "--constraint requirements-ci.lock",
                  "--constraint requirements.txt"):
        assert token in install
    run = _step(steps, "Run firewalled completion-auditor regressions")
    assert run["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert run["run"].strip().splitlines() == [
        "set -euo pipefail",
        "bash scripts/run_offline_pytest_firewalled.sh "
        + " ".join(TESTS)
        + ' 2>&1 | tee "$RUNNER_TEMP/vera-ci-completion-tests.log"',
    ]


def test_completion_fast_lane_binds_and_replays_exact_commit_evidence():
    steps = _load(FAST)["jobs"]["completion-auditor-regressions"]["steps"]
    names = [step["name"] for step in steps]
    assert len(names) == len(set(names))
    required = (
        "Verify runtime and exact checkout before dependencies",
        "Install pinned, offline test dependencies only",
        "Verify exact checkout before targeted tests",
        "Run firewalled completion-auditor regressions",
        "Verify runtime and checkout after targeted tests",
        "Bind exact-commit completion-auditor receipt",
        "Replay completion-auditor receipt before retention",
        "Retain source-bound completion-auditor evidence (90 days)",
    )
    assert [names.index(s) for s in required] == sorted(names.index(s) for s in required)
    bind = _step(steps, "Bind exact-commit completion-auditor receipt")["run"]
    replay = _step(steps, "Replay completion-auditor receipt before retention")["run"]
    assert "python -m scripts.verify_ci_test_evidence" in bind
    assert "python -m scripts.verify_retained_ci_test_evidence" in replay
    for flag in ('--checkout-sha "$GITHUB_SHA"', '--run-id "$GITHUB_RUN_ID"',
                 '--run-attempt "$GITHUB_RUN_ATTEMPT"', '--event "$GITHUB_EVENT_NAME"'):
        assert flag in replay
    assert 'vera-ci-completion-tests.log' in bind and 'vera-ci-completion-tests.log' in replay
    upload = _step(steps, "Retain source-bound completion-auditor evidence (90 days)")["with"]
    assert "vera-ci-completion-test-receipt.json" in upload["path"]
    assert upload["if-no-files-found"] == "error"
    assert upload["retention-days"] == "90"


def test_completion_auditor_essential_step_labels_match_actual_full_ci_contract():
    """Prevent a green metadata auditor when full CI silently renames a gate."""
    jobs = _load(FULL)["jobs"]
    assert jobs["unit-tests"]["strategy"]["fail-fast"] == "false"
    assert jobs["replay-complete-shard-set"]["needs"] == "unit-tests"
    unit_steps = jobs["unit-tests"]["steps"]
    replay_steps = jobs["replay-complete-shard-set"]["steps"]
    for steps, required in ((unit_steps, REQUIRED_SHARD_STEPS),
                            (replay_steps, REQUIRED_REPLAY_STEPS)):
        names = [step["name"] for step in steps]
        assert len(names) == len(set(names))
        assert required <= set(names)
    assert "scripts/run_offline_pytest_firewalled.sh" in _step(
        unit_steps, "Run offline unit tests"
    )["run"]
    assert "scripts.verify_retained_ci_test_evidence" in _step(
        unit_steps, "Replay exact-commit offline test evidence before upload"
    )["run"]
    assert "scripts.verify_full_ci_shard_set" in _step(
        replay_steps, "Independently replay all sixteen downloaded shard receipts"
    )["run"]
    for steps, label in (
        (unit_steps, "Retain source-bound offline test evidence (90 days)"),
        (replay_steps, "Retain verified sixteen-shard replay (90 days)"),
    ):
        upload = _step(steps, label)
        assert upload["uses"].startswith("actions/upload-artifact@")
        assert upload["with"]["if-no-files-found"] == "error"
