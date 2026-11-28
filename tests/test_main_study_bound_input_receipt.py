"""Synthetic source-generation binding regressions; no scientific reruns."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts import audit_main_study_bound_inputs as bound
from scripts import audit_main_study_numeric_inputs as numeric
from scripts.verify_published_main_study_inputs import (
    FROZEN_INPUTS, FROZEN_INPUT_AGGREGATE_SHA256, MANIFEST, ROOT,
    verify_published_frozen_inputs,
)


def _copy_published_inputs(tmp_path: Path) -> Path:
    for relative in (*FROZEN_INPUTS, MANIFEST):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return tmp_path


def _alter_semantically_valid_count(root: Path) -> None:
    path = root / numeric.MAIN_PATH
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    assert fields is not None and len(rows) == 40
    rows[0]["model_calls"] = str(int(rows[0]["model_calls"]) + 1)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_source_verifier_exposes_fingerprints_of_checked_in_inputs():
    receipt = verify_published_frozen_inputs()
    assert set(receipt["verified_input_sha256"]) == set(FROZEN_INPUTS)
    assert receipt["verified_input_sha256"] == numeric.audit_files()["input_sha256"]


def test_untouched_archived_copy_passes_without_modification(tmp_path):
    root = _copy_published_inputs(tmp_path)
    before = {name: (root / name).read_bytes() for name in (*FROZEN_INPUTS, MANIFEST)}
    receipt = bound.verify_bound_numeric_inputs(repo_root=root)
    assert receipt["n_cells"] == 40
    assert receipt["numeric_snapshot_bound_to_published_inputs"] is True
    assert receipt["published_input_aggregate_sha256"] == FROZEN_INPUT_AGGREGATE_SHA256
    assert receipt["original_treatment_report_trace_source_authenticated"] is False
    assert before == {name: (root / name).read_bytes() for name in (*FROZEN_INPUTS, MANIFEST)}


def test_post_verifier_csv_swap_cannot_combine_two_individual_passes(tmp_path, monkeypatch):
    root = _copy_published_inputs(tmp_path)
    verifier = bound.verify_published_frozen_inputs

    def replace_after_source_verification(*, repo_root):
        source_receipt = verifier(repo_root=repo_root)
        _alter_semantically_valid_count(repo_root)
        # This altered CSV passes the independent semantic check alone.
        assert numeric.audit_files(repo_root)["n_cells"] == 40
        return source_receipt

    monkeypatch.setattr(bound, "verify_published_frozen_inputs", replace_after_source_verification)
    with pytest.raises(numeric.NumericInputError, match="different from.*checked generation"):
        bound.verify_bound_numeric_inputs(repo_root=root)


def test_modified_csv_before_verification_fails_published_pin(tmp_path):
    root = _copy_published_inputs(tmp_path)
    _alter_semantically_valid_count(root)
    assert numeric.audit_files(root)["n_cells"] == 40
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        bound.verify_bound_numeric_inputs(repo_root=root)
