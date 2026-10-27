"""Synthetic-only tests for the joint automated-to-human distribution gate.

No genuine research artifacts, treatments, ratings, or participant data are
generated or modified. Two test tasks shorten the otherwise frozen 40-cell gate.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_human_eval_packet as builder
from scripts import export_human_eval_annotator_bundle as exporter
from scripts import verify_human_eval_automated_handoff as combined
from scripts import verify_human_eval_automated_run_lineage as lineage
from scripts import verify_human_eval_counterbalanced_handoff as handoff


TEST_TASKS = ("main-01", "main-02")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _archive_input_manifest(root: Path) -> tuple[Path, str]:
    entries = []
    for name in (lineage.MAIN_REL, lineage.SUPPORT_REL):
        raw = (root / name).read_bytes()
        entries.append({
            "path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        })
    entries.sort(key=lambda item: item["path"])
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    manifest = {
        "schema_version": 1,
        "algorithm": "sha256",
        "artifacts": entries,
        "aggregate_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    path = root / "frozen-input-manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def case(tmp_path):
    task_path = tmp_path / "experiments/main_budget_tasks.json"
    task_path.parent.mkdir(parents=True)
    task_path.write_text(json.dumps({
        "task_set_id": "synthetic-main-test", "frozen_before_execution": True,
        "tasks": [{"id": task, "question": f"Fictitious question {task}?"}
                  for task in TEST_TASKS],
    }) + "\n", encoding="utf-8")
    main_rows, evaluator_rows = [], []
    for task in TEST_TASKS:
        for variant in lineage.VARIANTS:
            run = f"synthetic-{variant.lower()}-{task}"
            report = tmp_path / "outputs" / run / "research_report.md"
            report.parent.mkdir(parents=True)
            report.write_text("# Fictitious report\n\nNeutral synthetic content.\n")
            trace = tmp_path / "outputs/experiment_traces" / variant / f"{run}.json"
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(json.dumps({
                "schema_version": 2,
                "experiment": {
                    "variant_id": variant, "task_id": task,
                    "task_set_id": "synthetic-main-test",
                },
                "trace": {
                    "run_id": run, "variant_id": variant, "task_id": task,
                    "question": f"Fictitious question {task}?",
                    "completed": True,
                    "report_path": f"./outputs/{run}/research_report.pdf",
                },
            }))
            main_rows.append({
                "variant_id": variant, "task_id": task, "completed": "True",
                "successful_sources": "1", "total_tokens": "100",
                "model_calls": "1", "report_words": "10",
                "treatment_cost_usd": "0.01", "latency_seconds": "1.0",
                "posthoc_claims_checked": "2",
            })
            evaluator_rows.append({
                "variant_id": variant, "task_id": task, "run_id": run,
                "claims_checked": "2", "supported": "1",
                "partially_supported": "0", "unsupported": "1",
                "contradicted": "0",
            })
    _write_csv(tmp_path / lineage.MAIN_REL, main_rows)
    _write_csv(tmp_path / lineage.SUPPORT_REL, evaluator_rows)
    packet_root = tmp_path / "outputs/human_eval"
    builder.build_packet(
        tmp_path / "outputs/experiment_traces", packet_root,
        task_manifest_path=task_path,
    )
    canonical_root = tmp_path / "canonical"
    reverse_root = tmp_path / "reverse"
    for output_root, order in ((canonical_root, "canonical"), (reverse_root, "reverse")):
        exporter.export_annotator_bundle(
            packet_root=packet_root, output_root=output_root,
            task_manifest_path=task_path, repo_root=tmp_path,
            presentation_order=order,
        )
    research_path, research_hash = _archive_input_manifest(tmp_path)
    return {
        "repo_root": tmp_path,
        "packet_root": packet_root,
        "canonical_root": canonical_root,
        "reverse_root": reverse_root,
        "research_manifest_path": research_path,
        "expected_research_manifest_sha256": research_hash,
        "expected_coordinator_manifest_sha256": hashlib.sha256(
            (packet_root / "manifest.json").read_bytes()
        ).hexdigest(),
        "task_manifest_path": task_path,
        "expected_tasks": TEST_TASKS,
    }


def test_composite_gate_proves_both_source_pins_and_report_run_coverage(case):
    receipt = combined.verify_automated_handoff(**case)
    assert receipt["status"] == "automated_run_and_counterbalanced_handoff_verified"
    assert receipt["n_reports"] == receipt["run_ids_matched"] == 8
    assert receipt["research_manifest_externally_pinned"] is True
    assert receipt["coordinator_manifest_externally_pinned"] is True
    assert receipt["presentation_orders"] == ["canonical", "reverse"]
    assert receipt["bundle_packet_sha256"]["canonical"] != receipt["bundle_packet_sha256"]["reverse"]
    for order, root_key in (("canonical", "canonical_root"), ("reverse", "reverse_root")):
        assert receipt["bundle_manifest_sha256"][order] == hashlib.sha256(
            (case[root_key] / "annotator_manifest.json").read_bytes()
        ).hexdigest()
    assert receipt["human_ratings_read"] is False
    assert all(secret not in json.dumps(receipt) for secret in (
        "blinding_key", '"run_id":', '"variant_id":', "synthetic-d3", "annotator_id",
    ))


def test_distribution_alone_can_pass_when_evaluator_run_was_replaced(case):
    path = case["repo_root"] / lineage.SUPPORT_REL
    rows = lineage._read_study_csv(path.read_bytes(), path=path)
    rows[0]["run_id"] = "synthetic-replacement-run"
    _write_csv(path, rows)
    research_path, research_hash = _archive_input_manifest(case["repo_root"])
    case["research_manifest_path"] = research_path
    case["expected_research_manifest_sha256"] = research_hash

    assert handoff.verify_counterbalanced_handoff(
        packet_root=case["packet_root"],
        canonical_root=case["canonical_root"],
        reverse_root=case["reverse_root"],
        expected_coordinator_manifest_sha256=case["expected_coordinator_manifest_sha256"],
        expected_n_reports=8,
        task_manifest_path=case["task_manifest_path"],
        repo_root=case["repo_root"],
    )["n_reports"] == 8
    with pytest.raises(ValueError, match="run lineage mismatch"):
        combined.verify_automated_handoff(**case)


@pytest.mark.parametrize("pin", ["research", "coordinator"])
def test_rejects_rewritten_or_wrong_external_anchors(case, pin):
    field = ("expected_research_manifest_sha256" if pin == "research"
             else "expected_coordinator_manifest_sha256")
    case[field] = "0" * 64
    with pytest.raises(ValueError, match="independently retained pin"):
        combined.verify_automated_handoff(**case)


@pytest.mark.parametrize("pin", ["research", "coordinator"])
def test_rejects_missing_or_invalid_pin_before_examining_sources(case, pin):
    field = ("expected_research_manifest_sha256" if pin == "research"
             else "expected_coordinator_manifest_sha256")
    case[field] = None
    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        combined.verify_automated_handoff(**case)


def test_does_not_accept_two_bundles_with_same_order(case):
    case["canonical_root"], case["reverse_root"] = (
        case["reverse_root"], case["canonical_root"]
    )
    with pytest.raises(ValueError, match="expected presentation order"):
        combined.verify_automated_handoff(**case)


def test_source_drift_between_both_successful_checks_fails_closed(case, monkeypatch):
    actual_handoff = handoff.verify_counterbalanced_handoff

    def changed_after_handoff(**kwargs):
        receipt = actual_handoff(**kwargs)
        with (case["repo_root"] / lineage.SUPPORT_REL).open("ab") as stream:
            stream.write(b"\n")
        return receipt

    monkeypatch.setattr(handoff, "verify_counterbalanced_handoff", changed_after_handoff)
    with pytest.raises(ValueError, match="common-evaluator CSV changed during combined"):
        combined.verify_automated_handoff(**case)


def test_does_not_write_to_any_frozen_or_distribution_inputs(case):
    files = (
        case["packet_root"] / "manifest.json",
        case["packet_root"] / "blinding_key.csv",
        case["repo_root"] / lineage.MAIN_REL,
        case["repo_root"] / lineage.SUPPORT_REL,
        case["canonical_root"] / "packet.jsonl",
        case["reverse_root"] / "packet.jsonl",
        case["research_manifest_path"],
    )
    before = {path: path.read_bytes() for path in files}
    combined.verify_automated_handoff(**case)
    assert before == {path: path.read_bytes() for path in files}

@pytest.mark.parametrize(("label", "root_key", "filename"), [
    ("coordinator packet.jsonl", "packet_root", "packet.jsonl"),
    ("coordinator ratings_template.csv", "packet_root", "ratings_template.csv"),
    ("canonical packet.jsonl", "canonical_root", "packet.jsonl"),
    ("reverse ratings_template.csv", "reverse_root", "ratings_template.csv"),
    ("frozen task manifest", "task_manifest_path", None),
    ("frozen annotator guide", "annotator_guide_path", None),
])
def test_rejects_shared_source_or_distribution_drift_after_verifiers(
    case, monkeypatch, label, root_key, filename,
):
    """Both component verifiers can pass before a distributed input changes."""
    if root_key == "annotator_guide_path":
        guide = case["repo_root"] / "synthetic-frozen-guide.md"
        guide.write_bytes(exporter.DEFAULT_ANNOTATOR_GUIDE.read_bytes())
        case["annotator_guide_path"] = guide

    target = case[root_key]
    if filename is not None:
        target = target / filename
    actual_handoff = handoff.verify_counterbalanced_handoff

    def changed_after_both_checks(**kwargs):
        receipt = actual_handoff(**kwargs)
        with target.open("ab") as stream:
            stream.write(b"\n")
        return receipt

    monkeypatch.setattr(
        handoff, "verify_counterbalanced_handoff", changed_after_both_checks
    )
    with pytest.raises(ValueError, match=label + " changed during combined"):
        combined.verify_automated_handoff(**case)


def test_detects_first_bundle_mutation_between_counterbalanced_checks(
    case, monkeypatch,
):
    """A validated canonical bundle must remain stable during reverse audit."""
    actual = exporter.verify_annotator_bundle_against_source

    def changed_after_canonical(**kwargs):
        receipt = actual(**kwargs)
        if kwargs["expected_presentation_order"] == "canonical":
            with (case["canonical_root"] / "packet.jsonl").open("ab") as stream:
                stream.write(b"\n")
        return receipt

    monkeypatch.setattr(
        exporter, "verify_annotator_bundle_against_source", changed_after_canonical
    )
    with pytest.raises(ValueError, match="canonical packet.jsonl changed during combined"):
        combined.verify_automated_handoff(**case)
