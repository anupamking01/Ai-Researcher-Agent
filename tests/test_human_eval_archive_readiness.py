"""Synthetic, offline checks for the archive recovery inventory contract."""
from pathlib import Path

from scripts import audit_human_eval_archive_readiness as audit
from scripts import export_human_eval_annotator_bundle as exporter


def test_missing_archives_are_reported_without_claiming_a_handoff(tmp_path):
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["status"] == "blocked"
    assert result["trace_candidates"] == {
        "status": "missing", "count": 0, "expected": 40,
    }
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
    assert result["trace_candidates"]["status"] == "40_candidates_unverified"
    assert result["published_automated_input_anchor"] == "verification_failed"
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
    assert second["trace_candidates"]["status"] == "40_candidates_unverified"
    assert second["handoff_verified"] is False


def test_trace_symlink_directory_rejected(tmp_path):
    root = tmp_path / "outputs/experiment_traces"
    root.mkdir(parents=True)
    target = tmp_path / "somewhere"
    target.mkdir()
    (root / "D3").symlink_to(target, target_is_directory=True)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "unsafe_directory_type"
    assert result["status"] == "blocked"


def test_pin_values_are_not_treated_as_authenticated_evidence(tmp_path):
    result = audit.audit_archive_readiness(
        repo_root=tmp_path,
        research_manifest_sha256="A" * 64,
        coordinator_manifest_sha256="0" * 64,
    )
    assert result["independent_pins"]["research_manifest_file"] == "invalid_pin_format"
    assert result["independent_pins"]["coordinator_manifest_file"] == (
        "pin_supplied_not_authenticated"
    )
    assert "research_manifest_file" in result["blockers"]
