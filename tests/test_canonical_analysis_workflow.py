"""Regression tests for the canonical main-study analysis workflow.

The workflow is part of the scientific provenance chain, so these tests pin the
exact recovered study artifact and require an offline verify-before-publish
sequence. They intentionally inspect the workflow as text to avoid introducing
another YAML parser solely for CI contract checks.
"""
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "canonical-main-study-analysis.yml"
)


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_pins_canonical_recovery_artifact() -> None:
    workflow = _workflow()
    assert 'CANONICAL_RECOVERY_RUN_ID: "34783525480"' in workflow
    assert (
        'CANONICAL_RECOVERY_ARTIFACT: "budget-main-study-recovered-34783525480"'
        in workflow
    )
    assert "actions/download-artifact@v4" in workflow
    assert "run-id: ${{ env.CANONICAL_RECOVERY_RUN_ID }}" in workflow


def test_workflow_has_explicit_scientific_trigger_only() -> None:
    workflow = _workflow()
    assert "workflow_dispatch:" in workflow
    assert "experiments/run_canonical_analysis.trigger" in workflow
    assert "research-paper-eval-2027" in workflow


def test_workflow_runs_verified_analysis_in_fail_closed_order() -> None:
    workflow = _workflow()
    fingerprint = workflow.index("python -m scripts.fingerprint_research_artifacts")
    analysis = workflow.index("python -m scripts.run_verified_main_study_analysis")
    provenance = workflow.index("python -m scripts.verify_analysis_provenance")
    output_check = workflow.index("python -m scripts.verify_main_study_outputs")

    assert fingerprint < analysis < provenance < output_check


def test_workflow_invokes_package_aware_analysis_modules() -> None:
    workflow = _workflow()
    assert "python -m scripts.fingerprint_research_artifacts" in workflow
    assert "python -m scripts.run_verified_main_study_analysis" in workflow
    assert "python -m scripts.verify_analysis_provenance" in workflow
    assert "python -m scripts.verify_main_study_outputs" in workflow


def test_workflow_is_offline_after_canonical_artifact_download() -> None:
    workflow = _workflow()
    assert "OPENAI_API_KEY" not in workflow
    assert "scripts/evaluate_posthoc_support.py" not in workflow
    assert "scripts/run_budget_main_study.py" not in workflow
    assert "scripts/run_pilot.py" not in workflow


def test_workflow_preserves_self_contained_analysis_bundle() -> None:
    workflow = _workflow()
    required = (
        "outputs/canonical_analysis_source.json",
        "outputs/main_study_analysis_inputs_manifest.json",
        "outputs/main_study_analysis_provenance.json",
        "outputs/main_study_inference.json",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "paper/MAIN_STUDY_INFERENCE.md",
    )
    for path in required:
        assert path in workflow
    assert "if-no-files-found: error" in workflow


def test_workflow_publishes_only_after_independent_verification() -> None:
    workflow = _workflow()
    assert "contents: write" in workflow
    verification = workflow.index("Independently verify analysis receipt")
    publish = workflow.index("Publish verified canonical analysis snapshot")
    assert verification < publish
    for path in (
        "outputs/canonical_analysis_source.json",
        "outputs/main_study_analysis_inputs_manifest.json",
        "outputs/main_study_analysis_provenance.json",
        "outputs/main_study_inference.json",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "paper/MAIN_STUDY_INFERENCE.md",
    ):
        assert path in workflow
    assert "Refusing to publish unexpected staged paths" in workflow
