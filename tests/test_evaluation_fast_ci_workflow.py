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


def test_fast_diagnostic_ci_bootstraps_only_pinned_minimal_dependencies():
    """Do not let unrelated transport packages or slow source builds block CI.

    This test protects the source-bound input specification and validates that
    the selected test dependencies are exact pins in the existing two locks.
    """
    root = WORKFLOW.parents[2]
    workflow = _load_workflow()
    steps = workflow["jobs"]["diagnostic-evaluation"]["steps"]
    setup = next(s for s in steps if s.get("name") == "Pin Python interpreter")
    assert setup["with"]["cache-dependency-path"].split() == [
        "requirements.txt", "requirements-ci.lock"
    ]

    install = next(
        s for s in steps
        if s.get("name") == "Install only pinned offline diagnostic-test dependencies"
    )
    script = install["run"]
    command = " ".join(script.splitlines())
    assert "set -euo pipefail" in script
    assert "--no-deps" in command
    assert "--only-binary=:all:" in command
    assert "--retries 1 --timeout 15" in command
    assert "--constraint requirements-ci.lock --constraint requirements.txt" in command
    assert "pytest pluggy iniconfig packaging PyYAML" in command
    assert "python -m pip check" in command
    assert "-r requirements-ci.lock" not in command

    ci_lock = (root / "requirements-ci.lock").read_text(encoding="utf-8")
    app_lock = (root / "requirements.txt").read_text(encoding="utf-8")
    for entry in ("pytest==8.3.2", "pluggy==1.7.0", "iniconfig==2.3.1"):
        assert entry in ci_lock.splitlines()
    for entry in ("packaging==24.0", "PyYAML==6.0.1"):
        assert entry in app_lock.splitlines()

    run = next(
        s for s in steps
        if s.get("name") == "Run firewalled diagnostic evaluation regressions"
    )
    assert run["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
