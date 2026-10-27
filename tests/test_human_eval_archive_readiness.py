"""Synthetic, offline checks for the archive recovery inventory contract."""
import csv
import hashlib
import json

import pytest
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


def _write_semantically_aligned_fixture(root: Path, monkeypatch, *, archive=None):
    """Synthetic run/task/report corpus; publication pin is stubbed in tests."""
    outputs = archive if archive is not None else root / "outputs"
    _write_candidate_matrix(outputs, dict.fromkeys(audit.VARIANTS, 10))
    _simulate_published_identity_inputs(root, monkeypatch)
    main_source = root / audit.lineage.MAIN_REL
    with main_source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "variant_id", "task_id", "completed", "source_budget",
            "successful_sources", "failed_sources", "search_calls",
            "model_calls", "total_tokens", "report_words",
        ))
        writer.writeheader()
        for variant in audit.VARIANTS:
            for task_id in audit.lineage.TASKS:
                writer.writerow({
                    "variant_id": variant, "task_id": task_id,
                    "completed": "True",
                    "source_budget": audit.main_input_contract.FROZEN_SOURCE_BUDGETS[variant],
                    "successful_sources": 2, "failed_sources": 1,
                    "search_calls": 1, "model_calls": 4,
                    "total_tokens": 250, "report_words": 50,
                })
    tasks = {
        "task_set_id": "synthetic-frozen-task-set",
        "frozen_before_execution": True,
        "tasks": [
            {"id": task_id, "question": f"Synthetic question for {task_id}"}
            for task_id in audit.lineage.TASKS
        ],
    }
    task_file = root / "experiments/main_budget_tasks.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text(json.dumps(tasks), encoding="utf-8")
    for variant in audit.VARIANTS:
        for n, task_id in enumerate(audit.lineage.TASKS):
            run_id = f"{variant.lower()}-run-{n:02d}"
            payload = {
                "schema_version": 2,
                "experiment": {
                    "variant_id": variant, "task_id": task_id,
                    "task_set_id": tasks["task_set_id"],
                    "source_budget": audit.main_input_contract.FROZEN_SOURCE_BUDGETS[variant],
                    "planning_mode": audit.FROZEN_EXECUTION_MODES[variant][0],
                    "verification_mode": audit.FROZEN_EXECUTION_MODES[variant][1],
                },
                "trace": {
                    "variant_id": variant, "task_id": task_id,
                    "task_set_id": tasks["task_set_id"],
                    "run_id": run_id, "completed": True,
                    "question": tasks["tasks"][n]["question"],
                    "report_path": f"./outputs/{run_id}/research_report.pdf",
                    "source_budget": audit.main_input_contract.FROZEN_SOURCE_BUDGETS[variant],
                    "successful_source_count": 2, "failed_source_count": 1,
                    "search_call_count": 1, "model_call_count": 4,
                    "total_tokens": 250, "report_words": 50,
                },
            }
            path = outputs / "experiment_traces" / variant / f"{run_id}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            (outputs / run_id / "research_report.md").write_text(
                f"Synthetic non-evaluation report for {run_id}.", encoding="utf-8"
            )
    return outputs


def test_recovered_trace_and_report_contents_align_only_diagnostically(
    tmp_path, monkeypatch
):
    _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"] == {
        "status": "40_trace_report_contents_align_to_frozen_cells_not_authenticated",
        "checked": 40, "expected": 40,
    }
    assert result["handoff_verified"] is False
    assert result["status"] == "blocked"  # original external pins/packets absent


@pytest.mark.parametrize("field,bad_value", [
    ("experiment_variant", "D6"),
    ("trace_variant", "P6"),
    ("experiment_task", "main-02"),
    ("trace_task", "main-02"),
    ("trace_run", "not-the-frozen-run"),
    ("task_set_id", "other-task-set"),
    ("question", "Different question"),
    ("completed", False),
    ("report_path", "./outputs/d6-run-00/research_report.pdf"),
])
def test_mismatched_embedded_trace_metadata_blocks_archive_readiness(
    tmp_path, monkeypatch, field, bad_value
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    trace_file = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(trace_file.read_text(encoding="utf-8"))
    if field == "experiment_variant":
        payload["experiment"]["variant_id"] = bad_value
    elif field == "trace_variant":
        payload["trace"]["variant_id"] = bad_value
    elif field == "experiment_task":
        payload["experiment"]["task_id"] = bad_value
    elif field == "trace_task":
        payload["trace"]["task_id"] = bad_value
    elif field == "trace_run":
        payload["trace"]["run_id"] = bad_value
    elif field == "task_set_id":
        payload["trace"]["task_set_id"] = bad_value
    else:
        payload["trace"][field] = bad_value
    trace_file.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


def test_duplicate_trace_json_member_cannot_hide_altered_run_identity(
    tmp_path, monkeypatch
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    text = path.read_text(encoding="utf-8")
    text = text.replace('"run_id": "d3-run-00"',
                        '"run_id": "some-other-run", "run_id": "d3-run-00"', 1)
    path.write_text(text, encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "duplicate JSON key" in result["trace_report_content"]["first_failure"]


@pytest.mark.parametrize("bad_report", ["", "   \n"])
def test_empty_report_cannot_pass_content_readiness(tmp_path, monkeypatch, bad_report):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    (outputs / "d3-run-00/research_report.md").write_text(
        bad_report, encoding="utf-8"
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["report_candidates"]["count"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "original_trace_report_content_alignment" in result["blockers"]


def test_external_recovered_archives_can_be_checked_without_copying(
    tmp_path, monkeypatch
):
    repo = tmp_path / "checkout"
    archive = tmp_path / "recovered"
    _write_semantically_aligned_fixture(repo, monkeypatch, archive=archive)
    result = audit.audit_archive_readiness(
        repo_root=repo, trace_root=archive / "experiment_traces",
        report_root=archive,
    )
    assert result["trace_report_content"]["checked"] == 40
    assert result["trace_report_content"]["status"].endswith(
        "_not_authenticated"
    )
    assert result["handoff_verified"] is False


def test_content_preflight_skips_without_anchored_run_ids(tmp_path):
    _write_candidate_matrix(tmp_path / "outputs", dict.fromkeys(audit.VARIANTS, 10))
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "not_checked_without_published_run_identity"
    )
    assert result["handoff_verified"] is False


def test_content_preflight_rejects_unstable_or_oversized_trace_capture(
    tmp_path, monkeypatch
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    original = audit.packet_builder._read_regular_file_captured
    def fail_trace_capture(path, *, label):
        if Path(path).name == "d3-run-00.json":
            raise ValueError("trace source changed during capture")
        return original(path, label=label)
    monkeypatch.setattr(
        audit.packet_builder, "_read_regular_file_captured", fail_trace_capture
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "original_trace_report_content_alignment" in result["blockers"]


@pytest.mark.parametrize("trace_field", [
    "source_budget", "successful_source_count", "failed_source_count",
    "search_call_count", "model_call_count", "total_tokens", "report_words",
])
def test_recovered_telemetry_must_match_frozen_treatment_measurements(
    tmp_path, monkeypatch, trace_field
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"][trace_field] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert trace_field in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]


@pytest.mark.parametrize("field,wrong_value", [
    ("planning_mode", "planner"),
    ("verification_mode", "verify"),
    ("source_budget", 6),
])
def test_recovered_experiment_config_must_match_frozen_treatment_arm(
    tmp_path, monkeypatch, field, wrong_value
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["experiment"][field] = wrong_value
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "original_trace_report_content_alignment" in result["blockers"]


def test_missing_or_boolean_trace_counter_is_not_canonical_measurement(
    tmp_path, monkeypatch
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"]["total_tokens"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "original_trace_report_content_alignment" in result["blockers"]
