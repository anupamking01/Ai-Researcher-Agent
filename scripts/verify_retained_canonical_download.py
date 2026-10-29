"""Verify the actual retained GitHub canonical ZIP against the current checkout.

The GitHub API metadata and pinned ZIP digest are provider-observed, not
independent historical custody evidence. This is an offline gate after a
separate trusted downloader has retrieved the metadata JSON and raw ZIP.
No original treatment, evaluator, or human-evaluation job is executed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from scripts import verify_canonical_archive_checkout as concordance

REPO = "anupamking01/Ai-Researcher-Agent"
REPO_ID = 812439224
RUN_ID = 36070798723
RUN_HEAD = "06c6a9ab0b1d01257e8985fbb09c999cef115779"
ARTIFACT_ID = 10837878458
ARTIFACT_NAME = "canonical-main-study-analysis-36070798723"
OBSERVED_ZIP_BYTES = 10270
# Observed from the actual retained GitHub artifact on 2026-10-29, matching
# GitHub's artifact metadata. NOT an independent, pre-existing historical pin.
OBSERVED_ZIP_SHA256 = "226f009ba6b158b77fc98f4e56ec96e1943d1749bc818b0876e90f76077de4b5"
MAX_METADATA_BYTES = 64 * 1024


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate GitHub metadata JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"invalid GitHub metadata JSON number: {value}")


def _read_regular(path: Path, limit: int, label: str) -> bytes:
    _require(not path.is_symlink() and path.is_file(), f"{label} must be a regular file")
    _require(path.stat().st_size <= limit, f"{label} exceeds byte limit")
    raw = path.read_bytes()
    _require(len(raw) <= limit, f"{label} exceeds byte limit")
    return raw


def _utc_expiry(value: object) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"), "artifact expiry must be UTC")
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("artifact expiry timestamp is invalid") from exc
    _require(expiry.utcoffset().total_seconds() == 0, "artifact expiry must be UTC")
    return expiry


def verify_download(
    metadata_path: Path,
    archive_path: Path,
    *,
    root: Path = concordance.ROOT,
    checked_at: datetime | None = None,
) -> dict:
    """Fail closed on source identity, archive bytes, and actual checkout concordance."""
    if checked_at is None:
        checked_at = datetime.now(timezone.utc)
    _require(
        isinstance(checked_at, datetime) and checked_at.tzinfo is not None
        and checked_at.utcoffset() is not None,
        "checked_at must be timezone-aware",
    )
    checked_at = checked_at.astimezone(timezone.utc)
    try:
        metadata = json.loads(
            _read_regular(Path(metadata_path), MAX_METADATA_BYTES, "GitHub metadata").decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("GitHub metadata must be valid UTF-8 JSON") from exc
    _require(type(metadata) is dict, "GitHub metadata must be an object")
    source = metadata.get("workflow_run")
    _require(type(source) is dict, "artifact workflow source is missing")
    _require(type(metadata.get("id")) is int and metadata["id"] == ARTIFACT_ID,
             "artifact ID differs from pinned canonical artifact")
    _require(metadata.get("name") == ARTIFACT_NAME, "artifact name differs")
    _require(metadata.get("expired") is False, "artifact is reported expired")
    _require(
        metadata.get("archive_download_url")
        == f"https://api.github.com/repos/{REPO}/actions/artifacts/{ARTIFACT_ID}/zip",
        "artifact download URL differs from pinned repository endpoint",
    )
    _require(
        type(source.get("id")) is int and source["id"] == RUN_ID
        and source.get("head_sha") == RUN_HEAD
        and source.get("head_branch") == "research-paper-eval-2027"
        and type(source.get("repository_id")) is int
        and source["repository_id"] == REPO_ID
        and type(source.get("head_repository_id")) is int
        and source["head_repository_id"] == REPO_ID,
        "historical workflow identity differs from canonical run",
    )
    expiry = _utc_expiry(metadata.get("expires_at"))
    _require(expiry > checked_at, "artifact expiry has elapsed")
    _require(
        type(metadata.get("size_in_bytes")) is int
        and metadata["size_in_bytes"] == OBSERVED_ZIP_BYTES,
        "GitHub-reported archive byte size differs from observed canonical size",
    )
    _require(
        metadata.get("digest") == "sha256:" + OBSERVED_ZIP_SHA256,
        "GitHub-reported ZIP digest differs from published provider observation",
    )

    archive_path = Path(archive_path)
    archive = _read_regular(archive_path, OBSERVED_ZIP_BYTES, "retained archive")
    _require(len(archive) == OBSERVED_ZIP_BYTES, "retained archive size differs")
    observed_sha = hashlib.sha256(archive).hexdigest()
    _require(observed_sha == OBSERVED_ZIP_SHA256,
             "retained ZIP bytes differ from published provider observation")
    # Do not pass the provider-observed hash as an independent historical pin.
    verified = concordance.verify_archive_against_checkout(archive_path, root=Path(root))
    _require(
        verified.get("archive_sha256_observed_now") == observed_sha,
        "archive changed between source and concordance verification",
    )
    _require(
        verified.get("historical_evidence_authenticated") is False
        and verified.get("original_treatment_traces_authenticated") is False
        and verified.get("human_evaluation_ready") is False
        and verified.get("independently_supplied_archive_pin_matched") is False,
        "unexpected historical authentication or human-readiness claim",
    )
    return {
        "schema_version": 1,
        "status": "provider_observed_canonical_archive_concordance_verified_not_original_evidence",
        "repository": REPO,
        "canonical_run_id": RUN_ID,
        "historical_head_sha": RUN_HEAD,
        "source_artifact_id": ARTIFACT_ID,
        "source_artifact_name": ARTIFACT_NAME,
        "source_artifact_expires_at": expiry.isoformat(),
        "provider_reported_zip_sha256_matched": True,
        "published_provider_observed_zip_sha256_matched": True,
        "archive_sha256_observed_now": observed_sha,
        "independent_historical_custody_authenticated": False,
        "original_treatment_traces_authenticated": False,
        "human_evaluation_ready": False,
        "treatments_or_evaluators_rerun": False,
        "human_ratings_generated": False,
        "checkout_concordance": verified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path, help="GitHub Actions artifact metadata JSON")
    parser.add_argument("archive", type=Path, help="raw GitHub archive ZIP; do not extract")
    parser.add_argument("--root", type=Path, default=concordance.ROOT)
    parser.add_argument("--receipt-out", type=Path, help="create-only JSON receipt after PASS")
    args = parser.parse_args()
    try:
        result = verify_download(args.metadata, args.archive, root=args.root)
        rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.receipt_out:
            with args.receipt_out.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        else:
            print(rendered, end="")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"RETAINED CANONICAL ZIP AUDIT: FAIL: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
