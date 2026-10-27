"""Regression gate for the independently published frozen 40-cell input digest.

Synthetic attacks modify only temporary copies. The actual historical study,
statistical analysis, evaluator outputs, and human evaluations are untouched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.fingerprint_research_artifacts import build_manifest
from scripts.verify_published_main_study_inputs import (
    FROZEN_INPUTS,
    MANIFEST,
    ROOT,
    FROZEN_INPUT_AGGREGATE_SHA256,
    verify_published_frozen_inputs,
)
from scripts.verify_research_artifact_manifest import verify_manifest_file


def _copied_archive(tmp_path: Path) -> Path:
    for name in (*FROZEN_INPUTS, MANIFEST):
        original = ROOT / name
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(original.read_bytes())
    return tmp_path


def _rehash_local_manifest(root: Path, names: tuple[str, ...]) -> None:
    manifest = build_manifest([root / name for name in names], root=root)
    destination = root / MANIFEST
    destination.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_checked_in_40_cell_inputs_match_published_frozen_anchor():
    result = verify_published_frozen_inputs()
    assert result["status"] == "published_frozen_input_fingerprint_matches"
    assert result["n_input_artifacts"] == 2
    assert result["published_aggregate_sha256"] == FROZEN_INPUT_AGGREGATE_SHA256
    assert result["experimental_treatments_rerun"] is False
    assert result["human_ratings_used"] is False


def test_coherently_rehashed_study_input_and_manifest_cannot_redefine_frozen_anchor(
    tmp_path,
):
    root = _copied_archive(tmp_path)
    source = root / "outputs/posthoc_support_runs.csv"
    original = source.read_bytes()
    needle = b",0.8333333333333334,6181,"
    assert original.count(needle) >= 1
    source.write_bytes(original.replace(needle, b",0.8333333333333334,6182,", 1))
    _rehash_local_manifest(root, FROZEN_INPUTS)

    # A self-consistent local manifest alone cannot distinguish historical
    # evidence from an altered export, whereas the published pin can.
    assert len(verify_manifest_file(root / MANIFEST, root=root)) == 2
    with pytest.raises(ValueError, match="published frozen input aggregate SHA-256 mismatch"):
        verify_published_frozen_inputs(repo_root=root)


def test_subset_manifest_cannot_claim_entire_frozen_matrix(tmp_path):
    root = _copied_archive(tmp_path)
    _rehash_local_manifest(root, FROZEN_INPUTS[:1])
    assert len(verify_manifest_file(root / MANIFEST, root=root)) == 1
    with pytest.raises(ValueError, match="exactly the two canonical CSVs"):
        verify_published_frozen_inputs(repo_root=root)


def test_unmodified_archived_copy_passes_without_writing_or_recomputing(tmp_path):
    root = _copied_archive(tmp_path)
    before = {name: (root / name).read_bytes() for name in (*FROZEN_INPUTS, MANIFEST)}
    assert verify_published_frozen_inputs(repo_root=root)["n_input_artifacts"] == 2
    assert before == {
        name: (root / name).read_bytes() for name in (*FROZEN_INPUTS, MANIFEST)
    }
