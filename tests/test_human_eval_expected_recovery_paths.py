"""Read-only frozen-run recovery targets, including incomplete backup sets."""
import csv
import hashlib
from pathlib import Path

import pytest

from scripts import audit_human_eval_archive_readiness as audit


def _frozen_stub(tmp_path: Path, monkeypatch):
    """Synthetic 4x10 matrix; publication verification mocked for test only."""
    root = tmp_path
    outputs = root / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "main_study_runs.csv").write_text("synthetic", encoding="utf-8")
    (outputs / "main_study_analysis_inputs_manifest.json").write_text(
        "synthetic", encoding="utf-8"
    )
    with (outputs / "posthoc_support_runs.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("variant_id", "task_id", "run_id")
        )
        writer.writeheader()
        for variant in audit.VARIANTS:
            for task_id in audit.lineage.TASKS:
                writer.writerow({
                    "variant_id": variant,
                    "task_id": task_id,
                    "run_id": f"{variant.lower()}-{task_id}",
                })
    monkeypatch.setattr(
        audit.published, "verify_published_frozen_inputs",
        lambda **kwargs: None,
    )
    # Use the synthetic evaluator digest only in this mocked-anchor fixture.
    monkeypatch.setattr(audit, "PUBLISHED_CSV_FILE_SHA256", {
        audit.lineage.SUPPORT_REL: hashlib.sha256(
            (root / audit.lineage.SUPPORT_REL).read_bytes()
        ).hexdigest()
    })
    return root


def test_empty_original_archive_yields_all_40_exact_missing_paths(
    tmp_path, monkeypatch
):
    root = _frozen_stub(tmp_path, monkeypatch)
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    receipt = audit.audit_archive_readiness(repo_root=root)
    targets = receipt["expected_recovery_paths"]
    assert targets["status"] == "expected_paths_missing_or_unsafe"
    assert targets["expected"] == 40
    assert (targets["traces_present"], targets["reports_present"]) == (0, 0)
    assert len(targets["missing_traces"]) == 40
    assert len(targets["missing_reports"]) == 40
    assert targets["missing_traces"][0] == {
        "variant_id": "D3", "task_id": "main-01",
        "run_id": "d3-main-01", "relative_path": "D3/d3-main-01.json",
        "reason": "missing",
    }
    assert targets["missing_reports"][0]["relative_path"] == (
        "d3-main-01/research_report.md"
    )
    assert "original_expected_run_archive_paths" in receipt["blockers"]
    assert receipt["handoff_verified"] is False
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == before


def test_partial_archives_list_only_unrecovered_expected_files(
    tmp_path, monkeypatch
):
    root = _frozen_stub(tmp_path, monkeypatch)
    outputs = root / "outputs"
    trace = outputs / "experiment_traces/D3/d3-main-01.json"
    trace.parent.mkdir(parents=True)
    trace.write_text("not authenticated", encoding="utf-8")
    report = outputs / "d3-main-01/research_report.md"
    report.parent.mkdir()
    report.write_text("not authenticated", encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=root)
    targets = receipt["expected_recovery_paths"]
    assert (targets["traces_present"], targets["reports_present"]) == (1, 1)
    assert len(targets["missing_traces"]) == 39
    assert len(targets["missing_reports"]) == 39
    assert not any(x["run_id"] == "d3-main-01"
                   for x in targets["missing_traces"])
    assert receipt["trace_report_content"]["status"] == (
        "not_checked_without_published_run_identity"
    )
    assert receipt["handoff_verified"] is False


def test_unsafe_recovered_candidates_are_separate_from_missing(
    tmp_path, monkeypatch
):
    root = _frozen_stub(tmp_path, monkeypatch)
    outputs = root / "outputs"
    foreign = tmp_path / "foreign.txt"
    foreign.write_text("untrusted", encoding="utf-8")
    trace = outputs / "experiment_traces/D3/d3-main-01.json"
    trace.parent.mkdir(parents=True)
    try:
        trace.symlink_to(foreign)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this test filesystem")
    report = outputs / "d3-main-01/research_report.md"
    report.parent.mkdir()
    report.symlink_to(foreign)

    targets = audit.audit_archive_readiness(repo_root=root)["expected_recovery_paths"]
    assert targets["traces_present"] == 0
    assert targets["reports_present"] == 0
    assert len(targets["missing_traces"]) == 39
    assert len(targets["missing_reports"]) == 39
    assert targets["unsafe_traces"][0]["reason"] == "unsafe_file_type"
    assert targets["unsafe_reports"][0]["reason"] == "unsafe_file_type"
    assert targets["unsafe_traces"][0]["run_id"] == "d3-main-01"


def test_missing_published_anchor_never_exposes_untrusted_expected_ids(tmp_path):
    targets = audit._expected_recovery_paths(
        repo_root=tmp_path,
        trace_root=tmp_path / "not-there",
        report_root=tmp_path / "not-there",
        published_input_anchor="verification_failed",
    )
    assert targets["status"] == "not_checked_without_published_input_anchor"
    assert targets["missing_traces"] == []
    assert targets["missing_reports"] == []
    assert targets["traces_present"] == 0


def test_invalid_frozen_evaluator_matrix_blocks_target_reconstruction(
    tmp_path, monkeypatch
):
    root = _frozen_stub(tmp_path, monkeypatch)
    csv_path = root / "outputs/posthoc_support_runs.csv"
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    # Duplicate run identity in two distinct frozen cells.
    rows[2] = rows[2].replace("d3-main-02", "d3-main-01")
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=root)
    targets = receipt["expected_recovery_paths"]
    assert targets["status"] == "invalid_published_evaluator_run_ids"
    assert targets["missing_traces"] == []
    assert targets["missing_reports"] == []
    assert "original_expected_run_archive_paths" in receipt["blockers"]
    assert receipt["handoff_verified"] is False
