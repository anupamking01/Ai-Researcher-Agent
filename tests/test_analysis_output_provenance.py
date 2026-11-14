"""Tests for cryptographic binding of verified manuscript-facing outputs."""
import hashlib
from pathlib import Path

import pytest

from scripts.run_verified_main_study_analysis import _bind_verified_outputs


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_verified_outputs_are_hash_bound_without_mutating_preflight_receipt(tmp_path: Path):
    outputs = tmp_path / "outputs"
    paper = tmp_path / "paper"
    outputs.mkdir()
    paper.mkdir()
    canonical = b'{"result":"measured"}\n'
    manuscript = b"# Main-study inference\n\nMeasured result.\n"
    (outputs / "main_study_inference.json").write_bytes(canonical)
    (paper / "MAIN_STUDY_INFERENCE.md").write_bytes(manuscript)
    preflight = {"schema_version": 1, "input_manifest_aggregate_sha256": "abc"}

    receipt = _bind_verified_outputs(preflight, root=tmp_path)

    assert preflight == {"schema_version": 1, "input_manifest_aggregate_sha256": "abc"}
    assert receipt["verified_outputs"] == {
        "canonical_inference": {
            "path": "outputs/main_study_inference.json",
            "sha256": _sha256(canonical),
        },
        "manuscript_rendering": {
            "path": "paper/MAIN_STUDY_INFERENCE.md",
            "sha256": _sha256(manuscript),
        },
    }


def test_output_mutation_changes_success_attestation(tmp_path: Path):
    outputs = tmp_path / "outputs"
    paper = tmp_path / "paper"
    outputs.mkdir()
    paper.mkdir()
    json_path = outputs / "main_study_inference.json"
    markdown_path = paper / "MAIN_STUDY_INFERENCE.md"
    json_path.write_text('{"effect":0.1}\n', encoding="utf-8")
    markdown_path.write_text("effect: 0.1\n", encoding="utf-8")

    before = _bind_verified_outputs({}, root=tmp_path)
    markdown_path.write_text("effect: 0.2\n", encoding="utf-8")
    after = _bind_verified_outputs({}, root=tmp_path)

    assert before["verified_outputs"]["canonical_inference"] == after["verified_outputs"]["canonical_inference"]
    assert before["verified_outputs"]["manuscript_rendering"]["sha256"] != after["verified_outputs"]["manuscript_rendering"]["sha256"]


def test_output_binding_fails_closed_when_verified_artifact_is_missing(tmp_path: Path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "paper").mkdir()
    (tmp_path / "outputs" / "main_study_inference.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="verified analysis output is missing"):
        _bind_verified_outputs({}, root=tmp_path)
