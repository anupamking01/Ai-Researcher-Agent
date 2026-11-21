"""Synthetic, offline recovered-ZIP matrix checks; no treatment or evaluator reruns."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

import pytest

from scripts import audit_recovered_artifact_treatment_matrix as matrix
from scripts import preflight_recovered_artifact_zip as preflight
from scripts import verify_human_eval_automated_run_lineage as lineage


def _paths():
    csv_path = matrix.REPO_ROOT / lineage.SUPPORT_REL
    csv_bytes, _generation = matrix._capture_evaluator(csv_path)
    return matrix._expected_paths(csv_bytes, csv_path=csv_path)


def _make_zip(tmp_path, *, prefix="", edit=None, compression=zipfile.ZIP_STORED):
    traces, reports = _paths()
    files = {
        prefix + name: b'{"synthetic_fixture_only": true}'
        for name in sorted(traces)
    }
    files.update({
        prefix + name: b"# Synthetic report; not an experimental output\n"
        for name in sorted(reports)
    })
    if edit is not None:
        edit(files, traces, reports)
    path = tmp_path / "synthetic-recovered.zip"
    with zipfile.ZipFile(path, "w", compression=compression) as out:
        for name, payload in sorted(files.items()):
            out.writestr(name, payload)
    return path


def _anchor_zip(monkeypatch, path, *, role="original_treatment"):
    pinned = preflight.GITHUB_JOB_LOG_ARCHIVES[role]
    synthetic = {
        **pinned,
        "zip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }
    monkeypatch.setattr(preflight, "GITHUB_JOB_LOG_ARCHIVES", {
        **preflight.GITHUB_JOB_LOG_ARCHIVES, role: synthetic,
    })


@pytest.mark.parametrize("prefix", ("", "outputs/"))
@pytest.mark.parametrize("role", ("original_treatment", "evaluator_recovery"))
def test_complete_40_cell_member_matrix_is_a_non_authentication_diagnostic(
    tmp_path, monkeypatch, role, prefix
):
    path = _make_zip(tmp_path, prefix=prefix)
    _anchor_zip(monkeypatch, path, role=role)
    receipt = matrix.audit_recovered_treatment_matrix(path, artifact_role=role)
    assert receipt["trace_members_matched"] == 40
    assert receipt["report_members_matched"] == 40
    assert receipt["source_layout_prefix"] == prefix
    assert receipt["unselected_trace_or_report_members"] == 0
    assert receipt["github_job_log_zip_correspondence"]["artifact_role"] == role
    assert receipt["caller_claimed_independent_zip_pin_matched"] is False
    assert receipt["independent_archive_custody_verified"] is False
    assert receipt["trace_contents_verified"] is False
    assert receipt["report_contents_verified"] is False
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert list(tmp_path.iterdir()) == [path]


def test_missing_original_report_prevents_a_complete_matrix_claim(tmp_path, monkeypatch):
    def omit(files, traces, reports):
        files.pop(sorted(reports)[0])
    path = _make_zip(tmp_path, edit=omit)
    _anchor_zip(monkeypatch, path)
    with pytest.raises(matrix.RecoveryMatrixError, match="complete published"):
        matrix.audit_recovered_treatment_matrix(path, artifact_role="original_treatment")


def test_mislabelled_variant_trace_is_not_selected_by_count(tmp_path, monkeypatch):
    def relocate(files, traces, reports):
        original = sorted(traces)[0]
        files["experiment_traces/P6V/" + original.split("/")[-1]] = files.pop(original)
    path = _make_zip(tmp_path, edit=relocate)
    _anchor_zip(monkeypatch, path)
    with pytest.raises(matrix.RecoveryMatrixError, match="complete published"):
        matrix.audit_recovered_treatment_matrix(path, artifact_role="original_treatment")


@pytest.mark.parametrize("extra", [
    "experiment_traces/D3/unselected.json",
    "outputs/experiment_traces/D3/hidden.json",
    "extra-run/research_report.md",
    "research_report.md",
])
def test_unselected_evidence_cannot_hide_beside_complete_frozen_matrix(
    tmp_path, monkeypatch, extra
):
    def add(files, traces, reports):
        files[extra] = b"unselected synthetic fixture"
    path = _make_zip(tmp_path, edit=add)
    _anchor_zip(monkeypatch, path)
    with pytest.raises(matrix.RecoveryMatrixError, match="unselected treatment"):
        matrix.audit_recovered_treatment_matrix(path, artifact_role="original_treatment")


def test_mixed_layouts_cannot_stand_in_for_an_exact_complete_matrix(tmp_path, monkeypatch):
    def mix(files, traces, reports):
        name = sorted(traces)[0]
        files["outputs/" + name] = files.pop(name)
    path = _make_zip(tmp_path, edit=mix)
    _anchor_zip(monkeypatch, path)
    with pytest.raises(matrix.RecoveryMatrixError, match="complete published"):
        matrix.audit_recovered_treatment_matrix(path, artifact_role="original_treatment")


def test_unpinned_new_zip_cannot_claim_historical_github_correspondence(tmp_path):
    path = _make_zip(tmp_path)
    with pytest.raises(preflight.RecoveredArchiveError, match="historical GitHub"):
        matrix.audit_recovered_treatment_matrix(path, artifact_role="original_treatment")


def test_unknown_role_is_rejected_before_reading_archive(tmp_path):
    with pytest.raises(matrix.RecoveryMatrixError, match="pinned historical"):
        matrix.audit_recovered_treatment_matrix(
            tmp_path / "does-not-exist.zip", artifact_role="unrelated"
        )


def test_mutated_frozen_evaluator_does_not_authorize_member_selection(
    tmp_path, monkeypatch
):
    path = _make_zip(tmp_path)
    _anchor_zip(monkeypatch, path)
    root = tmp_path / "checkout"
    (root / "outputs").mkdir(parents=True)
    source = matrix.REPO_ROOT / lineage.SUPPORT_REL
    (root / lineage.SUPPORT_REL).write_bytes(
        source.read_bytes().replace(b"D3,main-01", b"D3,main-99", 1)
    )
    with pytest.raises(matrix.RecoveryMatrixError, match="frozen input fingerprint"):
        matrix.audit_recovered_treatment_matrix(
            path, artifact_role="original_treatment", repo_root=root
        )


def test_same_byte_source_replacement_during_zip_inspection_fails_closed(
    tmp_path, monkeypatch
):
    path = _make_zip(tmp_path)
    _anchor_zip(monkeypatch, path)
    root = tmp_path / "checkout"
    (root / "outputs").mkdir(parents=True)
    csv_path = root / lineage.SUPPORT_REL
    csv_path.write_bytes((matrix.REPO_ROOT / lineage.SUPPORT_REL).read_bytes())
    original_preflight = preflight.audit_recovered_zip

    def swap_csv(*args, **kwargs):
        receipt = original_preflight(*args, **kwargs)
        replacement = csv_path.with_suffix(".replacement")
        replacement.write_bytes(csv_path.read_bytes())
        os.replace(replacement, csv_path)
        return receipt

    monkeypatch.setattr(preflight, "audit_recovered_zip", swap_csv)
    with pytest.raises(matrix.RecoveryMatrixError, match="changed during ZIP inspection"):
        matrix.audit_recovered_treatment_matrix(
            path, artifact_role="original_treatment", repo_root=root
        )


def test_observed_content_manifest_binds_all_published_cells_without_authentication(
    tmp_path, monkeypatch
):
    path = _make_zip(tmp_path)
    _anchor_zip(monkeypatch, path)
    receipt = matrix.audit_recovered_treatment_matrix(path, artifact_role="original_treatment")
    manifest = receipt["observed_source_content_manifest"]
    assert manifest["schema_version"] == 1
    assert len(manifest["cells"]) == 40
    assert len({(c["treatment"], c["task_id"], c["run_id"]) for c in manifest["cells"]}) == 40
    assert manifest["cells"] == sorted(
        manifest["cells"], key=lambda c: (c["treatment"], c["task_id"])
    )
    assert all(c["trace_uncompressed_bytes"] > 0 and
               c["report_uncompressed_bytes"] > 0 for c in manifest["cells"])
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    assert receipt["observed_source_content_manifest_sha256"] == hashlib.sha256(
        encoded
    ).hexdigest()
    assert receipt["source_content_fingerprint_independently_retained"] is False
    assert receipt["historical_evidence_authenticated"] is False


def test_source_content_digest_survives_zip_repackaging_and_outputs_prefix(
    tmp_path, monkeypatch
):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _make_zip(first_dir)
    _anchor_zip(monkeypatch, first)
    one = matrix.audit_recovered_treatment_matrix(first, artifact_role="original_treatment")
    second = _make_zip(
        second_dir, prefix="outputs/", compression=zipfile.ZIP_DEFLATED
    )
    _anchor_zip(monkeypatch, second)
    two = matrix.audit_recovered_treatment_matrix(second, artifact_role="original_treatment")
    assert one["zip_sha256_observed_now"] != two["zip_sha256_observed_now"]
    assert one["observed_source_content_manifest"] == two["observed_source_content_manifest"]
    assert (
        one["observed_source_content_manifest_sha256"]
        == two["observed_source_content_manifest_sha256"]
    )


def test_source_content_digest_changes_when_a_single_report_body_changes(
    tmp_path, monkeypatch
):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _make_zip(first_dir)
    _anchor_zip(monkeypatch, first)
    one = matrix.audit_recovered_treatment_matrix(first, artifact_role="original_treatment")

    def mutate_one_report(files, traces, reports):
        name = sorted(reports)[0]
        files[name] += b"\nSynthetic change to original report bytes.\n"

    second = _make_zip(second_dir, edit=mutate_one_report)
    _anchor_zip(monkeypatch, second)
    two = matrix.audit_recovered_treatment_matrix(second, artifact_role="original_treatment")
    assert (
        one["observed_source_content_manifest_sha256"]
        != two["observed_source_content_manifest_sha256"]
    )
    assert sum(
        a["report_sha256"] != b["report_sha256"]
        for a, b in zip(
            one["observed_source_content_manifest"]["cells"],
            two["observed_source_content_manifest"]["cells"],
        )
    ) == 1


def test_unrelated_zip_member_does_not_change_selected_source_digest(
    tmp_path, monkeypatch
):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = _make_zip(first_dir)
    _anchor_zip(monkeypatch, first)
    one = matrix.audit_recovered_treatment_matrix(first, artifact_role="original_treatment")

    def add_unrelated_member(files, traces, reports):
        files["recovery_notes.txt"] = b"synthetic non-evidence metadata"

    second = _make_zip(second_dir, edit=add_unrelated_member)
    _anchor_zip(monkeypatch, second)
    two = matrix.audit_recovered_treatment_matrix(second, artifact_role="original_treatment")
    assert one["zip_sha256_observed_now"] != two["zip_sha256_observed_now"]
    assert (
        one["observed_source_content_manifest_sha256"]
        == two["observed_source_content_manifest_sha256"]
    )
    assert two["historical_evidence_authenticated"] is False


def test_cli_produces_explicit_non_custody_receipt(tmp_path, monkeypatch, capsys):
    path = _make_zip(tmp_path)
    _anchor_zip(monkeypatch, path)
    monkeypatch.setattr(sys, "argv", [
        "audit_recovered_artifact_treatment_matrix", str(path),
        "--artifact-role", "original_treatment",
    ])
    assert matrix.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"].endswith("_not_authenticated")
    assert receipt["trace_members_matched"] == 40
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_ratings_generated"] is False
