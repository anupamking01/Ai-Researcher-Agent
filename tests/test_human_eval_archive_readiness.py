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
    # Only this synthetic fixture substitutes known test CSV bytes for the
    # canonical published file digests.
    monkeypatch.setattr(audit, "PUBLISHED_CSV_FILE_SHA256", {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in (audit.lineage.MAIN_REL, audit.lineage.SUPPORT_REL)
    })


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
    # This fixture intentionally substitutes synthetic questions: bypass only
    # the immutable ORIGINAL task-byte pin, not trace/content checks.
    monkeypatch.setattr(
        audit.frozen_tasks, "verify_frozen_task_manifest", lambda **_kwargs: {}
    )
    main_source = root / audit.lineage.MAIN_REL
    with main_source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "variant_id", "task_id", "completed", "source_budget",
            "successful_sources", "failed_sources", "search_calls",
            "model_calls", "total_tokens", "report_words",
            "treatment_cost_usd", "cost_status", "latency_seconds",
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
                    "treatment_cost_usd": 0.0002,
                    "cost_status": "estimated_from_frozen_uncached_rates",
                    "latency_seconds": 1.25,
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
    monkeypatch.setattr(
        audit.frozen_tasks, "ORIGINAL_TASK_MANIFEST_SHA256",
        hashlib.sha256(task_file.read_bytes()).hexdigest(),
    )
    # Treatment CSV was rewritten after the identity-only synthetic fixture.
    monkeypatch.setattr(audit, "PUBLISHED_CSV_FILE_SHA256", {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in (audit.lineage.MAIN_REL, audit.lineage.SUPPORT_REL)
    })
    # Synthetic pricing replaces the historical pin only within test fixtures.
    price_file = root / audit.FROZEN_PRICING_REL
    rates = {"input": 0.2, "output": 1.2}
    price_file.write_text(json.dumps({
        "currency": "USD", "unit": "per_1m_text_tokens",
        "models": {name: (dict(rates) if name != "expensive-model"
                           else {"input": 2.0, "output": 12.0})
                   for name in ("synthetic-model", "model-a", "model-b",
                                "expensive-model")}
    }), encoding="utf-8")
    monkeypatch.setattr(audit, "ORIGINAL_PRICING_SHA256",
                        hashlib.sha256(price_file.read_bytes()).hexdigest())
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
                    "latency_seconds": 1.25,
                    "source_count": 3, "query_count": 1,
                    "search_queries": [tasks["tasks"][n]["question"]],
                    "search_records": [{
                        "query": tasks["tasks"][n]["question"],
                        "candidate_urls": [
                            "https://example.test/a", "https://example.test/b",
                            "https://example.test/c",
                        ],
                        "scheduled_urls": [
                            "https://example.test/a", "https://example.test/b",
                            "https://example.test/c",
                        ],
                    }],
                    "usage_accounting_status": "provider_usage_complete",
                    "prompt_tokens": 100, "completion_tokens": 150,
                    "unavailable_usage_call_count": 0,
                    "provider_usage_by_model": {
                        "synthetic-model": {
                            "model_calls": 4, "unavailable_calls": 0,
                            "prompt_tokens": 100, "completion_tokens": 150,
                            "total_tokens": 250,
                        },
                    },
                    "scheduled_urls": [
                        "https://example.test/a", "https://example.test/b",
                        "https://example.test/c",
                    ],
                    "successful_urls": [
                        "https://example.test/a", "https://example.test/b",
                    ],
                    "failed_urls": ["https://example.test/c"],
                },
            }
            path = outputs / "experiment_traces" / variant / f"{run_id}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            (outputs / run_id / "research_report.md").write_text(
                "synthetic " * 49 + "archive-ending", encoding="utf-8"
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



@pytest.mark.parametrize("field,bad_value,error_fragment", [
    ("source_count", None, "source_count"),
    ("source_count", True, "source_count"),
    ("source_count", 4, "source_count"),
    ("source_count", 2, "source_count"),
    ("query_count", False, "query_count"),
    ("query_count", 0, "query_count"),
    ("usage_accounting_status", "estimated", "usage_accounting_status"),
    ("scheduled_urls", ["https://example.test/a", "https://example.test/a",
                        "https://example.test/c"], "scheduled_urls"),
    ("scheduled_urls", ["https://example.test/a", "https://example.test/b"],
     "scheduled_urls"),
    ("scheduled_urls", ["https://example.test/a", "https://example.test/b", 5],
     "scheduled_urls"),
    ("successful_urls", ["https://example.test/a", "https://example.test/a"],
     "successful_urls"),
    ("successful_urls", ["https://example.test/a", "https://example.test/d"],
     "source URL ledger partition"),
    ("failed_urls", ["https://example.test/a"], "source URL ledger partition"),
    ("failed_urls", [" https://example.test/c "], "failed_urls"),
])
def test_recovered_source_provenance_requires_consistent_original_ledgers(
    tmp_path, monkeypatch, field, bad_value, error_fragment
):
    """Frozen CSV counters alone must not approve contradictory source evidence."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"][field] = bad_value
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert error_fragment in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False



@pytest.mark.parametrize("field,bad_value,error_fragment", [
    ("provider_usage_by_model", None, "provider_usage_by_model"),
    ("provider_usage_by_model", {}, "provider_usage_by_model"),
    ("prompt_tokens", True, "aggregate prompt_tokens"),
    ("prompt_tokens", 101, "aggregate prompt_tokens"),
    ("completion_tokens", 149, "aggregate completion_tokens"),
    ("unavailable_usage_call_count", 1, "aggregate unavailable_usage_call_count"),
])
def test_recovered_provider_usage_requires_complete_aggregate_concordance(
    tmp_path, monkeypatch, field, bad_value, error_fragment
):
    """Frozen total counts alone must not certify a corrupted model ledger."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"][field] = bad_value
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert error_fragment in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


@pytest.mark.parametrize("field,bad_value,error_fragment", [
    ("model_calls", True, "model_calls"),
    ("model_calls", 0, "model_calls"),
    ("unavailable_calls", 1, "unavailable_calls"),
    ("prompt_tokens", -1, "prompt_tokens"),
    ("completion_tokens", 151, "total_tokens"),
    ("total_tokens", 249, "total_tokens"),
])
def test_recovered_provider_usage_rejects_inconsistent_per_model_counters(
    tmp_path, monkeypatch, field, bad_value, error_fragment
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"]["provider_usage_by_model"]["synthetic-model"][field] = bad_value
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert error_fragment in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]


def test_recovered_provider_usage_accepts_consistent_multi_model_accounting(
    tmp_path, monkeypatch
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"]["provider_usage_by_model"] = {
        "model-a": {
            "model_calls": 2, "unavailable_calls": 0,
            "prompt_tokens": 70, "completion_tokens": 80, "total_tokens": 150,
        },
        "model-b": {
            "model_calls": 2, "unavailable_calls": 0,
            "prompt_tokens": 30, "completion_tokens": 70, "total_tokens": 100,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "40_trace_report_contents_align_to_frozen_cells_not_authenticated"
    )
    assert receipt["trace_report_content"]["checked"] == 40
    assert receipt["handoff_verified"] is False


@pytest.mark.parametrize("replacement", [
    "a shorter replacement report",
    "an unrelated but substantially longer recovered report " * 20,
])
def test_recovered_report_word_count_must_match_frozen_trace(
    tmp_path, monkeypatch, replacement
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    report = outputs / "d3-run-00/research_report.md"
    report.write_text(replacement, encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "report word count" in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


def test_matching_report_word_count_is_not_report_authentication(
    tmp_path, monkeypatch
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    report = outputs / "d3-run-00/research_report.md"
    report.write_text("different " * 49 + "same-count", encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "40_trace_report_contents_align_to_frozen_cells_not_authenticated"
    )
    assert result["handoff_verified"] is False
    assert result["status"] == "blocked"


@pytest.mark.parametrize("unsafe_report", [
    "D3",
    "run_id",
    "![figure](https://example.org/figure.png)",
    '<img src="https://example.org/figure.png">',
])
def test_recovered_report_must_be_safe_for_blinded_packet_even_if_counts_match(
    tmp_path, monkeypatch, unsafe_report
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    report = outputs / "d3-run-00/research_report.md"
    tokens = unsafe_report.split()
    assert len(tokens) < 50
    report.write_text(
        "neutral " * (50 - len(tokens)) + unsafe_report, encoding="utf-8"
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "annotator-facing" in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


def test_archival_content_preflight_fails_closed_if_validator_contract_drifts(
    tmp_path, monkeypatch
):
    _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        audit.packet_builder,
        "_content_validator_runtime_contract_now",
        lambda: {"schema_version": -1},
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_content_validator_contract"
    )
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


def test_trace_directory_enumeration_stops_after_bounded_overflow(
    tmp_path, monkeypatch
):
    """A hostile archive iterator cannot force an unbounded eager sort."""
    trace_root = tmp_path / "outputs/experiment_traces"
    trace_root.mkdir(parents=True)
    original = Path.iterdir
    consumed = []

    def oversized_root(self):
        if self == trace_root:
            for n in range(1_000_000):
                consumed.append(n)
                yield trace_root / f"unexpected-{n}"
        else:
            yield from original(self)

    monkeypatch.setattr(Path, "iterdir", oversized_root)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["status"] == "blocked"
    assert result["trace_candidates"]["status"] == (
        "trace_root_entry_limit_exceeded"
    )
    assert len(consumed) == len(audit.VARIANTS) + 2
    assert "original_experiment_trace_candidates" in result["blockers"]


def test_oversized_variant_directory_is_rejected_without_full_scan(
    tmp_path, monkeypatch
):
    trace_root = tmp_path / "outputs/experiment_traces"
    variant_root = trace_root / "D3"
    variant_root.mkdir(parents=True)
    original = Path.iterdir
    consumed = []

    def oversized_variant(self):
        if self == variant_root:
            for n in range(1_000_000):
                consumed.append(n)
                yield variant_root / f"synthetic-{n}.json"
        else:
            yield from original(self)

    monkeypatch.setattr(Path, "iterdir", oversized_variant)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["status"] == "blocked"
    assert result["trace_candidates"]["status"] == (
        "trace_variant_entry_limit_exceeded"
    )
    assert len(consumed) == audit.EXPECTED_TRACES + 2
    assert "original_experiment_trace_candidates" in result["blockers"]


def test_single_unexpected_trace_root_entry_retains_specific_diagnosis(tmp_path):
    trace_root = tmp_path / "outputs/experiment_traces"
    for name in (*audit.VARIANTS, "unexpected"):
        (trace_root / name).mkdir(parents=True)
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "unexpected_trace_root_entry"
    assert result["status"] == "blocked"


def test_41_trace_entries_retains_count_mismatch_status(tmp_path):
    variant_root = tmp_path / "outputs/experiment_traces/D3"
    variant_root.mkdir(parents=True)
    for n in range(audit.EXPECTED_TRACES + 1):
        (variant_root / f"synthetic-{n:02d}.json").write_text("{}")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_candidates"]["status"] == "candidate_count_mismatch"
    assert result["status"] == "blocked"



@pytest.mark.parametrize("relative", [audit.lineage.MAIN_REL, audit.lineage.SUPPORT_REL])
def test_published_csv_capture_rejects_later_replacement(tmp_path, monkeypatch, relative):
    """A previous canonical check cannot approve a subsequently changed file."""
    source = tmp_path / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"pinned synthetic bytes")
    monkeypatch.setattr(audit, "PUBLISHED_CSV_FILE_SHA256", {
        relative: hashlib.sha256(source.read_bytes()).hexdigest()
    })
    assert audit._capture_published_csv(
        tmp_path, relative, label="synthetic frozen CSV"
    ) == b"pinned synthetic bytes"
    source.write_bytes(b"changed synthetic bytes")
    with pytest.raises(ValueError, match="changed after published input verification"):
        audit._capture_published_csv(
            tmp_path, relative, label="synthetic frozen CSV"
        )


def test_late_evaluator_replacement_blocks_recovered_run_identity(tmp_path, monkeypatch):
    _write_candidate_matrix(tmp_path / "outputs", dict.fromkeys(audit.VARIANTS, 10))
    _simulate_published_identity_inputs(tmp_path, monkeypatch)
    support = tmp_path / audit.lineage.SUPPORT_REL

    def change_after_stated_verification(**_kwargs):
        support.write_bytes(support.read_bytes().replace(b"d3-run-00", b"new-run-00"))
        return {}

    monkeypatch.setattr(
        audit.published, "verify_published_frozen_inputs",
        change_after_stated_verification,
    )
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    # The mocked earlier publication receipt is not sufficient for a later read.
    assert receipt["published_automated_input_anchor"] == "published_aggregate_matches"
    assert receipt["trace_to_published_evaluator"]["status"] == (
        "invalid_published_evaluator_run_ids"
    )
    assert receipt["expected_recovery_paths"]["status"] == (
        "invalid_published_evaluator_run_ids"
    )
    assert "original_trace_to_evaluator_run_identity" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


def test_late_treatment_replacement_blocks_telemetry_concordance(tmp_path, monkeypatch):
    _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    main = tmp_path / audit.lineage.MAIN_REL

    def change_after_stated_verification(**_kwargs):
        content = main.read_bytes()
        assert b",250,50" in content
        main.write_bytes(content.replace(b",250,50", b",251,50", 1))
        return {}

    monkeypatch.setattr(
        audit.published, "verify_published_frozen_inputs",
        change_after_stated_verification,
    )
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_to_published_evaluator"]["matched"] == 40
    assert receipt["trace_report_content"]["status"] == (
        "invalid_frozen_task_or_evaluator"
    )
    assert "changed after published input verification" in (
        receipt["trace_report_content"]["reason"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]


def test_late_task_manifest_replacement_blocks_question_alignment(tmp_path, monkeypatch):
    _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    task_file = tmp_path / "experiments/main_budget_tasks.json"

    def change_after_stated_verification(**_kwargs):
        payload = json.loads(task_file.read_text(encoding="utf-8"))
        payload["tasks"][0]["question"] = "Changed after the source check"
        task_file.write_text(json.dumps(payload), encoding="utf-8")
        return {}

    monkeypatch.setattr(
        audit.frozen_tasks, "verify_frozen_task_manifest",
        change_after_stated_verification,
    )
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["frozen_task_manifest_anchor"] == (
        "original_treatment_run_task_manifest_matches"
    )
    assert receipt["trace_report_content"]["status"] == (
        "invalid_frozen_task_or_evaluator"
    )
    assert "changed after source verification" in (
        receipt["trace_report_content"]["reason"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]

@pytest.mark.parametrize("latency", [-1.0, True, None, "1.25", 2.0])
def test_archived_latency_must_match_frozen_efficiency_measurement(
    tmp_path, monkeypatch, latency
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"]["latency_seconds"] = latency
    path.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "latency_seconds" in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]


@pytest.mark.parametrize("replacement,diagnostic", [
    ("expensive-model", "treatment_cost_usd"),
    ("unknown-model", "no original frozen price"),
])
def test_archived_cost_rejects_model_substitution_with_same_token_totals(
    tmp_path, monkeypatch, replacement, diagnostic
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    ledger = payload["trace"]["provider_usage_by_model"]
    ledger[replacement] = ledger.pop("synthetic-model")
    path.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert diagnostic in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]


def test_modified_historical_pricing_bytes_block_cost_concordance(
    tmp_path, monkeypatch
):
    _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = tmp_path / audit.FROZEN_PRICING_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["models"]["synthetic-model"]["output"] = 1.3
    path.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_frozen_task_or_evaluator"
    )
    assert "pricing table source fingerprint mismatch" in (
        receipt["trace_report_content"]["reason"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]


def test_missing_historical_pricing_bytes_block_cost_concordance(
    tmp_path, monkeypatch
):
    _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    (tmp_path / audit.FROZEN_PRICING_REL).unlink()
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_frozen_task_or_evaluator"
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]


@pytest.mark.parametrize("mutation,expected_fragment", [
    ("missing_queries", "search_queries"),
    ("empty_queries", "search_queries"),
    ("nonstring_query", "search_queries"),
    ("missing_records", "search_records"),
    ("empty_records", "search_records"),
    ("nonobject_record", "search_records[0]"),
    ("record_unplanned_query", "query order differs"),
    ("record_candidate_type", "candidate_urls"),
    ("record_candidate_without_scheduled_url", "scheduled URL is missing"),
    ("record_reordered_urls", "candidate-result order"),
    ("record_incomplete_schedule", "scheduled URLs differ"),
    ("record_error_with_schedule", "search_error record"),
])
def test_recovered_search_result_ledger_cannot_mask_frozen_source_counts(
    tmp_path, monkeypatch, mutation, expected_fragment
):
    """All aggregate counters still agree; tampered nested retrieval must fail."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    trace = payload["trace"]
    record = trace["search_records"][0]
    if mutation == "missing_queries":
        del trace["search_queries"]
    elif mutation == "empty_queries":
        trace["search_queries"] = []
    elif mutation == "nonstring_query":
        trace["search_queries"] = [123]
    elif mutation == "missing_records":
        del trace["search_records"]
    elif mutation == "empty_records":
        trace["search_records"] = []
    elif mutation == "nonobject_record":
        trace["search_records"] = [False]
    elif mutation == "record_unplanned_query":
        record["query"] = "unplanned search"
    elif mutation == "record_candidate_type":
        record["candidate_urls"] = "https://example.test/a"
    elif mutation == "record_candidate_without_scheduled_url":
        record["candidate_urls"] = ["https://example.test/a"]
    elif mutation == "record_reordered_urls":
        record["scheduled_urls"] = list(reversed(record["scheduled_urls"]))
    elif mutation == "record_incomplete_schedule":
        record["scheduled_urls"] = record["scheduled_urls"][:-1]
    elif mutation == "record_error_with_schedule":
        record["search_error"] = "synthetic search outage"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert expected_fragment in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


def test_search_provenance_accepts_skipped_planned_query_and_failed_search():
    """The runner may skip a plan step and record a search outage with no URLs."""
    trace = {
        "query_count": 3,
        "search_call_count": 2,
        "search_queries": ["query one", "budget skipped", "query three"],
        "search_records": [
            {"query": "query one",
             "candidate_urls": ["https://example.test/one"],
             "scheduled_urls": ["https://example.test/one"]},
            {"query": "query three", "candidate_urls": [], "scheduled_urls": [],
             "search_error": "synthetic transient failure"},
        ],
        "scheduled_urls": ["https://example.test/one"],
    }
    audit._validate_recovered_search_provenance(trace)


def test_search_provenance_rejects_out_of_order_executed_queries():
    """Matching query counts do not permit reshuffling the retrieval plan."""
    trace = {
        "query_count": 2,
        "search_call_count": 2,
        "search_queries": ["first", "second"],
        "search_records": [
            {"query": "second", "candidate_urls": [], "scheduled_urls": []},
            {"query": "first", "candidate_urls": [], "scheduled_urls": []},
        ],
        "scheduled_urls": [],
    }
    with pytest.raises(ValueError, match="query order"):
        audit._validate_recovered_search_provenance(trace)
