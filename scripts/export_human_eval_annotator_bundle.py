"""Create and verify an annotator-safe human-evaluation distribution bundle.

The coordinator packet contains a treatment mapping and blinding metadata that
must not be distributed to annotators. This utility snapshots the coordinator
packet, verifies that snapshot with the existing packet verifier, then exports
only packet.jsonl and ratings_template.csv plus a seed-free annotator manifest.

No ratings are generated, no treatment identity is exposed, and no model/API
calls are made.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import tempfile
from pathlib import Path

from scripts import build_human_eval_packet as build
from scripts.verify_human_eval_packet import verify_packet


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET_ROOT = build.DEFAULT_OUTPUT_ROOT
DEFAULT_OUTPUT_ROOT = DEFAULT_PACKET_ROOT / "annotator-bundle-v1"
DEFAULT_TASK_MANIFEST = build.DEFAULT_TASK_MANIFEST
COORDINATOR_ARTIFACTS = ("packet.jsonl", "ratings_template.csv", "blinding_key.csv", "manifest.json")
ANNOTATOR_ARTIFACTS = ("packet.jsonl", "ratings_template.csv", "annotator_manifest.json")


def _regular_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _fingerprint(content: bytes) -> dict:
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with Path(path).open("xb") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite annotator-bundle artifact: {path}") from exc


def _snapshot_coordinator_bundle(packet_root: Path, snapshot_root: Path) -> dict[str, bytes]:
    captured = {}
    for name in COORDINATOR_ARTIFACTS:
        content = _regular_bytes(packet_root / name, label=f"coordinator {name}")
        captured[name] = content
        (snapshot_root / name).write_bytes(content)
    return captured


def _read_jsonl_packet(content: bytes) -> list[dict]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("annotator packet is not valid UTF-8") from exc
    rows = []
    expected = {"blind_id", "task_id", "question", "report_markdown"}
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"annotator packet line {line_number} is not valid JSON") from exc
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError(
                f"annotator packet line {line_number} schema must be exactly {sorted(expected)}"
            )
        rows.append(row)
    if not rows:
        raise ValueError("annotator packet contains no reports")
    return rows


def _read_ratings_template(content: bytes) -> list[dict]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("annotator ratings template is not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != list(build.RATING_FIELDS):
        raise ValueError("annotator ratings template schema mismatch")
    rows = list(reader)
    if not rows:
        raise ValueError("annotator ratings template contains no rows")
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("annotator ratings template contains malformed rows")
        populated = {
            name: value
            for name, value in row.items()
            if name != "blind_id" and str(value).strip()
        }
        if populated:
            raise ValueError(
                f"annotator ratings template must be unscored for {row.get('blind_id', '')}"
            )
    return rows


def verify_annotator_bundle(output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    """Verify that a published bundle contains only annotator-safe artifacts."""
    output_root = Path(output_root)
    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError(f"annotator bundle root must be a regular directory: {output_root}")

    children = {path.name for path in output_root.iterdir()}
    if children != set(ANNOTATOR_ARTIFACTS):
        extra = sorted(children - set(ANNOTATOR_ARTIFACTS))
        missing = sorted(set(ANNOTATOR_ARTIFACTS) - children)
        raise ValueError(
            "annotator bundle artifact set mismatch; "
            f"missing={missing}, extra={extra}"
        )

    packet_bytes = _regular_bytes(output_root / "packet.jsonl", label="annotator packet")
    template_bytes = _regular_bytes(
        output_root / "ratings_template.csv", label="annotator ratings template"
    )
    manifest_bytes = _regular_bytes(
        output_root / "annotator_manifest.json", label="annotator manifest"
    )
    packet_rows = _read_jsonl_packet(packet_bytes)
    template_rows = _read_ratings_template(template_bytes)

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("annotator manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("annotator manifest must contain a JSON object")

    expected_identity = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_distribution",
        "coordinator_artifacts_included": False,
    }
    for key, expected in expected_identity.items():
        if manifest.get(key) != expected:
            raise ValueError(
                f"annotator manifest {key} mismatch: expected {expected!r}, got {manifest.get(key)!r}"
            )

    forbidden_manifest_keys = {
        "blind_seed",
        "blind_seed_source",
        "blinding_key",
        "variant_id",
        "run_id",
        "treatment",
    }
    leaked = sorted(forbidden_manifest_keys & set(manifest))
    if leaked:
        raise ValueError(f"annotator manifest leaks coordinator metadata: {leaked}")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"packet", "ratings_template"}:
        raise ValueError("annotator manifest artifact contract mismatch")
    expected_artifacts = {
        "packet": {"path": "packet.jsonl", **_fingerprint(packet_bytes)},
        "ratings_template": {
            "path": "ratings_template.csv",
            **_fingerprint(template_bytes),
        },
    }
    if artifacts != expected_artifacts:
        raise ValueError("annotator manifest artifact fingerprint mismatch")

    packet_ids = [str(row["blind_id"]).strip() for row in packet_rows]
    template_ids = [str(row["blind_id"]).strip() for row in template_rows]
    if not all(packet_ids) or len(set(packet_ids)) != len(packet_ids):
        raise ValueError("annotator packet blind IDs must be unique and non-empty")
    if set(packet_ids) != set(template_ids) or len(template_ids) != len(set(template_ids)):
        raise ValueError("annotator packet/template blind-ID coverage mismatch")

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_distribution_verified",
        "n_reports": len(packet_rows),
        "coordinator_artifacts_included": False,
        "packet_sha256": _fingerprint(packet_bytes)["sha256"],
        "ratings_template_sha256": _fingerprint(template_bytes)["sha256"],
    }


def export_annotator_bundle(
    *,
    packet_root: Path = DEFAULT_PACKET_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    task_manifest_path: Path = DEFAULT_TASK_MANIFEST,
    repo_root: Path = REPO_ROOT,
) -> dict:
    """Snapshot, verify, and export only annotator-facing packet artifacts."""
    packet_root = Path(packet_root)
    output_root = Path(output_root)
    task_manifest_path = Path(task_manifest_path)
    repo_root = Path(repo_root)

    if packet_root.is_symlink() or not packet_root.is_dir():
        raise ValueError(f"coordinator packet root must be a regular directory: {packet_root}")
    if output_root.exists() or output_root.is_symlink():
        raise ValueError(
            f"refusing to overwrite annotator bundle output: {output_root}; "
            "choose a new, nonexistent output root"
        )

    with tempfile.TemporaryDirectory(prefix="vera-annotator-export-") as tmp_name:
        snapshot_root = Path(tmp_name) / "packet"
        snapshot_root.mkdir(parents=True)
        captured = _snapshot_coordinator_bundle(packet_root, snapshot_root)

        verify_packet(
            output_root=snapshot_root,
            task_manifest_path=task_manifest_path,
            repo_root=repo_root,
        )

        packet_bytes = captured["packet.jsonl"]
        template_bytes = captured["ratings_template.csv"]
        _read_jsonl_packet(packet_bytes)
        _read_ratings_template(template_bytes)

        try:
            output_root.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ValueError(
                f"refusing to overwrite annotator bundle output: {output_root}"
            ) from exc

        _write_exclusive(output_root / "packet.jsonl", packet_bytes)
        _write_exclusive(output_root / "ratings_template.csv", template_bytes)
        manifest = {
            "schema_version": 1,
            "study_id": "budget-main-v1",
            "status": "human_eval_annotator_distribution",
            "coordinator_artifacts_included": False,
            "n_reports": len(_read_jsonl_packet(packet_bytes)),
            "artifacts": {
                "packet": {"path": "packet.jsonl", **_fingerprint(packet_bytes)},
                "ratings_template": {
                    "path": "ratings_template.csv",
                    **_fingerprint(template_bytes),
                },
            },
            "distribution_note": (
                "This directory is safe for annotator distribution only after this "
                "manifest verifies. It intentionally excludes blinding_key.csv and "
                "the coordinator packet manifest."
            ),
        }
        _write_exclusive(
            output_root / "annotator_manifest.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

    return verify_annotator_bundle(output_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-root", type=Path, default=DEFAULT_PACKET_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--task-manifest", type=Path, default=DEFAULT_TASK_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_only:
            receipt = verify_annotator_bundle(args.output_root)
        else:
            receipt = export_annotator_bundle(
                packet_root=args.packet_root,
                output_root=args.output_root,
                task_manifest_path=args.task_manifest,
                repo_root=args.repo_root,
            )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL ANNOTATOR EXPORT: FAIL: {exc}") from exc
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN EVAL ANNOTATOR EXPORT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
