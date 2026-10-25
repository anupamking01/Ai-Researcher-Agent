"""Create and verify an annotator-safe human-evaluation distribution bundle.

The coordinator packet contains a treatment mapping and blinding metadata that
must not be distributed to annotators. This utility snapshots the coordinator
packet, verifies that snapshot with the existing packet verifier, then exports
only packet.jsonl, ratings_template.csv, the frozen treatment-blind annotator
guide, and a seed-free annotator manifest.

No ratings are generated, no treatment identity is exposed, and no model/API
calls are made.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import errno
import hashlib
import io
import json
import os
import stat
import tempfile
from pathlib import Path

from scripts import build_human_eval_packet as build
from scripts.verify_human_eval_packet import verify_packet


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET_ROOT = build.DEFAULT_OUTPUT_ROOT
DEFAULT_OUTPUT_ROOT = DEFAULT_PACKET_ROOT / "annotator-bundle-v2"
DEFAULT_TASK_MANIFEST = build.DEFAULT_TASK_MANIFEST
DEFAULT_ANNOTATOR_GUIDE = REPO_ROOT / "paper" / "HUMAN_EVAL_ANNOTATOR_GUIDE.md"
FROZEN_ANNOTATOR_GUIDE_SHA256 = (
    "3e27ef38231ed70fe36370af31ced7762a253a72dc5cc4997d8ef62d0a6e3370"
)
COORDINATOR_ARTIFACTS = ("packet.jsonl", "ratings_template.csv", "blinding_key.csv", "manifest.json")
ANNOTATOR_ARTIFACTS = (
    "packet.jsonl",
    "ratings_template.csv",
    "annotator_instructions.md",
    "annotator_manifest.json",
)
DISTRIBUTION_NOTE = (
    "This directory is safe for annotator distribution only after this "
    "manifest verifies. It intentionally excludes blinding_key.csv and "
    "the coordinator packet manifest."
)
CONTENT_VALIDATOR_PATH = "scripts/build_human_eval_packet.py"
PRESENTATION_ORDERS = ("canonical", "reverse")


def _regular_bytes(path: Path, *, label: str) -> bytes:
    """Capture one bounded, descriptor-bound generation of an evidence file.

    Reuse the packet producer's 64 MiB capture contract rather than reading a
    potentially growing coordinator or annotator artifact into memory without
    a bound. The shared reader also rejects symlinks, non-regular files,
    truncation, growth, and path/parent replacement during capture.
    """
    return build._read_regular_file_captured(Path(path), label=label)


def _fingerprint(content: bytes) -> dict:
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _content_validator_source_contract() -> dict:
    content = _regular_bytes(
        Path(build.__file__), label="annotator content validator source"
    )
    return {"path": CONTENT_VALIDATOR_PATH, **_fingerprint(content)}


def _frozen_guide_bytes(path: Path) -> bytes:
    content = _regular_bytes(path, label="frozen annotator guide")
    actual = hashlib.sha256(content).hexdigest()
    if actual != FROZEN_ANNOTATOR_GUIDE_SHA256:
        raise ValueError(
            "frozen annotator guide fingerprint mismatch: "
            f"expected {FROZEN_ANNOTATOR_GUIDE_SHA256}, got {actual}"
        )
    return content


def _unique_json_object(label: str):
    def unique_object(pairs):
        value = {}
        for key, child in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key {key!r} in {label}")
            value[key] = child
        return value

    return unique_object


def _write_exclusive_at(directory_fd: int, name: str, content: bytes) -> None:
    try:
        file_fd = os.open(
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o666,
            dir_fd=directory_fd,
        )
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite annotator-bundle artifact: {name}") from exc
    with os.fdopen(file_fd, "wb") as handle:
        handle.write(content)


def _open_bound_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        directory_fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError(
            f"annotator bundle output root must be a regular directory: {path}"
        ) from exc
    if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
        os.close(directory_fd)
        raise ValueError(
            f"annotator bundle output root must be a regular directory: {path}"
        )
    return directory_fd


def _require_directory_binding(path: Path, directory_fd: int) -> None:
    try:
        current = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"annotator bundle output root changed during publication: {path}") from exc
    opened = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(f"annotator bundle output root changed during publication: {path}")


def _publish_directory_noreplace(staging_root: Path, output_root: Path) -> None:
    """Atomically install a staged directory without replacing any path."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise ValueError(
            "atomic no-replace directory publication is unavailable on this platform"
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    rename_noreplace = 1
    if (
        renameat2(
            at_fdcwd,
            os.fsencode(staging_root),
            at_fdcwd,
            os.fsencode(output_root),
            rename_noreplace,
        )
        == 0
    ):
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ValueError(
            f"refusing to overwrite annotator bundle output: {output_root}"
        )
    raise OSError(
        error_number,
        f"could not atomically publish annotator bundle: {output_root}",
    )


def _snapshot_coordinator_bundle(packet_root: Path, snapshot_root: Path) -> dict[str, bytes]:
    captured = {}
    for name in COORDINATOR_ARTIFACTS:
        content = _regular_bytes(packet_root / name, label=f"coordinator {name}")
        captured[name] = content
        (snapshot_root / name).write_bytes(content)
    return captured


def _require_annotator_artifact_set(output_root: Path) -> None:
    children = {path.name for path in Path(output_root).iterdir()}
    expected = set(ANNOTATOR_ARTIFACTS)
    if children != expected:
        extra = sorted(children - expected)
        missing = sorted(expected - children)
        raise ValueError(
            "annotator bundle artifact set mismatch; "
            f"missing={missing}, extra={extra}"
        )


def _snapshot_annotator_bundle(output_root: Path, snapshot_root: Path) -> dict[str, bytes]:
    # Enforce the live inventory before whitelisting files into the snapshot;
    # otherwise an injected coordinator artifact would disappear from the
    # captured view that receives the success receipt.
    _require_annotator_artifact_set(output_root)
    captured = {}
    for name in ANNOTATOR_ARTIFACTS:
        content = _regular_bytes(output_root / name, label=f"annotator {name}")
        captured[name] = content
        (snapshot_root / name).write_bytes(content)
    return captured


def _source_bound_receipt(
    *,
    receipt: dict,
    coordinator_bytes: dict[str, bytes],
    annotator_bytes: dict[str, bytes],
    guide_bytes: bytes,
    expected_presentation_order: str,
) -> dict:
    """Bind a locally verified distribution snapshot to its coordinator source."""
    if expected_presentation_order not in PRESENTATION_ORDERS:
        raise ValueError(
            "expected presentation order must be one of "
            + ", ".join(repr(value) for value in PRESENTATION_ORDERS)
        )
    presentation_order = receipt["presentation_order"]
    if presentation_order != expected_presentation_order:
        raise ValueError(
            "annotator bundle does not match expected presentation order: "
            f"expected {expected_presentation_order!r}, got {presentation_order!r}"
        )
    expected_packet, expected_template = _ordered_artifacts(
        coordinator_bytes["packet.jsonl"],
        coordinator_bytes["ratings_template.csv"],
        presentation_order=expected_presentation_order,
    )
    expected = {
        "packet.jsonl": expected_packet,
        "ratings_template.csv": expected_template,
    }
    for name, expected_bytes in expected.items():
        if annotator_bytes[name] != expected_bytes:
            raise ValueError(
                "annotator presentation order does not match the verified "
                f"coordinator source for {name}"
            )
    if annotator_bytes["annotator_instructions.md"] != guide_bytes:
        raise ValueError(
            "annotator instructions do not match the frozen annotator guide source"
        )
    return {
        **receipt,
        "source_bound_to_verified_coordinator": True,
        "coordinator_manifest_sha256": _fingerprint(
            coordinator_bytes["manifest.json"]
        )["sha256"],
        "annotator_guide_sha256": _fingerprint(guide_bytes)["sha256"],
    }


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
            row = json.loads(
                raw,
                object_pairs_hook=_unique_json_object(
                    f"annotator packet line {line_number}"
                ),
            )
        except json.JSONDecodeError as exc:
            raise ValueError(f"annotator packet line {line_number} is not valid JSON") from exc
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError(
                f"annotator packet line {line_number} schema must be exactly {sorted(expected)}"
            )
        # A hash-matching JSON object can still contain nested coordinator
        # metadata in a supposedly text-only field. Never stringify such
        # values into annotator-facing packet content.
        for field in expected:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(
                    f"annotator packet line {line_number} {field} must be non-empty text"
                )
        rows.append(row)
    if not rows:
        raise ValueError("annotator packet contains no reports")
    build.validate_annotator_facing_content(rows, label="annotator packet")
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


def _ordered_artifacts(
    packet_content: bytes,
    template_content: bytes,
    *,
    presentation_order: str,
) -> tuple[bytes, bytes]:
    """Return one declared ordering of the same validated blinded rows."""
    if presentation_order not in PRESENTATION_ORDERS:
        raise ValueError(
            "presentation order must be one of "
            + ", ".join(repr(value) for value in PRESENTATION_ORDERS)
        )
    packet_rows = _read_jsonl_packet(packet_content)
    template_rows = _read_ratings_template(template_content)
    if presentation_order == "canonical":
        return packet_content, template_content

    packet_rows.reverse()
    template_rows.reverse()
    packet_bytes = (
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in packet_rows
        )
        + "\n"
    ).encode("utf-8")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(build.RATING_FIELDS))
    writer.writeheader()
    writer.writerows(template_rows)
    return packet_bytes, output.getvalue().encode("utf-8")


def verify_annotator_bundle(output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict:
    """Verify that a published bundle contains only annotator-safe artifacts."""
    output_root = Path(output_root)
    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError(f"annotator bundle root must be a regular directory: {output_root}")

    _require_annotator_artifact_set(output_root)

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
        manifest = json.loads(
            manifest_bytes.decode("utf-8"),
            object_pairs_hook=_unique_json_object("annotator manifest"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("annotator manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("annotator manifest must contain a JSON object")
    if "content_validator_runtime" not in manifest:
        raise ValueError(
            "annotator manifest content validator runtime contract is missing"
        )
    if "content_validator" not in manifest:
        raise ValueError(
            "annotator manifest content validator source contract is missing"
        )

    required_manifest_keys = {
        "schema_version",
        "study_id",
        "status",
        "coordinator_artifacts_included",
        "n_reports",
        "artifacts",
        "content_validator",
        "content_validator_runtime",
        "presentation_order",
    }
    allowed_manifest_keys = required_manifest_keys | {"distribution_note"}
    if not required_manifest_keys.issubset(manifest) or not set(manifest).issubset(
        allowed_manifest_keys
    ):
        raise ValueError("annotator manifest schema contains missing or undeclared fields")
    if (
        "distribution_note" in manifest
        and manifest["distribution_note"] != DISTRIBUTION_NOTE
    ):
        raise ValueError("annotator manifest distribution_note mismatch")

    expected_identity = {
        "schema_version": 2,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_distribution",
        "coordinator_artifacts_included": False,
    }
    for key, expected in expected_identity.items():
        if manifest.get(key) != expected:
            raise ValueError(
                f"annotator manifest {key} mismatch: expected {expected!r}, got {manifest.get(key)!r}"
            )
    presentation_order = manifest.get("presentation_order")
    if presentation_order not in PRESENTATION_ORDERS:
        raise ValueError("annotator manifest presentation order is invalid")
    expected_runtime = build.content_validator_runtime_contract()
    if manifest.get("content_validator_runtime") != expected_runtime:
        raise ValueError(
            "annotator manifest content validator runtime contract mismatch: "
            f"expected {expected_runtime!r}, got "
            f"{manifest.get('content_validator_runtime')!r}"
        )
    expected_validator = _content_validator_source_contract()
    if manifest.get("content_validator") != expected_validator:
        raise ValueError(
            "annotator manifest content validator source contract mismatch: "
            f"expected {expected_validator!r}, got "
            f"{manifest.get('content_validator')!r}"
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
    if not isinstance(artifacts, dict) or set(artifacts) != {
        "packet",
        "ratings_template",
        "annotator_instructions",
    }:
        raise ValueError("annotator manifest artifact contract mismatch")
    guide_bytes = _regular_bytes(
        output_root / "annotator_instructions.md",
        label="annotator instructions",
    )
    if _fingerprint(guide_bytes)["sha256"] != FROZEN_ANNOTATOR_GUIDE_SHA256:
        raise ValueError("annotator instructions do not match the frozen guide")
    expected_artifacts = {
        "packet": {"path": "packet.jsonl", **_fingerprint(packet_bytes)},
        "ratings_template": {
            "path": "ratings_template.csv",
            **_fingerprint(template_bytes),
        },
        "annotator_instructions": {
            "path": "annotator_instructions.md",
            **_fingerprint(guide_bytes),
        },
    }
    if artifacts != expected_artifacts:
        raise ValueError("annotator manifest artifact fingerprint mismatch")

    packet_ids = [row["blind_id"].strip() for row in packet_rows]
    template_ids = [str(row["blind_id"]).strip() for row in template_rows]
    if not all(packet_ids) or len(set(packet_ids)) != len(packet_ids):
        raise ValueError("annotator packet blind IDs must be unique and non-empty")
    if set(packet_ids) != set(template_ids) or len(template_ids) != len(set(template_ids)):
        raise ValueError("annotator packet/template blind-ID coverage mismatch")
    if packet_ids != template_ids:
        raise ValueError("annotator packet/template blind-ID order mismatch")

    declared_count = manifest.get("n_reports")
    if type(declared_count) is not int or declared_count != len(packet_rows):
        raise ValueError("annotator manifest n_reports must equal the packet count as an integer")

    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_distribution_verified",
        "n_reports": len(packet_rows),
        "coordinator_artifacts_included": False,
        "packet_sha256": _fingerprint(packet_bytes)["sha256"],
        "ratings_template_sha256": _fingerprint(template_bytes)["sha256"],
        "annotator_guide_sha256": _fingerprint(guide_bytes)["sha256"],
        "presentation_order": presentation_order,
    }


def verify_annotator_bundle_against_source(
    *,
    expected_presentation_order: str,
    packet_root: Path = DEFAULT_PACKET_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    task_manifest_path: Path = DEFAULT_TASK_MANIFEST,
    repo_root: Path = REPO_ROOT,
    annotator_guide_path: Path = DEFAULT_ANNOTATOR_GUIDE,
) -> dict:
    """Verify a distribution bundle against one verified coordinator snapshot."""
    packet_root = Path(packet_root)
    output_root = Path(output_root)
    task_manifest_path = Path(task_manifest_path)
    repo_root = Path(repo_root)
    guide_bytes = _frozen_guide_bytes(Path(annotator_guide_path))
    if packet_root.is_symlink() or not packet_root.is_dir():
        raise ValueError(f"coordinator packet root must be a regular directory: {packet_root}")
    if output_root.is_symlink() or not output_root.is_dir():
        raise ValueError(f"annotator bundle root must be a regular directory: {output_root}")
    with tempfile.TemporaryDirectory(prefix="vera-annotator-source-verify-") as tmp_name:
        tmp_root = Path(tmp_name)
        coordinator_snapshot = tmp_root / "coordinator"
        annotator_snapshot = tmp_root / "annotator"
        coordinator_snapshot.mkdir()
        annotator_snapshot.mkdir()
        coordinator_bytes = _snapshot_coordinator_bundle(packet_root, coordinator_snapshot)
        annotator_bytes = _snapshot_annotator_bundle(output_root, annotator_snapshot)
        verify_packet(
            output_root=coordinator_snapshot,
            task_manifest_path=task_manifest_path,
            repo_root=repo_root,
        )
        receipt = verify_annotator_bundle(annotator_snapshot)
        return _source_bound_receipt(
            receipt=receipt,
            coordinator_bytes=coordinator_bytes,
            annotator_bytes=annotator_bytes,
            guide_bytes=guide_bytes,
            expected_presentation_order=expected_presentation_order,
        )


def export_annotator_bundle(
    *,
    packet_root: Path = DEFAULT_PACKET_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    task_manifest_path: Path = DEFAULT_TASK_MANIFEST,
    repo_root: Path = REPO_ROOT,
    annotator_guide_path: Path = DEFAULT_ANNOTATOR_GUIDE,
    presentation_order: str = "canonical",
) -> dict:
    """Snapshot, verify, and export only annotator-facing packet artifacts."""
    packet_root = Path(packet_root)
    output_root = Path(output_root)
    task_manifest_path = Path(task_manifest_path)
    repo_root = Path(repo_root)
    guide_bytes = _frozen_guide_bytes(Path(annotator_guide_path))
    if presentation_order not in PRESENTATION_ORDERS:
        raise ValueError(
            "presentation order must be one of "
            + ", ".join(repr(value) for value in PRESENTATION_ORDERS)
        )

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

        packet_bytes, template_bytes = _ordered_artifacts(
            captured["packet.jsonl"],
            captured["ratings_template.csv"],
            presentation_order=presentation_order,
        )

        output_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(
            prefix=f".{output_root.name}.staging-",
            dir=output_root.parent,
            )
        )
        output_fd = _open_bound_directory(staging_root)
        try:
            _write_exclusive_at(output_fd, "packet.jsonl", packet_bytes)
            _write_exclusive_at(output_fd, "ratings_template.csv", template_bytes)
            _write_exclusive_at(
                output_fd,
                "annotator_instructions.md",
                guide_bytes,
            )
            manifest = {
                "schema_version": 2,
                "study_id": "budget-main-v1",
                "status": "human_eval_annotator_distribution",
                "coordinator_artifacts_included": False,
                "presentation_order": presentation_order,
                "n_reports": len(_read_jsonl_packet(packet_bytes)),
                "content_validator": _content_validator_source_contract(),
                "content_validator_runtime": (
                    build.content_validator_runtime_contract()
                ),
                "artifacts": {
                    "packet": {
                        "path": "packet.jsonl",
                        **_fingerprint(packet_bytes),
                    },
                    "ratings_template": {
                        "path": "ratings_template.csv",
                        **_fingerprint(template_bytes),
                    },
                    "annotator_instructions": {
                        "path": "annotator_instructions.md",
                        **_fingerprint(guide_bytes),
                    },
                },
                "distribution_note": DISTRIBUTION_NOTE,
            }
            manifest_bytes = (
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            _write_exclusive_at(
                output_fd,
                "annotator_manifest.json",
                manifest_bytes,
            )
            # Verify one captured publication revision and prove that its
            # coordinator-generated byte streams and frozen guide still equal
            # their verified sources. Local manifest consistency alone cannot
            # establish source identity after a coherent artifact replacement.
            annotator_snapshot = Path(tmp_name) / "annotator"
            annotator_snapshot.mkdir()
            _require_directory_binding(staging_root, output_fd)
            annotator_bytes = _snapshot_annotator_bundle(
                staging_root, annotator_snapshot
            )
            _require_directory_binding(staging_root, output_fd)
            if annotator_bytes["annotator_manifest.json"] != manifest_bytes:
                raise ValueError(
                    "annotator manifest does not match the published candidate"
                )
            receipt = verify_annotator_bundle(annotator_snapshot)
            source_bound_receipt = _source_bound_receipt(
                receipt=receipt,
                coordinator_bytes=captured,
                annotator_bytes=annotator_bytes,
                guide_bytes=guide_bytes,
                expected_presentation_order=presentation_order,
            )
            _require_directory_binding(staging_root, output_fd)
            _publish_directory_noreplace(staging_root, output_root)
            _require_directory_binding(output_root, output_fd)
            return source_bound_receipt
        finally:
            # A failed staging directory is retained deliberately. Deleting by
            # pathname could remove a concurrent replacement after any identity
            # check; successful publication has already moved this inode away.
            os.close(output_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-root", type=Path, default=DEFAULT_PACKET_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--task-manifest", type=Path, default=DEFAULT_TASK_MANIFEST)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--annotator-guide",
        type=Path,
        default=DEFAULT_ANNOTATOR_GUIDE,
    )
    parser.add_argument(
        "--presentation-order",
        choices=PRESENTATION_ORDERS,
        default=None,
        help=(
            "Annotator-facing row order. Defaults to canonical for export and "
            "is required for source-bound verification."
        ),
    )
    verification = parser.add_mutually_exclusive_group()
    verification.add_argument("--verify-only", action="store_true")
    verification.add_argument("--verify-against-source", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_against_source:
            if args.presentation_order is None:
                raise ValueError(
                    "--presentation-order is required with --verify-against-source"
                )
            receipt = verify_annotator_bundle_against_source(
                expected_presentation_order=args.presentation_order,
                packet_root=args.packet_root,
                output_root=args.output_root,
                task_manifest_path=args.task_manifest,
                repo_root=args.repo_root,
                annotator_guide_path=args.annotator_guide,
            )
        elif args.verify_only:
            receipt = verify_annotator_bundle(args.output_root)
            if (
                args.presentation_order is not None
                and receipt["presentation_order"] != args.presentation_order
            ):
                raise ValueError(
                    "annotator bundle does not match expected presentation order: "
                    f"expected {args.presentation_order!r}, got "
                    f"{receipt['presentation_order']!r}"
                )
        else:
            receipt = export_annotator_bundle(
                packet_root=args.packet_root,
                output_root=args.output_root,
                task_manifest_path=args.task_manifest,
                repo_root=args.repo_root,
                annotator_guide_path=args.annotator_guide,
                presentation_order=args.presentation_order or "canonical",
            )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"HUMAN EVAL ANNOTATOR EXPORT: FAIL: {exc}") from exc
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN EVAL ANNOTATOR EXPORT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
