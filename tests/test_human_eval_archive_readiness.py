"""Synthetic, offline checks for the archive recovery inventory contract."""
import csv
import hashlib
from pathlib import Path

from scripts import audit_human_eval_archive_readiness as audit
from scripts import export_human_eval_annotator_bundle as exporter


def test_missing_archives_are_reported_without_claiming_a_handoff(tmp_path):
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["status"] == "blocked"
    assert result["trace_candidates"]["status"] == "missing"
    assert result["trace_candidates"]["count"] == 0
    assert result["trace_candidates"]["by_variant"] == {
        "D3": 0, "D6": 0, "P6": 0, "P6V": 0,
    }
    assert result["report_candidates"]["status"] == "not_checked_without_trace_candidates"
    assert "coordinator/packet.jsonl" in result["blockers"]
    assert "research_manifest_file" in result["blockers"]
    assert result["handoff_verified"] is False
    assert result["human_ratings_used"] is False
    assert result["treatments_rerun"] is False
    assert not (tmp_path / "outputs").exists()


def test_full_candidate_inventory_is_never_mislabeled_as_verified(tmp_path):
    root = tmp_path
    for relative in (
        "outputs/main_study_analysis_inputs_manifest.json",
        "outputs/main_study_runs.csv",
        "outputs/posthoc_support_runs.csv",
        "experiments/main_budget_tasks.json",
        "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic-not-archived", encoding="utf-8")
    packet = root / "outputs/human_eval"
    for name in exporter.COORDINATOR_ARTIFACTS:
        (packet / name).parent.mkdir(parents=True, exist_ok=True)
        (packet / name).write_text("fixture", encoding="utf-8")
    for order in ("canonical", "reverse"):
        for name in exporter.ANNOTATOR_ARTIFACTS:
            path = packet / f"annotator-{order}-v1" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture", encoding="utf-8")
    for n in range(40):
        path = root / "outputs/experiment_traces/D3" / f"test-{n:02d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    result = audit.audit_archive_readiness(
        repo_root=root,
        research_manifest_sha256="a" * 64,
        coordinator_manifest_sha256="b" * 64,
    )
    assert result["trace_candidates"]["status"] == "candidate_matrix_mismatch"
    assert result["trace_candidates"]["by_variant"]["D3"] == 40
    assert result["published_automated_input_anchor"] == "verification_failed"
    assert result["independent_pins"] == {
        "research_manifest_file": "pin_mismatch",
        "coordinator_manifest_file": "pin_mismatch",
    }
    assert result["status"] == "blocked"
    assert result["handoff_verified"] is False
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == before


def test_symlink_is_not_accepted_as_archived_evidence(tmp_path):
    target = tmp_path / "some-other-file"
    target.write_text("fixture", encoding="utf-8")
    coordinator = tmp_path / "outputs/human_eval"
    coordinator.mkdir(parents=True)
    (coordinator / "packet.jsonl").symlink_to(target)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["resources"]["coordinator/packet.jsonl"] == "unsafe_file_type"
    assert "coordinator/packet.jsonl" in result["blockers"]


def test_trace_count_cannot_be_taken_as_identity_or_validity(tmp_path):
    trace = tmp_path / "outputs/experiment_traces/D3"
    trace.mkdir(parents=True)
    for n in range(39):
        (trace / f"run-{n:02d}.json").write_text("{}", encoding="utf-8")
    first = audit.audit_archive_readiness(repo_root=tmp_path)
    assert first["trace_candidates"]["status"] == "candidate_count_mismatch"
    assert first["trace_candidates"]["count"] == 39
    (trace / "extra.json").write_text("not even JSON", encoding="utf-8")
    second = audit.audit_archive_readiness(repo_root=tmp_path)
    assert second["trace_candidates"]["status"] == "candidate_matrix_mismatch"
    assert second["handoff_verified"] is False


def test_trace_symlink_directory_rejected(tmp_path):
    root = tmp_path / "outputs/experiment_traces"
    root.mkdir(parents=True)
    target = tmp_path / "somewhere"
    target.mkdir()
    (root / "D3").symlink_to(target, target_is_directory=True)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "unsafe_variant_directory"
    assert result["status"] == "blocked"


def test_pin_values_are_not_treated_as_authenticated_evidence(tmp_path):
    result = audit.audit_archive_readiness(
        repo_root=tmp_path,
        research_manifest_sha256="A" * 64,
        coordinator_manifest_sha256="0" * 64,
    )
    assert result["independent_pins"]["research_manifest_file"] == "invalid_pin_format"
    assert result["independent_pins"]["coordinator_manifest_file"] == (
        "pinned_file_missing_or_unsafe"
    )
    assert "research_manifest_file" in result["blockers"]


def _write_candidate_matrix(root: Path, counts: dict[str, int],
                            *, with_reports: bool = True) -> None:
    for variant, count in counts.items():
        for i in range(count):
            run_id = f"{variant.lower()}-run-{i:02d}"
            trace = root / "experiment_traces" / variant / f"{run_id}.json"
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text("not-validated-json", encoding="utf-8")
            if with_reports:
                report = root / run_id / "research_report.md"
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text("not-validated-report", encoding="utf-8")


def test_balanced_matrix_and_reports_are_still_only_candidates(tmp_path):
    _write_candidate_matrix(
        tmp_path / "outputs", {"D3": 10, "D6": 10, "P6": 10, "P6V": 10}
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "40_matrix_candidates_unverified"
    assert result["trace_candidates"]["by_variant"] == dict.fromkeys(
        ("D3", "D6", "P6", "P6V"), 10
    )
    assert result["report_candidates"]["status"] == "40_report_candidates_unverified"
    assert result["report_candidates"]["count"] == 40
    assert result["status"] == "blocked"
    assert result["handoff_verified"] is False


def test_unbalanced_40_traces_cannot_satisfy_the_frozen_matrix(tmp_path):
    _write_candidate_matrix(
        tmp_path / "outputs", {"D3": 11, "D6": 9, "P6": 10, "P6V": 10}
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["count"] == 40
    assert result["trace_candidates"]["status"] == "candidate_matrix_mismatch"
    assert "original_experiment_trace_candidates" in result["blockers"]


def test_duplicate_run_filename_across_variants_is_not_a_unique_report(tmp_path):
    _write_candidate_matrix(
        tmp_path / "outputs", {"D3": 10, "D6": 10, "P6": 10, "P6V": 10}
    )
    d6 = tmp_path / "outputs/experiment_traces/D6/d6-run-00.json"
    d6.rename(d6.with_name("d3-run-00.json"))
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "duplicate_trace_run_id"
    assert result["report_candidates"]["status"] == "not_checked_without_trace_candidates"


def test_missing_markdown_report_blocks_even_a_balanced_trace_inventory(tmp_path):
    _write_candidate_matrix(
        tmp_path / "outputs", {"D3": 10, "D6": 10, "P6": 10, "P6V": 10}
    )
    (tmp_path / "outputs/d6-run-03/research_report.md").unlink()
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "40_matrix_candidates_unverified"
    assert result["report_candidates"]["count"] == 39
    assert result["report_candidates"]["missing_or_unsafe"] == {"missing": 1}
    assert "original_markdown_report_candidates" in result["blockers"]


def test_symlinked_report_parent_cannot_count_as_original_report(tmp_path):
    _write_candidate_matrix(
        tmp_path / "outputs", {"D3": 10, "D6": 10, "P6": 10, "P6V": 10}
    )
    original = tmp_path / "outputs/d6-run-03"
    original.rename(tmp_path / "outputs/retained-d6-run-03")
    original.symlink_to(tmp_path / "outputs/retained-d6-run-03", target_is_directory=True)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["report_candidates"]["count"] == 39
    assert result["report_candidates"]["missing_or_unsafe"] == {
        "unsafe_parent_symlink": 1,
    }


def test_trace_root_symlink_cannot_be_counted(tmp_path):
    _write_candidate_matrix(
        tmp_path / "archive", {"D3": 10, "D6": 10, "P6": 10, "P6V": 10}
    )
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs/experiment_traces").symlink_to(
        tmp_path / "archive/experiment_traces", target_is_directory=True
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "unsafe_directory_type"


def test_external_trace_and_report_roots_are_diagnosed_read_only(tmp_path):
    external = tmp_path / "recovered"
    _write_candidate_matrix(
        external, {"D3": 10, "D6": 10, "P6": 10, "P6V": 10}
    )
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    result = audit.audit_archive_readiness(
        repo_root=tmp_path / "checkout",
        trace_root=external / "experiment_traces",
        report_root=external,
    )
    assert result["trace_candidates"]["status"] == "40_matrix_candidates_unverified"
    assert result["report_candidates"]["status"] == "40_report_candidates_unverified"
    assert not (tmp_path / "checkout").exists()
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == before


def test_unknown_trace_variant_is_blocked_even_with_40_valid_candidates(tmp_path):
    _write_candidate_matrix(
        tmp_path / "outputs", {"D3": 10, "D6": 10, "P6": 10, "P6V": 10}
    )
    alien = tmp_path / "outputs/experiment_traces/experimental"
    alien.mkdir()
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "unexpected_trace_root_entry"
    assert "original_experiment_trace_candidates" in result["blockers"]


def test_matching_manifest_bytes_do_not_authenticate_pin_custody(tmp_path):
    research = tmp_path / "outputs/main_study_analysis_inputs_manifest.json"
    coordinator = tmp_path / "outputs/human_eval/manifest.json"
    for path, content in ((research, b"retained-research-manifest"),
                          (coordinator, b"retained-coordinator-manifest")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    result = audit.audit_archive_readiness(
        repo_root=tmp_path,
        research_manifest_sha256=hashlib.sha256(research.read_bytes()).hexdigest(),
        coordinator_manifest_sha256=hashlib.sha256(coordinator.read_bytes()).hexdigest(),
    )
    assert result["independent_pins"] == {
        "research_manifest_file": "pin_matches_file_not_authenticated",
        "coordinator_manifest_file": "pin_matches_file_not_authenticated",
    }
    assert result["status"] == "blocked"
    assert result["handoff_verified"] is False


def test_coherently_supplied_but_wrong_manifest_pin_blocks_readiness(tmp_path):
    manifest = tmp_path / "outputs/human_eval/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(b"candidate-manifest")
    result = audit.audit_archive_readiness(
        repo_root=tmp_path,
        coordinator_manifest_sha256=hashlib.sha256(b"original-manifest").hexdigest(),
    )
    assert result["independent_pins"]["coordinator_manifest_file"] == "pin_mismatch"
    assert "coordinator_manifest_file" in result["blockers"]


def test_symlinked_manifest_cannot_satisfy_even_a_matching_pin(tmp_path):
    target = tmp_path / "manifest-source"
    target.write_bytes(b"local-data")
    manifest = tmp_path / "outputs/human_eval/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.symlink_to(target)
    result = audit.audit_archive_readiness(
        repo_root=tmp_path,
        coordinator_manifest_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    )
    assert result["independent_pins"]["coordinator_manifest_file"] == (
        "pinned_file_missing_or_unsafe"
    )
    assert result["handoff_verified"] is False


def test_unstable_or_oversized_manifest_capture_blocks_pin(tmp_path, monkeypatch):
    manifest = tmp_path / "outputs/human_eval/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(b"manifest")
    def fail_capture(*args, **kwargs):
        raise ValueError("manifest changed or exceeds the read bound")
    monkeypatch.setattr(audit.packet_builder, "_read_regular_file_captured", fail_capture)
    assert audit._pin_status(
        hashlib.sha256(b"manifest").hexdigest(), manifest
    ) == "pinned_file_unreadable_or_unstable"


def _simulate_published_identity_inputs(root: Path, monkeypatch) -> None:
    """Test fixture: a stubbed published anchor is NOT a real provenance check."""
    for rel in ("outputs/main_study_analysis_inputs_manifest.json",
                "outputs/main_study_runs.csv"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic-only", encoding="utf-8")
    support = root / audit.lineage.SUPPORT_REL
    support.parent.mkdir(parents=True, exist_ok=True)
    with support.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("variant_id", "task_id", "run_id")
        )
        writer.writeheader()
        for variant in audit.VARIANTS:
            for n, task_id in enumerate(audit.lineage.TASKS):
                writer.writerow({
                    "variant_id": variant, "task_id": task_id,
                    "run_id": f"{variant.lower()}-run-{n:02d}",
                })
    monkeypatch.setattr(
        audit.published, "verify_published_frozen_inputs", lambda **_kwargs: {}
    )


def test_recovered_filename_identity_matches_frozen_evaluator_only_diagnostically(
    tmp_path, monkeypatch
):
    _write_candidate_matrix(
        tmp_path / "outputs", dict.fromkeys(audit.VARIANTS, 10)
    )
    _simulate_published_identity_inputs(tmp_path, monkeypatch)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"] == {
        "status": "40_run_ids_match_published_evaluator_not_authenticated",
        "matched": 40, "missing": 0, "unexpected": 0, "expected": 40,
    }
    assert result["handoff_verified"] is False
    assert result["status"] == "blocked"  # no independent pins or packet


def test_balanced_wrong_run_ids_fail_canonical_identity_preflight(
    tmp_path, monkeypatch
):
    _write_candidate_matrix(
        tmp_path / "outputs", dict.fromkeys(audit.VARIANTS, 10)
    )
    _simulate_published_identity_inputs(tmp_path, monkeypatch)
    root = tmp_path / "outputs"
    (root / "experiment_traces/D3/d3-run-00.json").rename(
        root / "experiment_traces/D3/not-from-frozen-evaluator.json"
    )
    first = audit.audit_archive_readiness(repo_root=tmp_path)
    assert first["trace_candidates"]["status"] == "40_matrix_candidates_unverified"
    assert first["trace_to_published_evaluator"] == {
        "status": "candidate_run_identity_mismatch",
        "matched": 39, "missing": 1, "unexpected": 1, "expected": 40,
    }
    assert "original_trace_to_evaluator_run_identity" in first["blockers"]


def test_treatment_swapped_trace_filenames_fail_even_with_40_unique_runs(
    tmp_path, monkeypatch
):
    _write_candidate_matrix(
        tmp_path / "outputs", dict.fromkeys(audit.VARIANTS, 10)
    )
    _simulate_published_identity_inputs(tmp_path, monkeypatch)
    root = tmp_path / "outputs/experiment_traces"
    one = root / "D3/d3-run-00.json"
    other = root / "D6/d6-run-00.json"
    transit = root / "D3/intermediate.tmp"
    one.rename(transit)
    other.rename(root / "D3/d6-run-00.json")
    transit.rename(root / "D6/d3-run-00.json")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "40_matrix_candidates_unverified"
    assert result["trace_to_published_evaluator"]["status"] == (
        "candidate_run_identity_mismatch"
    )
    assert result["trace_to_published_evaluator"]["matched"] == 38
    assert result["trace_to_published_evaluator"]["missing"] == 2
    assert result["trace_to_published_evaluator"]["unexpected"] == 2


def test_unanchored_or_missing_trace_archive_never_claims_run_identity_match(
    tmp_path
):
    _write_candidate_matrix(
        tmp_path / "outputs", dict.fromkeys(audit.VARIANTS, 10)
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["status"] == (
        "not_checked_without_published_input_anchor"
    )
    empty = audit.audit_archive_readiness(repo_root=tmp_path / "absent")
    assert empty["trace_to_published_evaluator"]["status"] == (
        "not_checked_without_40_trace_candidates"
    )


def test_malformed_evaluator_run_id_matrix_cannot_be_used_as_an_identity_gate(
    tmp_path, monkeypatch
):
    _write_candidate_matrix(
        tmp_path / "outputs", dict.fromkeys(audit.VARIANTS, 10)
    )
    _simulate_published_identity_inputs(tmp_path, monkeypatch)
    support = tmp_path / audit.lineage.SUPPORT_REL
    support.write_text(
        "variant_id,task_id,run_id\\nD3,main-01,duplicate-run\\n",
        encoding="utf-8",
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["status"] == (
        "invalid_published_evaluator_run_ids"
    )
    assert "original_trace_to_evaluator_run_identity" in result["blockers"]

