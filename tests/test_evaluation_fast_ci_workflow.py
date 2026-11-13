"""Structural regression checks for the independent diagnostic-evaluation CI lane.

This verifies an offline, pinned, source-bound targeted test route exists even
when the much larger suite has not finished. Passing does not establish that
the full test suite, historical experiment or human validation has passed.
"""
from pathlib import Path

import yaml


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/diagnostic-evaluation-fast-ci.yml"
)
SCOPE = (
    "bash scripts/run_offline_pytest_firewalled.sh "
    "tests/test_evaluation.py tests/test_evaluation_fast_ci_workflow.py "
    '2>&1 | tee "$RUNNER_TEMP/vera-diagnostic-evaluation-tests.log"'
)


def _load_workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_fast_diagnostic_ci_uses_pinned_offline_scope_without_provider_calls():
    workflow = _load_workflow()
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["diagnostic-evaluation"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert int(job["timeout-minutes"]) <= 12

    steps = job["steps"]
    setup = next(s for s in steps if s.get("name") == "Pin Python interpreter")
    assert setup["with"]["python-version"] == "3.11.17"
    assert setup["with"]["pip-version"] == "26.2.1"
    checkout = next(
        s for s in steps if s.get("name") == "Checkout source without stored credentials"
    )
    assert checkout["with"]["persist-credentials"] == "false"

    test = next(
        s for s in steps if s.get("name") == "Run firewalled diagnostic evaluation regressions"
    )
    assert test["run"].strip().splitlines() == ["set -euo pipefail", SCOPE]
    assert "workflow_dispatch" in workflow["on"]
    for trigger in ("push", "pull_request"):
        paths = workflow["on"][trigger]["paths"]
        assert "logic/evaluation.py" in paths
        assert "tests/test_evaluation.py" in paths
        assert "tests/test_evaluation_fast_ci_workflow.py" in paths
        assert ".github/workflows/diagnostic-evaluation-fast-ci.yml" in paths


def test_fast_diagnostic_ci_fails_closed_and_replays_exact_commit_receipt():
    steps = _load_workflow()["jobs"]["diagnostic-evaluation"]["steps"]
    names = [step["name"] for step in steps]
    order = (
        "Verify pinned interpreter before targeted tests",
        "Verify source checkout before targeted tests",
        "Run firewalled diagnostic evaluation regressions",
        "Verify source checkout after targeted tests",
        "Verify pinned interpreter after targeted tests",
        "Bind exact-commit diagnostic test receipt",
        "Independently replay diagnostic receipt before retention",
        "Retain source-bound targeted diagnostic test evidence (90 days)",
    )
    assert [names.index(name) for name in order] == sorted(
        names.index(name) for name in order
    )
    receipt = steps[names.index("Bind exact-commit diagnostic test receipt")]
    replay = steps[names.index("Independently replay diagnostic receipt before retention")]
    assert "python -m scripts.verify_ci_test_evidence" in receipt["run"]
    assert "python -m scripts.verify_retained_ci_test_evidence" in replay["run"]
    assert '--checkout-sha "$GITHUB_SHA"' in replay["run"]
    assert '--run-id "$GITHUB_RUN_ID"' in replay["run"]
    assert '--event "$GITHUB_EVENT_NAME"' in replay["run"]

    upload = steps[names.index("Retain source-bound targeted diagnostic test evidence (90 days)")]
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == "90"
    assert "vera-diagnostic-evaluation-tests.log" in upload["with"]["path"]
    assert "vera-diagnostic-evaluation-test-receipt.json" in upload["with"]["path"]
