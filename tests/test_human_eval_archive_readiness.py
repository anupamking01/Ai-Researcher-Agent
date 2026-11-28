"""Synthetic, offline checks for the archive recovery inventory contract."""
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone

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


def _write_semantically_aligned_fixture(
    root: Path, monkeypatch, *, archive=None,
    latency_overrides=None,
):
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
                latency = (latency_overrides or {}).get((variant, task_id), 1.25)
                writer.writerow({
                    "variant_id": variant, "task_id": task_id,
                    "completed": "True",
                    "source_budget": audit.main_input_contract.FROZEN_SOURCE_BUDGETS[variant],
                    "successful_sources": 2, "failed_sources": 1,
                    "search_calls": (1 if variant in ("D3", "D6") else 4),
                    "model_calls": (5 if variant == "P6V" else 4),
                    "total_tokens": 250, "report_words": 50,
                    "treatment_cost_usd": 0.0002,
                    "cost_status": "estimated_from_frozen_uncached_rates",
                    "latency_seconds": latency,
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
                   for name in ("gpt-5.6-terra", "gpt-5.6-luna", "model-a", "model-b",
                                "expensive-model")}
    }), encoding="utf-8")
    monkeypatch.setattr(audit, "ORIGINAL_PRICING_SHA256",
                        hashlib.sha256(price_file.read_bytes()).hexdigest())
    for variant in audit.VARIANTS:
        for n, task_id in enumerate(audit.lineage.TASKS):
            run_id = f"{variant.lower()}-run-{n:02d}"
            latency = (latency_overrides or {}).get((variant, task_id), 1.25)
            # The historical runner interleaves variants, unlike file order.
            start = datetime(2026, 9, 11, 16, 20, tzinfo=timezone.utc)
            position = n * len(audit.VARIANTS) + audit.VARIANTS.index(variant)
            start += timedelta(seconds=2 * position)
            question = tasks["tasks"][n]["question"]
            plan = ([question] if variant in ("D3", "D6") else [
                f"Synthetic planned query {i} for {task_id}" for i in range(4)
            ])
            urls = [
                "https://example.test/a", "https://example.test/b",
                "https://example.test/c",
            ]
            # Direct searches may schedule all three; the 6-source planner
            # allocates [2, 2, 1, 1] across four planned searches.
            schedules = ([urls] if len(plan) == 1
                         else [urls[:2], urls[2:], [], []])
            records = [
                {"query": query, "candidate_urls": list(scheduled),
                 "scheduled_urls": list(scheduled),
                 **({"search_error": "synthetic metasearch outage"}
                    if not scheduled else {})}
                for query, scheduled in zip(plan, schedules)
            ]
            payload = {
                "schema_version": 2,
                "recorded_at_utc": (start + timedelta(seconds=latency)).isoformat(),
                "experiment": {
                    "variant_id": variant, "task_id": task_id,
                    "task_set_id": tasks["task_set_id"],
                    "source_budget": audit.main_input_contract.FROZEN_SOURCE_BUDGETS[variant],
                    "planning_mode": audit.FROZEN_EXECUTION_MODES[variant][0],
                    "verification_mode": audit.FROZEN_EXECUTION_MODES[variant][1],
                    "browse_timeout_seconds": 60.0,
                    "run_timeout_seconds": 480.0,
                    **audit.ORIGINAL_SHARED_EXECUTION_CONFIG,
                },
                "trace": {
                    "variant_id": variant, "task_id": task_id,
                    "task_set_id": tasks["task_set_id"],
                    "run_id": run_id, "completed": True,
                    "started_at_utc": start.isoformat(),
                    "question": tasks["tasks"][n]["question"],
                    "verification_status": (
                        "ok" if variant == "P6V" else "not_requested"
                    ),
                    "citation_count": (4 if variant == "P6V" else 0),
                    "supported_claim_count": (2 if variant == "P6V" else 0),
                    "partially_supported_claim_count": (1 if variant == "P6V" else 0),
                    "unsupported_claim_count": (1 if variant == "P6V" else 0),
                    "contradicted_claim_count": 0,
                    "report_path": f"./outputs/{run_id}/research_report.pdf",
                    "source_budget": audit.main_input_contract.FROZEN_SOURCE_BUDGETS[variant],
                    "planning_mode": audit.FROZEN_EXECUTION_MODES[variant][0],
                    "verification_mode": audit.FROZEN_EXECUTION_MODES[variant][1],
                    "browse_timeout_seconds": 60.0,
                    "run_timeout_seconds": 480.0,
                    "successful_source_count": 2, "failed_source_count": 1,
                    "search_call_count": len(records),
                    "model_call_count": (5 if variant == "P6V" else 4),
                    "total_tokens": 250, "report_words": 50,
                    "research_context_words": 24,
                    "latency_seconds": latency,
                    "source_count": 3, "query_count": len(plan),
                    "search_queries": plan,
                    "search_records": records,
                    "usage_accounting_status": "provider_usage_complete",
                    "cost_accounting_status": audit.ORIGINAL_TRACE_COST_STATUS,
                    "estimated_cost_usd": 0.0,
                    "smart_model": "gpt-5.6-terra",
                    "fast_model": "gpt-5.6-luna",
                    "temperature": 1.0,
                    "prompt_tokens": 100, "completion_tokens": 150,
                    "unavailable_usage_call_count": 0,
                    # These are emitted by the original RunTrace.to_dict(),
                    # not synthetic human or common-evaluator outcomes.
                    "source_success_rate": 2 / 3,
                    "verified_claim_count": (4 if variant == "P6V" else 0),
                    "claim_support_rate": (0.5 if variant == "P6V" else 0.0),
                    "citation_precision_proxy": (0.75 if variant == "P6V" else 0.0),
                    "provider_usage_by_model": {
                        "gpt-5.6-terra": {
                            "model_calls": (3 if variant == "P6V" else
                                            2 if variant == "P6" else 1),
                            "unavailable_calls": 0,
                            "prompt_tokens": 70, "completion_tokens": 80,
                            "total_tokens": 150,
                        },
                        "gpt-5.6-luna": {
                            "model_calls": (2 if variant in ("P6", "P6V") else 3),
                            "unavailable_calls": 0,
                            "prompt_tokens": 30, "completion_tokens": 70,
                            "total_tokens": 100,
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



@pytest.mark.parametrize("cell", [("D3", "main-01"), ("P6V", "main-01")])
def test_original_sequential_run_durations_cannot_grossly_overlap(
    tmp_path, monkeypatch, cell,
):
    # The frozen treatment CSV and trace agree on duration, and all trace
    # starts remain strictly ordered. A 16s run followed 2s later is still
    # inconsistent with the original single-process awaited treatment loop.
    _write_semantically_aligned_fixture(
        tmp_path, monkeypatch, latency_overrides={cell: 16.0}
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "implausibly overlaps" in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


def test_original_sequential_run_duration_allows_small_cross_clock_drift(
    tmp_path, monkeypatch,
):
    # A 2s UTC start gap with 6.9s monotonic runtime stays within the
    # five-second allowance, not proof of source custody or synchronized clocks.
    _write_semantically_aligned_fixture(
        tmp_path, monkeypatch, latency_overrides={("D3", "main-01"): 6.9}
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "40_trace_report_contents_align_to_frozen_cells_not_authenticated"
    )
    assert result["handoff_verified"] is False


@pytest.mark.parametrize("bad_time", [
    None, "", "2026-09-11T16:20:00", "2026-09-11T16:20:00+05:30",
    "2026-09-11 16:20:00+00:00", "not-an-instant",
    "2026-09-11T16:15:14+00:00",
    "2026-09-11T17:22:44+00:00",
])
def test_original_treatment_run_clock_requires_utc_and_workflow_window(bad_time):
    with pytest.raises(ValueError, match="started_at_utc"):
        audit._validate_recovered_start_time({"started_at_utc": bad_time})


def test_original_treatment_run_clock_includes_workflow_last_second():
    assert audit._validate_recovered_start_time({
        "started_at_utc": "2026-09-11T17:22:43.999999+00:00",
    }) == datetime(2026, 9, 11, 17, 22, 43, 999999, tzinfo=timezone.utc)


@pytest.mark.parametrize("variant,task_n,bad_time", [
    ("D6", 0, "2026-09-11T16:19:59+00:00"),  # Before task 1's D3.
    ("D3", 1, "2026-09-11T16:20:05+00:00"),  # Before task 1's P6V.
])
def test_original_treatment_task_interleaving_cannot_be_reordered(
    tmp_path, monkeypatch, variant, task_n, bad_time
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    run_id = f"{variant.lower()}-run-{task_n:02d}"
    trace_file = outputs / "experiment_traces" / variant / f"{run_id}.json"
    payload = json.loads(trace_file.read_text(encoding="utf-8"))
    payload["trace"]["started_at_utc"] = bad_time
    trace_file.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert receipt["trace_report_content"]["checked"] == 40
    assert "task-interleaved treatment execution order" in (
        receipt["trace_report_content"]["first_failure"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]


@pytest.mark.parametrize("variant", ["D3", "D6", "P6", "P6V"])
def test_historical_treatment_verification_valid_state(variant):
    """The original runner's two outcome paths are distinct from post-hoc evaluation."""
    zero = dict.fromkeys((
        "citation_count", "supported_claim_count", "partially_supported_claim_count",
        "unsupported_claim_count", "contradicted_claim_count",
    ), 0)
    if variant != "P6V":
        audit._validate_recovered_treatment_verification(
            {**zero, "verification_status": "not_requested"}, variant=variant
        )
    else:
        audit._validate_recovered_treatment_verification(
            {**zero, "verification_status": "parse_error"}, variant=variant
        )
        audit._validate_recovered_treatment_verification(
            {**zero, "verification_status": "ok"}, variant=variant
        )
        audit._validate_recovered_treatment_verification(
            {**zero, "verification_status": "ok", "citation_count": 3,
             "supported_claim_count": 1, "partially_supported_claim_count": 1,
             "unsupported_claim_count": 1}, variant=variant
        )


@pytest.mark.parametrize("variant,field,bad_value,remove", [
    ("D3", "verification_status", "ok", False),
    ("D6", "verification_status", None, True),
    ("P6", "citation_count", 1, False),
    ("D3", "supported_claim_count", 2, False),
    ("P6V", "verification_status", "not_requested", False),
    ("P6V", "verification_status", "parse_error", False),
    ("P6V", "verification_status", False, False),
    ("P6V", "verification_status", None, True),
    ("P6V", "citation_count", 3, False),
    ("P6V", "partially_supported_claim_count", 2, False),
    ("P6V", "contradicted_claim_count", -1, False),
    ("P6V", "unsupported_claim_count", True, False),
    ("P6V", "supported_claim_count", None, True),
])
def test_recovered_treatment_verification_must_match_original_execution(
    tmp_path, monkeypatch, variant, field, bad_value, remove
):
    """Disallow false verifier execution or invented claim counts with frozen CSVs unchanged."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    run_id = f"{variant.lower()}-run-00"
    path = outputs / "experiment_traces" / variant / f"{run_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if remove:
        del payload["trace"][field]
    else:
        payload["trace"][field] = bad_value
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "verification" in result["trace_report_content"]["first_failure"] or (
        "claim" in result["trace_report_content"]["first_failure"]
    )
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False



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


@pytest.mark.parametrize("variant,error_fields", [
    ("D3", {"error_type": "TimeoutError", "error_message": "synthetic timeout"}),
    ("P6V", {"error_type": "RuntimeError", "error_message": "synthetic error"}),
    ("D3", {"error_type": None}),
    ("P6V", {"error_message": ""}),
])
def test_completed_recovered_treatment_cannot_contain_run_error_metadata(
    tmp_path, monkeypatch, variant, error_fields
):
    """Original completed traces never contain top-level run-error keys."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces" / variant / f"{variant.lower()}-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["trace"]["completed"] is True
    payload["trace"].update(error_fields)
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "completed treatment contains original run-error metadata" in (
        result["trace_report_content"]["first_failure"]
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
    def fail_trace_capture(path, *, label, **kwargs):
        if Path(path).name == "d3-run-00.json":
            raise ValueError("trace source changed during capture")
        return original(path, label=label, **kwargs)
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


@pytest.mark.parametrize("variant,section,field,invalid", [
    ("D3", "trace", "planning_mode", "planner"),
    ("P6", "trace", "planning_mode", "direct"),
    ("P6V", "trace", "verification_mode", "none"),
    ("D3", "trace", "verification_mode", "verify"),
    ("D6", "trace", "planning_mode", None),
    ("D3", "trace", "browse_timeout_seconds", 120.0),
    ("P6V", "experiment", "browse_timeout_seconds", 15.0),
    ("P6", "trace", "run_timeout_seconds", True),
    ("D6", "experiment", "run_timeout_seconds", -1.0),
])
def test_recovered_trace_execution_metadata_must_match_original_config(
    tmp_path, monkeypatch, variant, section, field, invalid
):
    """Original treatment metadata is duplicated in config and trace.

    A single altered value must not pass the 40-cell archive diagnostic
    merely because the frozen published metrics and report bytes still match.
    """
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    run_id = f"{variant.lower()}-run-00"
    path = outputs / "experiment_traces" / variant / f"{run_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[section][field] = invalid
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert field in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


@pytest.mark.parametrize("field,replacement", [
    ("browse_timeout_seconds", 120.0),
    ("run_timeout_seconds", 960.0),
    ("browse_timeout_seconds", 60),
    ("run_timeout_seconds", 480),
])
def test_recovered_timeouts_must_match_original_defaults_even_when_concordant(
    tmp_path, monkeypatch, field, replacement
):
    """Two concordant edits cannot redefine the original censoring guardrails."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/P6/p6-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["experiment"][field] = replacement
    payload["trace"][field] = replacement
    path.write_text(json.dumps(payload), encoding="utf-8")
    # All frozen counts, costs, latencies and report bytes remain unchanged.
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert field in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


@pytest.mark.parametrize("variant,field,bad_value,remove", [
    ("D3", "search_candidate_multiplier", 2, False),
    ("P6V", "search_candidate_multiplier", True, False),
    ("P6", "max_concurrent_browses", 4, False),
    ("D6", "max_concurrent_browses", 2.0, False),
    ("D3", "stream_report", True, False),
    ("P6V", "stream_report", 0, False),
    ("P6", "trace_root", "../unverified-traces", False),
    ("D6", "search_candidate_multiplier", None, True),
    ("D3", "trace_root", None, True),
])
def test_recovered_shared_execution_factors_match_original_runner(
    tmp_path, monkeypatch, variant, field, bad_value, remove
):
    """Changing a shared runner factor must not pass as the frozen treatment."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    run_id = f"{variant.lower()}-run-00"
    path = outputs / "experiment_traces" / variant / f"{run_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if remove:
        del payload["experiment"][field]
    else:
        payload["experiment"][field] = bad_value
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert field in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False



@pytest.mark.parametrize("field,replacement", [
    ("smart_model", "another-valid-model"),
    ("fast_model", "other-fast-model"),
    ("temperature", 0.7),
])
def test_original_runtime_llm_controls_cannot_drift_between_treatments(
    tmp_path, monkeypatch, field, replacement
):
    """One altered later-run control cannot silently confound arm comparisons."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D6/d6-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"][field] = replacement
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "LLM controls differ" in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


@pytest.mark.parametrize("field,replacement", [
    ("smart_model", "model-a"),
    ("fast_model", "model-b"),
    ("temperature", 0.7),
    ("temperature", 1),
])
def test_original_runtime_llm_controls_reject_uniform_matrix_substitution(
    tmp_path, monkeypatch, field, replacement
):
    """Even unanimous controls and unchanged synthetic costs are insufficient."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    paths = sorted((outputs / "experiment_traces").glob("*/*.json"))
    assert len(paths) == 40
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        trace = payload["trace"]
        if field == "smart_model":
            # Substitute the corresponding usage bucket at identical synthetic
            # prices, preserving the frozen totals and ledger consistency.
            ledger = trace["provider_usage_by_model"]
            ledger[replacement] = ledger.pop(trace[field])
        trace[field] = replacement
        path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_to_published_evaluator"]["matched"] == 40
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert field in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


@pytest.mark.parametrize("field,replacement,remove", [
    ("smart_model", "", False),
    ("fast_model", "  ", False),
    ("temperature", True, False),
    ("fast_model", None, True),
    ("temperature", None, True),
])
def test_original_runtime_llm_controls_require_valid_trace_values(
    tmp_path, monkeypatch, field, replacement, remove
):
    """Invalid original runtime metadata is not a source-consistent trace."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if remove:
        del payload["trace"][field]
    else:
        payload["trace"][field] = replacement
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert field in result["trace_report_content"]["first_failure"]
    assert result["handoff_verified"] is False



@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_original_runtime_llm_controls_reject_nonfinite_in_memory(invalid):
    """The production JSON reader also rejects nonfinite numbers before this gate."""
    with pytest.raises(ValueError, match="temperature"):
        audit._validate_recovered_llm_controls(
            {"smart_model": "gpt-5.6-terra", "fast_model": "gpt-5.6-luna",
             "temperature": invalid},
        )



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



@pytest.mark.parametrize("variant,field,wrong_value,remove", [
    ("D3", "source_success_rate", 1.0, False),
    ("P6V", "source_success_rate", True, False),
    ("D3", "source_success_rate", None, True),
    ("D3", "verified_claim_count", 1, False),
    ("P6V", "verified_claim_count", 3, False),
    ("P6V", "verified_claim_count", None, True),
    ("P6V", "claim_support_rate", 0.75, False),
    ("P6V", "claim_support_rate", -0.1, False),
    ("P6V", "claim_support_rate", None, True),
    ("P6V", "citation_precision_proxy", 1.0, False),
    ("D3", "citation_precision_proxy", 0.2, False),
    ("D3", "citation_precision_proxy", "0", False),
])
def test_recovered_derived_telemetry_cannot_contradict_original_counters(
    tmp_path, monkeypatch, variant, field, wrong_value, remove
):
    """Archived redundant rates/claim totals cannot be invented or suppressed."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    run_id = f"{variant.lower()}-run-00"
    path = outputs / "experiment_traces" / variant / f"{run_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if remove:
        del payload["trace"][field]
    else:
        payload["trace"][field] = wrong_value
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert field in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


def _zero_source_and_claim_derived_trace():
    return {
        "source_count": 0, "successful_source_count": 0,
        "citation_count": 0, "supported_claim_count": 0,
        "partially_supported_claim_count": 0, "unsupported_claim_count": 0,
        "contradicted_claim_count": 0, "source_success_rate": 0.0,
        "verified_claim_count": 0, "claim_support_rate": 0.0,
        "citation_precision_proxy": 0.0,
    }


def test_original_derived_telemetry_zero_denominators_are_valid():
    """Zero-source and zero-claim traces have defined historical rates of zero."""
    audit._validate_recovered_derived_telemetry(
        _zero_source_and_claim_derived_trace()
    )


@pytest.mark.parametrize("field", [
    "source_success_rate", "claim_support_rate", "citation_precision_proxy",
])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_original_derived_telemetry_rejects_nonfinite_in_memory(field, invalid):
    """Production JSON parsing already rejects nonfinite tokens before this."""
    trace = _zero_source_and_claim_derived_trace()
    trace[field] = invalid
    with pytest.raises(ValueError, match=field):
        audit._validate_recovered_derived_telemetry(trace)


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
    payload["trace"]["provider_usage_by_model"]["gpt-5.6-terra"][field] = bad_value
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert error_fragment in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]


@pytest.mark.parametrize("replacement", ["model-a", "model-b"])
def test_recovered_model_usage_cannot_impersonate_an_unconfigured_model(
    tmp_path, monkeypatch, replacement
):
    """An identically priced unconfigured model must not pass frozen totals."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    provider = payload["trace"]["provider_usage_by_model"]
    provider[replacement] = provider.pop("gpt-5.6-terra")
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_to_published_evaluator"]["matched"] == 40
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "outside recorded smart_model/fast_model" in (
        receipt["trace_report_content"]["first_failure"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


def test_recovered_provider_usage_accepts_consistent_multi_model_accounting(
    tmp_path, monkeypatch
):
    # Both model names are fixed across all 40 recovered treatment traces;
    # a single run may legitimately consume tokens from each.
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"]["provider_usage_by_model"] = {
        "gpt-5.6-terra": {
            "model_calls": 1, "unavailable_calls": 0,
            "prompt_tokens": 60, "completion_tokens": 90, "total_tokens": 150,
        },
        "gpt-5.6-luna": {
            "model_calls": 3, "unavailable_calls": 0,
            "prompt_tokens": 40, "completion_tokens": 60, "total_tokens": 100,
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



def _write_synthetic_annotator_manifest(bundle, order):
    artifacts = {
        role: {"path": name, **exporter._fingerprint((bundle / name).read_bytes())}
        for role, name in (
            ("packet", "packet.jsonl"),
            ("ratings_template", "ratings_template.csv"),
            ("annotator_instructions", "annotator_instructions.md"),
        )
    }
    manifest = {
        "schema_version": 2,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_distribution",
        "coordinator_artifacts_included": False,
        "presentation_order": order,
        "n_reports": len(exporter._read_jsonl_packet((bundle / "packet.jsonl").read_bytes())),
        "content_validator": exporter._content_validator_source_contract(),
        "content_validator_runtime": audit.packet_builder.content_validator_runtime_contract(),
        "artifacts": artifacts,
        "distribution_note": exporter.DISTRIBUTION_NOTE,
    }
    (bundle / "annotator_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8",
    )


def _complete_readiness_inventory(tmp_path, monkeypatch):
    # Synthetic evidence only; the independent handoff is never asserted.
    _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    guide = tmp_path / "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md"
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_bytes(exporter.DEFAULT_ANNOTATOR_GUIDE.read_bytes())
    packet = tmp_path / "outputs/human_eval"
    for name in exporter.COORDINATOR_ARTIFACTS:
        path = packet / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic coordinator artifact", encoding="utf-8")
    for order in ("canonical", "reverse"):
        for name in exporter.ANNOTATOR_ARTIFACTS:
            path = packet / f"annotator-{order}-v1" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name == "annotator_instructions.md":
                path.write_bytes(guide.read_bytes())
            else:
                path.write_text("synthetic annotator artifact", encoding="utf-8")
    # Produce the same byte-level canonical/reverse transformation as export.
    # These are synthetic text rows, never historical reports or human scores.
    rows = []
    key_rows = []
    for n, task in enumerate(audit.lineage.TASKS):
        for variant in audit.VARIANTS:
            blind_id = f"H{len(rows) + 1:03d}"
            run_id = f"{variant.lower()}-run-{n:02d}"
            trace_rel = f"outputs/experiment_traces/{variant}/{run_id}.json"
            report_rel = f"outputs/{run_id}/research_report.md"
            # Make each report distinct while preserving the fixture's frozen
            # 50-word count; no treatment identity in annotator-facing text.
            report = f"Synthetic report {len(rows) + 1} " + "evidence " * 46 + "ending"
            (tmp_path / report_rel).write_text(report, encoding="utf-8")
            rows.append({
                "blind_id": blind_id, "task_id": task,
                "question": f"Synthetic question for {task}",
                "report_markdown": report,
            })
            key_rows.append({
                "blind_id": blind_id, "variant_id": variant, "task_id": task,
                "run_id": run_id, "trace_path": trace_rel, "report_path": report_rel,
            })
    with (packet / "blinding_key.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=audit.packet_verifier.KEY_FIELDS)
        writer.writeheader()
        writer.writerows(key_rows)
    (packet / "packet.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    with (packet / "ratings_template.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit.packet_builder.RATING_FIELDS))
        writer.writeheader()
        writer.writerows({"blind_id": row["blind_id"]} for row in rows)
    for order in ("canonical", "reverse"):
        expected = exporter._ordered_artifacts(
            (packet / "packet.jsonl").read_bytes(),
            (packet / "ratings_template.csv").read_bytes(),
            presentation_order=order,
        )
        for name, content in zip(("packet.jsonl", "ratings_template.csv"), expected):
            (packet / f"annotator-{order}-v1" / name).write_bytes(content)
        _write_synthetic_annotator_manifest(packet / f"annotator-{order}-v1", order)
    kwargs = {
        "repo_root": tmp_path,
        "research_manifest_sha256": hashlib.sha256(
            (tmp_path / audit.published.MANIFEST).read_bytes()
        ).hexdigest(),
        "coordinator_manifest_sha256": hashlib.sha256(
            (packet / "manifest.json").read_bytes()
        ).hexdigest(),
    }
    return packet, kwargs


@pytest.mark.parametrize("resource,relative", [
    ("coordinator/blinding_key.csv", "blinding_key.csv"),
    ("canonical/packet.jsonl", "annotator-canonical-v1/packet.jsonl"),
    ("reverse/ratings_template.csv", "annotator-reverse-v1/ratings_template.csv"),
])
def test_hardlink_alias_blocks_otherwise_complete_inventory(
    tmp_path, monkeypatch, resource, relative
):
    packet, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    baseline = audit.audit_archive_readiness(**kwargs)
    assert baseline["blockers"] == []
    candidate = packet / relative
    before = candidate.read_bytes()
    alias = tmp_path / "unselected-alias"
    try:
        alias.hardlink_to(candidate)
    except (OSError, NotImplementedError):
        pytest.skip("hardlinks unavailable on this test filesystem")
    assert candidate.read_bytes() == before == alias.read_bytes()

    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["resources"][resource] == "unsafe_hardlink"
    assert receipt["blockers"] == [resource]
    assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False


@pytest.mark.parametrize("mutation", ["missing", "symlink", "directory"])
def test_late_task_manifest_unavailability_blocks_otherwise_complete_inventory(
    tmp_path, monkeypatch, mutation
):
    _, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    baseline = audit.audit_archive_readiness(**kwargs)
    assert baseline["status"] == "candidate_inputs_present_not_verified"
    assert baseline["blockers"] == []
    assert baseline["handoff_verified"] is False

    task_file = tmp_path / "experiments/main_budget_tasks.json"

    def change_after_stated_verification(**_kwargs):
        original = task_file.read_bytes()
        task_file.unlink()
        if mutation == "symlink":
            target = tmp_path / "unverified-task-copy.json"
            target.write_bytes(original)
            task_file.symlink_to(target)
        elif mutation == "directory":
            task_file.mkdir()
        return {}

    monkeypatch.setattr(
        audit.frozen_tasks, "verify_frozen_task_manifest",
        change_after_stated_verification,
    )
    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["resources"]["frozen_task_manifest"] == "present_unverified"
    assert receipt["frozen_task_manifest_anchor"] == (
        "original_treatment_run_task_manifest_matches"
    )
    assert receipt["trace_report_content"]["status"] == (
        "invalid_frozen_task_or_evaluator"
    )
    assert receipt["trace_report_content"]["checked"] == 0
    assert "unavailable after source verification" in (
        receipt["trace_report_content"]["reason"]
    )
    assert receipt["blockers"] == ["original_trace_report_content_alignment"]
    assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


@pytest.mark.parametrize("field,bad_value,remove", [
    ("cost_accounting_status", "provider_billed", False),
    ("cost_accounting_status", "estimated_from_frozen_uncached_rates", False),
    ("cost_accounting_status", "", False),
    ("cost_accounting_status", None, False),
    ("cost_accounting_status", None, True),
    ("estimated_cost_usd", 0.0002, False),
    ("estimated_cost_usd", -0.01, False),
    ("estimated_cost_usd", True, False),
    ("estimated_cost_usd", 0, False),
    ("estimated_cost_usd", "0.0", False),
    ("estimated_cost_usd", None, False),
    ("estimated_cost_usd", None, True),
])
def test_recovered_trace_preserves_original_unpriced_cost_semantics(
    tmp_path, monkeypatch, field, bad_value, remove
):
    """Frozen-priced costs cannot be laundered into raw execution telemetry."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if remove:
        del payload["trace"][field]
    else:
        payload["trace"][field] = bad_value
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_to_published_evaluator"]["matched"] == 40
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert field in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


@pytest.mark.parametrize("field,invalid", [
    ("estimated_cost_usd", float("nan")),
    ("estimated_cost_usd", float("inf")),
    ("estimated_cost_usd", -float("inf")),
])
def test_recovered_unpriced_cost_rejects_nonfinite_in_memory(field, invalid):
    """The validator remains safe even without the production strict JSON reader."""
    trace = {
        "cost_accounting_status": audit.ORIGINAL_TRACE_COST_STATUS,
        "estimated_cost_usd": 0.0,
    }
    trace[field] = invalid
    with pytest.raises(ValueError, match="estimated_cost_usd"):
        audit._validate_recovered_trace_cost_provenance(trace)


def test_original_unpriced_trace_cost_contract_accepts_valid_placeholder():
    audit._validate_recovered_trace_cost_provenance({
        "cost_accounting_status": audit.ORIGINAL_TRACE_COST_STATUS,
        "estimated_cost_usd": 0.0,
    })


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
    ledger[replacement] = ledger.pop("gpt-5.6-terra")
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
    payload["models"]["gpt-5.6-terra"]["output"] = 1.3
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
            {"query": "second", "candidate_urls": [], "scheduled_urls": [],
             "search_error": "synthetic outage"},
            {"query": "first", "candidate_urls": [], "scheduled_urls": [],
             "search_error": "synthetic outage"},
        ],
        "scheduled_urls": [],
    }
    with pytest.raises(ValueError, match="query order"):
        audit._validate_recovered_search_provenance(trace)


@pytest.mark.parametrize("variant", ["D3", "D6"])
def test_original_direct_query_must_be_exact_frozen_question(
    tmp_path, monkeypatch, variant
):
    """Self-consistent renamed search records cannot change direct treatment."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    trace_file = outputs / "experiment_traces" / variant / f"{variant.lower()}-run-00.json"
    payload = json.loads(trace_file.read_text(encoding="utf-8"))
    trace = payload["trace"]
    trace["search_queries"] = ["Different research question"]
    trace["search_records"][0]["query"] = "Different research question"
    trace_file.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "direct search query differs" in (
        receipt["trace_report_content"]["first_failure"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]


@pytest.mark.parametrize("variant", ["P6", "P6V"])
def test_planner_per_query_budget_cannot_be_reallocated_in_recovered_trace(
    tmp_path, monkeypatch, variant
):
    """Frozen global source totals cannot conceal violating the planned split."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    trace_file = outputs / "experiment_traces" / variant / f"{variant.lower()}-run-00.json"
    payload = json.loads(trace_file.read_text(encoding="utf-8"))
    trace = payload["trace"]
    # Original planner distribution is [2, 2, 1, 1]. Move the third
    # scheduled URL into query one while leaving every global counter,
    # order, URL partition, and frozen CSV measurement unchanged.
    trace["search_records"][0]["candidate_urls"].append("https://example.test/c")
    trace["search_records"][0]["scheduled_urls"].append("https://example.test/c")
    trace["search_records"][1]["scheduled_urls"] = []
    trace_file.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "per-query browse budget" in (
        receipt["trace_report_content"]["first_failure"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]


@pytest.mark.parametrize("variant", ["P6", "P6V"])
def test_recovered_planner_requires_four_planned_queries(
    tmp_path, monkeypatch, variant
):
    """A valid source ledger must also obey the frozen planner contract."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    trace_file = outputs / "experiment_traces" / variant / f"{variant.lower()}-run-00.json"
    payload = json.loads(trace_file.read_text(encoding="utf-8"))
    trace = payload["trace"]
    trace["search_queries"].append("fifth planned query")
    trace["query_count"] += 1
    trace_file.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "original four-query plan" in receipt["trace_report_content"]["first_failure"]


def test_query_allocation_accepts_skipped_and_duplicate_planner_queries():
    """Distinct planned slots remain enforceable even when text repeats."""
    trace = {
        "source_budget": 6,
        "search_queries": ["same", "same", "other", "last"],
        "search_records": [
            {"query": "same", "candidate_urls": ["a", "b"],
             "scheduled_urls": ["a", "b"]},
            {"query": "same", "candidate_urls": ["a", "c", "d"],
             "scheduled_urls": ["c", "d"]},
            {"query": "other", "candidate_urls": ["b", "e"],
             "scheduled_urls": ["e"]},
            {"query": "last", "candidate_urls": ["e", "f"],
             "scheduled_urls": ["f"]},
        ],
    }
    audit._validate_recovered_query_budget_allocation(trace, variant="P6V")


def test_query_allocation_rejects_search_without_allocated_budget():
    trace = {
        "source_budget": 1,
        "search_queries": ["first", "second", "third", "fourth"],
        "search_records": [
            {"query": "second", "scheduled_urls": []},
        ],
    }
    with pytest.raises(ValueError, match="skipped an eligible planned query"):
        audit._validate_recovered_query_budget_allocation(trace, variant="P6")


def test_query_allocation_rejects_skipping_earlier_eligible_candidate():
    """Original get_new_urls cannot silently omit an unseen candidate."""
    trace = {
        "source_budget": 3,
        "question": "original question",
        "search_queries": ["original question"],
        "search_records": [{
            "query": "original question",
            "candidate_urls": ["a", "b", "c"],
            "scheduled_urls": ["a", "c"],
        }],
    }
    with pytest.raises(ValueError, match="greedy candidate URL scheduling"):
        audit._validate_recovered_query_budget_allocation(trace, variant="D3")


def test_query_allocation_accepts_greedy_deduplication_and_search_failure():
    """Candidates are unique within a search; cross-query repeats are skipped."""
    trace = {
        "source_budget": 6,
        "search_queries": ["first", "second", "third", "fourth"],
        "search_records": [
            {"query": "first", "candidate_urls": ["a", "b", "c"],
             "scheduled_urls": ["a", "b"]},
            {"query": "second", "candidate_urls": ["b", "a", "c", "d"],
             "scheduled_urls": ["c", "d"]},
            {"query": "third", "candidate_urls": ["c", "e"],
             "scheduled_urls": ["e"]},
            {"query": "fourth", "candidate_urls": [], "scheduled_urls": [],
             "search_error": "transient outage"},
        ],
    }
    audit._validate_recovered_search_provenance({
        **trace, "query_count": 4, "search_call_count": 4,
        "scheduled_urls": ["a", "b", "c", "d", "e"],
    })
    audit._validate_recovered_query_budget_allocation(trace, variant="P6")


def test_archive_recovery_rejects_omitted_greedy_result_with_frozen_counts(
    tmp_path, monkeypatch
):
    """A tampered candidate order cannot hide behind matching frozen totals."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/P6/p6-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    first = payload["trace"]["search_records"][0]
    first["candidate_urls"].insert(0, "https://example.test/unseen")
    # Leave scheduled URLs and every aggregate measurement unchanged. The old
    # subsequence/plan-budget checks accepted this altered search record.
    path.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "greedy candidate URL scheduling" in (
        receipt["trace_report_content"]["first_failure"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


def test_late_report_rewrite_blocks_complete_matrix_content_alignment(
    tmp_path, monkeypatch
):
    """One early source changing after its own check must fail the 40-cell gate."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    original_report = outputs / "d3-run-00" / "research_report.md"
    original_validator = audit.packet_builder.validate_annotator_facing_content
    checked = {"count": 0}

    def change_after_last_content_check(*args, **kwargs):
        result = original_validator(*args, **kwargs)
        checked["count"] += 1
        if checked["count"] == 40:
            original_report.write_text(
                original_report.read_text(encoding="utf-8").replace(
                    "archive-ending", "archive-changed"
                ),
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(
        audit.packet_builder, "validate_annotator_facing_content",
        change_after_last_content_check,
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert checked["count"] == 40
    assert result["trace_report_content"]["status"] == (
        "recovered_candidates_changed_during_audit"
    )
    assert result["trace_report_content"]["checked"] == 40
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


def _historical_candidate_limit_trace(*, candidates):
    scheduled = [f"https://example.test/{index}" for index in range(6)]
    return {
        "source_budget": 6,
        "question": "frozen question",
        "query_count": 1,
        "search_call_count": 1,
        "search_queries": ["frozen question"],
        "search_records": [{
            "query": "frozen question",
            "candidate_urls": candidates,
            "scheduled_urls": scheduled,
        }],
        "scheduled_urls": scheduled,
    }


def test_recovered_search_accepts_maximum_historical_unique_candidate_pool():
    """D6 requested up to 18 normalized candidates and browsed at most six."""
    candidates = [f"https://example.test/{index}" for index in range(18)]
    trace = _historical_candidate_limit_trace(candidates=candidates)
    audit._validate_recovered_search_provenance(trace)
    audit._validate_recovered_query_budget_allocation(trace, variant="D6")


@pytest.mark.parametrize("mutation", ["over_limit", "duplicate", "untrimmed"])
def test_recovered_search_rejects_impossible_historical_candidate_list(mutation):
    """Frozen scheduled-source totals can agree with an impossible search list."""
    candidates = [f"https://example.test/{index}" for index in range(18)]
    if mutation == "over_limit":
        candidates.append("https://example.test/18")
    elif mutation == "duplicate":
        candidates[-1] = candidates[0]
    else:
        candidates[-1] += " "
    trace = _historical_candidate_limit_trace(candidates=candidates)
    audit._validate_recovered_search_provenance(trace)
    with pytest.raises(ValueError, match="search candidate list"):
        audit._validate_recovered_query_budget_allocation(trace, variant="D6")


def test_archive_readiness_blocks_oversized_candidate_pool_despite_frozen_counts(
    tmp_path, monkeypatch
):
    """The 40-cell recovery diagnostic must enforce original candidate limits."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    record = payload["trace"]["search_records"][0]
    # D3 has already scheduled its complete three-source budget; the prior
    # greedy scheduler accepted arbitrarily many trailing search candidates.
    # Ten exceeds the source-pinned three-times-budget limit of nine.
    record["candidate_urls"].extend(
        f"https://example.test/extra-{index}" for index in range(7)
    )
    # Do not alter frozen CSVs, scheduled URLs, search counts or report bytes.
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "search candidate list" in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False

def _planner_query_trace(*, queries, records, budget=6):
    """Produce internally coherent synthetic provenance without frozen outcomes."""
    trace = {
        "source_budget": budget,
        "search_queries": queries,
        "query_count": len(queries),
        "search_records": records,
        "search_call_count": len(records),
        "scheduled_urls": [
            url for record in records for url in record["scheduled_urls"]
        ],
    }
    return trace


def test_query_allocation_rejects_skipped_eligible_middle_query():
    """A missing planned search cannot be hidden behind later valid records."""
    queries = ["first", "second", "third", "fourth"]
    records = [
        {"query": "first", "candidate_urls": ["a", "b"],
         "scheduled_urls": ["a", "b"]},
        {"query": "third", "candidate_urls": ["c"],
         "scheduled_urls": ["c"]},
        {"query": "fourth", "candidate_urls": ["d"],
         "scheduled_urls": ["d"]},
    ]
    trace = _planner_query_trace(queries=queries, records=records)
    # Earlier subsequence and greedy checks accepted these ledgers. Yet the
    # historical loop would have run "second" with two available browse slots.
    audit._validate_recovered_search_provenance(trace)
    with pytest.raises(ValueError, match="skipped an eligible planned query"):
        audit._validate_recovered_query_budget_allocation(trace, variant="P6")


def test_query_allocation_rejects_omitted_final_search_with_budget_remaining():
    """No trailing eligible planner query can disappear from a completed trace."""
    queries = ["first", "second", "third", "fourth"]
    records = [
        {"query": "first", "candidate_urls": ["a", "b"],
         "scheduled_urls": ["a", "b"]},
        {"query": "second", "candidate_urls": ["c", "d"],
         "scheduled_urls": ["c", "d"]},
        {"query": "third", "candidate_urls": ["e"], "scheduled_urls": ["e"]},
    ]
    trace = _planner_query_trace(queries=queries, records=records)
    audit._validate_recovered_search_provenance(trace)
    with pytest.raises(ValueError, match="omit an eligible planned query"):
        audit._validate_recovered_query_budget_allocation(trace, variant="P6")


def test_query_allocation_accepts_all_eligible_queries_even_after_search_failure():
    """A failed metasearch call still occupies its sequential planned slot."""
    queries = ["first", "second", "third", "fourth"]
    records = [
        {"query": "first", "candidate_urls": [], "scheduled_urls": [],
         "search_error": "synthetic outage"},
        {"query": "second", "candidate_urls": ["a", "b"],
         "scheduled_urls": ["a", "b"]},
        {"query": "third", "candidate_urls": ["c"], "scheduled_urls": ["c"]},
        {"query": "fourth", "candidate_urls": ["d"], "scheduled_urls": ["d"]},
    ]
    trace = _planner_query_trace(queries=queries, records=records)
    audit._validate_recovered_search_provenance(trace)
    audit._validate_recovered_query_budget_allocation(trace, variant="P6V")


def test_query_allocation_allows_omitting_only_zero_allocation_plan_slots():
    """The runner can skip zero-budget queries but must attempt every eligible."""
    queries = ["first", "second", "third", "fourth"]
    records = [
        {"query": "first", "candidate_urls": ["a"],
         "scheduled_urls": ["a"]},
    ]
    trace = _planner_query_trace(queries=queries, records=records, budget=1)
    audit._validate_recovered_search_provenance(trace)
    audit._validate_recovered_query_budget_allocation(trace, variant="P6")


def _search_outcome_trace():
    """Synthetic coherent search ledger with a legitimate metasearch failure."""
    records = [
        {"query": "first", "candidate_urls": ["a"], "scheduled_urls": ["a"]},
        {"query": "second", "candidate_urls": [], "scheduled_urls": [],
         "search_error": "synthetic backend outage"},
        {"query": "third", "candidate_urls": ["b"], "scheduled_urls": ["b"]},
        {"query": "fourth", "candidate_urls": ["c"], "scheduled_urls": ["c"]},
    ]
    return _planner_query_trace(
        queries=["first", "second", "third", "fourth"], records=records
    )


def test_search_outcome_accepts_bounded_recorded_failure():
    """The original async_search can continue after a recorded RuntimeError."""
    trace = _search_outcome_trace()
    audit._validate_recovered_search_provenance(trace)
    audit._validate_recovered_query_budget_allocation(trace, variant="P6")
    trace["search_records"][1]["search_error"] = "x" * 1000
    audit._validate_recovered_search_provenance(trace)


@pytest.mark.parametrize("mutation", ["missing", "empty", "overlong"])
def test_search_outcome_rejects_impossible_unmarked_or_malformed_failure(mutation):
    """Budget/URL totals alone cannot distinguish an invented no-hit outcome."""
    trace = _search_outcome_trace()
    record = trace["search_records"][1]
    if mutation == "missing":
        del record["search_error"]
    elif mutation == "empty":
        record["search_error"] = ""
    else:
        record["search_error"] = "x" * 1001
    # Existing budget/allocation checks independently accept these same
    # frozen-counter-compatible records; only the search-outcome gate rejects.
    audit._validate_recovered_query_budget_allocation(trace, variant="P6")
    message = ("without search_error" if mutation == "missing"
               else "search_error record")
    with pytest.raises(ValueError, match=message):
        audit._validate_recovered_search_provenance(trace)


def test_archive_readiness_rejects_unmarked_search_failure_in_40_cell_matrix(
    tmp_path, monkeypatch
):
    """A plausible frozen aggregate must not excuse an impossible search event."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces/P6/p6-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["trace"]["search_records"][2]["search_error"]
    del payload["trace"]["search_records"][2]["search_error"]
    # No changes to published measurements, counts, scheduled URLs or report.
    path.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "empty candidates without search_error" in (
        receipt["trace_report_content"]["first_failure"]
    )
    assert "original_trace_report_content_alignment" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


@pytest.mark.parametrize("bad_time", [
    None, "", 123, False, "2026-09-11T16:20:02",
    "2026-09-11T16:20:02+05:30", "2026-09-11 16:20:02+00:00",
    "not-a-time", "2026-09-11T16:19:54+00:00",
    "2026-09-11T17:22:44+00:00",
])
def test_historical_trace_save_timestamp_requires_original_utc_window(bad_time):
    started = datetime(2026, 9, 11, 16, 20, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="recorded_at_utc"):
        audit._validate_recovered_persistence_time(
            {"recorded_at_utc": bad_time},
            started_at=started, latency_seconds=1.25,
        )


def test_historical_trace_save_timestamp_rejects_impossible_elapsed_duration():
    started = datetime(2026, 9, 11, 16, 20, tzinfo=timezone.utc)
    # Save time is within the historical workflow yet predates completion
    # by more than the existing five-second wall/monotonic-clock allowance.
    with pytest.raises(ValueError, match="completed run duration"):
        audit._validate_recovered_persistence_time(
            {"recorded_at_utc": started.isoformat()},
            started_at=started, latency_seconds=6.9,
        )


def test_historical_trace_save_timestamp_accepts_small_clock_margin():
    started = datetime(2026, 9, 11, 16, 20, tzinfo=timezone.utc)
    recorded = started + timedelta(seconds=1.9)
    assert audit._validate_recovered_persistence_time(
        {"recorded_at_utc": recorded.isoformat()},
        started_at=started, latency_seconds=6.9,
    ) == recorded


@pytest.mark.parametrize("value", [None, "2026-09-11T16:20:02+05:30"])
def test_historical_trace_save_timestamp_is_required_in_whole_matrix(
    tmp_path, monkeypatch, value,
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    trace_path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    if value is None:
        del payload["recorded_at_utc"]
    else:
        payload["recorded_at_utc"] = value
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "recorded_at_utc" in result["trace_report_content"]["first_failure"]
    assert result["handoff_verified"] is False


def test_original_trace_save_must_precede_next_treatment_start(
    tmp_path, monkeypatch,
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    trace_path = outputs / "experiment_traces/D3/d3-run-00.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    # Treatment starts and frozen measurements stay valid. The prior
    # persisted-trace timestamp alone is nine seconds after its own start,
    # seven seconds after the next treatment start.
    payload["recorded_at_utc"] = "2026-09-11T16:20:09+00:00"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "next sequential treatment start" in (
        result["trace_report_content"]["first_failure"]
    )
    assert result["handoff_verified"] is False


@pytest.mark.parametrize("variant", ["D3", "P6V"])
def test_recovered_source_outcome_order_blocks_full_matrix_readiness(
    tmp_path, monkeypatch, variant
):
    """Reordering outcomes changes provenance without changing frozen counts."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces" / variant / f"{variant.lower()}-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["trace"]["successful_urls"].reverse()
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "successful_urls violates original source outcome order" in (
        result["trace_report_content"]["first_failure"]
    )
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


@pytest.mark.parametrize("reversed_ledger", [None, "successful_urls", "failed_urls"])
def test_original_source_outcome_ledgers_preserve_scheduling_order(reversed_ledger):
    trace = {
        "source_count": 4, "query_count": 4, "search_call_count": 4,
        "successful_source_count": 2, "failed_source_count": 2,
        "usage_accounting_status": "provider_usage_complete",
        "scheduled_urls": ["a", "b", "c", "d"],
        "successful_urls": ["a", "c"],
        "failed_urls": ["b", "d"],
    }
    if reversed_ledger is None:
        audit._validate_recovered_source_ledgers(trace, variant="P6V")
    else:
        trace[reversed_ledger].reverse()
        with pytest.raises(ValueError, match=f"{reversed_ledger} violates original source outcome order"):
            audit._validate_recovered_source_ledgers(trace, variant="P6V")


@pytest.mark.parametrize("variant,words", [
    ("D3", None), ("P6V", True), ("D3", 24.0), ("P6V", -1),
    ("D3", 0), ("P6V", 11),
])
def test_recovered_context_word_count_blocks_full_matrix_readiness(
    tmp_path, monkeypatch, variant, words,
):
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces" / variant / f"{variant.lower()}-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if words is None:
        del payload["trace"]["research_context_words"]
    else:
        payload["trace"]["research_context_words"] = words
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "research_context_words" in result["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in result["blockers"]
    assert result["handoff_verified"] is False


@pytest.mark.parametrize("urls,words,valid", [
    ([], 0, True), ([], 1, False),
    (["https://example.test/a"], 6, True),
    (["https://example.test/a"], 5, False),
    (["a", "b"], 12, True), (["a", "b"], 11, False),
    (["a", "b"], 100, True),
    (["a b"], 7, True),
])
def test_original_retrieval_context_word_bound(urls, words, valid):
    trace = {"successful_urls": urls, "research_context_words": words}
    if valid:
        audit._validate_recovered_context_words(trace)
    else:
        with pytest.raises(ValueError, match="contradicts original source summaries"):
            audit._validate_recovered_context_words(trace)


@pytest.mark.parametrize("variant,smart_delta", [
    ("D3", 1), ("D6", 1), ("P6", -1), ("P6V", -1),
])
def test_original_model_call_roles_reject_reallocated_calls(
    tmp_path, monkeypatch, variant, smart_delta
):
    """Preserve total calls, tokens, costs and all frozen CSV/report bytes."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    path = outputs / "experiment_traces" / variant / f"{variant.lower()}-run-00.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    ledger = payload["trace"]["provider_usage_by_model"]
    ledger["gpt-5.6-terra"]["model_calls"] += smart_delta
    ledger["gpt-5.6-luna"]["model_calls"] -= smart_delta
    path.write_text(json.dumps(payload), encoding="utf-8")
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert receipt["trace_to_published_evaluator"]["matched"] == 40
    assert receipt["trace_report_content"]["status"] == (
        "invalid_or_mismatched_trace_report_content"
    )
    assert "smart model call count" in receipt["trace_report_content"]["first_failure"]
    assert "original_trace_report_content_alignment" in receipt["blockers"]
    assert receipt["handoff_verified"] is False


@pytest.mark.parametrize("variant,smart,fast,success,scheduled,valid", [
    ("D3", 1, 0, 0, 3, True),
    ("D3", 1, 2, 2, 3, True),
    ("D3", 1, 3, 2, 3, True),
    ("D3", 1, 1, 2, 3, False),
    ("D6", 1, 7, 2, 6, False),
    ("P6", 2, 4, 3, 6, True),
    ("P6V", 3, 4, 0, 6, True),
])
def test_original_model_call_role_source_bounds(
    variant, smart, fast, success, scheduled, valid
):
    trace = {
        "smart_model": "gpt-5.6-terra", "fast_model": "gpt-5.6-luna",
        "successful_source_count": success, "source_count": scheduled,
        "provider_usage_by_model": {
            "gpt-5.6-terra": {"model_calls": smart},
            **({"gpt-5.6-luna": {"model_calls": fast}} if fast else {}),
        },
    }
    if valid:
        audit._validate_recovered_model_call_roles(trace, variant=variant)
    else:
        with pytest.raises(ValueError, match="fast model call count"):
            audit._validate_recovered_model_call_roles(trace, variant=variant)


@pytest.mark.parametrize("addition", [None, "D3/unexpected.json", "extra"])
def test_late_trace_inventory_addition_blocks_matrix_content_alignment(
    tmp_path, monkeypatch, addition,
):
    """The complete inventory must remain exact, not only its pinned files."""
    outputs = _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    trace_root = outputs / "experiment_traces"
    original_validator = audit.packet_builder.validate_annotator_facing_content
    checked = 0

    def change_after_last_content_check(*args, **kwargs):
        nonlocal checked
        result = original_validator(*args, **kwargs)
        checked += 1
        if checked == 40 and addition is not None:
            extra = trace_root / addition
            if extra.suffix == ".json":
                extra.write_text("{}", encoding="utf-8")
            else:
                extra.mkdir()
        return result

    monkeypatch.setattr(
        audit.packet_builder, "validate_annotator_facing_content",
        change_after_last_content_check,
    )
    result = audit.audit_archive_readiness(repo_root=tmp_path)
    assert checked == 40
    assert result["trace_to_published_evaluator"]["matched"] == 40
    assert result["trace_report_content"]["checked"] == 40
    if addition is None:
        assert result["trace_report_content"]["status"] == (
            "40_trace_report_contents_align_to_frozen_cells_not_authenticated"
        )
        assert "original_trace_report_content_alignment" not in result["blockers"]
    else:
        assert result["trace_report_content"]["status"] == (
            "recovered_candidates_changed_during_audit"
        )
        assert "recovered trace inventory changed" in result["trace_report_content"]["reason"]
        assert "original_trace_report_content_alignment" in result["blockers"]
        assert result["status"] == "blocked"
    assert result["handoff_verified"] is False


@pytest.mark.parametrize("relative,mutation", [
    (None, None),
    ("experiments/main_budget_tasks.json", "append"),
    (audit.lineage.MAIN_REL, "append"),
    (audit.lineage.SUPPORT_REL, "append"),
    (audit.FROZEN_PRICING_REL, "append"),
    (audit.FROZEN_PRICING_REL, "missing"),
    ("experiments/main_budget_tasks.json", "symlink"),
])
def test_late_frozen_content_input_change_blocks_matrix_alignment(
    tmp_path, monkeypatch, relative, mutation,
):
    """Unchanged candidate bytes cannot compensate for stale governing inputs."""
    _write_semantically_aligned_fixture(tmp_path, monkeypatch)
    original_validator = audit.packet_builder.validate_annotator_facing_content
    checked = 0

    def change_after_last_content_check(*args, **kwargs):
        nonlocal checked
        result = original_validator(*args, **kwargs)
        checked += 1
        if checked == 40 and relative is not None:
            path = tmp_path / relative
            if mutation == "append":
                path.write_bytes(path.read_bytes() + b"\n")
            elif mutation == "missing":
                path.unlink()
            elif mutation == "symlink":
                target = tmp_path / "unverified-task-copy.json"
                target.write_bytes(path.read_bytes())
                path.unlink()
                path.symlink_to(target)
        return result

    monkeypatch.setattr(
        audit.packet_builder, "validate_annotator_facing_content",
        change_after_last_content_check,
    )
    receipt = audit.audit_archive_readiness(repo_root=tmp_path)
    assert checked == 40
    assert receipt["trace_to_published_evaluator"]["matched"] == 40
    assert receipt["trace_report_content"]["checked"] == 40
    if relative is None:
        assert receipt["trace_report_content"]["status"] == (
            "40_trace_report_contents_align_to_frozen_cells_not_authenticated"
        )
        assert "original_trace_report_content_alignment" not in receipt["blockers"]
    else:
        assert receipt["trace_report_content"]["status"] == (
            "invalid_frozen_task_or_evaluator"
        )
        assert relative in receipt["trace_report_content"]["reason"]
        assert "original_trace_report_content_alignment" in receipt["blockers"]
        assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


@pytest.mark.parametrize("relative,mutation,resource,pin", [
    (None, None, None, None),
    ("outputs/human_eval/blinding_key.csv", "remove",
     "coordinator/blinding_key.csv", None),
    ("outputs/human_eval/annotator-canonical-v1/packet.jsonl", "hardlink",
     "canonical/packet.jsonl", None),
    ("paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md", "symlink",
     "frozen_annotator_guide", None),
    ("outputs/human_eval/manifest.json", "append",
     "coordinator/manifest.json", "coordinator_manifest_file"),
    (audit.published.MANIFEST, "append",
     "research_manifest", "research_manifest_file"),
])
def test_final_inventory_and_pins_cannot_report_stale_zero_blockers(
    tmp_path, monkeypatch, relative, mutation, resource, pin,
):
    _, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    original = audit._trace_report_content_status

    def change_after_content_check(**arguments):
        result = original(**arguments)
        assert result["checked"] == 40
        assert result["status"] == (
            "40_trace_report_contents_align_to_frozen_cells_not_authenticated"
        )
        if relative is not None:
            candidate = tmp_path / relative
            if mutation == "remove":
                candidate.unlink()
            elif mutation == "hardlink":
                try:
                    (tmp_path / "late-alias").hardlink_to(candidate)
                except (OSError, NotImplementedError):
                    pytest.skip("hardlinks unavailable on this test filesystem")
            elif mutation == "symlink":
                alias = tmp_path / "late-alias"
                candidate.rename(alias)
                try:
                    candidate.symlink_to(alias)
                except (OSError, NotImplementedError):
                    pytest.skip("symlinks unavailable on this test filesystem")
            elif mutation == "append":
                candidate.write_bytes(candidate.read_bytes() + b"\\n")
        return result

    monkeypatch.setattr(audit, "_trace_report_content_status", change_after_content_check)
    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    if relative is None:
        assert receipt["blockers"] == []
        assert receipt["status"] == "candidate_inputs_present_not_verified"
    elif pin is not None:
        assert receipt["resources"][resource] == "present_unverified"
        assert receipt["independent_pins"][pin] == "pin_mismatch"
        assert receipt["blockers"] == [pin]
        assert receipt["status"] == "blocked"
    else:
        assert receipt["resources"][resource] == {
            "remove": "missing", "hardlink": "unsafe_hardlink",
            "symlink": "unsafe_file_type",
        }[mutation]
        assert receipt["blockers"] == [resource]
        assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


@pytest.mark.parametrize("relative,resource", [
    ("paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md", "frozen_annotator_guide"),
    ("outputs/human_eval/annotator-canonical-v1/annotator_instructions.md",
     "canonical/annotator_instructions.md"),
    ("outputs/human_eval/annotator-reverse-v1/annotator_instructions.md",
     "reverse/annotator_instructions.md"),
])
@pytest.mark.parametrize("late", [False, True])
def test_frozen_instruction_bytes_required_for_complete_readiness(
    tmp_path, monkeypatch, relative, resource, late,
):
    _, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    candidate = tmp_path / relative

    def change_guide():
        candidate.write_bytes(candidate.read_bytes() + b"\nChanged scoring instructions.\n")

    if late:
        original = audit._trace_report_content_status

        def change_after_content_check(**arguments):
            result = original(**arguments)
            assert result["checked"] == 40
            change_guide()
            return result

        monkeypatch.setattr(audit, "_trace_report_content_status", change_after_content_check)
    else:
        change_guide()

    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    assert receipt["resources"][resource] == "frozen_guide_fingerprint_mismatch"
    assert receipt["blockers"] == [resource]
    assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


def test_concordant_instruction_substitutions_do_not_define_new_rubric(
    tmp_path, monkeypatch,
):
    packet, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    for candidate in (
        tmp_path / "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
        packet / "annotator-canonical-v1/annotator_instructions.md",
        packet / "annotator-reverse-v1/annotator_instructions.md",
    ):
        candidate.write_bytes(b"Identical but unfrozen scoring instructions.")
    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    assert receipt["blockers"] == [
        "canonical/annotator_instructions.md",
        "frozen_annotator_guide",
        "reverse/annotator_instructions.md",
    ]
    assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False


@pytest.mark.parametrize("order,extra,late", [
    ("canonical", "blinding_key.csv", False),
    ("reverse", "blinding_key.csv", False),
    ("canonical", "blinding_key.csv", True),
    ("reverse", "manifest.json", True),
    ("reverse", "unexpected-directory", False),
])
def test_contaminated_annotator_inventory_blocks_complete_readiness(
    tmp_path, monkeypatch, order, extra, late,
):
    packet, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    bundle = packet / f"annotator-{order}-v1"
    baseline = audit.audit_archive_readiness(**kwargs)
    assert baseline["blockers"] == []
    before = {name: (bundle / name).read_bytes()
              for name in exporter.ANNOTATOR_ARTIFACTS}

    def contaminate():
        candidate = bundle / extra
        if extra == "unexpected-directory":
            candidate.mkdir()
        else:
            # Synthetic coordinator-only content, not genuine ratings.
            candidate.write_bytes((packet / extra).read_bytes())

    if late:
        original = audit._trace_report_content_status

        def contaminate_after_content_check(**arguments):
            result = original(**arguments)
            assert result["checked"] == 40
            contaminate()
            return result

        monkeypatch.setattr(
            audit, "_trace_report_content_status", contaminate_after_content_check
        )
    else:
        contaminate()

    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    assert receipt["trace_report_content"]["status"] == (
        "40_trace_report_contents_align_to_frozen_cells_not_authenticated"
    )
    assert before == {name: (bundle / name).read_bytes()
                      for name in exporter.ANNOTATOR_ARTIFACTS}
    label = f"{order}/artifact_inventory"
    assert receipt["resources"][label] == "annotator_bundle_artifact_set_mismatch"
    assert receipt["blockers"] == [label]
    assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


@pytest.mark.parametrize("mutation,late", [
    ("duplicate_packet", False),
    ("duplicate_template", False),
    ("swapped_packets", False),
    ("changed_report", False),
    ("duplicate_packet", True),
])
def test_presentation_pair_requires_actual_exported_order(
    tmp_path, monkeypatch, mutation, late,
):
    packet, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    canonical = packet / "annotator-canonical-v1"
    reverse = packet / "annotator-reverse-v1"
    assert audit.audit_archive_readiness(**kwargs)["blockers"] == []

    def mutate():
        if mutation == "duplicate_packet":
            (reverse / "packet.jsonl").write_bytes((canonical / "packet.jsonl").read_bytes())
        elif mutation == "duplicate_template":
            (reverse / "ratings_template.csv").write_bytes(
                (canonical / "ratings_template.csv").read_bytes()
            )
        elif mutation == "swapped_packets":
            first = (canonical / "packet.jsonl").read_bytes()
            (canonical / "packet.jsonl").write_bytes((reverse / "packet.jsonl").read_bytes())
            (reverse / "packet.jsonl").write_bytes(first)
        else:
            path = reverse / "packet.jsonl"
            path.write_bytes(path.read_bytes().replace(b"Synthetic report 40", b"Different report 40"))

    if late:
        original = audit._trace_report_content_status

        def change_after_content_check(**arguments):
            result = original(**arguments)
            assert result["checked"] == 40
            mutate()
            return result

        monkeypatch.setattr(audit, "_trace_report_content_status", change_after_content_check)
    else:
        mutate()

    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    assert receipt["resources"]["annotator_presentation_pair"] == (
        "annotator_presentation_pair_mismatch"
    )
    assert receipt["blockers"] == ["annotator_presentation_pair"]
    assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


@pytest.mark.parametrize("order,mutation,late", [
    ("canonical", "malformed", False),
    ("reverse", "coordinator_metadata", False),
    ("canonical", "stale_fingerprint", False),
    ("reverse", "wrong_order", False),
    ("reverse", "coordinator_metadata", True),
])
def test_distribution_manifest_must_verify_even_when_presentation_bytes_match(
    tmp_path, monkeypatch, order, mutation, late,
):
    packet, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    bundle = packet / f"annotator-{order}-v1"
    path = bundle / "annotator_manifest.json"
    assert audit.audit_archive_readiness(**kwargs)["blockers"] == []
    before = {name: (bundle / name).read_bytes()
              for name in exporter.ANNOTATOR_ARTIFACTS if name != path.name}

    def mutate():
        if mutation == "malformed":
            path.write_text("{", encoding="utf-8")
            return
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "coordinator_metadata":
            manifest["blinding_key"] = "synthetic confidential marker"
        elif mutation == "stale_fingerprint":
            manifest["artifacts"]["packet"]["sha256"] = "0" * 64
        elif mutation == "wrong_order":
            manifest["presentation_order"] = "canonical"
        path.write_text(json.dumps(manifest), encoding="utf-8")

    if late:
        original = audit._trace_report_content_status

        def change_after_content_check(**arguments):
            result = original(**arguments)
            assert result["checked"] == 40
            mutate()
            return result

        monkeypatch.setattr(audit, "_trace_report_content_status", change_after_content_check)
    else:
        mutate()

    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    label = f"{order}/distribution_manifest"
    assert receipt["resources"][label] == "annotator_distribution_verification_failed"
    assert receipt["blockers"] == [label]
    assert receipt["status"] == "blocked"
    assert "synthetic confidential marker" not in json.dumps(receipt)
    assert before == {name: (bundle / name).read_bytes() for name in before}
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


def test_self_consistent_short_distribution_pair_is_not_main_study_ready(
    tmp_path, monkeypatch,
):
    packet, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    names = ("packet.jsonl", "ratings_template.csv")
    for name in names:
        path = packet / name
        path.write_bytes(b"".join(path.read_bytes().splitlines(keepends=True)[:-1]))
    for order in ("canonical", "reverse"):
        bundle = packet / f"annotator-{order}-v1"
        ordered = exporter._ordered_artifacts(
            (packet / names[0]).read_bytes(), (packet / names[1]).read_bytes(),
            presentation_order=order,
        )
        for name, content in zip(names, ordered):
            (bundle / name).write_bytes(content)
        _write_synthetic_annotator_manifest(bundle, order)
        assert exporter.verify_annotator_bundle(bundle)["n_reports"] == 39

    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    assert receipt["status"] == "blocked"
    assert receipt["blockers"] == [
        "canonical/distribution_manifest", "reverse/distribution_manifest",
    ]
    for label in receipt["blockers"]:
        assert receipt["resources"][label] == "annotator_distribution_identity_mismatch"
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


@pytest.mark.parametrize("mutation,late,expected_status", [
    ("unbalanced", False, "annotator_task_coverage_mismatch"),
    ("wrong_question", False, "annotator_question_mismatch"),
    ("swapped_questions", False, "annotator_question_mismatch"),
    ("wrong_question", True, "annotator_question_mismatch"),
])
def test_complete_distribution_pair_requires_frozen_task_coverage_and_questions(
    tmp_path, monkeypatch, mutation, late, expected_status,
):
    packet, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    assert audit.audit_archive_readiness(**kwargs)["blockers"] == []

    def mutate():
        path = packet / "packet.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if mutation == "unbalanced":
            rows[0]["task_id"] = rows[4]["task_id"]
            rows[0]["question"] = rows[4]["question"]
        elif mutation == "wrong_question":
            rows[0]["question"] += " altered prompt"
        else:
            rows[0]["question"], rows[4]["question"] = (
                rows[4]["question"], rows[0]["question"],
            )
        path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        for order in ("canonical", "reverse"):
            bundle = packet / f"annotator-{order}-v1"
            names = ("packet.jsonl", "ratings_template.csv")
            ordered = exporter._ordered_artifacts(
                path.read_bytes(), (packet / names[1]).read_bytes(),
                presentation_order=order,
            )
            for name, content in zip(names, ordered):
                (bundle / name).write_bytes(content)
            _write_synthetic_annotator_manifest(bundle, order)
            assert exporter.verify_annotator_bundle(bundle)["n_reports"] == 40

    if late:
        original = audit._trace_report_content_status

        def change_after_content_check(**arguments):
            result = original(**arguments)
            assert result["checked"] == 40
            mutate()
            return result

        monkeypatch.setattr(audit, "_trace_report_content_status", change_after_content_check)
    else:
        mutate()

    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    assert receipt["resources"]["annotator_presentation_pair"] == expected_status
    assert receipt["blockers"] == ["annotator_presentation_pair"]
    assert receipt["status"] == "blocked"
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False


@pytest.mark.parametrize("mutation,late,expected", [
    ("substitute_report", False, "candidate_blinded_report_content_mismatch"),
    ("swap_reports", False, "candidate_blinded_report_content_mismatch"),
    ("swap_key_cells", False, "candidate_blinded_report_content_mismatch"),
    ("duplicate_key_cell", False, "candidate_blinding_key_cell_mismatch"),
    ("duplicate_blind_id", False, "candidate_blind_id_coverage_mismatch"),
    ("substitute_report", True, "candidate_blinded_report_content_mismatch"),
])
def test_recovered_packet_must_link_blind_ids_to_captured_report_cells(
    tmp_path, monkeypatch, mutation, late, expected,
):
    packet, kwargs = _complete_readiness_inventory(tmp_path, monkeypatch)
    assert audit.audit_archive_readiness(**kwargs)["blockers"] == []

    def mutate():
        if mutation in ("substitute_report", "swap_reports"):
            path = packet / "packet.jsonl"
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            if mutation == "substitute_report":
                # Same word count; regenerate both legitimate presentation
                # manifests to isolate source linkage, not stale hashes.
                rows[0]["report_markdown"] = rows[0]["report_markdown"].replace(
                    "Synthetic", "Replacement", 1
                )
            else:
                rows[0]["report_markdown"], rows[1]["report_markdown"] = (
                    rows[1]["report_markdown"], rows[0]["report_markdown"],
                )
            path.write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
            for order in ("canonical", "reverse"):
                bundle = packet / f"annotator-{order}-v1"
                ordered = exporter._ordered_artifacts(
                    path.read_bytes(), (packet / "ratings_template.csv").read_bytes(),
                    presentation_order=order,
                )
                for name, content in zip(("packet.jsonl", "ratings_template.csv"), ordered):
                    (bundle / name).write_bytes(content)
                _write_synthetic_annotator_manifest(bundle, order)
                assert exporter.verify_annotator_bundle(bundle)["n_reports"] == 40
        else:
            path = packet / "blinding_key.csv"
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            if mutation == "duplicate_blind_id":
                rows[0]["blind_id"] = rows[1]["blind_id"]
            elif mutation == "duplicate_key_cell":
                for field in audit.packet_verifier.KEY_FIELDS[1:]:
                    rows[0][field] = rows[1][field]
            else:
                for field in audit.packet_verifier.KEY_FIELDS[1:]:
                    rows[0][field], rows[1][field] = rows[1][field], rows[0][field]
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=audit.packet_verifier.KEY_FIELDS)
                writer.writeheader()
                writer.writerows(rows)

    if late:
        original = audit._trace_report_content_status

        def change_after_content_check(**arguments):
            result = original(**arguments)
            assert result["checked"] == 40
            mutate()
            return result

        monkeypatch.setattr(audit, "_trace_report_content_status", change_after_content_check)
    else:
        mutate()

    receipt = audit.audit_archive_readiness(**kwargs)
    assert receipt["trace_report_content"]["checked"] == 40
    assert receipt["resources"]["candidate_packet_source_linkage"] == expected
    assert receipt["blockers"] == ["candidate_packet_source_linkage"]
    assert receipt["status"] == "blocked"
    assert "Synthetic report" not in json.dumps(receipt)
    assert "H001" not in json.dumps(receipt)
    assert receipt["handoff_verified"] is False
    assert receipt["human_ratings_used"] is False
    assert receipt["treatments_rerun"] is False
