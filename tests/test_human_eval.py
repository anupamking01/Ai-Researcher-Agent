import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_human_eval_packet import build_packet


VARIANTS = ("D3", "D6", "P6", "P6V")


def _write_trace(
    tmp_path: Path,
    *,
    variant: str,
    task_id: str,
    run_id: str,
    completed: bool = True,
    create_report: bool = True,
) -> Path:
    outputs = tmp_path / "outputs"
    report_dir = outputs / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_md = report_dir / "research_report.md"
    if create_report:
        report_md.write_text(
            f"# Report for {task_id}\n\nEvidence-backed report body from run {run_id}.\n",
            encoding="utf-8",
        )

    trace_dir = outputs / "experiment_traces" / variant
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{run_id}.json"
    payload = {
        "schema_version": 2,
        "experiment": {
            "variant_id": variant,
            "task_id": task_id,
            "task_set_id": "main-budget-v1-test",
        },
        "trace": {
            "run_id": run_id,
            "variant_id": variant,
            "task_id": task_id,
            "question": f"Research question for {task_id}?",
            "completed": completed,
            "report_path": f"./outputs/{run_id}/research_report.pdf",
        },
    }
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    return trace_path


def _write_complete_matrix(tmp_path: Path) -> Path:
    for task_index in range(1, 3):
        task_id = f"main-{task_index:02d}"
        for variant in VARIANTS:
            _write_trace(
                tmp_path,
                variant=variant,
                task_id=task_id,
                run_id=f"{variant.lower()}-{task_id}",
            )
    return tmp_path / "outputs" / "experiment_traces"


def _write_task_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "main_budget_tasks.json"
    payload = {
        "task_set_id": "main-budget-v1-test",
        "frozen_before_execution": True,
        "tasks": [
            {
                "id": f"main-{task_index:02d}",
                "question": f"Research question for main-{task_index:02d}?",
            }
            for task_index in range(1, 3)
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _build_packet(trace_root: Path, output_root: Path, tmp_path: Path, *, seed=20260915):
    return build_packet(
        trace_root,
        output_root,
        seed=seed,
        task_manifest_path=_write_task_manifest(tmp_path),
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_build_packet_is_deterministic_and_blinds_variant_labels(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)

    first = _build_packet(trace_root, tmp_path / "packet-a", tmp_path, seed=20260915)
    second = _build_packet(trace_root, tmp_path / "packet-b", tmp_path, seed=20260915)

    assert first["n_reports"] == 8
    assert first["n_tasks"] == 2
    assert first["blind_seed"] == 20260915
    assert first["task_set_id"] == "main-budget-v1-test"
    task_manifest = _write_task_manifest(tmp_path)
    assert first["task_manifest"]["n_tasks"] == 2
    assert first["task_manifest"]["bytes"] == task_manifest.stat().st_size
    assert first["task_manifest"]["sha256"] == hashlib.sha256(task_manifest.read_bytes()).hexdigest()
    assert first == second

    packet_a = _read_jsonl(tmp_path / "packet-a" / "packet.jsonl")
    packet_b = _read_jsonl(tmp_path / "packet-b" / "packet.jsonl")
    assert packet_a == packet_b
    assert len({row["blind_id"] for row in packet_a}) == 8
    assert all("variant_id" not in row for row in packet_a)
    assert all("run_id" not in row for row in packet_a)
    assert all(row["report_markdown"].startswith("# Report") for row in packet_a)

    with (tmp_path / "packet-a" / "blinding_key.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        key_rows = list(csv.DictReader(handle))
    assert {row["variant_id"] for row in key_rows} == set(VARIANTS)
    assert len(key_rows) == 8

    with (tmp_path / "packet-a" / "ratings_template.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        ratings_rows = list(csv.DictReader(handle))
        fieldnames = handle.seek(0) or None
    assert len(ratings_rows) == 8
    assert all("variant_id" not in row for row in ratings_rows)
    assert set(ratings_rows[0]) == {
        "annotator_id",
        "blind_id",
        "correctness_1_5",
        "completeness_1_5",
        "source_quality_1_5",
        "synthesis_reasoning_1_5",
        "clarity_1_5",
        "notes",
    }


def test_build_packet_rejects_duplicate_variant_task_cells(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    _write_trace(
        tmp_path,
        variant="D3",
        task_id="main-01",
        run_id="duplicate-d3-main-01",
    )

    with pytest.raises(ValueError, match="Duplicate variant/task cell"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_missing_markdown_report(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    missing = tmp_path / "outputs" / "d3-main-01" / "research_report.md"
    missing.unlink()

    with pytest.raises(FileNotFoundError, match="Missing Markdown report"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_incomplete_run(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["completed"] = False
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Incomplete run"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_incomplete_task_matrix(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    (trace_root / "P6V" / "p6v-main-02.json").unlink()

    with pytest.raises(ValueError, match="Expected variants"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_when_an_entire_frozen_task_is_missing(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    for variant in VARIANTS:
        (trace_root / variant / f"{variant.lower()}-main-02.json").unlink()
    output_root = tmp_path / "human-eval"

    with pytest.raises(ValueError, match="task coverage.*missing=.*main-02"):
        _build_packet(trace_root, output_root, tmp_path)

    assert not output_root.exists()


def test_build_packet_rejects_question_drift_from_frozen_task_manifest(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["question"] = "A changed research question?"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="question does not match frozen task manifest"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_task_set_identity_drift(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    trace_path = trace_root / "D3" / "d3-main-01.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["experiment"]["task_set_id"] = "other-task-set"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="task_set_id mismatch"):
        _build_packet(trace_root, tmp_path / "human-eval", tmp_path)


def test_build_packet_rejects_unfrozen_task_manifest(tmp_path):
    trace_root = _write_complete_matrix(tmp_path)
    task_manifest = _write_task_manifest(tmp_path)
    payload = json.loads(task_manifest.read_text(encoding="utf-8"))
    payload["frozen_before_execution"] = False
    task_manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="frozen before execution"):
        build_packet(
            trace_root,
            tmp_path / "human-eval",
            task_manifest_path=task_manifest,
        )
