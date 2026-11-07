"""Ensure the historical freeze audit is actually executed against full Git history.

No tests here inspect the original results or assert outcome blinding.
"""

from pathlib import Path
import yaml


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/analysis-freeze-chronology.yml"
)


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_chronology_audit_triggers_on_its_own_contract_and_frozen_plan():
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert "workflow_dispatch" in workflow["on"]
    needed = {
        ".github/workflows/analysis-freeze-chronology.yml",
        "scripts/audit_analysis_plan_freeze_chronology.py",
        "tests/test_analysis_plan_freeze_chronology.py",
        "tests/test_analysis_freeze_chronology_workflow.py",
        "docs/MAIN_STUDY_ANALYSIS_FREEZE_CHRONOLOGY.md",
        "paper/RESEARCH_PROTOCOL.md",
        "paper/ANALYSIS_PLAN.md",
        "paper/MAIN_STUDY_INFERENCE.md",
    }
    for event in ("push", "pull_request"):
        assert needed <= set(workflow["on"][event]["paths"])
    assert "research-paper-eval-2027" in workflow["on"]["push"]["branches"]


def test_chronology_audit_requires_full_history_and_read_only_checkout():
    workflow = _workflow()
    jobs = workflow["jobs"]
    assert list(jobs) == ["verify-original-freeze-chronology"]
    job = jobs["verify-original-freeze-chronology"]
    assert job["runs-on"] == "ubuntu-24.04"
    steps = job["steps"]
    checkout = steps[0]
    assert checkout["uses"] == (
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    )
    assert checkout["with"]["fetch-depth"] == "0"
    assert checkout["with"]["persist-credentials"] == "false"
    assert steps[1]["uses"] == (
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
    )
    assert steps[1]["with"]["python-version"] == "3.11.17"
    run = steps[2]["run"]
    assert 'git rev-parse --is-shallow-repository' in run
    assert 'git rev-parse HEAD' in run
    assert "python -m scripts.audit_analysis_plan_freeze_chronology" in run
    assert "python -m scripts.run_budget_main_study" not in run
    assert "python -m scripts.evaluate_posthoc_support" not in run
    assert "python -m scripts.analyze_human_eval" not in run


def test_chronology_receipt_does_not_elevate_claims_and_is_retained():
    steps = _workflow()["jobs"]["verify-original-freeze-chronology"]["steps"]
    run = steps[2]["run"]
    for status in (
        "prospective_precollection_analysis_preregistration_established",
        "pre_analysis_outcome_blinding_established",
        "original_treatment_authenticity_established",
        "human_validation_performed",
    ):
        assert f'receipt[claim] is False' in run
        assert status in run or 'for claim in (' in run
    assert "chronology_receipt_sha256" in run
    assert "checkout_sha" in run
    upload = steps[3]
    assert upload["uses"] == (
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    )
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == "90"
