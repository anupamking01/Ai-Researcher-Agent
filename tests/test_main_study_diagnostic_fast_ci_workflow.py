"""Guard the independent, source-bound local diagnostic provenance CI lane.

This proves the workflow selects the actual bundle-verifier regressions, not
an unrelated evaluation module. A passing lane does not authenticate missing
September artifacts or establish human/confirmatory evidence.
"""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/main-study-local-diagnostic-fast-ci.yml"
TARGETS = (
    "tests/test_main_study_diagnostic_input_receipt.py",
    "tests/test_main_study_diagnostic_publication_content.py",
    "tests/test_main_study_diagnostic_fast_ci_workflow.py",
    "tests/test_main_study_input_preflight.py",
)
SOURCE_PATHS = (
    "scripts/analyze_main_study.py",
    "scripts/analyze_main_study_with_preflight.py",
    "scripts/verify_main_study_diagnostic.py",
    "scripts/validate_main_study_inputs.py",
    "scripts/validate_numeric_inputs.py",
)


def test_local_diagnostic_lane_includes_every_diagnostic_regression_module():
    """Prevent new source-linked diagnostic modules silently missing fast CI."""
    discovered = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "tests").glob("test_main_study_diagnostic_*.py")
    }
    assert set(TARGETS) - {"tests/test_main_study_input_preflight.py"} == discovered
    # The standalone CSV preflight shares the diagnostic's strict input
    # validator and must be exercised whenever that module changes.
    assert "tests/test_main_study_input_preflight.py" in TARGETS


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step(steps, name):
    return next(step for step in steps if step.get("name") == name)


def test_local_diagnostic_lane_is_narrow_pinned_and_firewalled():
    definition = _workflow()
    assert definition["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in definition["on"]
    for event in ("push", "pull_request"):
        paths = definition["on"][event]["paths"]
        assert str(WORKFLOW.relative_to(ROOT)) in paths
        assert set(SOURCE_PATHS) <= set(paths)
        assert set(TARGETS) <= set(paths)
        assert {"requirements.txt", "requirements-ci.lock",
                "scripts/run_offline_pytest_firewalled.sh"} <= set(paths)
    assert definition["on"]["push"]["branches"] == ["research-*"]
    job = definition["jobs"]["local-diagnostic-regressions"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert int(job["timeout-minutes"]) <= 12
    steps = job["steps"]
    checkout = _step(steps, "Checkout source without stored credentials")
    assert checkout["with"]["persist-credentials"] == "false"
    setup = _step(steps, "Pin Python interpreter")
    assert setup["with"]["python-version"] == "3.11.17"
    assert setup["with"]["pip-version"] == "26.2.1"
    install = _step(steps, "Install only pinned offline diagnostic-test dependencies")
    assert "--no-deps" in install["run"]
    assert "--only-binary=:all:" in install["run"]
    assert "--constraint requirements-ci.lock" in install["run"]
    assert "--constraint requirements.txt" in install["run"]
    test = _step(steps, "Run firewalled diagnostic provenance regressions")
    assert test["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert test["run"].strip().splitlines() == [
        "set -euo pipefail",
        "bash scripts/run_offline_pytest_firewalled.sh "
        + " ".join(TARGETS)
        + ' 2>&1 | tee "$RUNNER_TEMP/vera-local-diagnostic-tests.log"',
    ]


def test_local_diagnostic_evidence_is_bound_replayed_and_retained():
    steps = _workflow()["jobs"]["local-diagnostic-regressions"]["steps"]
    names = [step["name"] for step in steps]
    order = (
        "Verify pinned Python before dependency-free diagnostic gate",
        "Verify exact checkout before dependency-free diagnostic gate",
        "Run dependency-free diagnostic invariants before pip installation",
        "Independently replay dependency-free evidence before retention",
        "Install only pinned offline diagnostic-test dependencies",
        "Verify source checkout before targeted tests",
        "Run firewalled diagnostic provenance regressions",
        "Verify source checkout after targeted tests",
        "Verify pinned interpreter after targeted tests",
        "Bind exact-commit diagnostic test receipt",
        "Independently replay diagnostic receipt before retention",
        "Retain source-bound targeted local diagnostic test evidence (90 days)",
    )
    assert list(map(names.index, order)) == sorted(map(names.index, order))
    bind = _step(steps, "Bind exact-commit diagnostic test receipt")["run"]
    replay = _step(steps, "Independently replay diagnostic receipt before retention")["run"]
    assert "python -m scripts.verify_ci_test_evidence" in bind
    assert "python -m scripts.verify_retained_ci_test_evidence" in replay
    for flag in ("--checkout-sha \"$GITHUB_SHA\"", "--run-id \"$GITHUB_RUN_ID\"",
                 "--run-attempt \"$GITHUB_RUN_ATTEMPT\"",
                 "--event \"$GITHUB_EVENT_NAME\""):
        assert flag in replay
    assert '--log "$RUNNER_TEMP/vera-local-diagnostic-tests.log"' in bind
    assert '--log "$RUNNER_TEMP/vera-local-diagnostic-tests.log"' in replay
    upload = _step(
        steps, "Retain source-bound targeted local diagnostic test evidence (90 days)"
    )
    assert "vera-local-diagnostic-tests.log" in upload["with"]["path"]
    assert "vera-local-diagnostic-test-receipt.json" in upload["with"]["path"]
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == "90"
