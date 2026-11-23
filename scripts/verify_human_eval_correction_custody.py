"""Audit whole-file blinded human-rating corrections against a verified freeze.

This is a coordinator-side custody check, not an exclusion decision or proof
that a correction was made before unblinding. It never opens the blinding key
or evaluates the direction of any rating change.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import stat
import unicodedata
from pathlib import Path

from scripts import build_human_eval_packet as capture
from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as freeze_verifier

MAX_LEDGER_BYTES = 64 * 1024
MAX_CHAINS = 64
MAX_VERSIONS = 16
MAX_ROWS_PER_FILE = 4096
# Cap the cumulative burden of retained whole-submission corrections. The
# shared safe file-capture helper has its own larger per-read ceiling; these
# stricter budgets prevent a bounded ledger from requiring enormous replay.
MAX_VERSION_BYTES = 4 * 1024 * 1024
MAX_TOTAL_VERSION_BYTES = 64 * 1024 * 1024
SAFE_FILE = re.compile(r"r(?P<series>[0-9]{3})_v(?P<revision>[0-9]{3})\.csv\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
REASONS = frozenset({
    "clerical_transcription",
    "missing_row_completion",
    "file_format_correction",
    "other_predeclared_validity_correction",
})


def _unique_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("correction ledger contains duplicate JSON keys")
        result[name] = value
    return result


def _load_json(path: Path, *, limit: int, label: str,
               expected_sha256: str | None = None,
               captured_sha256_out: list[str] | None = None) -> dict:
    raw = capture._read_regular_file_captured(
        path, label=label, max_bytes=limit)
    if len(raw) > limit:
        raise ValueError(f"{label} exceeds size bound")
    captured_digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and captured_digest != expected_sha256:
        raise ValueError(f"{label} differs from independently verified manifest bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda token: (_ for _ in ()).throw(
                               ValueError("nonfinite JSON value")))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    if captured_sha256_out is not None:
        captured_sha256_out.append(captured_digest)
    return value


def _canonical_id(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _file_annotator_and_blind_ids(raw: bytes) -> tuple[str, dict[str, tuple[str, ...]]]:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""),
                                strict=True)
        if reader.fieldnames != list(freeze.RATING_FIELDS):
            raise ValueError("correction CSV header differs from frozen rating schema")
        annotators = set()
        blinded_rows: dict[str, tuple[str, ...]] = {}
        n = 0
        for row in reader:
            n += 1
            if n > MAX_ROWS_PER_FILE or None in row or any(
                value is None for value in row.values()
            ):
                raise ValueError("correction CSV has malformed or excessive rows")
            annotators.add(_canonical_id(row["annotator_id"]))
            blind_id = row["blind_id"]
            if not blind_id.strip():
                raise ValueError("correction version contains a blank blinded report ID")
            if blind_id in blinded_rows:
                raise ValueError("correction version contains a duplicate blinded report ID")
            # Compare submitted fields, never score direction or treatment IDs.
            blinded_rows[blind_id] = tuple(
                row[field] for field in (*freeze.SCORE_FIELDS, "notes")
            )
            if len(annotators) > 1:
                raise ValueError("one correction version contains multiple annotators")
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("correction version is not a readable ratings CSV") from exc
    if n == 0 or not next(iter(annotators)):
        raise ValueError("correction version has no annotator rows")
    return next(iter(annotators)), blinded_rows


def _submissions_directory_state(root: Path) -> tuple[int, ...]:
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("correction submissions root must be a non-symlink directory")
    return capture._stat_contract(metadata)


def _verify_submissions_inventory(root: Path, expected: dict[str, tuple[int, ...]],
                                  initial_state: tuple[int, ...]) -> None:
    """Reject omitted visible files without reading any undeclared submission."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(root, flags)
    try:
        if capture._stat_contract(os.fstat(descriptor)) != initial_state:
            raise ValueError("correction submissions directory changed during audit")
        observed: set[str] = set()
        # Stop on the first undeclared entry, so enumeration is bounded by the
        # already validated ledger size (at most MAX_CHAINS * MAX_VERSIONS).
        with os.scandir(descriptor) as entries:
            for entry in entries:
                if entry.name not in expected or entry.name in observed:
                    raise ValueError("correction submissions contain an unlisted entry")
                metadata = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise ValueError("correction inventory requires single-link regular files")
                # Directory mtime does not change for an in-place file edit.
                # Bind the final visible file to the exact captured generation.
                if capture._stat_contract(metadata) != expected[entry.name]:
                    raise ValueError("correction version changed after capture")
                observed.add(entry.name)
        if (
            capture._stat_contract(os.fstat(descriptor)) != initial_state
            or _submissions_directory_state(root) != initial_state
        ):
            raise ValueError("correction submissions directory changed during audit")
        if observed != set(expected):
            raise ValueError("correction submissions inventory lacks a ledger entry")
    finally:
        os.close(descriptor)


def audit_corrections(*, ledger: Path, submissions_root: Path,
                      freeze_root: Path) -> dict:
    """Validate preserved whole-file revisions without comparing scores."""
    # Require the existing independent verifier before trusting freeze metadata.
    freeze_receipt = freeze_verifier.verify_frozen_snapshot(
        freeze_root=Path(freeze_root), use_retained_inputs=True,
        include_verified_manifest_sha256=True)
    verified_manifest_sha = (
        freeze_receipt.get("verified_manifest_sha256")
        if type(freeze_receipt) is dict else None
    )
    if type(verified_manifest_sha) is not str or not HASH.fullmatch(verified_manifest_sha):
        raise ValueError("independent freeze verifier did not bind manifest fingerprint")
    manifest = _load_json(Path(freeze_root) / "freeze_manifest.json",
                          limit=1024 * 1024, label="verified freeze manifest",
                          expected_sha256=verified_manifest_sha)
    if manifest.get("study_id") != "budget-main-v1" or type(
        manifest.get("rating_inputs")) is not list:
        raise ValueError("verified freeze lacks rated input inventory")
    frozen_hashes = [
        item.get("sha256") for item in manifest["rating_inputs"]
        if type(item) is dict
    ]
    if len(frozen_hashes) != len(manifest["rating_inputs"]) or any(
        type(h) is not str or not HASH.fullmatch(h) for h in frozen_hashes
    ) or len(frozen_hashes) != len(set(frozen_hashes)):
        raise ValueError("verified freeze input hashes are invalid")

    # Bind the receipt to the SAME captured ledger bytes that were parsed and
    # validated; rereading the pathname later would permit a TOCTOU mismatch.
    ledger_digest_capture: list[str] = []
    data = _load_json(Path(ledger), limit=MAX_LEDGER_BYTES,
                      label="blinded correction ledger",
                      captured_sha256_out=ledger_digest_capture)
    if set(data) != {"schema_version", "study_id", "phase", "chains"} or (
        type(data["schema_version"]) is not int or data["schema_version"] != 1
        or data["study_id"] != "budget-main-v1"
        or data["phase"] != "before_unblinding"
    ):
        raise ValueError("correction ledger schema or blinded phase is invalid")
    chains = data["chains"]
    if type(chains) is not list or not 1 <= len(chains) <= MAX_CHAINS:
        raise ValueError("correction ledger must contain bounded nonempty chains")

    seen_annotators: set[str] = set()
    seen_files: set[str] = set()
    captured_versions: dict[str, tuple[int, ...]] = {}
    seen_hashes: set[str] = set()
    accepted_hashes: set[str] = set()
    total_version_bytes = 0
    submissions_root = Path(submissions_root)
    initial_directory_state = _submissions_directory_state(submissions_root)
    for chain in chains:
        if type(chain) is not dict or set(chain) != {
            "annotator_id", "reason", "versions"
        }:
            raise ValueError("correction chain schema mismatch")
        aid = chain["annotator_id"]
        if type(aid) is not str or not aid or len(aid) > 64:
            raise ValueError("invalid correction annotator pseudonym")
        canonical = _canonical_id(aid)
        if canonical in seen_annotators:
            raise ValueError("duplicate or canonically equivalent correction annotator")
        seen_annotators.add(canonical)
        if chain["reason"] not in REASONS:
            raise ValueError("correction needs an allowed, pre-unblinding reason code")
        versions = chain["versions"]
        previous_blind_ids: frozenset[str] | None = None
        previous_blinded_rows: dict[str, tuple[str, ...]] | None = None
        chain_series: str | None = None
        if type(versions) is not list or not 2 <= len(versions) <= MAX_VERSIONS:
            raise ValueError("corrections require original and entire replacement file")
        for version_index, version in enumerate(versions, start=1):
            if type(version) is not dict or set(version) != {
                "file", "sha256"
            }:
                raise ValueError("correction version schema mismatch")
            filename, expected = version["file"], version["sha256"]
            matched_file = SAFE_FILE.fullmatch(filename) if type(filename) is str else None
            if matched_file is None:
                raise ValueError("correction files require neutral basename-only names")
            # The neutral filename sequence is a custody convention, not an
            # independent timestamp. It must agree with the ledger's asserted
            # original -> replacement order, and stay in one rNNN series.
            if chain_series is None:
                chain_series = matched_file["series"]
            elif matched_file["series"] != chain_series:
                raise ValueError("correction chain mixes unrelated filename series")
            if int(matched_file["revision"]) != version_index:
                raise ValueError(
                    "correction filename revision disagrees with ledger order "
                    "(expected contiguous v001, v002, ...)"
                )
            if type(expected) is not str or not HASH.fullmatch(expected):
                raise ValueError("correction version needs lowercase SHA-256")
            if filename in seen_files or expected in seen_hashes:
                raise ValueError("correction revisions cannot reuse files or bytes")
            seen_files.add(filename)
            seen_hashes.add(expected)
            # Enforce the tighter of the per-version and remaining aggregate
            # budgets on the securely opened file *before* its bytes are read.
            # Post-capture checks below remain a defense in depth.
            remaining_bytes = MAX_TOTAL_VERSION_BYTES - total_version_bytes
            if remaining_bytes < 0:
                raise ValueError("retained correction versions exceed total byte budget")
            captured_state: list[tuple[int, ...]] = []
            try:
                raw = capture._read_regular_file_captured(
                    Path(submissions_root) / filename,
                    label="blinded correction version",
                    max_bytes=min(MAX_VERSION_BYTES, remaining_bytes),
                    stat_contract_out=captured_state,
                )
            except ValueError as exc:
                if "exceeds requested capture byte limit" not in str(exc):
                    raise
                if MAX_VERSION_BYTES <= remaining_bytes:
                    raise ValueError(
                        "correction version exceeds per-file byte budget") from exc
                raise ValueError(
                    "retained correction versions exceed total byte budget") from exc
            if len(captured_state) != 1:
                raise ValueError("correction capture did not bind file generation")
            captured_versions[filename] = captured_state[0]
            if len(raw) > MAX_VERSION_BYTES:
                raise ValueError("correction version exceeds per-file byte budget")
            total_version_bytes += len(raw)
            if total_version_bytes > MAX_TOTAL_VERSION_BYTES:
                raise ValueError("retained correction versions exceed total byte budget")
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("retained correction version digest mismatch")
            version_annotator, blinded_rows = _file_annotator_and_blind_ids(raw)
            blind_ids = frozenset(blinded_rows)
            if version_annotator != canonical:
                raise ValueError("correction version changed annotator identity")
            # Whole-submission corrections must not silently swap or drop
            # assigned reports. Missing-row completion must add report IDs
            # without rewriting any previously submitted rating or note.
            # Format-only corrections must preserve all parsed ratings/notes;
            # transcription and predeclared-validity corrections can change
            # them only under separately retained blinded approval evidence.
            if previous_blind_ids is not None:
                if chain["reason"] == "missing_row_completion":
                    if not previous_blind_ids.issubset(blind_ids):
                        raise ValueError(
                            "missing-row correction removed a submitted blinded report"
                        )
                    if blind_ids == previous_blind_ids:
                        raise ValueError(
                            "missing-row correction did not add a blinded report"
                        )
                    if previous_blinded_rows is None or any(
                        blinded_rows[report_id] != previous_blinded_rows[report_id]
                        for report_id in previous_blind_ids
                    ):
                        raise ValueError(
                            "missing-row correction changed a previously submitted "
                            "report rating or note"
                        )
                elif blind_ids != previous_blind_ids:
                    raise ValueError(
                        "correction changed blinded report coverage without "
                        "a missing-row completion reason"
                    )
                elif chain["reason"] == "file_format_correction" and (
                    previous_blinded_rows is None
                    or blinded_rows != previous_blinded_rows
                ):
                    raise ValueError(
                        "file-format correction changed a previously submitted "
                        "report rating or note"
                    )
            previous_blind_ids = blind_ids
            previous_blinded_rows = blinded_rows
            if version_index == len(versions):
                if expected not in frozen_hashes:
                    raise ValueError("final correction is absent from verified freeze")
                accepted_hashes.add(expected)
            elif expected in frozen_hashes:
                raise ValueError("superseded correction was included in verified freeze")

    _verify_submissions_inventory(submissions_root, captured_versions, initial_directory_state)
    if len(accepted_hashes) != len(chains):
        raise ValueError("corrected annotators must have distinct final submissions")
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "blinded_whole_submission_corrections_consistent",
        "n_corrected_annotators": len(chains),
        "n_retained_versions": len(seen_files),
        "n_accepted_versions_bound_to_verified_freeze": len(accepted_hashes),
        "verified_freeze_manifest_sha256": verified_manifest_sha,
        "captured_correction_ledger_sha256": ledger_digest_capture[0],
        "historical_timing_independently_authenticated": False,
        "blinding_key_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--submissions-root", type=Path, required=True)
    parser.add_argument("--freeze-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_corrections(
            ledger=args.ledger, submissions_root=args.submissions_root,
            freeze_root=args.freeze_root)
    except (OSError, ValueError, TypeError) as exc:
        raise SystemExit(f"HUMAN CORRECTION CUSTODY: FAIL: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
