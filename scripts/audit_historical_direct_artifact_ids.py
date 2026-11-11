"""Read-only, double-observation audit of VERA's two original Actions artifact IDs.

This alternate lookup supplements run-scoped artifact listings. A 404 is an
access observation, never proof that an original ZIP or offline backup vanished.
A listed ID is metadata only: no ZIP is downloaded or evidence authenticated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts import audit_historical_artifact_job_logs as logs
from scripts import audit_historical_workflow_artifacts as inventory

REPOSITORY = inventory.REPOSITORY
API_BASE = inventory.API_BASE
MAX_METADATA_BYTES = 64 * 1024
MAX_METADATA_INTEGER_DIGITS = 20
# Same-provider upload pins, not independent source/report custody fingerprints.
ORIGINAL_PINS = (logs.ORIGINAL, logs.RECOVERED)
RUN_SOURCES = {role: (run_id, sha) for role, run_id, _, sha, _, _ in inventory.HISTORICAL_RUNS}
# Pinned GitHub Actions run_started_at/updated_at observed for the original
# workflow attempts. Same-provider chronology, NOT independent archive custody.
# A direct-ID ZIP cannot have been created outside its own historical run.
RUN_CREATION_WINDOWS_UTC = {
    "original_treatment": ("2026-09-11T16:15:15Z", "2026-09-11T17:22:43Z"),
    "evaluator_recovery": ("2026-09-13T21:20:32Z", "2026-09-13T21:21:40Z"),
}


class DirectArtifactAuditError(ValueError):
    """A lookup could not support a stable, correctly attributed observation."""


class _RejectMetadataRedirects(HTTPRedirectHandler):
    """Never follow a redirect whose final 404 could masquerade as an origin 404."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DirectArtifactAuditError("GitHub artifact metadata endpoint redirected")


def _open_direct_metadata(request: Request, *, timeout: int):
    """Request the pinned metadata endpoint without following HTTP redirects."""
    return build_opener(_RejectMetadataRedirects()).open(request, timeout=timeout)


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DirectArtifactAuditError(f"duplicate GitHub metadata key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str):
    raise DirectArtifactAuditError(f"non-finite GitHub metadata number: {value}")


def _bounded_metadata_integer(token: str) -> int:
    """Reject oversized integer literals before Python converts them."""
    if len(token.lstrip("-")) > MAX_METADATA_INTEGER_DIGITS:
        raise DirectArtifactAuditError("GitHub metadata integer exceeds digit limit")
    return int(token)


def _reject_metadata_float(token: str):
    """Pinned GitHub artifact metadata does not use float-valued fields."""
    raise DirectArtifactAuditError("GitHub metadata floating-point token is invalid")


def fetch_direct_metadata(artifact_id: int) -> dict | None:
    """Fetch only the two pinned JSON metadata endpoints, without downloading ZIPs.

    Only an actual HTTP 404 is represented as None. Rate limits, permissions,
    transport failures, invalid JSON and redirects fail closed.
    """
    if type(artifact_id) is not int or artifact_id not in {
        pin["artifact_id"] for pin in ORIGINAL_PINS
    }:
        raise DirectArtifactAuditError("unrecognized historical artifact ID")
    url = f"{API_BASE}/repos/{REPOSITORY}/actions/artifacts/{artifact_id}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "VERA-historical-direct-artifact-audit",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with _open_direct_metadata(Request(url, headers=headers), timeout=15) as response:
            if response.geturl() != url:
                raise DirectArtifactAuditError("GitHub artifact metadata endpoint redirected")
            raw = response.read(MAX_METADATA_BYTES + 1)
    except HTTPError as exc:
        # Defense in depth: never classify a 404 from another URL as the
        # original historical GitHub artifact endpoint's own 404.
        if exc.geturl() != url:
            raise DirectArtifactAuditError(
                "GitHub artifact metadata endpoint redirected"
            ) from exc
        if exc.code == 404:
            return None
        raise DirectArtifactAuditError(
            f"GitHub artifact metadata request failed: HTTP {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DirectArtifactAuditError(
            f"GitHub artifact metadata request failed: {type(exc).__name__}"
        ) from exc
    if len(raw) > MAX_METADATA_BYTES:
        raise DirectArtifactAuditError("GitHub artifact metadata response is oversized")
    try:
        parsed = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_keys,
            parse_constant=_reject_nonfinite,
            parse_int=_bounded_metadata_integer,
            parse_float=_reject_metadata_float,
        )
    except DirectArtifactAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise DirectArtifactAuditError("GitHub artifact metadata is not bounded UTF-8 JSON") from exc
    if type(parsed) is not dict:
        raise DirectArtifactAuditError("GitHub artifact metadata must be an object")
    return parsed


def _validate_metadata(value: object, pin: dict) -> tuple:
    """Require pinned original upload identity and self-consistent source fields."""
    if type(value) is not dict:
        raise DirectArtifactAuditError("direct-ID metadata must be a JSON object")
    role = pin["role"]
    run_id, sha = RUN_SOURCES[role]
    artifact_id = pin["artifact_id"]
    exact_url = f"{API_BASE}/repos/{REPOSITORY}/actions/artifacts/{artifact_id}"
    archive_url = exact_url + "/zip"
    if (
        type(value.get("id")) is not int or value["id"] != artifact_id
        or value.get("name") != pin["artifact_name"]
        or type(value.get("size_in_bytes")) is not int
        or value["size_in_bytes"] != pin["size_bytes"]
        or type(value.get("expired")) is not bool
        or value.get("url") != exact_url
        or value.get("archive_download_url") != archive_url
    ):
        raise DirectArtifactAuditError(f"{role}: direct-ID upload identity/size differs")
    digest = value.get("digest")
    if digest is not None and (
        type(digest) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        or digest != "sha256:" + pin["zip_sha256"]
    ):
        raise DirectArtifactAuditError(f"{role}: direct-ID ZIP digest differs or is invalid")
    source = value.get("workflow_run")
    if type(source) is not dict or (
        type(source.get("id")) is not int or source["id"] != run_id
        or source.get("head_sha") != sha
        or source.get("head_branch") != inventory.HISTORICAL_BRANCH
        or type(source.get("repository_id")) is not int
        or source["repository_id"] != inventory.HISTORICAL_REPOSITORY_ID
        or type(source.get("head_repository_id")) is not int
        or source["head_repository_id"] != inventory.HISTORICAL_REPOSITORY_ID
    ):
        raise DirectArtifactAuditError(f"{role}: workflow attribution differs")
    try:
        created = inventory._parse_utc_timestamp(value.get("created_at"), label="creation")
        updated = inventory._parse_utc_timestamp(value.get("updated_at"), label="update")
        expires = inventory._parse_utc_timestamp(value.get("expires_at"), label="expiry")
    except inventory.ArtifactInventoryError as exc:
        raise DirectArtifactAuditError(f"{role}: invalid artifact timestamps: {exc}") from exc
    if not created <= updated or not created < expires:
        raise DirectArtifactAuditError(f"{role}: artifact lifecycle timestamps disagree")
    # The run-scoped inventory already enforces this original-run chronology.
    # Apply the same source-bound interval to the alternate direct-ID path:
    # otherwise a correctly named/hashed ZIP with an impossible creation date
    # could be accepted as historical GitHub upload metadata.
    earliest, latest = (
        inventory._parse_utc_timestamp(stamp, label=f"{role} pinned run boundary")
        for stamp in RUN_CREATION_WINDOWS_UTC[role]
    )
    if not earliest <= created <= latest:
        raise DirectArtifactAuditError(
            f"{role}: artifact creation outside pinned original workflow window"
        )
    # Ignore only volatile fields (e.g. download_count). Reconcile every field
    # material to original ZIP attribution, including explicit missing digest.
    return (
        artifact_id, pin["artifact_name"], pin["size_bytes"], digest,
        value["expired"], created, updated, expires, run_id, sha,
        value["url"], value["archive_download_url"],
    )


def audit_direct_artifact_ids(
    *, fetch_artifact: Callable[[int], dict | None] = fetch_direct_metadata,
    checked_at: datetime | None = None,
) -> dict:
    """Two read-only observations per pinned ID; fail on any access inconsistency."""
    if checked_at is None:
        checked_at = datetime.now(timezone.utc)
    if (
        not isinstance(checked_at, datetime)
        or checked_at.tzinfo is None
        or checked_at.utcoffset() is None
    ):
        raise DirectArtifactAuditError("checked_at must be timezone-aware")
    checked_at = checked_at.astimezone(timezone.utc)
    # The run's updated_at timestamp has only whole-second precision, while
    # upload-artifact log events can occur later within its final second.
    # An observation dated before both historical uploads were complete cannot
    # establish *post-collection* artifact accessibility. Reject it before
    # making either network request, including when both endpoints give 404.
    latest_run_end = max(
        inventory._parse_utc_timestamp(end, label=f"{role} original run end")
        for role, (_start, end) in RUN_CREATION_WINDOWS_UTC.items()
    )
    if checked_at < latest_run_end + timedelta(seconds=1):
        raise DirectArtifactAuditError(
            "observation time predates completion of historical evidence uploads"
        )
    results = {}
    for pin in ORIGINAL_PINS:
        first = fetch_artifact(pin["artifact_id"])
        first_identity = None if first is None else _validate_metadata(first, pin)
        second = fetch_artifact(pin["artifact_id"])
        second_identity = None if second is None else _validate_metadata(second, pin)
        if first_identity != second_identity:
            raise DirectArtifactAuditError(
                f"{pin['role']}: direct-ID metadata changed between observations"
            )
        if first_identity is None:
            status = "http_404_at_both_observations_not_proof_of_destruction"
        elif first_identity[4]:
            status = "original_upload_metadata_listed_expired_not_download_verified"
        elif first_identity[7] <= checked_at:
            status = "original_upload_metadata_listed_elapsed_expiry_not_download_verified"
        else:
            status = "original_upload_metadata_listed_not_download_verified"
        results[pin["role"]] = {
            "historical_run_id": pin["run_id"],
            "artifact_id": pin["artifact_id"],
            "status": status,
            "two_matching_metadata_observations": True,
            "github_upload_log_id_size_concordance": first_identity is not None,
            "github_upload_log_zip_digest_concordance": (
                first_identity is not None and first_identity[3] is not None
            ),
        }
    return {
        "schema_version": 1,
        "checked_at_utc": checked_at.isoformat(),
        "repository": REPOSITORY,
        "status": "direct_id_metadata_observation_not_original_custody",
        "historical_artifacts": results,
        "historical_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "experimental_treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_generated": False,
        "interpretation": (
            "Two direct-ID GitHub metadata lookups per historical artifact; 404 "
            "can reflect deletion, expiration or access limits, not absence of "
            "authorized offline backups. Listed metadata is not a ZIP download "
            "or independent authentication of original traces/reports. "
            "Run-scoped inventory, offline recovered-ZIP preflight, and "
            "independent source custody gates remain necessary."
        ),
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        result = audit_direct_artifact_ids()
    except (DirectArtifactAuditError, OSError) as exc:
        raise SystemExit(f"VERA HISTORICAL DIRECT ARTIFACT AUDIT: FAIL: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
