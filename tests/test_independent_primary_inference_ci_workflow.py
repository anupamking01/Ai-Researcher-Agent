"""Contract for the exact-commit frozen primary arithmetic audit workflow.

Standard-library-only structural tests; CI executes these before the arithmetic.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/independent-primary-inference-audit.yml"


class IndependentInferenceCIContract(unittest.TestCase):
    def test_verifies_immutable_published_inputs_and_frozen_arithmetic(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("verify_published_frozen_inputs()", source)
        self.assertIn("audit_files(", source)
        self.assertIn("if before != after", source)
        self.assertIn("independent_primary_arithmetic_consistent_not_provenance", source)
        self.assertIn("secondary_bootstrap_intervals_checked", source)
        self.assertIn("original_treatment_reports_authenticated", source)
        self.assertIn("precollection_statistical_preregistration_established", source)
        self.assertIn("human_validation_performed", source)

    def test_read_only_uncredentialed_dispatch_and_precise_triggers(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("timeout-minutes: 20", source)
        self.assertIn("push:\n    branches: [research-paper-eval-2027]", source)
        self.assertIn("pull_request:\n    paths: *inference_paths", source)
        self.assertIn("workflow_dispatch:", source)
        for dependency in (
            "scripts/audit_primary_inference_independently.py",
            "scripts/verify_published_main_study_inputs.py",
            "scripts/audit_frozen_analysis_csv_inputs.py",
            "scripts/validate_main_study_inputs.py",
            "scripts/verify_research_artifact_manifest.py",
            "scripts/fingerprint_research_artifacts.py",
            "outputs/main_study_runs.csv",
            "outputs/posthoc_support_runs.csv",
            "outputs/main_study_inference.json",
            "outputs/main_study_analysis_inputs_manifest.json",
            "tests/test_independent_primary_inference_ci_workflow.py",
        ):
            self.assertIn(f"      - {dependency}\n", source)
        self.assertNotIn("OPENAI_API_KEY", source)
        self.assertNotIn("secrets.", source)

    def test_receipt_retained_and_scientific_gates_not_reclassified(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", source)
        self.assertIn("retention-days: 90", source)
        self.assertIn("if-no-files-found: error", source)
        self.assertIn("verify_ci_source_checkout --checkout-sha", source)
        for field in (
            '"original_treatment_reports_authenticated": False',
            '"precollection_statistical_preregistration_established": False',
            '"human_validation_performed": False',
        ):
            self.assertIn(field, source)


if __name__ == "__main__":
    unittest.main()
