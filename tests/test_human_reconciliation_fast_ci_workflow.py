"""Contract tests for the synthetic-only offline reconciliation CI lane.

Passing regressions do not constitute genuine human-validation evidence.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/human-reconciliation-fast-ci.yml"
IMPLEMENTATION = [
    "scripts/verify_human_reconciliation_readiness.py",
        "scripts/reconcile_human_automated.py",
        "scripts/verify_human_reconciliation_outputs.py",
        "scripts/verify_human_eval_analysis_outputs.py",
        "scripts/human_eval_analysis_core.py",
        "scripts/analyze_main_study.py",
        "scripts/verify_analysis_provenance.py",
        "scripts/verify_main_study_execution.py",
        "scripts/verify_main_study_outputs.py",
        "scripts/build_analysis_provenance.py"
]
TESTS = [
    "tests/test_human_reconciliation_readiness.py",
        "tests/test_human_reconciliation_readiness_file_identity.py",
        "tests/test_human_reconciliation_readiness_input_bounds.py",
        "tests/test_human_reconciliation_readiness_json_numbers.py",
        "tests/test_human_reconciliation_readiness_json_structure_bounds.py",
        "tests/test_human_reconciliation_legacy_source_binding.py",
        "tests/test_human_reconciliation_execution.py",
        "tests/test_human_reconciliation_artifact_size_contract.py",
        "tests/test_human_reconciliation_output_verification.py",
        "tests/test_human_reconciliation_fast_ci_workflow.py"
]
OTHER_TRIGGERS = [
    "tests/human_eval_test_support.py",
        "paper/HUMAN_RECONCILIATION_FREEZE.md",
        "paper/HUMAN_EVAL_ANALYSIS_PLAN.md",
        "paper/HUMAN_EVAL_PROTOCOL.md",
        "scripts/run_offline_pytest_firewalled.sh",
        "scripts/verify_ci_python_runtime.py",
        "scripts/verify_ci_source_checkout.py",
        "scripts/verify_ci_test_evidence.py",
        "scripts/verify_retained_ci_test_evidence.py",
        "requirements.txt",
        "requirements-ci.lock",
        ".python-version"
]
LOG = "vera-human-reconciliation-tests.log"
RECEIPT = "vera-human-reconciliation-test-receipt.json"


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_reconciliation_lane_covers_readiness_producer_and_independent_verifier():
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in wf["on"]
    job = wf["jobs"]["reconciliation-regressions"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert 0 < int(job["timeout-minutes"]) <= 15
    steps = job["steps"]
    checkout = next(s for s in steps if s["name"] == "Checkout source without credentials")
    assert checkout["uses"].startswith("actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803")
    assert checkout["with"]["persist-credentials"] == "false"
    setup = next(s for s in steps if s["name"] == "Pin offline Python interpreter")
    assert setup["uses"].startswith("actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1")
    assert setup["with"]["python-version"] == "3.11.17"
    assert setup["with"]["pip-version"] == "26.2.1"
    install = next(s for s in steps if s["name"] == "Install pinned reconciliation-test dependencies only")
    for value in ("set -euo pipefail", "--no-deps", "--only-binary=:all:",
                  "--retries 1 --timeout 15",
                  "--constraint requirements-ci.lock --constraint requirements.txt",
                  "pytest pluggy iniconfig packaging PyYAML markdown-it-py mdurl",
                  "python -m pip check"):
        assert value in install["run"]
    assert "-r requirements.txt" not in install["run"]

    compiled = next(s for s in steps if s["name"] == "Compile reconciliation implementation and regressions")
    for path in (*IMPLEMENTATION, *TESTS):
        assert path in compiled["run"]

    command = next(s for s in steps if s["name"] == "Run firewalled reconciliation regressions")
    assert command["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert command["run"].strip().splitlines() == [
        "set -euo pipefail",
        'bash scripts/run_offline_pytest_firewalled.sh '
        + " ".join(TESTS)
        + ' 2>&1 | tee "$RUNNER_TEMP/' + LOG + '"',
    ]
    assert len(TESTS) == len(set(TESTS))
    assert set(TESTS) & {"tests/test_human_reconciliation_execution.py", "tests/test_human_reconciliation_readiness.py", "tests/test_human_reconciliation_output_verification.py"} == {
        "tests/test_human_reconciliation_execution.py",
        "tests/test_human_reconciliation_readiness.py",
        "tests/test_human_reconciliation_output_verification.py",
    }
    for event in ("push", "pull_request"):
        paths = wf["on"][event]["paths"]
        for path in (str(WORKFLOW.relative_to(ROOT)), *IMPLEMENTATION, *TESTS, *OTHER_TRIGGERS):
            assert paths.count(path) == 1


def test_reconciliation_lane_binds_retained_evidence_to_exact_checkout():
    steps = _workflow()["jobs"]["reconciliation-regressions"]["steps"]
    names = [step["name"] for step in steps]
    order = [
        "Verify runtime and source before installing dependencies",
        "Install pinned reconciliation-test dependencies only",
        "Verify source immediately before reconciliation tests",
        "Run firewalled reconciliation regressions",
        "Verify runtime and source after reconciliation tests",
        "Bind exact-commit reconciliation-test evidence",
        "Replay reconciliation-test evidence before retention",
        "Retain source-bound reconciliation regression evidence",
    ]
    assert [names.index(n) for n in order] == sorted(names.index(n) for n in order)
    for name in (order[0], order[2], order[4]):
        assert '--checkout-sha "$GITHUB_SHA"' in steps[names.index(name)]["run"]
    bind = steps[names.index(order[5])]["run"]
    replay = steps[names.index(order[6])]["run"]
    assert "python -m scripts.verify_ci_test_evidence" in bind
    assert LOG in bind and RECEIPT in bind
    assert replay.strip().splitlines()[0] == "set -euo pipefail"
    assert "python -m scripts.verify_retained_ci_test_evidence" in replay
    for flag, value in (
        ("--checkout-sha", "$GITHUB_SHA"), ("--run-id", "$GITHUB_RUN_ID"),
        ("--run-attempt", "$GITHUB_RUN_ATTEMPT"), ("--event", "$GITHUB_EVENT_NAME"),
    ):
        assert f'{flag} "{value}"' in replay
    upload = steps[names.index(order[-1])]["with"]
    assert upload["if-no-files-found"] == "error"
    assert upload["retention-days"] == "90"
    assert LOG in upload["path"] and RECEIPT in upload["path"]
