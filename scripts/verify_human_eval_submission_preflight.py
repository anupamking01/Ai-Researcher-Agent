"""Independently verify a retained treatment-blind submission receipt.

The verifier never reads the coordinator-only blinding key and never joins
ratings to treatment labels. It recomputes submission preflight against the
same annotator-facing bundle and requires an exact receipt match.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import stat
from pathlib import Path

from scripts import freeze_human_eval_ratings as freeze


RECEIPT_NAME = "preflight_receipt.json"
# A receipt contains fixed metadata and hashes, never an annotation payload.
# Bound untrusted retained bytes before JSON parsing, including concurrent growth.
MAX_RECEIPT_BYTES = 64 * 1024
_RECEIPT_KEYS = {
    "schema_version",
    "study_id",
    "status",
    "annotator_id",
    "n_reports",
    "n_missing_dimension_values",
    "submission",
    "annotator_manifest_sha256",
    "packet_sha256",
    "ratings_template_sha256",
    "annotator_guide_sha256",
    "presentation_order",
}
_HASH_KEYS = {
    "annotator_manifest_sha256",
    "packet_sha256",
    "ratings_template_sha256",
    "annotator_guide_sha256",
}


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, member in pairs:
        if key in value:
            raise ValueError(
                f"human-evaluation preflight receipt contains duplicate key: {key!r}"
            )
        value[key] = member
    return value


def _require_receipt_size(size: int) -> None:
    if size > MAX_RECEIPT_BYTES:
        raise ValueError(
            f"human-evaluation preflight receipt exceeds {MAX_RECEIPT_BYTES} bytes"
        )


def _read_descriptor_bytes(file_descriptor: int) -> bytes:
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    chunks = []
    remaining = MAX_RECEIPT_BYTES
    while True:
        # One extra byte detects a receipt appended after the stat preflight.
        chunk = os.read(file_descriptor, min(64 * 1024, remaining + 1))
        if not chunk:
            return b"".join(chunks)
        if len(chunk) > remaining:
            _require_receipt_size(MAX_RECEIPT_BYTES + 1)
        chunks.append(chunk)
        remaining -= len(chunk)


def _bounded_receipt_entries(root_fd: int) -> set[str]:
    """Inspect at most two names from the already-open receipt directory.

    The receipt contract permits exactly one file. Read one overflow entry
    to reject oversized or unexpected inventories without materializing an
    unbounded external directory using os.listdir().
    """
    names: list[str] = []
    with os.scandir(root_fd) as entries:
        for entry in entries:
            if names:
                raise ValueError(
                    "human-evaluation preflight receipt artifact set mismatch: "
                    "more than one directory entry"
                )
            names.append(entry.name)
    return set(names)


def _require_same_object(current: os.stat_result, opened: os.stat_result) -> None:
    if (
        (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
        or current.st_size != opened.st_size
        or current.st_mtime_ns != opened.st_mtime_ns
    ):
        raise ValueError(
            "human-evaluation preflight receipt changed during verification"
        )


@contextmanager
def _retained_receipt_window(receipt_root: Path):
    """Keep the sole non-symlink receipt bound while the caller verifies it."""
    receipt_root = Path(receipt_root)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        root_fd = os.open(receipt_root, directory_flags)
    except OSError as exc:
        raise ValueError(
            "human-evaluation preflight receipt root must be a regular directory: "
            f"{receipt_root}"
        ) from exc
    try:
        opened_root = os.fstat(root_fd)
        if not stat.S_ISDIR(opened_root.st_mode):
            raise ValueError(
                "human-evaluation preflight receipt root must be a regular "
                f"directory: {receipt_root}"
            )
        entries = _bounded_receipt_entries(root_fd)
        if entries != {RECEIPT_NAME}:
            raise ValueError(
                "human-evaluation preflight receipt artifact set mismatch: "
                f"expected only {RECEIPT_NAME!r}, got {sorted(entries)!r}"
            )
        # Classify the directory entry before open: opening a FIFO in blocking
        # mode would otherwise hang indefinitely before the fstat() guard.
        # O_NONBLOCK closes the remaining race where a regular file is swapped
        # for a FIFO between stat() and open().
        try:
            candidate = os.stat(
                RECEIPT_NAME,
                dir_fd=root_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ValueError(
                "human-evaluation preflight receipt must be a regular file"
            ) from exc
        if not stat.S_ISREG(candidate.st_mode):
            raise ValueError(
                "human-evaluation preflight receipt must be a regular file"
            )
        _require_receipt_size(candidate.st_size)
        try:
            receipt_fd = os.open(
                RECEIPT_NAME,
                os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_fd,
            )
        except OSError as exc:
            raise ValueError(
                "human-evaluation preflight receipt must be a regular file"
            ) from exc
        try:
            opened = os.fstat(receipt_fd)
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError(
                    "human-evaluation preflight receipt must be a regular file"
                )
            _require_receipt_size(opened.st_size)
            _require_same_object(opened, candidate)
            receipt_bytes = _read_descriptor_bytes(receipt_fd)
            current = os.stat(
                RECEIPT_NAME,
                dir_fd=root_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISREG(current.st_mode):
                raise ValueError(
                    "human-evaluation preflight receipt must be a regular file"
                )
            _require_same_object(current, opened)
            try:
                retained = json.loads(
                    receipt_bytes.decode("utf-8"),
                    object_pairs_hook=_unique_json_object,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    "human-evaluation preflight receipt is not valid UTF-8 JSON"
                ) from exc
            if not isinstance(retained, dict):
                raise ValueError(
                    "human-evaluation preflight receipt must contain an object"
                )

            yield retained

            if _read_descriptor_bytes(receipt_fd) != receipt_bytes:
                raise ValueError(
                    "human-evaluation preflight receipt changed during verification"
                )
            _require_same_object(os.fstat(receipt_fd), opened)
            if _bounded_receipt_entries(root_fd) != {RECEIPT_NAME}:
                raise ValueError(
                    "human-evaluation preflight receipt artifact set changed during "
                    "verification"
                )
            try:
                visible_receipt = os.stat(
                    RECEIPT_NAME,
                    dir_fd=root_fd,
                    follow_symlinks=False,
                )
                visible_root = os.stat(receipt_root, follow_symlinks=False)
            except OSError as exc:
                raise ValueError(
                    "human-evaluation preflight receipt changed during verification"
                ) from exc
            if not stat.S_ISREG(visible_receipt.st_mode):
                raise ValueError(
                    "human-evaluation preflight receipt changed during verification"
                )
            _require_same_object(visible_receipt, opened)
            if not stat.S_ISDIR(visible_root.st_mode):
                raise ValueError(
                    "human-evaluation preflight receipt changed during verification"
                )
            _require_same_object(visible_root, opened_root)
        finally:
            os.close(receipt_fd)
    finally:
        os.close(root_fd)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_receipt_schema(receipt: dict) -> None:
    if set(receipt) != _RECEIPT_KEYS:
        raise ValueError("human-evaluation preflight receipt schema mismatch")
    if type(receipt["schema_version"]) is not int or receipt["schema_version"] != 2:
        raise ValueError("human-evaluation preflight receipt schema_version mismatch")
    for key in ("study_id", "status", "annotator_id", "presentation_order"):
        if not isinstance(receipt[key], str) or not receipt[key]:
            raise ValueError(
                f"human-evaluation preflight receipt schema invalid for {key}"
            )
    for key in ("n_reports", "n_missing_dimension_values"):
        if type(receipt[key]) is not int or receipt[key] < 0:
            raise ValueError(
                f"human-evaluation preflight receipt schema invalid for {key}"
            )
    if receipt["n_reports"] == 0:
        raise ValueError("human-evaluation preflight receipt schema has no reports")
    submission = receipt["submission"]
    if not isinstance(submission, dict) or set(submission) != {
        "name",
        "bytes",
        "sha256",
    }:
        raise ValueError("human-evaluation preflight receipt submission schema mismatch")
    if not isinstance(submission["name"], str) or not submission["name"]:
        raise ValueError("human-evaluation preflight receipt submission name is invalid")
    if type(submission["bytes"]) is not int or submission["bytes"] < 0:
        raise ValueError("human-evaluation preflight receipt submission bytes are invalid")
    if not _is_sha256(submission["sha256"]):
        raise ValueError("human-evaluation preflight receipt submission hash is invalid")
    for key in _HASH_KEYS:
        if not _is_sha256(receipt[key]):
            raise ValueError(
                f"human-evaluation preflight receipt schema invalid for {key}"
            )


def verify_preflight_receipt(
    *,
    receipt_root: Path,
    rating_path: Path,
    annotator_bundle_root: Path,
) -> dict:
    """Recompute blinded preflight and require the retained receipt to match."""
    with _retained_receipt_window(Path(receipt_root)) as retained:
        _validate_receipt_schema(retained)
        expected = freeze.preflight_annotator_submission(
            Path(rating_path),
            annotator_bundle_root=Path(annotator_bundle_root),
        )
        if retained != expected:
            raise ValueError(
                "retained human-evaluation preflight receipt does not match the "
                "verified blinded submission and annotator bundle"
            )
    return retained


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--preflight-bundle", type=Path, required=True)
    args = parser.parse_args()

    try:
        receipt = verify_preflight_receipt(
            receipt_root=args.receipt_root,
            rating_path=args.ratings,
            annotator_bundle_root=args.preflight_bundle,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"HUMAN EVAL SUBMISSION RECEIPT VERIFY: FAIL: {exc}"
        ) from exc
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("HUMAN EVAL SUBMISSION RECEIPT VERIFY: PASS (ratings remain blinded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
