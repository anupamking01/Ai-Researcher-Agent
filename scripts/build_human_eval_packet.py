"""Build a deterministic blinded packet for human evaluation.

This module is intentionally offline. It reads completed experiment traces and
the Markdown reports already produced by those runs, then emits annotator-facing
artifacts that do not reveal experimental variant labels. The coordinator-only
blinding key is written separately.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from urllib.parse import unquote


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "human_eval"
DEFAULT_TASK_MANIFEST = REPO_ROOT / "experiments" / "main_budget_tasks.json"
EXPECTED_VARIANTS = ("D3", "D6", "P6", "P6V")
DEFAULT_SEED = 20260915

RATING_FIELDS = (
    "annotator_id",
    "blind_id",
    "correctness_1_5",
    "completeness_1_5",
    "source_quality_1_5",
    "synthesis_reasoning_1_5",
    "clarity_1_5",
    "notes",
)


def _resolve_report_markdown(trace_root: Path, report_path: str) -> Path:
    """Resolve a persisted report path to its sibling Markdown file."""
    if not report_path:
        raise FileNotFoundError("Missing Markdown report: trace has no report_path")

    decoded = Path(unquote(str(report_path)))
    if decoded.suffix.lower() == ".pdf":
        decoded = decoded.with_suffix(".md")

    # Experiment traces live under <repo>/outputs/experiment_traces. Report
    # paths are persisted relative to the repository, typically
    # ./outputs/<run_id>/research_report.pdf.
    repo_root = trace_root.parent.parent
    if decoded.is_absolute():
        candidate = decoded
    else:
        parts = decoded.parts
        if parts and parts[0] == ".":
            decoded = Path(*parts[1:])
        candidate = repo_root / decoded

    if not candidate.is_file():
        raise FileNotFoundError(f"Missing Markdown report: {candidate}")
    return candidate


def _load_task_manifest(task_manifest_path: Path) -> dict:
    """Load and validate the frozen task set used by the human-eval packet."""
    task_manifest_path = Path(task_manifest_path)
    if not task_manifest_path.is_file():
        raise FileNotFoundError(f"Frozen task manifest does not exist: {task_manifest_path}")
    content = task_manifest_path.read_bytes()
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Frozen task manifest is not valid UTF-8 JSON: {task_manifest_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Frozen task manifest must contain a JSON object")
    if payload.get("frozen_before_execution") is not True:
        raise ValueError("Human evaluation requires a task manifest frozen before execution")
    task_set_id = str(payload.get("task_set_id") or "").strip()
    task_rows = payload.get("tasks")
    if not task_set_id:
        raise ValueError("Frozen task manifest is missing task_set_id")
    if not isinstance(task_rows, list) or not task_rows:
        raise ValueError("Frozen task manifest contains no tasks")
    tasks: dict[str, str] = {}
    for index, row in enumerate(task_rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Frozen task manifest task {index} must be an object")
        task_id = str(row.get("id") or "").strip()
        question = str(row.get("question") or "").strip()
        if not task_id or not question:
            raise ValueError(f"Frozen task manifest task {index} is missing id/question")
        if task_id in tasks:
            raise ValueError(f"Duplicate task ID in frozen task manifest: {task_id}")
        tasks[task_id] = question
    return {
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "task_set_id": task_set_id,
        "tasks": tasks,
    }


def _load_records(trace_root: Path, *, task_manifest: dict) -> list[dict]:
    if not trace_root.is_dir():
        raise FileNotFoundError(f"Trace root does not exist: {trace_root}")

    records: list[dict] = []
    seen_cells: set[tuple[str, str]] = set()

    for trace_path in sorted(trace_root.glob("*/*.json")):
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        experiment = payload.get("experiment", {})
        trace = payload.get("trace", {})

        variant_id = str(trace.get("variant_id") or experiment.get("variant_id") or "").strip()
        task_id = str(trace.get("task_id") or experiment.get("task_id") or "").strip()
        run_id = str(trace.get("run_id") or trace_path.stem).strip()
        question = str(trace.get("question") or "").strip()
        trace_task_set_id = str(experiment.get("task_set_id") or "").strip()

        if not variant_id or not task_id:
            raise ValueError(f"Trace missing variant/task identity: {trace_path}")
        if variant_id not in EXPECTED_VARIANTS:
            raise ValueError(f"Unexpected variant {variant_id!r} in {trace_path}")
        if not bool(trace.get("completed")):
            raise ValueError(f"Incomplete run cannot enter human evaluation: {variant_id}/{task_id}")
        if not question:
            raise ValueError(f"Trace missing research question: {variant_id}/{task_id}")
        if trace_task_set_id != task_manifest["task_set_id"]:
            raise ValueError(
                f"Trace task_set_id mismatch for {variant_id}/{task_id}: "
                f"{trace_task_set_id!r} != {task_manifest['task_set_id']!r}"
            )
        expected_question = task_manifest["tasks"].get(task_id)
        if expected_question is None:
            raise ValueError(f"Unexpected task {task_id!r}; not present in frozen task manifest")
        if question != expected_question:
            raise ValueError(
                f"Trace question does not match frozen task manifest for {variant_id}/{task_id}"
            )

        cell = (variant_id, task_id)
        if cell in seen_cells:
            raise ValueError(f"Duplicate variant/task cell: {variant_id}/{task_id}")
        seen_cells.add(cell)

        report_md = _resolve_report_markdown(trace_root, str(trace.get("report_path") or ""))
        report_text = report_md.read_text(encoding="utf-8").strip()
        if not report_text:
            raise ValueError(f"Empty Markdown report: {report_md}")

        repo_root = trace_root.parent.parent
        records.append(
            {
                "variant_id": variant_id,
                "task_id": task_id,
                "run_id": run_id,
                "question": question,
                "report_markdown": report_text,
                "trace_path": trace_path.relative_to(repo_root).as_posix(),
                "report_path": report_md.relative_to(repo_root).as_posix(),
            }
        )

    if not records:
        raise ValueError(f"No experiment traces found under {trace_root}")

    observed_task_ids = {record["task_id"] for record in records}
    expected_task_ids = set(task_manifest["tasks"])
    if observed_task_ids != expected_task_ids:
        missing = sorted(expected_task_ids - observed_task_ids)
        unexpected = sorted(observed_task_ids - expected_task_ids)
        raise ValueError(
            "Human-evaluation task coverage must exactly match the frozen task manifest; "
            f"missing={missing}, unexpected={unexpected}"
        )

    task_variants: dict[str, set[str]] = {}
    for record in records:
        task_variants.setdefault(record["task_id"], set()).add(record["variant_id"])
    expected = set(EXPECTED_VARIANTS)
    for task_id, variants in sorted(task_variants.items()):
        if variants != expected:
            raise ValueError(
                f"Expected variants {list(EXPECTED_VARIANTS)} for task {task_id}; "
                f"got {sorted(variants)}"
            )

    return records


def _write_csv(path: Path, fieldnames: tuple[str, ...] | list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_packet(
    trace_root: Path,
    output_root: Path,
    *,
    seed: int = DEFAULT_SEED,
    task_manifest_path: Path = DEFAULT_TASK_MANIFEST,
) -> dict:
    """Build deterministic blinded evaluation artifacts from completed traces."""
    trace_root = Path(trace_root)
    output_root = Path(output_root)
    task_manifest_path = Path(task_manifest_path)
    task_manifest = _load_task_manifest(task_manifest_path)
    records = _load_records(trace_root, task_manifest=task_manifest)

    # Sort first so filesystem traversal order can never affect randomization.
    shuffled = sorted(records, key=lambda row: (row["task_id"], row["variant_id"], row["run_id"]))
    random.Random(seed).shuffle(shuffled)

    packet_rows: list[dict] = []
    key_rows: list[dict] = []
    ratings_rows: list[dict] = []

    for index, record in enumerate(shuffled, start=1):
        blind_id = f"H{index:03d}"
        packet_rows.append(
            {
                "blind_id": blind_id,
                "task_id": record["task_id"],
                "question": record["question"],
                "report_markdown": record["report_markdown"],
            }
        )
        key_rows.append(
            {
                "blind_id": blind_id,
                "variant_id": record["variant_id"],
                "task_id": record["task_id"],
                "run_id": record["run_id"],
                "trace_path": record["trace_path"],
                "report_path": record["report_path"],
            }
        )
        ratings_rows.append(
            {
                "annotator_id": "",
                "blind_id": blind_id,
                "correctness_1_5": "",
                "completeness_1_5": "",
                "source_quality_1_5": "",
                "synthesis_reasoning_1_5": "",
                "clarity_1_5": "",
                "notes": "",
            }
        )

    output_root.mkdir(parents=True, exist_ok=True)
    packet_path = output_root / "packet.jsonl"
    packet_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in packet_rows)
        + "\n",
        encoding="utf-8",
    )

    _write_csv(
        output_root / "blinding_key.csv",
        ["blind_id", "variant_id", "task_id", "run_id", "trace_path", "report_path"],
        key_rows,
    )
    _write_csv(output_root / "ratings_template.csv", list(RATING_FIELDS), ratings_rows)

    manifest = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "task_set_id": task_manifest["task_set_id"],
        "task_manifest": {
            "name": task_manifest_path.name,
            "bytes": task_manifest["bytes"],
            "sha256": task_manifest["sha256"],
            "n_tasks": len(task_manifest["tasks"]),
        },
        "blind_seed": int(seed),
        "n_reports": len(packet_rows),
        "n_tasks": len({row["task_id"] for row in packet_rows}),
        "variants": list(EXPECTED_VARIANTS),
        "packet": "packet.jsonl",
        "ratings_template": "ratings_template.csv",
        "blinding_key": "blinding_key.csv",
        "blinding_note": (
            "Annotators receive packet.jsonl and ratings_template.csv only. "
            "blinding_key.csv is coordinator-only until scoring is frozen."
        ),
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-root", type=Path, default=DEFAULT_TRACE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--task-manifest", type=Path, default=DEFAULT_TASK_MANIFEST)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    manifest = build_packet(
        args.trace_root,
        args.output_root,
        seed=args.seed,
        task_manifest_path=args.task_manifest,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
