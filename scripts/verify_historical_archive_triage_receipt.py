"""Read-only replay of a historical ZIP candidate-triage receipt.

Reinspect every explicitly supplied archive in its original role and CLI order.
A replay checks present-day inventory consistency, NOT original source custody.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import stat
from typing import Sequence

from scripts import triage_historical_archive_candidates as triage

MAX_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_NUMBER_TOKEN_CHARS = 128


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


def _bounded_json_int(token: str) -> int:
    if len(token) > MAX_RECEIPT_NUMBER_TOKEN_CHARS:
        raise ReceiptVerificationError("oversized JSON number in triage receipt")
    return int(token)


def _bounded_json_float(token: str) -> float:
    if len(token) > MAX_RECEIPT_NUMBER_TOKEN_CHARS:
        raise ReceiptVerificationError("oversized JSON number in triage receipt")
    value = float(token)
    if not math.isfinite(value):
        raise ReceiptVerificationError("nonfinite JSON number in triage receipt")
    return value


def _preflight_receipt_roster(
    recorded: dict, assignments: Sequence[tuple[str, Path]],
) -> None:
    """Reject impossible candidate rosters before expensive ZIP reads.

    This is an early shape/order check, not a substitute for full replay of
    candidate hashes, structural diagnostics or resource-budget accounting.
    Never include caller-supplied private directory names in an error.
    """
    rows = recorded.get("candidates")
    if type(rows) is not list or len(rows) != len(assignments):
        raise ReceiptVerificationError(
            "recorded candidate inventory differs from supplied candidate roster"
        )
    for index, (row, (role, path)) in enumerate(zip(rows, assignments), 1):
        if (
            type(row) is not dict
            or type(row.get("candidate_index")) is not int
            or row["candidate_index"] != index
            or type(row.get("role")) is not str
            or row["role"] != role
            or type(row.get("supplied_filename")) is not str
            or row["supplied_filename"] != path.name
        ):
            raise ReceiptVerificationError(
                "recorded candidate inventory differs from supplied candidate roster"
            )



# Validate declared source identities before a potential 1-GiB candidate rescan.
# These checks reject internally impossible receipts; only full ZIP replay can
# establish continuity of the present-day candidate bytes.
_CANDIDATE_BASE_FIELDS = frozenset({
    "candidate_index", "role", "supplied_filename", "status",
    "structural_preflight_succeeded",
    "github_provider_zip_digest_and_size_match",
    "other_role_github_provider_zip_match",
    "duplicate_verified_zip_of_candidate_index",
    "observed_regular_member_content_sha256",
    "same_regular_members_as_candidate_index",
})
_CANDIDATE_VERIFIED_FIELDS = frozenset({
    "observed_zip_bytes", "observed_zip_sha256", "file_count",
})
_CANDIDATE_FAILED_FIELDS = frozenset({"diagnostic"})
_CANDIDATE_FAILED_STATUSES = frozenset({
    "not_inspected_batch_archive_byte_budget_exceeded",
    "not_inspected_batch_decompression_budget_exceeded",
    "structural_preflight_failed",
})


def _preflight_candidate_source_claims(recorded: dict) -> None:
    """Fail before ZIP I/O on impossible candidate digests, roles, or row types."""
    failed = "recorded triage receipt has inconsistent claims: candidate source identity"
    first_zip: dict[str, int] = {}
    first_members: dict[str, int] = {}

    def digest_valid(value) -> bool:
        return (
            type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value)
        )

    for row in recorded["candidates"]:
        success = row.get("structural_preflight_succeeded")
        provider = row.get("github_provider_zip_digest_and_size_match")
        if type(success) is not bool or type(provider) is not bool:
            raise ReceiptVerificationError(failed)
        if set(row) != (
            _CANDIDATE_BASE_FIELDS
            | (_CANDIDATE_VERIFIED_FIELDS if success else _CANDIDATE_FAILED_FIELDS)
        ):
            raise ReceiptVerificationError(failed)

        if not success:
            if (
                row["status"] not in _CANDIDATE_FAILED_STATUSES
                or provider
                or row["other_role_github_provider_zip_match"] is not None
                or row["duplicate_verified_zip_of_candidate_index"] is not None
                or row["observed_regular_member_content_sha256"] is not None
                or row["same_regular_members_as_candidate_index"] is not None
                or type(row["diagnostic"]) is not str
                or not 0 < len(row["diagnostic"]) <= 300
            ):
                raise ReceiptVerificationError(failed)
            continue

        size = row["observed_zip_bytes"]
        file_count = row["file_count"]
        digest = row["observed_zip_sha256"]
        members = row["observed_regular_member_content_sha256"]
        if (
            type(size) is not int
            or not 0 < size <= triage.zip_preflight.MAX_ARCHIVE_BYTES
            or type(file_count) is not int
            or not 0 <= file_count <= triage.zip_preflight.MAX_MEMBERS
            or not digest_valid(digest)
            or not digest_valid(members)
        ):
            raise ReceiptVerificationError(failed)

        role = row["role"]  # The ordered-roster preflight already checks the role.
        anchor = triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES[role]
        matches_declared = (
            size == anchor["size_bytes"] and digest == anchor["zip_sha256"]
        )
        other_role = next((
            other for other in triage.ROLES
            if other != role
            and size == triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES[other]["size_bytes"]
            and digest == triage.zip_preflight.GITHUB_JOB_LOG_ARCHIVES[other]["zip_sha256"]
        ), None) if not matches_declared else None
        expected_status = (
            "github_provider_zip_concordant_not_authenticated"
            if matches_declared else
            "matches_other_historical_role_not_declared_role"
            if other_role is not None else
            "does_not_match_historical_github_provider_zip"
        )
        if (
            provider is not matches_declared
            or row["other_role_github_provider_zip_match"] != other_role
            or row["status"] != expected_status
        ):
            raise ReceiptVerificationError(failed)

        # Duplicate references must identify the FIRST preceding matching
        # verified source, not an arbitrary row or a failed candidate.
        index = row["candidate_index"]
        if (
            row["duplicate_verified_zip_of_candidate_index"] != first_zip.get(digest)
            or row["same_regular_members_as_candidate_index"] != first_members.get(members)
        ):
            raise ReceiptVerificationError(failed)
        first_zip.setdefault(digest, index)
        first_members.setdefault(members, index)


def _preflight_receipt_claims(recorded: dict) -> None:
    """Reject impossible research claims/accounting before costly ZIP rescans.

    This is a cheap consistency check on *untrusted receipt declarations*,
    not proof of the candidate source bytes or independent archive custody.
    Full replay remains mandatory after these checks pass.
    """
    failed = "recorded triage receipt has inconsistent claims or accounting"
    fixed = {
        "status": "candidate_triage_only_no_historical_authentication",
        "all_explicit_candidates_accounted_for": True,
        "distinct_zip_bytes_establish_independent_custody": False,
        "supplied_candidates_proven_exhaustive": False,
        "github_service_metadata_is_independent_custody": False,
        "original_treatment_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "experimental_treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_generated": False,
        "batch_archive_byte_budget": triage.MAX_BATCH_ARCHIVE_BYTES,
        "batch_declared_uncompressed_byte_budget": triage.MAX_BATCH_UNCOMPRESSED_BYTES,
    }
    if any(
        type(recorded.get(key)) is not type(value) or recorded[key] != value
        for key, value in fixed.items()
    ):
        raise ReceiptVerificationError(failed)

    rows = recorded["candidates"]  # Already type-checked by roster preflight.
    # JSON permits arrays/objects in place of hash strings. Reject their types
    # before building distinct-digest sets, rather than leaking a TypeError.
    for row in rows:
        if any(
            row.get(field) is not None and type(row[field]) is not str
            for field in (
                "observed_regular_member_content_sha256", "observed_zip_sha256",
            )
        ):
            raise ReceiptVerificationError(failed)
    by_role = recorded.get("by_role")
    if type(by_role) is not dict or set(by_role) != set(triage.ROLES):
        raise ReceiptVerificationError(failed)

    for role in triage.ROLES:
        role_rows = [row for row in rows if row["role"] == role]
        expected = {
            "candidate_count": len(role_rows),
            "provider_concordant_count": sum(
                row.get("github_provider_zip_digest_and_size_match") is True
                for row in role_rows
            ),
            "other_role_provider_concordant_count": sum(
                row.get("other_role_github_provider_zip_match") is not None
                for row in role_rows
            ),
            "distinct_regular_member_content_count": len({
                row.get("observed_regular_member_content_sha256")
                for row in role_rows if row.get("structural_preflight_succeeded") is True
            }),
            "distinct_structurally_verified_zip_count": len({
                row.get("observed_zip_sha256")
                for row in role_rows if row.get("structural_preflight_succeeded") is True
            }),
            "distinct_provider_concordant_zip_count": len({
                row.get("observed_zip_sha256")
                for row in role_rows
                if row.get("github_provider_zip_digest_and_size_match") is True
            }),
        }
        observed = by_role[role]
        if type(observed) is not dict or set(observed) != set(expected):
            raise ReceiptVerificationError(failed)
        if any(
            type(observed[key]) is not int or observed[key] != value
            for key, value in expected.items()
        ):
            raise ReceiptVerificationError(failed)

    counts = {
        "batch_candidates_not_inspected_due_to_archive_budget": sum(
            row.get("status") == "not_inspected_batch_archive_byte_budget_exceeded"
            for row in rows
        ),
        "batch_candidates_not_inspected_due_to_budget": sum(
            row.get("status") == "not_inspected_batch_decompression_budget_exceeded"
            for row in rows
        ),
        "same_regular_members_duplicate_count": sum(
            row.get("same_regular_members_as_candidate_index") is not None
            for row in rows
        ),
        "verified_zip_byte_duplicate_count": sum(
            row.get("duplicate_verified_zip_of_candidate_index") is not None
            for row in rows
        ),
        "other_role_provider_concordant_candidate_count": sum(
            row.get("other_role_github_provider_zip_match") is not None
            for row in rows
        ),
    }
    if any(
        type(recorded.get(key)) is not int or recorded[key] != value
        for key, value in counts.items()
    ):
        raise ReceiptVerificationError(failed)
    for used, allowance in (
        ("batch_archive_bytes_reserved", triage.MAX_BATCH_ARCHIVE_BYTES),
        ("batch_declared_uncompressed_bytes_reserved", triage.MAX_BATCH_UNCOMPRESSED_BYTES),
    ):
        value = recorded.get(used)
        if type(value) is not int or not 0 <= value <= allowance:
            raise ReceiptVerificationError(failed)


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
            parse_int=_bounded_json_int,
            parse_float=_bounded_json_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReceiptVerificationError("receipt must be valid UTF-8 JSON") from exc
    if (
        type(recorded) is not dict
        or type(recorded.get("schema_version")) is not int
        or recorded["schema_version"] != 3
    ):
        raise ReceiptVerificationError("expected schema-v3 triage receipt")
    # Malformed receipt rosters must not trigger up to a gigabyte of ZIP I/O.
    _preflight_receipt_roster(recorded, assignments)
    _preflight_candidate_source_claims(recorded)
    _preflight_receipt_claims(recorded)
    try:
        recorded_canonical = json.dumps(
            recorded, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
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
    # An invalid, missing or budget-skipped candidate has no successfully
    # verified source-byte digest in the original triage receipt. Two different
    # bad archives can produce an identical diagnostic. Replaying that text
    # must not masquerade as verifying continuity of the candidate's bytes.
    unverified_indexes = [
        row["candidate_index"] for row in replayed["candidates"]
        if not row["structural_preflight_succeeded"]
    ]
    full_replay = not unverified_indexes
    return {
        "schema_version": 1,
        "status": (
            "triage_receipt_replayed_not_historically_authenticated"
            if full_replay else
            "triage_receipt_diagnostics_replayed_with_unverified_candidate_sources"
        ),
        "recorded_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate_count": len(assignments),
        "diagnostic_inventory_replayed": True,
        "full_recorded_inventory_replayed": full_replay,
        "unverified_candidate_indexes": unverified_indexes,
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
    # Preserve the replayed negative observations for diagnosis, but do not
    # signal successful source continuity when those sources were not hashed.
    return 0 if result["full_recorded_inventory_replayed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
