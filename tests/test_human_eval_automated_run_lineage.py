"""Synthetic-only checks for blinded report / automated evaluator run continuity.

All run IDs, experiments, questions, and scores below are fictitious. No real
treatments, human ratings, or inference outputs are created or changed.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_human_eval_packet as packet_builder
from scripts import verify_human_eval_automated_run_lineage as lineage


TEST_TASKS = ("main-01", "main-02")


def _rows(tasks=TEST_TASKS):
    key, main, support = [], [], []
    for task in tasks:
        for variant in lineage.VARIANTS:
            run = f"synthetic-{variant.lower()}-{task}"
            key.append({
                "blind_id": f"H{len(key) + 1:03d}",
                "variant_id": variant, "task_id": task, "run_id": run,
                "trace_path": f"outputs/experiment_traces/{variant}/{run}.json",
                "report_path": f"outputs/{run}/research_report.md",
            })
            main.append({
                "variant_id": variant, "task_id": task, "completed": "True",
                "successful_sources": "1", "total_tokens": "100",
                "model_calls": "1", "report_words": "10",
                "treatment_cost_usd": "0.01", "latency_seconds": "1.0",
                "posthoc_claims_checked": "2",
            })
            support.append({
                "variant_id": variant, "task_id": task, "run_id": run,
                "claims_checked": "2", "supported": "1",
                "partially_supported": "0", "unsupported": "1",
                "contradicted": "0",
            })
    return key, main, support


def test_canonical_run_identity_matches_all_frozen_cells():
    key, main, support = _rows(tuple(f"main-{i:02d}" for i in range(1, 11)))
    assert lineage.compare_run_lineage(key, main, support)["run_ids_matched"] == 40


def test_fixture_run_identity_matches_and_remains_blinded():
    key, main, support = _rows()
    result = lineage.compare_run_lineage(
        key, main, support, expected_tasks=TEST_TASKS
    )
    assert result["n_reports"] == 8
    assert result["human_ratings_read"] is False
    assert "synthetic-" not in json.dumps(result)
    assert "blind_id" not in json.dumps(result)


@pytest.mark.parametrize("mutation, expected", [
    ("changed_evaluator", "run lineage mismatch"),
    ("swapped_evaluator", "run lineage mismatch"),
    ("duplicated_evaluator_run", "aliases one run ID"),
    ("missing_evaluator_cell", "exactly 8 cells"),
    ("extra_evaluator_cell", "exactly 8 cells"),
    ("duplicated_key_cell", "duplicate cell"),
    ("missing_treatment", "exactly 8 cells"),
    ("changed_treatment_mirror", "count mirror mismatch"),
    ("whitespace_run", "invalid run ID"),
])
def test_rejects_false_run_lineage(mutation, expected):
    key, main, support = _rows()
    if mutation == "changed_evaluator":
        support[0]["run_id"] = "wrong-run"
    elif mutation == "swapped_evaluator":
        support[0]["run_id"], support[1]["run_id"] = (
            support[1]["run_id"], support[0]["run_id"]
        )
    elif mutation == "duplicated_evaluator_run":
        support[0]["run_id"] = support[1]["run_id"]
    elif mutation == "missing_evaluator_cell":
        support.pop()
    elif mutation == "extra_evaluator_cell":
        support.append(dict(support[0]))
    elif mutation == "duplicated_key_cell":
        key[0] = dict(key[1])
    elif mutation == "missing_treatment":
        main.pop()
    elif mutation == "changed_treatment_mirror":
        main[0]["posthoc_claims_checked"] = "1"
    elif mutation == "whitespace_run":
        key[0]["run_id"] += " "
    with pytest.raises(ValueError, match=expected):
        lineage.compare_run_lineage(
            key, main, support, expected_tasks=TEST_TASKS
        )


def _write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def packet_case(tmp_path: Path):
    manifest = tmp_path / "experiments/main_budget_tasks.json"
    manifest.parent.mkdir(parents=True)
    tasks = [
        {"id": task, "question": f"Fictitious question for {task}?"}
        for task in TEST_TASKS
    ]
    manifest.write_text(json.dumps({
        "task_set_id": "synthetic-main-test",
        "frozen_before_execution": True, "tasks": tasks,
    }) + "\n", encoding="utf-8")

    for task in tasks:
        for variant in lineage.VARIANTS:
            run_id = f"synthetic-{variant.lower()}-{task['id']}"
            report = tmp_path / "outputs" / run_id / "research_report.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("# Fictitious report\n\nNeutral synthetic content.\n")
            trace = (
                tmp_path / "outputs/experiment_traces" / variant / f"{run_id}.json"
            )
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(json.dumps({
                "schema_version": 2,
                "experiment": {
                    "variant_id": variant, "task_id": task["id"],
                    "task_set_id": "synthetic-main-test",
                },
                "trace": {
                    "run_id": run_id,
                    "variant_id": variant, "task_id": task["id"],
                    "question": task["question"],
                    "completed": True,
                    "report_path": f"./outputs/{run_id}/research_report.pdf",
                },
            }))
    packet_root = tmp_path / "outputs/human_eval"
    packet_builder.build_packet(
        tmp_path / "outputs/experiment_traces", packet_root,
        task_manifest_path=manifest,
    )
    _, main, support = _rows()
    _write_csv(tmp_path / lineage.MAIN_REL, main)
    _write_csv(tmp_path / lineage.SUPPORT_REL, support)
    return {
        "repo_root": tmp_path, "packet_root": packet_root,
        "task_manifest_path": manifest, "expected_tasks": TEST_TASKS,
    }


def _pinned_manifest(case):
    root = case["repo_root"]
    entries = []
    for name in (lineage.MAIN_REL, lineage.SUPPORT_REL):
        raw = (root / name).read_bytes()
        entries.append({
            "path": name, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    entries.sort(key=lambda item: item["path"])
    canonical = json.dumps(
        entries, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    blob = {
        "schema_version": 1, "algorithm": "sha256", "artifacts": entries,
        "aggregate_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    path = root / "frozen-inputs.json"
    path.write_text(json.dumps(blob, sort_keys=True) + "\n")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_end_to_end_packet_matches_automated_run_ids(packet_case):
    path, digest = _pinned_manifest(packet_case)
    result = lineage.audit_files(
        **packet_case,
        research_manifest_path=path,
        expected_manifest_sha256=digest,
    )
    assert result["run_ids_matched"] == 8
    assert result["archival_manifest_externally_pinned"] is True
    assert result["human_ratings_read"] is False


def test_end_to_end_rejects_mismatched_evaluator_run_even_if_repinned(packet_case):
    root = packet_case["repo_root"]
    path = root / lineage.SUPPORT_REL
    rows = lineage._read_study_csv(path.read_bytes(), path=path)
    rows[0]["run_id"] = "synthetic-replacement-run"
    _write_csv(path, rows)
    pinned, digest = _pinned_manifest(packet_case)
    with pytest.raises(ValueError, match="run lineage mismatch"):
        lineage.audit_files(
            **packet_case,
            research_manifest_path=pinned,
            expected_manifest_sha256=digest,
        )


def test_end_to_end_rejects_stale_external_input_manifest(packet_case):
    pinned, digest = _pinned_manifest(packet_case)
    with pytest.raises(ValueError, match="manifest"):
        lineage.audit_files(
            **packet_case,
            research_manifest_path=pinned,
            expected_manifest_sha256="0" * 64,
        )
    assert digest != "0" * 64


def test_end_to_end_rejects_modified_report(packet_case):
    root = packet_case["repo_root"]
    report = root / "outputs/synthetic-d3-main-01/research_report.md"
    report.write_text("# Changed synthetic report\n\nDrift.")
    with pytest.raises(ValueError, match="fingerprint|report content"):
        lineage.audit_files(**packet_case)


def test_end_to_end_rejects_half_specified_archival_pin(packet_case):
    with pytest.raises(ValueError, match="requires both"):
        lineage.audit_files(
            **packet_case, expected_manifest_sha256="0" * 64
        )


def test_rejects_noncanonical_csv_structures():
    with pytest.raises(ValueError, match="duplicated study CSV headers"):
        lineage._read_study_csv(
            b"variant_id,variant_id,task_id\nD3,D3,main-01\n",
            path=Path("synthetic.csv"),
        )
