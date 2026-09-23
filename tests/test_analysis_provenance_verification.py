"""Tests for independent verification of manuscript-facing provenance receipts."""
import hashlib
from pathlib import Path

import pytest

from scripts import analyze_main_study
from scripts.build_analysis_provenance import ANALYSIS_PLAN, ANALYSIS_REQUIREMENTS, ANALYSIS_SCRIPT
from scripts.fingerprint_research_artifacts import build_manifest
from scripts.verify_analysis_provenance import verify_receipt


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> dict:
    for relative, content in {
        ANALYSIS_SCRIPT: "# frozen analyzer\n",
        ANALYSIS_PLAN: "# frozen plan\n",
        ANALYSIS_REQUIREMENTS: "numpy==1.26.4\n",
        "outputs/main_study_runs.csv": "variant_id,task_id\nD3,main-01\n",
        "outputs/posthoc_support_runs.csv": "variant_id,task_id\nD3,main-01\n",
        "outputs/main_study_inference.json": "{}\n",
        "paper/MAIN_STUDY_INFERENCE.md": "# result\n",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest = build_manifest(
        [tmp_path / "outputs/main_study_runs.csv", tmp_path / "outputs/posthoc_support_runs.csv"],
        root=tmp_path,
    )
    return {
        "schema_version": 1,
        "input_manifest_aggregate_sha256": manifest["aggregate_sha256"],
        "verified_inputs": manifest["artifacts"],
        "analysis_implementation": {"path": ANALYSIS_SCRIPT, "sha256": _digest(tmp_path / ANALYSIS_SCRIPT)},
        "analysis_plan": {"path": ANALYSIS_PLAN, "sha256": _digest(tmp_path / ANALYSIS_PLAN)},
        "analysis_environment": {
            "requirements": {"path": ANALYSIS_REQUIREMENTS, "sha256": _digest(tmp_path / ANALYSIS_REQUIREMENTS)},
        },
        "frozen_configuration": {
            "variants": list(analyze_main_study.VARIANTS),
            "primary_contrasts": [list(item) for item in analyze_main_study.PRIMARY_CONTRASTS],
            "bootstrap_seed": analyze_main_study.BOOTSTRAP_SEED,
            "bootstrap_draws": analyze_main_study.BOOTSTRAP_DRAWS,
            "expected_tasks": analyze_main_study.EXPECTED_TASKS,
        },
        "verified_outputs": {
            "canonical_inference": {"path": "outputs/main_study_inference.json", "sha256": _digest(tmp_path / "outputs/main_study_inference.json")},
            "manuscript_rendering": {"path": "paper/MAIN_STUDY_INFERENCE.md", "sha256": _digest(tmp_path / "paper/MAIN_STUDY_INFERENCE.md")},
        },
    }


def test_complete_current_receipt_verifies(tmp_path: Path):
    verify_receipt(_fixture(tmp_path), root=tmp_path)


@pytest.mark.parametrize("relative", [
    "outputs/main_study_runs.csv",
    "outputs/posthoc_support_runs.csv",
    ANALYSIS_SCRIPT,
    ANALYSIS_PLAN,
    ANALYSIS_REQUIREMENTS,
    "outputs/main_study_inference.json",
    "paper/MAIN_STUDY_INFERENCE.md",
])
def test_mutating_any_bound_artifact_invalidates_receipt(tmp_path: Path, relative: str):
    receipt = _fixture(tmp_path)
    (tmp_path / relative).write_text("mutated\n", encoding="utf-8")
    with pytest.raises(ValueError, match="(SHA-256 mismatch|byte-size mismatch)"):
        verify_receipt(receipt, root=tmp_path)


def test_configuration_drift_invalidates_receipt(tmp_path: Path):
    receipt = _fixture(tmp_path)
    receipt["frozen_configuration"]["bootstrap_draws"] += 1
    with pytest.raises(ValueError, match="frozen configuration"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_verified_inputs_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path)
    receipt.pop("verified_inputs")
    with pytest.raises(ValueError, match="embed the verified analysis inputs"):
        verify_receipt(receipt, root=tmp_path)


def test_tampered_input_aggregate_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path)
    receipt["input_manifest_aggregate_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="aggregate research-artifact fingerprint mismatch"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_analysis_environment_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path)
    receipt.pop("analysis_environment")
    with pytest.raises(ValueError, match="dependency environment"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_verified_outputs_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path)
    receipt.pop("verified_outputs")
    with pytest.raises(ValueError, match="bind exactly both"):
        verify_receipt(receipt, root=tmp_path)
