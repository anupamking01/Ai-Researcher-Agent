"""Prevent regression of evidence-generation and non-confirmatory CI boundaries."""
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/exploratory-measurement-replay.yml"
)


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_both_posthoc_diagnostics_are_replayed_and_independently_checked_before_upload():
    text = _workflow()
    upload = text.index("name: Retain checked diagnostic JSONs")
    pairs = (
        ("analyze_main_study_retrieval_exposure",
         "verify_main_study_retrieval_exposure_artifact"),
        ("analyze_main_study_claim_denominators",
         "verify_main_study_claim_denominator_artifact"),
    )
    for producer, verifier in pairs:
        assert text.index("python -m scripts." + producer + " >") < text.index(
            "python -m scripts." + verifier
        ) < upload
    assert "set -euo pipefail" in text


def test_replay_artifact_binds_executed_checkout_and_four_file_digests():
    text = _workflow()
    for name in (
        "retrieval_exposure.json",
        "retrieval_exposure_verification.json",
        "claim_denominators.json",
        "claim_denominators_verification.json",
        "artifact_index.json",
    ):
        assert name in text
    for field in ("GITHUB_SHA", "GITHUB_RUN_ID", "files_sha256",
                  "diagnostic_sha256", "paired_contrast_rows_checked"):
        assert field in text
    assert "if-no-files-found: error" in text
    assert "retention-days: 90" in text


def test_replay_excludes_online_execution_and_does_not_write_confirmatory_outputs():
    text = _workflow()
    assert "permissions:\n  contents: read" in text
    assert "persist-credentials: false" in text
    assert "python-version: \"3.11.17\"" in text
    assert "human_validation_performed" in text
    assert "original_execution_authenticated" in text
    assert "confirmatory_inference_changed" in text
    assert "confirmatory_primary_estimand_changed" in text
    for prohibited in (
        "scripts.run_budget_main_study",
        "scripts.evaluate_posthoc_support",
        "scripts.run_pilot",
        "scripts.run_verified_main_study_analysis",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "secrets.",
        "schedule:",
    ):
        assert prohibited not in text


def test_relevant_source_changes_trigger_replay_but_not_other_branches():
    text = _workflow()
    for path in (
        "scripts/audit_frozen_analysis_csv_inputs.py",
        "scripts/analyze_main_study_retrieval_exposure.py",
        "scripts/analyze_main_study_claim_denominators.py",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "experiments/main_budget_tasks.json",
    ):
        assert text.count('"' + path + '"') == 2
    assert "branches: [research-paper-eval-2027]" in text
    assert "workflow_dispatch:" in text


def test_bundle_verification_is_a_prerequisite_for_artifact_upload():
    text = _workflow()
    assert text.count('"scripts/verify_exploratory_measurement_bundle.py"') == 2
    assert text.count('"tests/test_exploratory_measurement_bundle_verification.py"') == 2
    invoked = text.index("python -m scripts.verify_exploratory_measurement_bundle")
    uploaded = text.index("name: Retain checked diagnostic JSONs")
    assert text.index('"workflow_run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]') < invoked < uploaded
    assert '"schema_version": 2' in text
    assert '--expected-checkout-sha "$GITHUB_SHA"' in text
    assert '--expected-run-id "$GITHUB_RUN_ID"' in text
    assert '--expected-run-attempt "$GITHUB_RUN_ATTEMPT"' in text
    assert '["git", "rev-parse", "HEAD"]' in text


def test_reruns_retain_separate_attempt_bound_artifacts():
    text = _workflow()
    assert 'vera-exploratory-measurement-${{ github.run_id }}-${{ github.run_attempt }}' in text
    assert 'name: vera-exploratory-measurement-${{ github.run_id }}' in text
