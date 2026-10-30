"""Synthetic recovered-original-to-evaluator ZIP checks; no live research data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

from scripts import audit_recovered_artifact_treatment_matrix as matrix
from scripts import compare_recovered_artifact_treatment_sources as concordance
from scripts import preflight_recovered_artifact_zip as preflight
from scripts import verify_human_eval_automated_run_lineage as lineage


def _pair(tmp_path, monkeypatch, *, mutate=None, drop=None):
    csv_path = matrix.REPO_ROOT / lineage.SUPPORT_REL
    csv_bytes, _ = matrix._capture_evaluator(csv_path)
    traces, reports = matrix._expected_paths(csv_bytes, csv_path=csv_path)
    files = {
        **{name: b'{"synthetic_fixture_only":true}' for name in sorted(traces)},
        **{name: b"# Synthetic markdown; not a research result\n" for name in sorted(reports)},
    }
    original_path = tmp_path / "original.zip"
    recovered_path = tmp_path / "evaluator-recovery.zip"
    with zipfile.ZipFile(original_path, "w", compression=zipfile.ZIP_STORED) as out:
        for name, data in sorted(files.items()):
            out.writestr(name, data)
    recovered = dict(files)
    if drop:
        del recovered[drop]
    if mutate:
        recovered[mutate] += b"\nSynthetic modification to research source\n"
    recovered = {"outputs/" + name: data for name, data in recovered.items()}
    recovered["recovery_note.txt"] = b"synthetic evaluator-only bookkeeping"
    with zipfile.ZipFile(recovered_path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name, data in sorted(recovered.items()):
            out.writestr(name, data)
    anchors = {}
    for role, path in (
        ("original_treatment", original_path),
        ("evaluator_recovery", recovered_path),
    ):
        anchors[role] = {
            **preflight.GITHUB_JOB_LOG_ARCHIVES[role],
            "zip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }
    monkeypatch.setattr(preflight, "GITHUB_JOB_LOG_ARCHIVES", anchors)
    return original_path, recovered_path, traces, reports


def test_matching_40_sources_survive_repackaging_and_extra_recovery_metadata(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    receipt = concordance.compare_recovered_treatment_sources(original, recovered)
    assert receipt["trace_sources_unchanged"] == 40
    assert receipt["report_sources_unchanged"] == 40
    assert receipt["original_zip_sha256_observed_now"] != receipt[
        "recovery_zip_sha256_observed_now"
    ]
    assert receipt["status"].endswith("_not_authenticated")
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert receipt["independent_archive_custody_verified"] is False
    assert set(tmp_path.iterdir()) == {original, recovered}


@pytest.mark.parametrize("source", ("trace", "report"))
def test_one_changed_original_source_blocks_evaluator_only_lineage(
    tmp_path, monkeypatch, source
):
    csv_path = matrix.REPO_ROOT / lineage.SUPPORT_REL
    raw, _ = matrix._capture_evaluator(csv_path)
    traces, reports = matrix._expected_paths(raw, csv_path=csv_path)
    changed = sorted(traces if source == "trace" else reports)[0]
    original, recovered, _, _ = _pair(tmp_path, monkeypatch, mutate=changed)
    with pytest.raises(
        concordance.RecoveryConcordanceError, match=f"{source}"
    ):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_recovery_zip_missing_source_fails_before_concordance(tmp_path, monkeypatch):
    raw, _ = matrix._capture_evaluator(matrix.REPO_ROOT / lineage.SUPPORT_REL)
    _, reports = matrix._expected_paths(
        raw, csv_path=matrix.REPO_ROOT / lineage.SUPPORT_REL
    )
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, drop=sorted(reports)[0]
    )
    with pytest.raises(matrix.RecoveryMatrixError, match="complete published"):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_role_pin_cannot_be_bypassed_by_a_plausible_source_matrix(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    with zipfile.ZipFile(recovered, "a") as out:
        out.writestr("extra.txt", b"synthetic alteration after pinning")
    with pytest.raises(preflight.RecoveredArchiveError, match="historical GitHub"):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_same_file_cannot_claim_independent_original_and_recovery_roles(
    tmp_path, monkeypatch
):
    original, _, _, _ = _pair(tmp_path, monkeypatch)
    with pytest.raises(concordance.RecoveryConcordanceError, match="distinct"):
        concordance.compare_recovered_treatment_sources(original, original)


def test_independent_pin_argument_is_checked_not_inferred(tmp_path, monkeypatch):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    with pytest.raises(preflight.RecoveredArchiveError, match="independent pin"):
        concordance.compare_recovered_treatment_sources(
            original, recovered, original_expected_archive_sha256="0" * 64,
        )


def test_cli_emits_explicitly_non_authenticating_comparison_receipt(
    tmp_path, monkeypatch, capsys
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [
        "compare_recovered_artifact_treatment_sources",
        "--original-zip", str(original),
        "--recovery-zip", str(recovered),
    ])
    assert concordance.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source_cells_compared"] == 40
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_ratings_generated"] is False
