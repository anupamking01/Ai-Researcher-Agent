"""Verify a human-evaluation packet and coordinator blinding key.

This coordinator-side verifier checks that packet.jsonl, ratings_template.csv,
blinding_key.csv, the frozen task manifest, persisted traces, and Markdown
reports still agree with the packet manifest. It does not read human ratings,
compute treatment outcomes, or modify research artifacts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from scripts import build_human_eval_packet as build


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = build.DEFAULT_OUTPUT_ROOT
DEFAULT_TASK_MANIFEST = build.DEFAULT_TASK_MANIFEST
KEY_FIELDS = (
    "blind_id",
    "variant_id",
    "task_id",
    "run_id",
    "trace_path",
    "report_path",
)


def _require_regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _load_json_object(content: bytes, *, label: str) -> dict:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _fingerprint(content: bytes, *, path: str) -> dict:
    return {
        "path": path,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _require_equal(actual, expected, *, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def _read_csv(content: bytes, *, fields: tuple[str, ...], label: str) -> list[dict]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} is not valid UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    fieldnames = reader.fieldnames or []
    duplicates = sorted({name for name in fieldnames if fieldnames.count(name) > 1})
    if duplicates:
        raise ValueError(f"{label} has duplicate columns: {duplicates}")
    if fieldnames != list(fields):
        raise ValueError(
            f"{label} schema mismatch: expected {list(fields)!r}, got {fieldnames!r}"
        )

    rows = []
    for raw in reader:
        if None in raw:
            raise ValueError(f"{label} contains extra fields")
        missing = [name for name, value in raw.items() if value is None]
        if missing:
            raise ValueError(f"{label} contains missing fields: {missing}")
        rows.append({name: str(raw[name]) for name in fields})
    return rows


def _read_packet(content: bytes, *, task_manifest: dict) -> list[dict]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("packet.jsonl is not valid UTF-8") from exc

    rows = []
    seen = set()
    required = {"blind_id", "task_id", "question", "report_markdown"}
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"packet.jsonl line {line_number} is not valid JSON") from exc
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError(
                f"packet.jsonl line {line_number} schema must be exactly {sorted(required)}"
            )
        blind_id = str(row["blind_id"]).strip()
        task_id = str(row["task_id"]).strip()
        question = str(row["question"]).strip()
        report_markdown = str(row["report_markdown"]).strip()
        if not blind_id or blind_id in seen:
            raise ValueError(f"packet.jsonl has missing/duplicate blind_id {blind_id!r}")
        seen.add(blind_id)
        expected_question = task_manifest["tasks"].get(task_id)
        if expected_question is None:
            raise ValueError(f"packet.jsonl contains unexpected task {task_id!r}")
        if question != expected_question:
            raise ValueError(f"packet question drift for {blind_id}/{task_id}")
        if not report_markdown:
            raise ValueError(f"packet report is empty for {blind_id}/{task_id}")
        rows.append(
            {
                "blind_id": blind_id,
                "task_id": task_id,
                "question": question,
                "report_markdown": report_markdown,
            }
        )
    if not rows:
        raise ValueError("packet.jsonl contains no reports")
    return rows


def _repo_file(repo_root: Path, relative_path: str, *, label: str) -> Path:
    relative = Path(str(relative_path))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} must be a repository-relative path: {relative_path!r}")
    root = repo_root.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"{label} escapes repository root: {relative_path!r}")
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"{label} must resolve to a regular file: {candidate}")
    return candidate


def verify_packet(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    task_manifest_path: Path = DEFAULT_TASK_MANIFEST,
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Verify packet/key provenance without reading any human rating files."""
    output_root = Path(output_root)
    task_manifest_path = Path(task_manifest_path)
    repo_root = Path(repo_root)

    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError(f"human-evaluation output root must be a regular directory: {output_root}")

    manifest_content = _require_regular_file(output_root / "manifest.json", label="packet manifest")
    manifest = _load_json_object(manifest_content, label="packet manifest")
    task_manifest = build._load_task_manifest(task_manifest_path)

    _require_equal(manifest.get("schema_version"), 1, label="packet manifest schema_version")
    _require_equal(manifest.get("study_id"), "budget-main-v1", label="packet manifest study_id")
    _require_equal(manifest.get("task_set_id"), task_manifest["task_set_id"], label="task_set_id")
    _require_equal(manifest.get("variants"), list(build.EXPECTED_VARIANTS), label="variant contract")
    if not isinstance(manifest.get("blind_seed"), int):
        raise ValueError("packet manifest blind_seed must be an integer")

    expected_task_entry = {
        "name": task_manifest_path.name,
        "bytes": task_manifest["bytes"],
        "sha256": task_manifest["sha256"],
        "n_tasks": len(task_manifest["tasks"]),
    }
    _require_equal(manifest.get("task_manifest"), expected_task_entry, label="task-manifest provenance")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError(
            "packet manifest lacks artifact fingerprints; rebuild the deterministic packet "
            "before distributing it for human annotation"
        )

    filenames = {
        "packet": "packet.jsonl",
        "ratings_template": "ratings_template.csv",
        "blinding_key": "blinding_key.csv",
    }
    contents = {}
    for key, filename in filenames.items():
        _require_equal(manifest.get(key), filename, label=f"{key} filename")
        artifact_content = _require_regular_file(output_root / filename, label=key)
        contents[key] = artifact_content
        _require_equal(
            artifacts.get(key),
            _fingerprint(artifact_content, path=filename),
            label=f"{key} fingerprint",
        )

    packet_rows = _read_packet(contents["packet"], task_manifest=task_manifest)
    packet_by_blind = {row["blind_id"]: row for row in packet_rows}
    packet_blind_ids = set(packet_by_blind)

    key_rows = _read_csv(contents["blinding_key"], fields=KEY_FIELDS, label="blinding_key.csv")
    key_blind_ids = [row["blind_id"].strip() for row in key_rows]
    if any(not value for value in key_blind_ids) or len(set(key_blind_ids)) != len(key_blind_ids):
        raise ValueError("blinding_key.csv must contain one unique non-empty blind_id per row")
    _require_equal(set(key_blind_ids), packet_blind_ids, label="key/packet blind-id coverage")

    seen_cells = set()
    variants_by_task = {task_id: set() for task_id in task_manifest["tasks"]}
    for row in key_rows:
        blind_id = row["blind_id"].strip()
        variant_id = row["variant_id"].strip()
        task_id = row["task_id"].strip()
        run_id = row["run_id"].strip()
        if variant_id not in build.EXPECTED_VARIANTS:
            raise ValueError(f"unexpected key variant {variant_id!r} for {blind_id}")
        if task_id != packet_by_blind[blind_id]["task_id"]:
            raise ValueError(f"key task does not match packet for {blind_id}")
        if not run_id or not row["trace_path"].strip() or not row["report_path"].strip():
            raise ValueError(f"key source provenance is incomplete for {blind_id}")

        cell = (variant_id, task_id)
        if cell in seen_cells:
            raise ValueError(f"duplicate treatment/task mapping in blinding key: {cell}")
        seen_cells.add(cell)
        variants_by_task.setdefault(task_id, set()).add(variant_id)

        trace_path = _repo_file(repo_root, row["trace_path"], label=f"trace for {blind_id}")
        trace_payload = _load_json_object(
            _require_regular_file(trace_path, label=f"trace for {blind_id}"),
            label=f"trace for {blind_id}",
        )
        experiment = trace_payload.get("experiment", {})
        trace = trace_payload.get("trace", {})
        observed_variant = str(trace.get("variant_id") or experiment.get("variant_id") or "").strip()
        observed_task = str(trace.get("task_id") or experiment.get("task_id") or "").strip()
        observed_run = str(trace.get("run_id") or trace_path.stem).strip()
        _require_equal(observed_variant, variant_id, label=f"trace variant for {blind_id}")
        _require_equal(observed_task, task_id, label=f"trace task for {blind_id}")
        _require_equal(observed_run, run_id, label=f"trace run for {blind_id}")
        _require_equal(
            str(experiment.get("task_set_id") or "").strip(),
            task_manifest["task_set_id"],
            label=f"trace task_set_id for {blind_id}",
        )
        _require_equal(bool(trace.get("completed")), True, label=f"trace completed for {blind_id}")
        _require_equal(
            str(trace.get("question") or "").strip(),
            packet_by_blind[blind_id]["question"],
            label=f"trace question for {blind_id}",
        )

        report_path = _repo_file(repo_root, row["report_path"], label=f"report for {blind_id}")
        try:
            report_text = _require_regular_file(report_path, label=f"report for {blind_id}").decode(
                "utf-8"
            ).strip()
        except UnicodeDecodeError as exc:
            raise ValueError(f"report for {blind_id} is not valid UTF-8") from exc
        _require_equal(
            report_text,
            packet_by_blind[blind_id]["report_markdown"],
            label=f"report content for {blind_id}",
        )

    expected_variants = set(build.EXPECTED_VARIANTS)
    for task_id in sorted(task_manifest["tasks"]):
        _require_equal(
            variants_by_task.get(task_id, set()),
            expected_variants,
            label=f"variant coverage for {task_id}",
        )

    template_rows = _read_csv(
        contents["ratings_template"],
        fields=build.RATING_FIELDS,
        label="ratings_template.csv",
    )
    template_blind_ids = []
    for row in template_rows:
        blind_id = row["blind_id"].strip()
        if not blind_id:
            raise ValueError("ratings_template.csv contains an empty blind_id")
        template_blind_ids.append(blind_id)
        nonblank = {
            name: value
            for name, value in row.items()
            if name != "blind_id" and str(value).strip()
        }
        if nonblank:
            raise ValueError(
                f"ratings_template.csv must remain unscored for {blind_id}: {sorted(nonblank)}"
            )
    if len(set(template_blind_ids)) != len(template_blind_ids):
        raise ValueError("ratings_template.csv contains duplicate blind IDs")
    _require_equal(set(template_blind_ids), packet_blind_ids, label="template/packet blind-id coverage")

    _require_equal(manifest.get("n_reports"), len(packet_rows), label="packet report count")
    _require_equal(
        manifest.get("n_tasks"),
        len({row["task_id"] for row in packet_rows}),
        label="packet task count",
    )
    _require_equal(
        set(row["task_id"] for row in packet_rows),
        set(task_manifest["tasks"]),
        label="task coverage",
    )

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_eval_packet_verified",
        "blinding_key_checked": True,
        "human_ratings_read": False,
        "n_reports": len(packet_rows),
        "n_tasks": len(task_manifest["tasks"]),
        "n_variants": len(build.EXPECTED_VARIANTS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--task-manifest", type=Path, default=DEFAULT_TASK_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    try:
        receipt = verify_packet(
            output_root=args.output_root,
            task_manifest_path=args.task_manifest,
            repo_root=args.repo_root,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL PACKET VERIFY: FAIL: {exc}") from exc

    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN EVAL PACKET VERIFY: PASS (no human ratings read)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
