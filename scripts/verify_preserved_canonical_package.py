"""Safely inspect and replay an entire retained VERA Actions preservation ZIP.

The outer Actions upload is itself a ZIP. Verify its exact member inventory
before extracting even to a private temporary directory, then replay both
the original source audit and (when present) its saved offline audit. This
does not authenticate the historical treatments, GitHub custody, or time.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

from scripts import preflight_recovered_artifact_zip as preflight
from scripts import verify_preserved_canonical_bundle as preserved
from scripts import verify_retained_canonical_download as source

MAX_PACKAGE_BYTES = 2 * 1024 * 1024
METADATA = "canonical-source-metadata.json"
INNER_ZIP = "retained-canonical.zip"
ORIGINAL_RECEIPT = "retained-canonical-verification.json"
OFFLINE_RECEIPT = "retained-canonical-offline-reverification.json"
CORE_FILES = frozenset((METADATA, INNER_ZIP, ORIGINAL_RECEIPT))
ALLOWED_SIZES = {
    METADATA: source.MAX_METADATA_BYTES,
    INNER_ZIP: source.OBSERVED_ZIP_BYTES,
    ORIGINAL_RECEIPT: preserved.MAX_PRESERVED_RECEIPT_BYTES,
    OFFLINE_RECEIPT: preserved.MAX_PRESERVED_RECEIPT_BYTES,
}


def _strict_json(raw: bytes, label: str) -> dict:
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=source._unique_object,
            parse_constant=source._reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    source._require(type(data) is dict, f"{label} must be a JSON object")
    return data


def _saved_replay_time(saved: dict) -> datetime:
    value = saved.get("reverified_at_utc")
    source._require(type(value) is str and value.endswith("+00:00"),
                    "saved offline replay time must be explicit UTC")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("saved offline replay time is malformed") from exc
    source._require(
        instant.tzinfo is not None
        and instant.utcoffset() == timedelta(0)
        and instant.isoformat() == value,
        "saved offline replay time must use canonical UTC ISO format",
    )
    # A saved time is not itself independently attested. It is used solely to
    # reproduce the previously recorded clock-dependent field exactly.
    return instant


def verify_package(
    package_path: Path,
    *,
    root: Path = source.concordance.ROOT,
    expected_package_sha256: str | None = None,
) -> dict:
    """Audit both ZIP layers and every retained receipt, without unpacking paths."""
    path = Path(package_path)
    outer = source._read_regular(path, MAX_PACKAGE_BYTES, "preservation package ZIP")
    source._require(bool(outer), "preservation package ZIP is empty")
    observed = hashlib.sha256(outer).hexdigest()
    if expected_package_sha256 is not None:
        source._require(
            type(expected_package_sha256) is str
            and preflight.HEX_SHA256.fullmatch(expected_package_sha256) is not None,
            "expected package SHA-256 must be lowercase 64-hex",
        )
        source._require(
            observed == expected_package_sha256,
            "preservation package differs from caller-supplied ZIP SHA-256",
        )

    # Reuse the fail-closed central-directory/local-header/CRC/ZIP-bomb audit,
    # not Python's permissive ZIP parser as the first line of inspection.
    inspected = preflight.audit_recovered_zip(path)
    source._require(
        observed == inspected["archive_sha256_observed_now"],
        "preservation package changed during ZIP preflight",
    )
    files = inspected["files"]
    names = {entry["path"] for entry in files}
    source._require(
        names in (CORE_FILES, CORE_FILES | {OFFLINE_RECEIPT})
        and len(files) == len(names),
        "preservation package has missing, additional or duplicate members",
    )
    for item in files:
        source._require(
            0 < item["uncompressed_bytes"] <= ALLOWED_SIZES[item["path"]],
            f"preservation member outside byte limit: {item['path']}",
        )

    # Reopen the already hashed bytes, never a filesystem path supplied by
    # an archive member. No extraction to the operator's working tree occurs.
    content = {}
    try:
        with zipfile.ZipFile(io.BytesIO(outer)) as archive:
            source._require(
                len(archive.infolist()) == len(files),
                "preservation ZIP contains unexpected directory entries",
            )
            for item in files:
                data = archive.read(item["path"])
                source._require(
                    len(data) == item["uncompressed_bytes"]
                    and hashlib.sha256(data).hexdigest() == item["sha256"],
                    f"preservation member changed during capture: {item['path']}",
                )
                content[item["path"]] = data
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as exc:
        raise ValueError("preservation ZIP changed during capture") from exc

    has_saved_offline = OFFLINE_RECEIPT in content
    saved = _strict_json(content[OFFLINE_RECEIPT], OFFLINE_RECEIPT) if has_saved_offline else None
    saved_time = _saved_replay_time(saved) if has_saved_offline else datetime.now(timezone.utc)

    # All paths are hard-coded single-component names already checked above.
    # Temporary files exist only because the existing audited source gate has
    # a file-path interface; they are private and removed on return/error.
    with tempfile.TemporaryDirectory(prefix="vera-canonical-preservation-") as tmp:
        root_tmp = Path(tmp)
        for name, data in content.items():
            with (root_tmp / name).open("xb") as handle:
                handle.write(data)
        verified = preserved.verify_preserved_bundle(
            root_tmp / METADATA, root_tmp / INNER_ZIP,
            root_tmp / ORIGINAL_RECEIPT, root=Path(root), checked_at=saved_time,
        )

    if has_saved_offline:
        source._require(
            preserved._canonical_json(saved) == preserved._canonical_json(verified),
            "saved offline replay receipt differs from exact recomputation",
        )

    now = datetime.now(timezone.utc)
    expiry = source._utc_expiry(
        verified["source_artifact_expires_at"].replace("+00:00", "Z")
    )
    return {
        "schema_version": 1,
        "status": "retained_actions_package_reverified_not_independent_custody",
        "package_sha256_observed_now": observed,
        "caller_supplied_package_sha256_matched": expected_package_sha256 is not None,
        "package_member_count": len(files),
        "package_member_sha256": {
            entry["path"]: entry["sha256"] for entry in sorted(files, key=lambda x: x["path"])
        },
        "original_source_receipt_recomputed": True,
        "saved_offline_receipt_included": has_saved_offline,
        "saved_offline_receipt_recomputed": has_saved_offline,
        "original_source_expiry_elapsed_now": expiry <= now,
        "original_source_availability_checked_now": False,
        "original_canonical_zip_sha256_observed_now": verified["archive_sha256_observed_now"],
        "historical_package_time_independently_attested": False,
        "independent_historical_custody_authenticated": False,
        "original_treatment_traces_authenticated": False,
        "human_evaluation_ready": False,
        "experimental_treatments_rerun": False,
        "human_ratings_generated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="outer raw GitHub Actions preservation ZIP")
    parser.add_argument("--root", type=Path, default=source.concordance.ROOT)
    parser.add_argument(
        "--expected-package-sha256",
        help="optional earlier recorded outer ZIP digest; provenance is not asserted",
    )
    parser.add_argument("--receipt-out", type=Path, help="create-only replay receipt")
    args = parser.parse_args()
    try:
        result = verify_package(
            args.package, root=args.root,
            expected_package_sha256=args.expected_package_sha256,
        )
        rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.receipt_out is None:
            print(rendered, end="")
        else:
            with args.receipt_out.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"RETAINED ACTIONS PACKAGE AUDIT: FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
