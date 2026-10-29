"""Reverify a retained canonical-analysis preservation bundle offline.

The three inputs are the raw historical ZIP, metadata captured while the
original artifact existed, and the original verification receipt. This mode
is valid after the GitHub source artifact expires, but must NEVER be used to
claim that the original artifact remains downloadable or that original
treatment evidence has been independently authenticated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from scripts import verify_retained_canonical_download as source

MAX_PRESERVED_RECEIPT_BYTES = 256 * 1024


def _canonical_json(value: object) -> str:
    """Compare JSON types exactly (not Python's 1 == True shortcut)."""
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    )


def verify_preserved_bundle(
    metadata_path: Path,
    archive_path: Path,
    receipt_path: Path,
    *,
    root: Path = source.concordance.ROOT,
    checked_at: datetime | None = None,
) -> dict:
    """Fail closed if retained inputs and the saved receipt disagree."""
    if checked_at is None:
        checked_at = datetime.now(timezone.utc)

    raw_receipt = source._read_regular(
        Path(receipt_path), MAX_PRESERVED_RECEIPT_BYTES,
        "preserved verification receipt",
    )
    try:
        stored = json.loads(
            raw_receipt.decode("utf-8"),
            object_pairs_hook=source._unique_object,
            parse_constant=source._reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("preserved receipt must be valid UTF-8 JSON") from exc
    source._require(type(stored) is dict, "preserved receipt must be a JSON object")

    # The captured metadata's expired=false field is a *historical* API
    # observation. All immutable identity, digest, and scientific concordance
    # gates remain mandatory. Only the current-clock expiry gate is omitted.
    replay = source.verify_download(
        Path(metadata_path),
        Path(archive_path),
        root=Path(root),
        checked_at=checked_at,
        require_source_unexpired=False,
    )
    source._require(
        _canonical_json(stored) == _canonical_json(replay),
        "preserved verification receipt differs from recomputed source audit",
    )

    expiry = source._utc_expiry(replay["source_artifact_expires_at"].replace("+00:00", "Z"))
    rechecked = checked_at.astimezone(timezone.utc)  # verified by source.verify_download
    return {
        "schema_version": 1,
        "status": "offline_preserved_canonical_bundle_reverified_not_independent_custody",
        "reverified_at_utc": rechecked.isoformat(),
        "source_expiry_time_passed_at_reverification": expiry <= rechecked,
        "original_github_source_availability_checked": False,
        "original_source_artifact_id": replay["source_artifact_id"],
        "source_artifact_expires_at": replay["source_artifact_expires_at"],
        "archive_sha256_observed_now": replay["archive_sha256_observed_now"],
        "saved_verification_receipt_sha256_observed_now": hashlib.sha256(
            raw_receipt
        ).hexdigest(),
        "source_provider_metadata_and_archive_reverified": True,
        "saved_receipt_exactly_recomputed": True,
        "original_treatment_traces_authenticated": False,
        "independent_historical_custody_authenticated": False,
        "human_evaluation_ready": False,
        "treatments_or_evaluators_rerun": False,
        "human_ratings_generated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path, help="captured original GitHub metadata JSON")
    parser.add_argument("archive", type=Path, help="raw retained canonical ZIP")
    parser.add_argument("receipt", type=Path, help="original verification receipt JSON")
    parser.add_argument("--root", type=Path, default=source.concordance.ROOT)
    parser.add_argument("--receipt-out", type=Path, help="create-only offline replay receipt")
    args = parser.parse_args()
    try:
        report = verify_preserved_bundle(
            args.metadata, args.archive, args.receipt, root=args.root,
        )
        rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.receipt_out is not None:
            with args.receipt_out.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        else:
            print(rendered, end="")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"PRESERVED CANONICAL BUNDLE: FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
