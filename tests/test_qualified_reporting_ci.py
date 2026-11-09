"""Verification of the artifact users will actually download, not only its exporter."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.assemble_qualified_main_study_report import ROOT, assemble_qualified_report
from scripts.verify_qualified_reporting_copy import main, verify_qualified_copy

WORKFLOW = ROOT / ".github/workflows/qualified-main-study-report.yml"


def _copy(tmp_path: Path) -> Path:
    destination = tmp_path / "qualified_main_study.md"
    destination.write_text(assemble_qualified_report(), encoding="utf-8")
    return destination


def test_exact_source_bound_copy_has_explicit_noncanonical_receipt(tmp_path):
    path = _copy(tmp_path)
    receipt = verify_qualified_copy(report_path=path)
    assert receipt["status"] == "noncanonical_qualified_reporting_copy_verified"
    assert receipt["qualified_copy_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["qualified_copy_bytes"] == len(path.read_bytes())
    for claim in (
        "original_reports_and_traces_independently_authenticated",
        "prospective_precollection_statistical_preregistration_established",
        "randomized_causal_effect_identified",
        "human_validation_performed",
    ):
        assert receipt[claim] is False


@pytest.mark.parametrize("tamper", [
    lambda data: data[:-8],
    lambda data: data.replace(b"noncanonical", b"CONFIRMATORY", 1),
    lambda data: data + b"\nNew, unreviewed conclusions.\n",
])
def test_truncated_relabelled_or_appended_copy_has_no_receipt(tmp_path, tamper):
    path = _copy(tmp_path)
    path.write_bytes(tamper(path.read_bytes()))
    with pytest.raises(ValueError, match="does not match source-verified assembly"):
        verify_qualified_copy(report_path=path)


def test_redirected_reporting_copy_is_not_verified(tmp_path):
    original = _copy(tmp_path)
    alias = tmp_path / "redirected.md"
    alias.symlink_to(original)
    with pytest.raises(ValueError, match="unsafe"):
        verify_qualified_copy(report_path=alias)


def test_receipt_cli_is_create_only(tmp_path, monkeypatch):
    report = _copy(tmp_path)
    receipt_path = tmp_path / "qualified_receipt.json"
    monkeypatch.setattr("sys.argv", [
        "verify_qualified_reporting_copy", "--report", str(report),
        "--receipt", str(receipt_path),
    ])
    assert main() == 0
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["qualified_copy_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()
    old = receipt_path.read_bytes()
    with pytest.raises(SystemExit):
        main()
    assert receipt_path.read_bytes() == old


def test_ci_runs_real_reporter_and_verifier_on_scientific_changes():
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert workflow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in workflow["on"]
    dependencies = {
        ".github/workflows/qualified-main-study-report.yml",
        "scripts/assemble_qualified_main_study_report.py",
        "scripts/verify_qualified_reporting_copy.py",
        "tests/test_qualified_main_study_report.py",
        "tests/test_qualified_reporting_ci.py",
        "docs/MAIN_STUDY_QUALIFIED_REPORTING.md",
        "paper/MAIN_STUDY_REPORTING_COVER.md",
        "paper/MAIN_STUDY_INFERENCE.md",
        "outputs/main_study_inference.json",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "outputs/main_study_analysis_inputs_manifest.json",
        "scripts/verify_published_main_study_inputs.py",
        "scripts/verify_main_study_outputs.py",
        "scripts/verify_research_artifact_manifest.py",
        "scripts/fingerprint_research_artifacts.py",
        "scripts/analyze_main_study.py",
    }
    for event in ("push", "pull_request"):
        assert dependencies <= set(workflow["on"][event]["paths"])
    assert "research-paper-eval-2027" in workflow["on"]["push"]["branches"]
    job = workflow["jobs"]["verify-qualified-report"]
    assert job["runs-on"] == "ubuntu-24.04"
    steps = job["steps"]
    assert steps[0]["uses"] == (
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    )
    assert steps[0]["with"]["persist-credentials"] == "false"
    assert steps[1]["uses"] == (
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
    )
    script = steps[2]["run"]
    assert "python -m scripts.assemble_qualified_main_study_report" in script
    assert "python -m scripts.verify_qualified_reporting_copy" in script
    assert "git diff --exit-code" in script
    for forbidden in (
        "run_budget_main_study", "evaluate_posthoc_support",
        "run_pilot", "analyze_human_eval",
    ):
        assert forbidden not in script
    upload = steps[3]
    assert upload["uses"] == (
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == "90"
