"""Regression tests for canonical input-path binding in provenance verification."""
from pathlib import Path

import pytest

from scripts.fingerprint_research_artifacts import build_manifest
from scripts.verify_analysis_provenance import CANONICAL_INPUTS, _verify_inputs


def _receipt(tmp_path: Path) -> dict:
    paths = []
    for relative in sorted(CANONICAL_INPUTS):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture for {relative}\n", encoding="utf-8")
        paths.append(path)
    manifest = build_manifest(paths, root=tmp_path)
    return {
        "input_manifest_aggregate_sha256": manifest["aggregate_sha256"],
        "verified_inputs": manifest["artifacts"],
    }


def test_canonical_input_paths_verify(tmp_path: Path):
    _verify_inputs(_receipt(tmp_path), root=tmp_path)


def test_byte_identical_alternate_input_path_is_rejected(tmp_path: Path):
    """A copied input must not be accepted as the canonical analysis dataset."""
    receipt = _receipt(tmp_path)
    original = tmp_path / "outputs/main_study_runs.csv"
    alternate = tmp_path / "outputs/alternate_main_study_runs.csv"
    alternate.write_bytes(original.read_bytes())

    manifest = build_manifest(
        [alternate, tmp_path / "outputs/posthoc_support_runs.csv"],
        root=tmp_path,
    )
    receipt["verified_inputs"] = manifest["artifacts"]
    receipt["input_manifest_aggregate_sha256"] = manifest["aggregate_sha256"]

    with pytest.raises(ValueError, match="exactly the canonical analysis input paths"):
        _verify_inputs(receipt, root=tmp_path)


def test_extra_input_path_is_rejected(tmp_path: Path):
    receipt = _receipt(tmp_path)
    extra = tmp_path / "outputs/unrelated.csv"
    extra.write_text("unrelated\n", encoding="utf-8")
    manifest = build_manifest(
        [tmp_path / relative for relative in sorted(CANONICAL_INPUTS)] + [extra],
        root=tmp_path,
    )
    receipt["verified_inputs"] = manifest["artifacts"]
    receipt["input_manifest_aggregate_sha256"] = manifest["aggregate_sha256"]

    with pytest.raises(ValueError, match="exactly the canonical analysis input paths"):
        _verify_inputs(receipt, root=tmp_path)
