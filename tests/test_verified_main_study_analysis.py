"""Tests for the provenance-gated main-study analysis entry point."""
from pathlib import Path

import pytest

from scripts.fingerprint_research_artifacts import build_manifest
from scripts.run_verified_main_study_analysis import verify_and_run


MAIN_HEADER = "successful_sources,total_tokens,treatment_cost_usd,latency_seconds,model_calls,report_words\n"
MAIN_ROW = "2,100,0.05,1.2,3,250\n"
SUPPORT_HEADER = "claims_checked,supported,partially_supported,unsupported,contradicted\n"
SUPPORT_ROW = "4,2,1,1,0\n"


def _study(tmp_path: Path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    main = outputs / "main_study_runs.csv"
    support = outputs / "posthoc_support_runs.csv"
    main.write_text(MAIN_HEADER + MAIN_ROW, encoding="utf-8")
    support.write_text(SUPPORT_HEADER + SUPPORT_ROW, encoding="utf-8")
    return main, support


def test_verified_gate_runs_analysis_only_after_checks(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []

    result = verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 7)

    assert result == 7
    assert calls == ["ran"]


def test_verified_gate_blocks_mutated_input_before_analysis(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    main.write_text(MAIN_HEADER + "9,100,0.05,1.2,3,250\n", encoding="utf-8")
    calls = []

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 0)
    assert calls == []


def test_verified_gate_rejects_manifest_for_wrong_artifacts(tmp_path):
    main, _ = _study(tmp_path)
    manifest = build_manifest([main], root=tmp_path)
    calls = []

    with pytest.raises(ValueError, match="exactly the canonical analysis inputs"):
        verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 0)
    assert calls == []


def test_verified_gate_blocks_invalid_scientific_counts(tmp_path):
    main, support = _study(tmp_path)
    support.write_text(SUPPORT_HEADER + "4,2.5,0.5,1,0\n", encoding="utf-8")
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []

    with pytest.raises(ValueError, match="non-integer value"):
        verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 0)
    assert calls == []
