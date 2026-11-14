"""Configuration contract for offline human-analysis result-verification CI.

Only synthetic test fixtures are exercised; no real human ratings are asserted.
"""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/human-eval-analysis-fast-ci.yml"
ANALYSIS_SCRIPTS = (
    "scripts/human_eval_analysis_core.py",
    "scripts/analyze_human_eval.py",
    "scripts/verify_human_eval_analysis_outputs.py",
    "scripts/freeze_human_eval_ratings.py",
    "scripts/verify_human_eval_freeze.py",
    "scripts/build_human_eval_packet.py",
    "scripts/verify_human_eval_packet.py",
    "scripts/analyze_main_study.py"
)
ANALYSIS_MODULES = (
    "tests/test_human_eval_analysis_stats.py",
    "tests/test_human_eval_analysis_helper_input_domain.py",
    "tests/test_human_eval_analysis_snapshot_integrity.py",
    "tests/test_human_eval_analysis_snapshot_bounds.py",
    "tests/test_human_eval_analysis_snapshot_hardlinks.py",
    "tests/test_human_eval_analysis_ancestor_custody.py",
    "tests/test_human_eval_analysis_producer_snapshot.py",
    "tests/test_human_eval_analysis_producer_provenance_capture.py",
    "tests/test_human_eval_analysis_output_size_contract.py",
    "tests/test_human_eval_analysis_output_verification.py",
    "tests/test_human_eval_analysis_fast_ci_workflow.py"
)
SOURCE_TRIGGER_PATHS = (
    "tests/human_eval_test_support.py",
    "paper/HUMAN_EVAL_ANALYSIS_PLAN.md",
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
    ".python-version"
)
LOG = "vera-human-analysis-tests.log"
RECEIPT = "vera-human-analysis-test-receipt.json"


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_human_analysis_lane_covers_production_verification_and_triggers():
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in workflow["on"]
    job = workflow["jobs"]["analysis-regressions"]
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
    install = next(s for s in steps if s["name"] == "Install pinned analysis-test dependencies only")
    for value in ("set -euo pipefail", "--no-deps", "--only-binary=:all:",
                  "--retries 1 --timeout 15",
                  "--constraint requirements-ci.lock --constraint requirements.txt",
                  "pytest pluggy iniconfig packaging PyYAML markdown-it-py mdurl",
                  "python -m pip check"):
        assert value in install["run"]
    assert "-r requirements.txt" not in install["run"]

    compiled = next(s for s in steps if s["name"] == "Compile human-analysis implementation and regressions")
    for path in (*ANALYSIS_SCRIPTS, *ANALYSIS_MODULES):
        assert path in compiled["run"]

    invocation = next(s for s in steps if s["name"] == "Run firewalled human-analysis regressions")
    assert invocation["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert invocation["run"].strip().splitlines() == [
        "set -euo pipefail",
        'bash scripts/run_offline_pytest_firewalled.sh '
        + " ".join(ANALYSIS_MODULES)
        + ' 2>&1 | tee "$RUNNER_TEMP/' + LOG + '"',
    ]
    assert len(ANALYSIS_MODULES) == len(set(ANALYSIS_MODULES))
    for event in ("push", "pull_request"):
        paths = workflow["on"][event]["paths"]
        for path in (str(WORKFLOW.relative_to(ROOT)), *ANALYSIS_SCRIPTS,
                     *ANALYSIS_MODULES, *SOURCE_TRIGGER_PATHS):
            assert paths.count(path) == 1


def test_human_analysis_lane_binds_retained_receipts_to_exact_commit():
    steps = _workflow()["jobs"]["analysis-regressions"]["steps"]
    names = [s["name"] for s in steps]
    order = [
        "Verify runtime and source before installing dependencies",
        "Install pinned analysis-test dependencies only",
        "Verify source immediately before analysis tests",
        "Run firewalled human-analysis regressions",
        "Verify runtime and source after analysis tests",
        "Bind exact-commit analysis-test evidence",
        "Replay analysis-test evidence before retention",
        "Retain source-bound analysis regression evidence",
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
    for flag, variable in (
        ("--checkout-sha", "$GITHUB_SHA"), ("--run-id", "$GITHUB_RUN_ID"),
        ("--run-attempt", "$GITHUB_RUN_ATTEMPT"), ("--event", "$GITHUB_EVENT_NAME"),
    ):
        assert f'{flag} "{variable}"' in replay
    upload = steps[names.index(order[-1])]["with"]
    assert upload["if-no-files-found"] == "error"
    assert upload["retention-days"] == "90"
    assert LOG in upload["path"] and RECEIPT in upload["path"]
