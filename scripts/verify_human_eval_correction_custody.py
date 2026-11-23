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
import re
import unicodedata
from pathlib import Path

from scripts import build_human_eval_packet as capture
from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as freeze_verifier

MAX_LEDGER_BYTES = 64 * 1024
MAX_CHAINS = 64
MAX_VERSIONS = 16
MAX_ROWS_PER_FILE = 4096
SAFE_FILE = re.compile(r"r[0-9]{3}_v[0-9]{3}\.csv\Z")
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


def _load_json(path: Path, *, limit: int, label: str) -> dict:
    raw = capture._read_regular_file_captured(path, label=label)
    if len(raw) > limit:
        raise ValueError(f"{label} exceeds size bound")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda token: (_ for _ in ()).throw(
                               ValueError("nonfinite JSON value")))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    return value


def _canonical_id(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _file_annotator(raw: bytes) -> str:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""),
                                strict=True)
        if reader.fieldnames != list(freeze.RATING_FIELDS):
            raise ValueError("correction CSV header differs from frozen rating schema")
        annotators = set()
        n = 0
        for row in reader:
            n += 1
            if n > MAX_ROWS_PER_FILE or None in row or any(
                value is None for value in row.values()
            ):
                raise ValueError("correction CSV has malformed or excessive rows")
            annotators.add(_canonical_id(row["annotator_id"]))
            if len(annotators) > 1:
                raise ValueError("one correction version contains multiple annotators")
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("correction version is not a readable ratings CSV") from exc
    if n == 0 or not next(iter(annotators)):
        raise ValueError("correction version has no annotator rows")
    return next(iter(annotators))


def audit_corrections(*, ledger: Path, submissions_root: Path,
                      freeze_root: Path) -> dict:
    """Validate preserved whole-file revisions without comparing scores."""
    # Require the existing independent verifier before trusting freeze metadata.
    freeze_verifier.verify_frozen_snapshot(
        freeze_root=Path(freeze_root), use_retained_inputs=True)
    manifest = _load_json(Path(freeze_root) / "freeze_manifest.json",
                          limit=1024 * 1024, label="verified freeze manifest")
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

    data = _load_json(Path(ledger), limit=MAX_LEDGER_BYTES,
                      label="blinded correction ledger")
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
    seen_hashes: set[str] = set()
    accepted_hashes: set[str] = set()
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
        if type(versions) is not list or not 2 <= len(versions) <= MAX_VERSIONS:
            raise ValueError("corrections require original and entire replacement file")
        for version_index, version in enumerate(versions, start=1):
            if type(version) is not dict or set(version) != {
                "file", "sha256"
            }:
                raise ValueError("correction version schema mismatch")
            filename, expected = version["file"], version["sha256"]
            if type(filename) is not str or not SAFE_FILE.fullmatch(filename):
                raise ValueError("correction files require neutral basename-only names")
            if type(expected) is not str or not HASH.fullmatch(expected):
                raise ValueError("correction version needs lowercase SHA-256")
            if filename in seen_files or expected in seen_hashes:
                raise ValueError("correction revisions cannot reuse files or bytes")
            seen_files.add(filename)
            seen_hashes.add(expected)
            raw = capture._read_regular_file_captured(
                Path(submissions_root) / filename, label="blinded correction version")
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("retained correction version digest mismatch")
            if _file_annotator(raw) != canonical:
                raise ValueError("correction version changed annotator identity")
            if version_index == len(versions):
                if expected not in frozen_hashes:
                    raise ValueError("final correction is absent from verified freeze")
                accepted_hashes.add(expected)
            elif expected in frozen_hashes:
                raise ValueError("superseded correction was included in verified freeze")

    if len(accepted_hashes) != len(chains):
        raise ValueError("corrected annotators must have distinct final submissions")
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "blinded_whole_submission_corrections_consistent",
        "n_corrected_annotators": len(chains),
        "n_retained_versions": len(seen_files),
        "n_accepted_versions_bound_to_verified_freeze": len(accepted_hashes),
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
