"""Assert that the independent runner lane executes the actual offline safety suite.

This test is itself selected by that lane. Passing CI cannot authenticate
historical reports or promote diagnostic, exploratory or human claims.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/main-study-runner-provenance-fast-ci.yml"
TARGETS = ('tests/test_main_study_runner_replication_gate.py','tests/test_main_study_runner_trace_completion.py','tests/test_main_study_task_file.py','tests/test_main_study_pricing_file.py','tests/test_main_study_trace_accounting.py','tests/test_main_study_runner_fast_ci_workflow.py','tests/test_planner_query_contract.py','tests/test_search_candidate_provenance.py',)
SOURCES = ('.github/workflows/main-study-runner-provenance-fast-ci.yml','.github/workflows/budget-main-study.yml','scripts/run_budget_main_study.py','logic/experiment.py','logic/planner_queries.py','logic/research_agent.py','logic/run.py','logic/search_provenance.py','scripts/validate_main_study_inputs.py',)


def _definition():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(steps, name):
    return next(step for step in steps if step["name"] == name)


def test_runner_lane_selects_all_runner_safety_modules():
    discovered = {
        str(p.relative_to(ROOT))
        for p in (ROOT / "tests").glob("test_main_study_runner_*.py")
    }
    assert discovered <= set(TARGETS)
    assert set(TARGETS) == {
        "tests/test_main_study_runner_replication_gate.py",
        "tests/test_main_study_runner_trace_completion.py",
        "tests/test_main_study_task_file.py",
        "tests/test_main_study_pricing_file.py",
        "tests/test_main_study_trace_accounting.py",
        "tests/test_main_study_runner_fast_ci_workflow.py",
        "tests/test_planner_query_contract.py",
        "tests/test_search_candidate_provenance.py",
    }


def test_runner_lane_is_read_only_firewalled_and_source_triggered():
    workflow = _definition()
    assert workflow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in workflow["on"]
    for event in ("push", "pull_request"):
        paths = set(workflow["on"][event]["paths"])
        assert set(SOURCES) <= paths
        assert set(TARGETS) <= paths
        assert {
            "requirements.txt", "requirements-ci.lock",
            "scripts/run_offline_pytest_firewalled.sh",
            "scripts/verify_ci_source_checkout.py",
            "scripts/verify_ci_test_evidence.py",
            "scripts/verify_retained_ci_test_evidence.py",
        } <= paths
    assert workflow["on"]["push"]["branches"] == ["research-*"]
    assert len(workflow["jobs"]) == 1
    job = workflow["jobs"]["noncanonical-runner-regressions"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert int(job["timeout-minutes"]) <= 12
    steps = job["steps"]
    assert _step(steps, "Checkout source without stored credentials")["with"]["persist-credentials"] == "false"
    setup = _step(steps, "Pin Python interpreter")["with"]
    assert setup["python-version"] == "3.11.17"
    assert setup["pip-version"] == "26.2.1"
    install = _step(steps, "Install constrained offline runner-test dependencies")["run"]
    assert "--no-deps" in install
    assert "--only-binary=:all:" in install
    assert "--constraint requirements-ci.lock" in install
    assert "--constraint requirements.txt" in install
    test = _step(steps, "Run firewalled noncanonical runner regressions")
    assert test["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert test["env"]["VERA_CI_PRIVATE_NETNS"] == "1"
    assert test["run"].strip().splitlines() == [
        "set -euo pipefail",
        "bash scripts/run_offline_pytest_firewalled.sh "
        + " ".join(TARGETS)
        + ' | tee "$RUNNER_TEMP/vera-runner-provenance-tests.log"',
    ]


def test_runner_lane_replays_exact_checkout_and_retains_receipts():
    steps = _definition()["jobs"]["noncanonical-runner-regressions"]["steps"]
    names = [step["name"] for step in steps]
    expected_order = (
        "Verify exact checkout before dependency-free diagnostic gate",
        "Run dependency-free diagnostic invariants before pip installation",
        "Independently replay dependency-free evidence before retention",
        "Install constrained offline runner-test dependencies",
        "Verify source checkout before targeted tests",
        "Run firewalled noncanonical runner regressions",
        "Verify source checkout after targeted tests",
        "Bind exact-commit runner test receipt",
        "Independently replay runner receipt before retention",
        "Retain source-bound targeted runner test evidence (90 days)",
    )
    assert [names.index(n) for n in expected_order] == sorted(names.index(n) for n in expected_order)
    bind = _step(steps, "Bind exact-commit runner test receipt")["run"]
    replay = _step(steps, "Independently replay runner receipt before retention")["run"]
    assert "python -m scripts.verify_ci_test_evidence" in bind
    assert "python -m scripts.verify_retained_ci_test_evidence" in replay
    for flag in (
        '--checkout-sha "$GITHUB_SHA"', '--run-id "$GITHUB_RUN_ID"',
        '--run-attempt "$GITHUB_RUN_ATTEMPT"', '--event "$GITHUB_EVENT_NAME"',
    ):
        assert flag in replay
    assert '--log "$RUNNER_TEMP/vera-runner-provenance-tests.log"' in bind
    assert '--log "$RUNNER_TEMP/vera-runner-provenance-tests.log"' in replay
    upload = _step(steps, "Retain source-bound targeted runner test evidence (90 days)")
    assert "vera-runner-provenance-tests.log" in upload["with"]["path"]
    assert "vera-runner-provenance-test-receipt.json" in upload["with"]["path"]
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == "90"
