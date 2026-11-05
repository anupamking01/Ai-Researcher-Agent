"""Read-only replay of a historical ZIP candidate-triage receipt.

Reinspect every explicitly supplied archive in its original role and CLI order.
A replay checks present-day inventory consistency, NOT original source custody.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Sequence

from scripts import triage_historical_archive_candidates as triage

MAX_RECEIPT_BYTES = 2 * 1024 * 1024


class ReceiptVerificationError(ValueError):
    """A saved candidate inventory cannot be reproduced safely."""


def _identity(info: os.stat_result) -> tuple:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_nlink,
        info.st_mtime_ns, info.st_ctime_ns,
    )


def _read_receipt(path: Path) -> bytes:
    """Bound receipt bytes and fail closed on symlink/hardlink or path replacement."""
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(path, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            source = os.stat(path, follow_symlinks=False)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or not 0 < before.st_size <= MAX_RECEIPT_BYTES
                or _identity(before) != _identity(source)
            ):
                raise ReceiptVerificationError(
                    "receipt must be a stable bounded single-link regular file"
                )
            raw = stream.read(MAX_RECEIPT_BYTES + 1)
            if (
                len(raw) != before.st_size
                or _identity(before) != _identity(os.fstat(stream.fileno()))
                or _identity(before)
                != _identity(os.stat(path, follow_symlinks=False))
            ):
                raise ReceiptVerificationError("receipt changed during capture")
    except OSError as exc:
        raise ReceiptVerificationError(
            "cannot read receipt: filesystem error "
            f"({errno.errorcode.get(exc.errno, 'UNKNOWN')})"
        ) from exc
    return raw


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptVerificationError("duplicate JSON key in triage receipt")
        result[key] = value
    return result


def _reject_nonfinite(token: str):
    raise ReceiptVerificationError("nonfinite number in triage receipt")


def verify_receipt(
    receipt_path: Path, assignments: Sequence[tuple[str, Path]],
) -> dict:
    """Recompute the full inventory with the same role/order and resource bounds."""
    if not 0 < len(assignments) <= triage.MAX_CANDIDATES:
        raise ReceiptVerificationError("provide original ordered candidate paths")
    raw = _read_receipt(receipt_path)
    try:
        recorded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptVerificationError("receipt must be valid UTF-8 JSON") from exc
    if (
        type(recorded) is not dict
        or type(recorded.get("schema_version")) is not int
        or recorded["schema_version"] != 3
    ):
        raise ReceiptVerificationError("expected schema-v3 triage receipt")
    try:
        recorded_canonical = json.dumps(
            recorded, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
    except (ValueError, TypeError, OverflowError) as exc:
        raise ReceiptVerificationError("invalid receipt JSON number or value") from exc
    replayed = triage.triage_candidates(assignments)
    replayed_canonical = json.dumps(
        replayed, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )
    # Do not compare dicts: True == 1 and 1 == 1.0 mask edits.
    if recorded_canonical != replayed_canonical:
        raise ReceiptVerificationError(
            "recorded candidate inventory differs from replayed inspection"
        )
    return {
        "schema_version": 1,
        "status": "triage_receipt_replayed_not_historically_authenticated",
        "recorded_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate_count": len(assignments),
        "full_recorded_inventory_replayed": True,
        "github_provider_metadata_is_independent_custody": False,
        "historical_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "experimental_treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_generated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--original-treatment", dest="assignments", type=Path,
        action=triage._OrderedCandidate, role="original_treatment", metavar="ZIP",
    )
    parser.add_argument(
        "--evaluator-recovery", dest="assignments", type=Path,
        action=triage._OrderedCandidate, role="evaluator_recovery", metavar="ZIP",
    )
    args = parser.parse_args()
    try:
        result = verify_receipt(args.receipt, args.assignments or [])
    except (ReceiptVerificationError, triage.CandidateTriageError) as exc:
        parser.exit(1, f"VERA ARCHIVE TRIAGE RECEIPT REPLAY: FAIL: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
