"""Workflow contract for the read-only, synthetic diagnostic-pilot CI lane.

This test checks that CI runs *every* listed regression; a successful badge is
not evidence of new treatment results, provenance recovery, or human validation.
"""
from pathlib import Path
import shlex

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/pilot-integrity-fast-ci.yml"
SOURCE = [
    "scripts/summarize_pilot.py",
    "scripts/validate_pilot_artifacts.py",
    "scripts/audit_pilot_cost_summary.py",
    "scripts/audit_pilot_variant_summary.py",
    "scripts/audit_pilot_runs_csv.py"
]
TESTS = [
    "tests/test_pilot_cost_coverage.py",
    "tests/test_pilot_cost_ledger_integrity.py",
    "tests/test_pilot_csv_formula_safety.py",
    "tests/test_pilot_csv_source_reconciliation.py",
    "tests/test_pilot_json_document_integrity.py",
    "tests/test_pilot_model_usage_bucket_completeness.py",
    "tests/test_pilot_numeric_counter_integrity.py",
    "tests/test_pilot_paired_summary_reconciliation.py",
    "tests/test_pilot_postrun_token_ledger.py",
    "tests/test_pilot_pricing_source_continuity.py",
    "tests/test_pilot_progress_event_ledger.py",
    "tests/test_pilot_source_selection_integrity.py",
    "tests/test_pilot_source_url_accounting.py",
    "tests/test_pilot_summary_create_only_publication.py",
    "tests/test_pilot_summary_source_continuity.py",
    "tests/test_pilot_trace_capture_bounds.py",
    "tests/test_pilot_trace_inventory_identity.py",
    "tests/test_pilot_validator_trace_inventory.py",
    "tests/test_pilot_integrity_fast_ci_workflow.py",
    "tests/test_offline_ci_network_firewall.py"
]
OTHER_PATHS = [
    "experiments/openai_pricing_2026-09-08.json",
    "experiments/results/pilot_v1_canonical_runs.csv",
    "docs/PILOT_INTEGRITY_FAST_CI.md",
    "scripts/run_offline_pytest_firewalled.sh",
    "scripts/verify_ci_python_runtime.py",
    "scripts/verify_ci_source_checkout.py",
    "scripts/verify_ci_test_evidence.py",
    "scripts/verify_retained_ci_test_evidence.py",
    "requirements.txt",
    "requirements-ci.lock",
    ".python-version"
]
LOG = "vera-pilot-integrity-tests.log"
RECEIPT = "vera-pilot-integrity-test-receipt.json"


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_pilot_lane_selected_modules_and_trigger_paths_are_complete():
    wf = _workflow()
    assert wf["on"]["push"]["branches"] == ["research-*"]
    assert wf["on"]["pull_request"]["paths"] == wf["on"]["push"]["paths"]
    assert set([str(WORKFLOW.relative_to(ROOT)), *SOURCE, *TESTS, *OTHER_PATHS]).issubset(
        set(wf["on"]["push"]["paths"])
    )
    steps = wf["jobs"]["pilot-provenance-regressions"]["steps"]
    compilation = next(step["run"] for step in steps if step["name"].startswith("Compile pilot"))
    for path in [*SOURCE, *TESTS]:
        assert path in compilation
    execution = next(step["run"] for step in steps if step["name"].startswith("Run firewalled"))
    command = execution.split("bash scripts/run_offline_pytest_firewalled.sh ", 1)[1]
    assert shlex.split(command.split(" 2>&1", 1)[0]) == TESTS
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in str(
        next(step["env"] for step in steps if step["name"].startswith("Run firewalled"))
    )


def test_pilot_ci_is_read_only_pinned_and_source_bound():
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["pilot-provenance-regressions"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert int(job["timeout-minutes"]) <= 15
    steps = job["steps"]
    checkout = next(step for step in steps if step["name"].startswith("Checkout"))
    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["uses"].startswith("actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803")
    python = next(step for step in steps if step["name"].startswith("Pin offline Python"))
    assert python["with"]["python-version"] == "3.11.17"
    assert python["uses"].startswith("actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1")
    all_runs = "\n".join(step.get("run", "") for step in steps)
    assert "--no-deps" in all_runs
    assert "--constraint requirements-ci.lock" in all_runs
    assert "--constraint requirements.txt" in all_runs
    assert all_runs.count("scripts.verify_ci_source_checkout") >= 3
    assert all_runs.count("scripts.verify_ci_python_runtime") >= 2
    assert "scripts.verify_ci_test_evidence" in all_runs
    assert "scripts.verify_retained_ci_test_evidence" in all_runs
    assert all(f"--{field}" in all_runs for field in (
        "checkout-sha", "run-id", "run-attempt", "event"
    ))
    assert LOG in all_runs and RECEIPT in all_runs
    assert "workflow_dispatch" in wf["on"]
    assert all(
        "secrets." not in str(step) and "pip install -r requirements.txt" not in str(step)
        for step in steps
    )
    retained = next(step for step in steps if step["name"].startswith("Retain source-bound"))
    assert retained["with"]["if-no-files-found"] == "error"
    assert retained["with"]["retention-days"] == "90"
    assert LOG in retained["with"]["path"] and RECEIPT in retained["with"]["path"]
