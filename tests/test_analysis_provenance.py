"""Regression tests for manuscript-facing analysis provenance receipts."""
from pathlib import Path

import pytest

from scripts.build_analysis_provenance import build_receipt
from scripts.fingerprint_research_artifacts import build_manifest


def _repo_fixture(tmp_path: Path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "paper").mkdir()
    main = tmp_path / "outputs" / "main_study_runs.csv"
    support = tmp_path / "outputs" / "posthoc_support_runs.csv"
    main.write_text("variant_id,task_id\nD3,main-01\n", encoding="utf-8")
    support.write_text("variant_id,task_id\nD3,main-01\n", encoding="utf-8")
    (tmp_path / "scripts" / "analyze_main_study.py").write_text("# frozen analysis\n", encoding="utf-8")
    (tmp_path / "paper" / "ANALYSIS_PLAN.md").write_text("# Frozen plan\n", encoding="utf-8")
    return main, support


def test_receipt_binds_inputs_code_plan_and_configuration(tmp_path):
    main, support = _repo_fixture(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)

    receipt = build_receipt(manifest, root=tmp_path)

    assert receipt["input_manifest_aggregate_sha256"] == manifest["aggregate_sha256"]
    assert len(receipt["analysis_implementation"]["sha256"]) == 64
    assert len(receipt["analysis_plan"]["sha256"]) == 64
    assert receipt["frozen_configuration"]["bootstrap_draws"] == 20_000
    assert receipt["frozen_configuration"]["expected_tasks"] == 10
    assert receipt["frozen_configuration"]["variants"] == ["D3", "D6", "P6", "P6V"]


def test_receipt_changes_when_analysis_code_changes(tmp_path):
    main, support = _repo_fixture(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    before = build_receipt(manifest, root=tmp_path)
    (tmp_path / "scripts" / "analyze_main_study.py").write_text("# changed analysis\n", encoding="utf-8")

    after = build_receipt(manifest, root=tmp_path)

    assert before["analysis_implementation"]["sha256"] != after["analysis_implementation"]["sha256"]


def test_receipt_changes_when_frozen_plan_changes(tmp_path):
    main, support = _repo_fixture(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    before = build_receipt(manifest, root=tmp_path)
    (tmp_path / "paper" / "ANALYSIS_PLAN.md").write_text("# Revised plan\n", encoding="utf-8")

    after = build_receipt(manifest, root=tmp_path)

    assert before["analysis_plan"]["sha256"] != after["analysis_plan"]["sha256"]


def test_receipt_refuses_mutated_input_manifest(tmp_path):
    main, support = _repo_fixture(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    main.write_text("variant_id,task_id\nD6,main-01\n", encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_receipt(manifest, root=tmp_path)
