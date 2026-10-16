"""Tests for independent verification of manuscript-facing provenance receipts."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from scripts import analyze_main_study
from scripts.build_analysis_provenance import (
    ANALYSIS_OUTPUT_VERIFIER,
    ANALYSIS_PLAN,
    ANALYSIS_PROVENANCE_BUILDER,
    ANALYSIS_PYTHON_VERSION,
    ANALYSIS_REQUIREMENTS,
    ANALYSIS_SCRIPT,
    ANALYSIS_VERIFIER,
)
from scripts.fingerprint_research_artifacts import build_manifest
from scripts import verify_analysis_provenance as provenance
from scripts.verify_analysis_provenance import verify_receipt


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> dict:
    for relative, content in {
        ANALYSIS_SCRIPT: "# frozen analyzer\n",
        ANALYSIS_PLAN: "# frozen plan\n",
        ANALYSIS_REQUIREMENTS: "numpy==1.26.4\n",
        ANALYSIS_PYTHON_VERSION: "3.11\n",
        ANALYSIS_PROVENANCE_BUILDER: "# frozen provenance builder\n",
        ANALYSIS_VERIFIER: "# frozen provenance verifier\n",
        ANALYSIS_OUTPUT_VERIFIER: "# frozen output verifier\n",
        "scripts/verify_research_artifact_manifest.py": "# frozen artifact manifest verifier\n",
        "scripts/fingerprint_research_artifacts.py": "# frozen artifact fingerprinter\n",
        "outputs/main_study_runs.csv": "variant_id,task_id\nD3,main-01\n",
        "outputs/posthoc_support_runs.csv": "variant_id,task_id\nD3,main-01\n",
        "outputs/main_study_inference.json": "{}\n",
        "paper/MAIN_STUDY_INFERENCE.md": "# result\n",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest = build_manifest(
        [tmp_path / "outputs/main_study_runs.csv", tmp_path / "outputs/posthoc_support_runs.csv"], root=tmp_path
    )
    return {
        "schema_version": 1,
        "input_manifest_aggregate_sha256": manifest["aggregate_sha256"],
        "verified_inputs": manifest["artifacts"],
        "analysis_implementation": {"path": ANALYSIS_SCRIPT, "sha256": _digest(tmp_path / ANALYSIS_SCRIPT)},
        "analysis_plan": {"path": ANALYSIS_PLAN, "sha256": _digest(tmp_path / ANALYSIS_PLAN)},
        "analysis_environment": {
            "requirements": {"path": ANALYSIS_REQUIREMENTS, "sha256": _digest(tmp_path / ANALYSIS_REQUIREMENTS)},
            "python_version": {"path": ANALYSIS_PYTHON_VERSION, "sha256": _digest(tmp_path / ANALYSIS_PYTHON_VERSION)},
        },
        "provenance_builder": {
            "path": ANALYSIS_PROVENANCE_BUILDER,
            "sha256": _digest(tmp_path / ANALYSIS_PROVENANCE_BUILDER),
        },
        "verification_implementations": {
            "provenance": {"path": ANALYSIS_VERIFIER, "sha256": _digest(tmp_path / ANALYSIS_VERIFIER)},
            "output_consistency": {"path": ANALYSIS_OUTPUT_VERIFIER, "sha256": _digest(tmp_path / ANALYSIS_OUTPUT_VERIFIER)},
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


def test_receipt_rejects_unexpected_root_field(tmp_path: Path):
    receipt = _fixture(tmp_path)
    receipt["unexpected"] = "ambiguous extension"

    with pytest.raises(ValueError, match="unexpected root fields"):
        verify_receipt(receipt, root=tmp_path)


@pytest.mark.parametrize(
    "entry_path",
    [
        ("analysis_implementation",),
        ("analysis_plan",),
        ("analysis_environment", "requirements"),
        ("analysis_environment", "python_version"),
        ("provenance_builder",),
        ("verification_implementations", "provenance"),
        ("verification_implementations", "output_consistency"),
        ("verified_outputs", "canonical_inference"),
        ("verified_outputs", "manuscript_rendering"),
    ],
)
def test_receipt_rejects_extra_bound_file_fields(tmp_path: Path, entry_path):
    receipt = _fixture(tmp_path)
    entry = receipt
    for key in entry_path:
        entry = entry[key]
    entry["unexpected"] = "ambiguous extension"

    with pytest.raises(ValueError, match="exactly path and SHA-256"):
        verify_receipt(receipt, root=tmp_path)


def test_provenance_cli_rejects_duplicate_receipt_fields(
    tmp_path: Path, monkeypatch
):
    receipt = tmp_path / "duplicate.json"
    receipt.write_text(
        '{"schema_version": 1, "schema_version": 2}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["verify_analysis_provenance", str(receipt)])

    with pytest.raises(SystemExit, match="duplicate JSON field: schema_version"):
        provenance.main()


def _add_verified_execution(receipt: dict, tmp_path: Path) -> dict:
    execution = {}
    for key, relative in {
        "runner": "scripts/run_verified_main_study_analysis.py",
        "execution_verifier": "scripts/verify_main_study_execution.py",
        "input_validator": "scripts/validate_main_study_inputs.py",
    }.items():
        path = tmp_path / relative
        path.write_text(f"# frozen {key}\n", encoding="utf-8")
        execution[key] = {"path": relative, "sha256": _digest(path)}
    receipt["verified_execution"] = execution
    return receipt


def test_receipt_verifies_optional_execution_binding(tmp_path: Path):
    verify_receipt(_add_verified_execution(_fixture(tmp_path), tmp_path), root=tmp_path)


def test_receipt_rejects_extra_execution_root_field(tmp_path: Path):
    receipt = _add_verified_execution(_fixture(tmp_path), tmp_path)
    receipt["verified_execution"]["unexpected"] = {}

    with pytest.raises(ValueError, match="exact execution provenance fields"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_rejects_extra_execution_bound_file_field(tmp_path: Path):
    receipt = _add_verified_execution(_fixture(tmp_path), tmp_path)
    receipt["verified_execution"]["runner"]["unexpected"] = "ambiguous extension"

    with pytest.raises(ValueError, match="exactly path and SHA-256"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_rejects_execution_binding_drift(tmp_path: Path):
    receipt = _add_verified_execution(_fixture(tmp_path), tmp_path)
    receipt["verified_execution"]["runner"]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="execution runner SHA-256 mismatch"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_rejects_execution_path_substitution(tmp_path: Path):
    receipt = _add_verified_execution(_fixture(tmp_path), tmp_path)
    receipt["verified_execution"]["runner"] = dict(
        receipt["analysis_implementation"]
    )

    with pytest.raises(ValueError, match="execution runner provenance must bind canonical path"):
        verify_receipt(receipt, root=tmp_path)


@pytest.mark.parametrize("schema_version", [True, [], {}, "1", 3])
def test_malformed_receipt_schema_fails_with_validation_error(
    tmp_path: Path,
    schema_version,
):
    receipt = _fixture(tmp_path)
    receipt["schema_version"] = schema_version

    with pytest.raises(
        ValueError,
        match="unsupported or malformed analysis provenance receipt",
    ):
        verify_receipt(receipt, root=tmp_path)


def _schema_two_receipt(tmp_path: Path) -> dict:
    receipt = _fixture(tmp_path)
    receipt["schema_version"] = 2
    receipt["verification_implementations"].update(
        {
            "artifact_manifest": {
                "path": "scripts/verify_research_artifact_manifest.py",
                "sha256": _digest(
                    tmp_path / "scripts/verify_research_artifact_manifest.py"
                ),
            },
            "artifact_fingerprinter": {
                "path": "scripts/fingerprint_research_artifacts.py",
                "sha256": _digest(
                    tmp_path / "scripts/fingerprint_research_artifacts.py"
                ),
            },
        }
    )
    return receipt


def test_schema_two_receipt_verifies_transitive_manifest_chain(tmp_path: Path):
    verify_receipt(_schema_two_receipt(tmp_path), root=tmp_path)


def test_schema_two_receipt_requires_complete_transitive_manifest_chain(tmp_path: Path):
    receipt = _schema_two_receipt(tmp_path)
    receipt["verification_implementations"].pop("artifact_manifest")

    with pytest.raises(ValueError, match="complete canonical verification chain"):
        verify_receipt(receipt, root=tmp_path)


@pytest.mark.parametrize(
    ("key", "relative", "label"),
    [
        (
            "artifact_manifest",
            "scripts/verify_research_artifact_manifest.py",
            "artifact manifest verifier",
        ),
        (
            "artifact_fingerprinter",
            "scripts/fingerprint_research_artifacts.py",
            "artifact fingerprinter",
        ),
    ],
)
def test_schema_two_receipt_rejects_transitive_manifest_chain_drift(
    tmp_path: Path,
    key: str,
    relative: str,
    label: str,
):
    receipt = _schema_two_receipt(tmp_path)
    assert receipt["verification_implementations"][key]["path"] == relative
    (tmp_path / relative).write_text("# drift\n", encoding="utf-8")

    with pytest.raises(ValueError, match=rf"{label} SHA-256 mismatch"):
        verify_receipt(receipt, root=tmp_path)


@pytest.mark.parametrize("relative", [
    "outputs/main_study_runs.csv", "outputs/posthoc_support_runs.csv", ANALYSIS_SCRIPT,
    ANALYSIS_PLAN, ANALYSIS_REQUIREMENTS, ANALYSIS_PYTHON_VERSION, ANALYSIS_PROVENANCE_BUILDER,
    ANALYSIS_VERIFIER, ANALYSIS_OUTPUT_VERIFIER, "outputs/main_study_inference.json",
    "paper/MAIN_STUDY_INFERENCE.md",
])
def test_mutating_any_bound_artifact_invalidates_receipt(tmp_path: Path, relative: str):
    receipt = _fixture(tmp_path)
    (tmp_path / relative).write_text("mutated\n", encoding="utf-8")
    with pytest.raises(ValueError, match="(SHA-256 mismatch|byte-size mismatch)"):
        verify_receipt(receipt, root=tmp_path)


def test_matching_bound_artifact_symlink_is_not_accepted(tmp_path: Path):
    receipt = _fixture(tmp_path)
    requirements = tmp_path / ANALYSIS_REQUIREMENTS
    retained = tmp_path / "retained-requirements.txt"
    requirements.rename(retained)
    requirements.symlink_to(retained)

    with pytest.raises(ValueError, match="regular file"):
        verify_receipt(receipt, root=tmp_path)


def test_matching_bound_artifacts_through_symlinked_parent_are_not_accepted(
    tmp_path: Path,
):
    receipt = _fixture(tmp_path)
    paper = tmp_path / "paper"
    retained = tmp_path / "retained-paper"
    paper.rename(retained)
    paper.symlink_to(retained, target_is_directory=True)

    with pytest.raises(ValueError, match="regular file"):
        verify_receipt(receipt, root=tmp_path)


def test_configuration_drift_invalidates_receipt(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt["frozen_configuration"]["bootstrap_draws"] += 1
    with pytest.raises(ValueError, match="frozen configuration"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_verified_inputs_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt.pop("verified_inputs")
    with pytest.raises(ValueError, match="embed the verified analysis inputs"):
        verify_receipt(receipt, root=tmp_path)


def test_tampered_input_aggregate_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt["input_manifest_aggregate_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="aggregate research-artifact fingerprint mismatch"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_analysis_environment_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt.pop("analysis_environment")
    with pytest.raises(ValueError, match="Python environment"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_python_version_contract_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt["analysis_environment"].pop("python_version")
    with pytest.raises(ValueError, match="Python environment"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_provenance_builder_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt.pop("provenance_builder")
    with pytest.raises(ValueError, match="canonical provenance builder"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_verification_chain_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt.pop("verification_implementations")
    with pytest.raises(ValueError, match="complete canonical verification chain"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_output_verifier_identity_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt["verification_implementations"].pop("output_consistency")
    with pytest.raises(ValueError, match="complete canonical verification chain"):
        verify_receipt(receipt, root=tmp_path)


def test_receipt_without_verified_outputs_fails_closed(tmp_path: Path):
    receipt = _fixture(tmp_path); receipt.pop("verified_outputs")
    with pytest.raises(ValueError, match="bind exactly both"):
        verify_receipt(receipt, root=tmp_path)


@pytest.mark.parametrize(("key", "canonical", "alternate"), [
    ("canonical_inference", "outputs/main_study_inference.json", "outputs/alternate_inference.json"),
    ("manuscript_rendering", "paper/MAIN_STUDY_INFERENCE.md", "paper/ALTERNATE_INFERENCE.md"),
])
def test_verified_output_path_substitution_fails_closed(tmp_path: Path, key: str, canonical: str, alternate: str):
    receipt = _fixture(tmp_path)
    alternate_path = tmp_path / alternate
    alternate_path.parent.mkdir(parents=True, exist_ok=True)
    alternate_path.write_bytes((tmp_path / canonical).read_bytes())
    receipt["verified_outputs"][key] = {"path": alternate, "sha256": _digest(alternate_path)}
    with pytest.raises(ValueError, match="must bind canonical path"):
        verify_receipt(receipt, root=tmp_path)


def test_current_canonical_receipt_independently_recomputes_exact_outputs():
    root = Path(__file__).resolve().parents[1]
    receipt = json.loads(
        (root / provenance.DEFAULT_RECEIPT).read_text(encoding="utf-8")
    )

    provenance.verify_recomputed_outputs(receipt, root=root)


def test_rehashed_renderer_consistent_outcome_forgery_fails_recomputation(
    tmp_path: Path,
):
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "scripts/analyze_main_study.py",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "outputs/main_study_inference.json",
        "paper/MAIN_STUDY_INFERENCE.md",
    ):
        source = root / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    receipt = json.loads(
        (root / provenance.DEFAULT_RECEIPT).read_text(encoding="utf-8")
    )
    forged = json.loads(
        (tmp_path / "outputs/main_study_inference.json").read_text(
            encoding="utf-8"
        )
    )
    forged["variant_summary"]["D3"]["means"]["strict_support_rate"] = 0.999
    forged_json = json.dumps(forged, indent=2, sort_keys=True).encode("utf-8")
    forged_markdown = analyze_main_study._markdown(forged).encode("utf-8")
    (tmp_path / "outputs/main_study_inference.json").write_bytes(forged_json)
    (tmp_path / "paper/MAIN_STUDY_INFERENCE.md").write_bytes(forged_markdown)
    receipt["verified_outputs"]["canonical_inference"]["sha256"] = (
        hashlib.sha256(forged_json).hexdigest()
    )
    receipt["verified_outputs"]["manuscript_rendering"]["sha256"] = (
        hashlib.sha256(forged_markdown).hexdigest()
    )

    with pytest.raises(ValueError, match="independently recomputed canonical JSON"):
        provenance.verify_recomputed_outputs(receipt, root=tmp_path)


def test_recomputation_rejects_symlinked_published_output(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "scripts/analyze_main_study.py",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "outputs/main_study_inference.json",
        "paper/MAIN_STUDY_INFERENCE.md",
    ):
        source = root / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    receipt = json.loads(
        (root / provenance.DEFAULT_RECEIPT).read_text(encoding="utf-8")
    )
    canonical = tmp_path / "outputs/main_study_inference.json"
    replacement = tmp_path / "replacement.json"
    canonical.rename(replacement)
    canonical.symlink_to(replacement)

    with pytest.raises(ValueError, match="published canonical inference.*regular file"):
        provenance.verify_recomputed_outputs(receipt, root=tmp_path)


def test_recomputation_rejects_analysis_implementation_drift(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "scripts/analyze_main_study.py",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "outputs/main_study_inference.json",
        "paper/MAIN_STUDY_INFERENCE.md",
    ):
        source = root / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    receipt = json.loads(
        (root / provenance.DEFAULT_RECEIPT).read_text(encoding="utf-8")
    )
    implementation = tmp_path / "scripts/analyze_main_study.py"
    implementation.write_bytes(implementation.read_bytes() + b"\n# drift\n")

    with pytest.raises(
        ValueError,
        match="analysis implementation does not match recomputation receipt",
    ):
        provenance.verify_recomputed_outputs(receipt, root=tmp_path)


def test_recomputation_ignores_inherited_python_startup_paths(
    tmp_path: Path,
    monkeypatch,
):
    poison = tmp_path / "poison"
    poison.mkdir()
    (poison / "sitecustomize.py").write_text(
        "import os\nos._exit(91)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(poison))
    root = Path(__file__).resolve().parents[1]
    receipt = json.loads(
        (root / provenance.DEFAULT_RECEIPT).read_text(encoding="utf-8")
    )

    provenance.verify_recomputed_outputs(receipt, root=root)


def _copy_recomputation_fixture(tmp_path: Path) -> tuple[Path, dict]:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "scripts/analyze_main_study.py",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "outputs/main_study_inference.json",
        "paper/MAIN_STUDY_INFERENCE.md",
    ):
        source = root / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    receipt = json.loads(
        (root / provenance.DEFAULT_RECEIPT).read_text(encoding="utf-8")
    )
    return tmp_path, receipt


def test_recomputation_rejects_same_byte_published_output_inode_replacement(
    tmp_path: Path,
    monkeypatch,
):
    root, receipt = _copy_recomputation_fixture(tmp_path)
    artifact = root / "outputs/main_study_inference.json"
    detached = root / "outputs/detached-main-study-inference.json"
    real_run = provenance.subprocess.run

    def replace_after_recomputation(*args, **kwargs):
        completed = real_run(*args, **kwargs)
        content = artifact.read_bytes()
        artifact.rename(detached)
        artifact.write_bytes(content)
        return completed

    monkeypatch.setattr(provenance.subprocess, "run", replace_after_recomputation)

    with pytest.raises(
        ValueError,
        match="published canonical inference JSON changed during independent recomputation",
    ):
        provenance.verify_recomputed_outputs(receipt, root=root)


def test_recomputation_rejects_same_byte_input_inode_replacement(
    tmp_path: Path,
    monkeypatch,
):
    root, receipt = _copy_recomputation_fixture(tmp_path)
    artifact = root / "outputs/main_study_runs.csv"
    detached = root / "outputs/detached-main-study-runs.csv"
    real_run = provenance.subprocess.run

    def replace_after_recomputation(*args, **kwargs):
        completed = real_run(*args, **kwargs)
        content = artifact.read_bytes()
        artifact.rename(detached)
        artifact.write_bytes(content)
        return completed

    monkeypatch.setattr(provenance.subprocess, "run", replace_after_recomputation)

    with pytest.raises(
        ValueError,
        match="analysis input changed during independent recomputation",
    ):
        provenance.verify_recomputed_outputs(receipt, root=root)


def test_recomputation_rejects_directory_rename_during_snapshot_capture(
    tmp_path: Path,
    monkeypatch,
):
    root, receipt = _copy_recomputation_fixture(tmp_path)
    real_open = provenance._open_regular_snapshot_at
    renamed = False

    def rename_outputs_before_first_file(*args, **kwargs):
        nonlocal renamed
        if not renamed:
            renamed = True
            outputs = root / "outputs"
            detached = root / "detached-outputs"
            outputs.rename(detached)
            detached.rename(outputs)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(
        provenance,
        "_open_regular_snapshot_at",
        rename_outputs_before_first_file,
    )

    with pytest.raises(
        ValueError,
        match="repository (root|outputs directory) changed during independent recomputation",
    ):
        provenance.verify_recomputed_outputs(receipt, root=root)


def test_recomputation_rejects_root_rename_after_initial_path_binding(
    tmp_path: Path,
    monkeypatch,
):
    root, receipt = _copy_recomputation_fixture(tmp_path / "repository")
    real_require_binding = provenance._require_directory_path_binding
    renamed = False

    def rename_root_after_binding(*args, **kwargs):
        nonlocal renamed
        real_require_binding(*args, **kwargs)
        if not renamed:
            renamed = True
            detached = root.with_name("detached-repository")
            root.rename(detached)
            detached.rename(root)

    monkeypatch.setattr(
        provenance,
        "_require_directory_path_binding",
        rename_root_after_binding,
    )

    with pytest.raises(
        ValueError,
        match="repository root changed during independent recomputation",
    ):
        provenance.verify_recomputed_outputs(receipt, root=root)
