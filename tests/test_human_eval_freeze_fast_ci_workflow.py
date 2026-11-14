"""Contract for the dedicated offline blinded-rating freeze verification lane.

This tests code paths and workflow configuration, not any actual human ratings.
"""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/human-eval-freeze-fast-ci.yml"
FREEZE_SCRIPTS = (
    "scripts/freeze_human_eval_ratings.py",
    "scripts/verify_human_eval_freeze.py",
    "scripts/human_eval_analysis_core.py",
    "scripts/build_human_eval_packet.py",
    "scripts/verify_human_eval_packet.py",
)
FREEZE_MODULES = (
    "tests/test_human_eval_freeze.py",
    "tests/test_human_eval_freeze_capture_bounds.py",
    "tests/test_human_eval_freeze_destination.py",
    "tests/test_human_eval_freeze_inventory_bounds.py",
    "tests/test_human_eval_freeze_inventory_hardlinks.py",
    "tests/test_human_eval_freeze_json_number_integrity.py",
    "tests/test_human_eval_freeze_json_resource_bounds.py",
    "tests/test_human_eval_freeze_read_consistency.py",
    "tests/test_human_eval_freeze_tree_resource_bounds.py",
    "tests/test_human_eval_freeze_verification.py",
    "tests/test_human_eval_freeze_fast_ci_workflow.py",
)
SOURCE_TRIGGER_PATHS = (
    "tests/human_eval_test_support.py",
    "paper/HUMAN_EVAL_PROTOCOL.md",
    "paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
    "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
    "scripts/run_offline_pytest_firewalled.sh",
    "scripts/verify_ci_python_runtime.py",
    "scripts/verify_ci_source_checkout.py",
    "scripts/verify_ci_test_evidence.py",
    "scripts/verify_retained_ci_test_evidence.py",
    "requirements.txt",
    "requirements-ci.lock",
)
SCOPE = (
    "bash scripts/run_offline_pytest_firewalled.sh "
    + " ".join(FREEZE_MODULES)
    + ' 2>&1 | tee "$RUNNER_TEMP/vera-human-freeze-tests.log"'
)


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_freeze_lane_selects_entire_declared_regression_scope_and_triggers():
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in workflow["on"]
    job = workflow["jobs"]["freeze-regressions"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert 0 < int(job["timeout-minutes"]) <= 12
    steps = job["steps"]
    checkout = next(s for s in steps if s["name"] == "Checkout source without credentials")
    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["uses"].startswith("actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803")
    setup = next(s for s in steps if s["name"] == "Pin offline Python interpreter")
    assert setup["uses"].startswith("actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1")
    assert setup["with"]["python-version"] == "3.11.17"
    assert setup["with"]["pip-version"] == "26.2.1"
    install = next(s for s in steps if s["name"] == "Install pinned freeze-test dependencies only")
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
    compile_step = next(s for s in steps if s["name"] == "Compile freeze implementation and regressions")
    for path in (*FREEZE_SCRIPTS, *FREEZE_MODULES):
        assert path in compile_step["run"]
    test_step = next(s for s in steps if s["name"] == "Run firewalled blinded-freeze regressions")
    assert test_step["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert test_step["run"].strip().splitlines() == ["set -euo pipefail", SCOPE]
    assert len(FREEZE_MODULES) == len(set(FREEZE_MODULES))
    for event in ("push", "pull_request"):
        paths = workflow["on"][event]["paths"]
        for path in (
            ".github/workflows/human-eval-freeze-fast-ci.yml",
            *FREEZE_SCRIPTS,
            *FREEZE_MODULES,
            *SOURCE_TRIGGER_PATHS,
        ):
            assert path in paths


def test_freeze_lane_enforces_receipt_replay_and_evidence_retention():
    steps = _workflow()["jobs"]["freeze-regressions"]["steps"]
    names = [step["name"] for step in steps]
    required = (
        "Verify runtime and source before installing dependencies",
        "Install pinned freeze-test dependencies only",
        "Verify source immediately before freeze tests",
        "Run firewalled blinded-freeze regressions",
        "Verify runtime and source after freeze tests",
        "Bind exact-commit freeze-test evidence",
        "Replay freeze-test evidence before retention",
        "Retain source-bound freeze regression evidence",
    )
    assert [names.index(n) for n in required] == sorted(names.index(n) for n in required)
    for name in (required[0], required[2], required[4]):
        assert '--checkout-sha "$GITHUB_SHA"' in steps[names.index(name)]["run"]
    receipt = steps[names.index(required[5])]["run"]
    replay = steps[names.index(required[6])]["run"]
    assert "python -m scripts.verify_ci_test_evidence" in receipt
    assert replay.splitlines()[0].strip() == "set -euo pipefail"
    assert "python -m scripts.verify_retained_ci_test_evidence" in replay
    for option, value in (
        ("--checkout-sha", "$GITHUB_SHA"),
        ("--run-id", "$GITHUB_RUN_ID"),
        ("--run-attempt", "$GITHUB_RUN_ATTEMPT"),
        ("--event", "$GITHUB_EVENT_NAME"),
    ):
        assert f'{option} "{value}"' in replay
    upload = steps[names.index(required[-1])]["with"]
    assert upload["if-no-files-found"] == "error"
    assert upload["retention-days"] == "90"
    assert "vera-human-freeze-tests.log" in upload["path"]
    assert "vera-human-freeze-test-receipt.json" in upload["path"]
