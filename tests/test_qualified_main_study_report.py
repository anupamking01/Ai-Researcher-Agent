"""Noncanonical qualified-reporting regressions; no treatment or rating calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import assemble_qualified_main_study_report as qualified
from scripts.verify_published_main_study_inputs import ROOT, FROZEN_INPUTS, MANIFEST


def _checkout(tmp_path: Path) -> Path:
    files = (
        *FROZEN_INPUTS,
        MANIFEST,
        "outputs/main_study_inference.json",
        qualified.HISTORICAL.as_posix(),
        qualified.COVER.as_posix(),
    )
    for relative in files:
        dest = tmp_path / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / relative).read_bytes())
    return tmp_path


def test_historical_results_are_unchanged_and_qualified_before_numbers(tmp_path):
    root = _checkout(tmp_path)
    originals = {
        path.as_posix(): (root / path).read_bytes()
        for path in (qualified.HISTORICAL, qualified.COVER)
    }
    result = qualified.assemble_qualified_report(repo_root=root)
    assert "noncanonical" in result.partition("\n")[0]
    assert result.index("not justified by the design") < result.index(
        "## Original historically frozen inference"
    )
    historical = (root / qualified.HISTORICAL).read_text()
    assert historical in result
    assert result.count(historical) == 1
    assert "Published frozen CSV aggregate SHA-256:" in result
    assert originals == {
        path.as_posix(): (root / path).read_bytes()
        for path in (qualified.HISTORICAL, qualified.COVER)
    }


def test_missing_cover_fails_before_export(tmp_path):
    root = _checkout(tmp_path)
    (root / qualified.COVER).unlink()
    with pytest.raises(ValueError, match="reporting source"):
        qualified.assemble_qualified_report(repo_root=root)


def test_disclosure_removal_fails_even_though_frozen_results_are_unchanged(tmp_path):
    root = _checkout(tmp_path)
    cover = root / qualified.COVER
    cover.write_text(cover.read_text().replace(
        "not justified by the design as a randomization test",
        "justified by the design as a randomization test",
    ))
    with pytest.raises(ValueError, match="required scientific limitation"):
        qualified.assemble_qualified_report(repo_root=root)


def test_changed_historical_report_cannot_be_reframed_as_canonical(tmp_path):
    root = _checkout(tmp_path)
    historical = root / qualified.HISTORICAL
    historical.write_text(historical.read_text().replace(
        "Mean paired difference:", "Revised paired difference:"
    ))
    with pytest.raises(ValueError, match="does not match canonical JSON"):
        qualified.assemble_qualified_report(repo_root=root)


def test_coherent_claim_relabel_with_changed_frozen_csv_fails_pin(tmp_path):
    root = _checkout(tmp_path)
    csv = root / FROZEN_INPUTS[0]
    csv.write_bytes(csv.read_bytes().replace(b"estimated_from_frozen_uncached_rates",
                                             b"provider_billed_actual_cost"))
    with pytest.raises(ValueError, match="(mismatch|changed|SHA-256)"):
        qualified.assemble_qualified_report(repo_root=root)


def test_late_report_mutation_is_detected(tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    original = qualified.verify_outputs
    calls = 0

    def change_after_first_verification(*, root):
        nonlocal calls
        calls += 1
        original(root=root)
        if calls == 1:
            cover = root / qualified.COVER
            cover.write_bytes(cover.read_bytes() + b"\nNew disclosure?\n")

    monkeypatch.setattr(qualified, "verify_outputs", change_after_first_verification)
    with pytest.raises(ValueError, match="changed before export"):
        qualified.assemble_qualified_report(repo_root=root)
