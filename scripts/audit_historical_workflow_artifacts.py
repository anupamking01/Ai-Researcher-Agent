"""Read-only GitHub Actions artifact inventory for VERA's three historical runs.

This is an availability diagnostic, not retrieval of reports, a historical
custody proof, a treatment/evaluator rerun, or a human-evaluation result.
Only the exact historically named artifacts count as candidates.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable

from scripts import audit_historical_artifact_job_logs as historical_logs
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPOSITORY = "anupamking01/Ai-Researcher-Agent"
API_BASE = "https://api.github.com"
PAGE_SIZE = 100
MAX_PAGES = 20
MAX_RESPONSE_BYTES = 512 * 1024
MAX_API_JSON_DEPTH = 64
MAX_API_INTEGER_DIGITS = 20
# Immutable GitHub repository ID, captured from the original historical runs.
HISTORICAL_REPOSITORY_ID = 812439224
HISTORICAL_BRANCH = "research-paper-eval-2027"
# Anchors are from historical workflow metadata and version-controlled source,
# NOT newly generated fingerprints or independent archival attestations.
HISTORICAL_RUNS = (
    (
        "original_treatment",
        34620917346,
        "budget-main-study",
        "c3c15e46a8eec3a8bbc24c968eedc0548172a897",
        "failure",  # The common evaluator was interrupted; not a failed 40-run treatment claim.
        "budget-main-study-34620917346",
    ),
    (
        "evaluator_recovery",
        34783525480,
        "evaluator-recovery",
        "8733ce492abc74e7b2966ed22ce08d3fddec43ca",
        "success",
        "budget-main-study-recovered-34783525480",
    ),
    (
        "canonical_analysis",
        36070798723,
        "canonical-main-study-analysis",
        "06c6a9ab0b1d01257e8985fbb09c999cef115779",
        "success",
        "canonical-main-study-analysis-36070798723",
    ),
)

# Service-reported upload IDs, sizes, and ZIP digests taken from pinned
# contemporaneous GitHub job logs. These are NOT independent custody proofs.
HISTORICAL_UPLOAD_PINS = {
    "original_treatment": historical_logs.ORIGINAL,
    "evaluator_recovery": historical_logs.RECOVERED,
}

# Published provider-observed metadata retained in research-evidence/
# canonical-analysis-36070798723.metadata.json, distinct from the upload-log
# pins for original treatments. This is not an independently supplied custody
# fingerprint and cannot authenticate original treatment/report evidence.
CANONICAL_ARCHIVE_PIN = {
    "artifact_id": 10837878458,
    "size_bytes": 10270,
    "zip_sha256": "226f009ba6b158b77fc98f4e56ec96e1943d1749bc818b0876e90f76077de4b5",
}


class ArtifactInventoryError(ValueError):
    """A source or listing could not support an affirmative inventory claim."""


# These bytes were retained as the canonical GitHub-provider metadata JSON
# at the historical analysis checkout. The fixed SHA-256 checks local custody
# of that version-controlled record, not authenticity of the original study.
RETAINED_CANONICAL_METADATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "research-evidence/canonical-analysis-36070798723.metadata.json"
)
RETAINED_CANONICAL_METADATA_SHA256 = (
    "a980102216260faf66e4925bf09b5bcf2433d9dda43a74409480df4856e6a4c2"
)
MAX_RETAINED_CANONICAL_METADATA_BYTES = 16 * 1024


def _verify_retained_canonical_metadata_file() -> str:
    """Require the retained provider record's exact pinned bytes before API I/O.

    This rejects a missing, linked, oversized, or changed checkout record, even
    if GitHub no longer lists the canonical ZIP. It is not an external archive
    attestation and does not verify the original treatment/report provenance.
    """
    if not hasattr(os, "O_NOFOLLOW"):
        raise ArtifactInventoryError(
            "retained canonical metadata cannot be opened without following links"
        )
    flags = (
        os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        with os.fdopen(os.open(RETAINED_CANONICAL_METADATA_PATH, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_size > MAX_RETAINED_CANONICAL_METADATA_BYTES
            ):
                raise ArtifactInventoryError(
                    "retained canonical metadata is not a bounded regular file"
                )
            captured = stream.read(MAX_RETAINED_CANONICAL_METADATA_BYTES + 1)
            after = os.fstat(stream.fileno())
    except OSError as exc:
        raise ArtifactInventoryError(
            "retained canonical metadata could not be read safely"
        ) from exc
    identity = lambda value: (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )
    if (
        identity(before) != identity(after)
        or len(captured) != after.st_size
        or len(captured) > MAX_RETAINED_CANONICAL_METADATA_BYTES
    ):
        raise ArtifactInventoryError(
            "retained canonical metadata changed during bounded capture"
        )
    digest = hashlib.sha256(captured).hexdigest()
    if digest != RETAINED_CANONICAL_METADATA_SHA256:
        raise ArtifactInventoryError(
            "retained canonical metadata differs from pinned checkout bytes"
        )
    return digest


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactInventoryError(f"duplicate API JSON member: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ArtifactInventoryError(f"non-finite API JSON constant: {value}")


def _bounded_api_integer(token: str) -> int:
    # GitHub's historical artifact/run identifiers and byte counts are integers.
    # Reject oversized values before invoking Python's integer conversion.
    if len(token.lstrip("-")) > MAX_API_INTEGER_DIGITS:
        raise ArtifactInventoryError("GitHub Actions metadata integer exceeds digit limit")
    return int(token)


def _reject_api_float(token: str):
    # Workflow and artifact metadata have no float-valued source fields.
    raise ArtifactInventoryError("GitHub Actions metadata floating-point token is invalid")


def _require_bounded_api_json_depth(raw: bytes) -> None:
    """Bound container nesting without treating quoted brackets as structure."""
    depth = 0
    in_string = False
    escaped = False
    for octet in raw:
        if in_string:
            if escaped:
                escaped = False
            elif octet == 92:  # backslash
                escaped = True
            elif octet == 34:  # quote
                in_string = False
        elif octet == 34:
            in_string = True
        elif octet in (91, 123):  # open array or object
            depth += 1
            if depth > MAX_API_JSON_DEPTH:
                raise ArtifactInventoryError(
                    "GitHub Actions metadata exceeds JSON nesting limit"
                )
        elif octet in (93, 125):
            depth -= 1
            if depth < 0:
                raise ArtifactInventoryError(
                    "GitHub Actions metadata has unmatched JSON closing delimiter"
                )


class _RejectInventoryRedirects(HTTPRedirectHandler):
    """Keep run-scoped metadata reads on the pinned GitHub API endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ArtifactInventoryError("GitHub Actions metadata endpoint redirected")


def _open_inventory_metadata(request: Request, *, timeout: int):
    """Do not follow redirects carrying GitHub metadata or API credentials."""
    return build_opener(_RejectInventoryRedirects()).open(request, timeout=timeout)


def _fetch_json(path: str) -> object:
    """Read bounded origin-bound JSON; never follow redirects or fetch ZIPs."""
    if not path.startswith(f"/repos/{REPOSITORY}/actions/runs/"):
        raise ArtifactInventoryError("API path is outside the pinned repository run endpoints")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "VERA-historical-artifact-inventory",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = API_BASE + path
    try:
        with _open_inventory_metadata(Request(url, headers=headers), timeout=15) as response:
            if response.geturl() != url:
                raise ArtifactInventoryError("GitHub Actions metadata endpoint redirected")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # A moved endpoint's HTTP error is not a response from this run.
        if exc.geturl() != url:
            raise ArtifactInventoryError(
                "GitHub Actions metadata endpoint redirected"
            ) from exc
        raise ArtifactInventoryError(
            f"GitHub Actions metadata query failed for {path}: HTTP {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        # Never turn network/auth/rate-limit failures into "artifact absent".
        raise ArtifactInventoryError(
            f"GitHub Actions metadata query failed for {path}: {type(exc).__name__}"
        ) from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ArtifactInventoryError("GitHub Actions metadata response exceeds size limit")
    _require_bounded_api_json_depth(raw)
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_int=_bounded_api_integer,
            parse_float=_reject_api_float,
        )
    except ArtifactInventoryError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ArtifactInventoryError(
            "GitHub Actions response is not bounded valid UTF-8 JSON"
        ) from exc


def _require_object(value: object, *, label: str) -> dict:
    if type(value) is not dict:
        raise ArtifactInventoryError(f"{label} must be a JSON object")
    return value


def _parse_utc_timestamp(value: object, *, label: str) -> datetime:
    """Reject missing, ambiguous, non-UTC, or invalid GitHub timestamps."""
    if type(value) is not str or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)",
        value,
    ) is None:
        raise ArtifactInventoryError(f"{label} is not an RFC3339 UTC timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArtifactInventoryError(f"{label} timestamp is invalid") from exc


def _parse_expiry_utc(value: object) -> datetime:
    return _parse_utc_timestamp(value, label="artifact expiry")


def _listed_artifacts(
    run_id: int, *, expected_head_sha: str, started_at: datetime,
    last_updated_at: datetime, fetch_json: Callable[[str], object],
) -> list[dict]:
    """Read every page; never interpret a partial listing as a missing archive."""
    seen_ids = set()
    found: list[dict] = []
    total = None
    for page in range(1, MAX_PAGES + 1):
        path = (
            f"/repos/{REPOSITORY}/actions/runs/{run_id}/artifacts"
            f"?per_page={PAGE_SIZE}&page={page}"
        )
        payload = _require_object(fetch_json(path), label="artifact page")
        count = payload.get("total_count")
        entries = payload.get("artifacts")
        if type(count) is not int or count < 0 or type(entries) is not list:
            raise ArtifactInventoryError("artifact listing count or entries are invalid")
        if total is None:
            total = count
        elif count != total:
            raise ArtifactInventoryError("artifact listing changed during pagination")
        if len(entries) > PAGE_SIZE or len(found) + len(entries) > total:
            raise ArtifactInventoryError("artifact listing has inconsistent cardinality")
        for item in entries:
            artifact = _require_object(item, label="artifact")
            artifact_id = artifact.get("id")
            if type(artifact_id) is not int or artifact_id < 1 or artifact_id in seen_ids:
                raise ArtifactInventoryError("artifact listing has invalid or repeated artifact ID")
            seen_ids.add(artifact_id)
            if (
                type(artifact.get("name")) is not str
                or not artifact["name"]
                or type(artifact.get("expired")) is not bool
            ):
                raise ArtifactInventoryError("artifact listing has invalid name/expiry metadata")
            created_at = _parse_utc_timestamp(
                artifact.get("created_at"), label="artifact creation"
            )
            updated_at = _parse_utc_timestamp(
                artifact.get("updated_at"), label="artifact update"
            )
            if not started_at <= created_at <= last_updated_at:
                raise ArtifactInventoryError(
                    "artifact creation is outside historical start-to-last-update window"
                )
            if updated_at < created_at:
                raise ArtifactInventoryError("artifact update precedes creation")
            if _parse_expiry_utc(artifact.get("expires_at")) <= created_at:
                raise ArtifactInventoryError("artifact expiry must follow creation")
            if type(artifact.get("size_in_bytes")) is not int or artifact["size_in_bytes"] <= 0:
                raise ArtifactInventoryError("artifact ZIP has invalid or zero byte size")
            # A correctly named artifact and ZIP link do not establish
            # provenance if the provider's metadata self-link identifies a
            # different artifact or repository. Check both endpoint identities.
            expected_metadata_url = (
                f"{API_BASE}/repos/{REPOSITORY}/actions/artifacts/{artifact_id}"
            )
            if artifact.get("url") != expected_metadata_url:
                raise ArtifactInventoryError(
                    "artifact metadata URL does not match its run-repository artifact ID"
                )
            if artifact.get("archive_download_url") != expected_metadata_url + "/zip":
                raise ArtifactInventoryError(
                    "artifact ZIP download URL is not run-repository scoped"
                )
            digest = artifact.get("digest")
            if digest is not None and (
                type(digest) is not str
                or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            ):
                raise ArtifactInventoryError("artifact ZIP digest metadata is invalid")
            source = artifact.get("workflow_run")
            if type(source) is not dict or (
                type(source.get("id")) is not int or source["id"] != run_id
            ):
                raise ArtifactInventoryError("artifact belongs to a different workflow run")
            if (
                source.get("head_sha") != expected_head_sha
                or source.get("head_branch") != HISTORICAL_BRANCH
                or type(source.get("repository_id")) is not int
                or source["repository_id"] != HISTORICAL_REPOSITORY_ID
                or type(source.get("head_repository_id")) is not int
                or source["head_repository_id"] != HISTORICAL_REPOSITORY_ID
            ):
                raise ArtifactInventoryError(
                    "artifact workflow source identity differs from historical run"
                )
            found.append(artifact)
        if len(found) == total:
            return found
        if len(entries) != PAGE_SIZE:
            raise ArtifactInventoryError("artifact listing ended before declared total_count")
    raise ArtifactInventoryError("artifact listing exceeds bounded pagination limit")



def _listing_identity(artifacts: list[dict]) -> dict[int, tuple]:
    """Compare custody-relevant metadata, not volatile download counters or API order."""
    identity_fields = (
        "name", "expired", "created_at", "updated_at", "expires_at",
        "size_in_bytes", "digest", "archive_download_url",
    )
    source_fields = (
        "id", "head_sha", "head_branch", "repository_id", "head_repository_id",
    )
    return {
        artifact["id"]: (
            *(artifact.get(field) for field in identity_fields),
            *(artifact["workflow_run"].get(field) for field in source_fields),
        )
        for artifact in artifacts
    }

def _workflow_snapshot_identity(run: dict) -> tuple:
    """Compare only historical execution/custody fields, not volatile counters."""
    fields = (
        "id", "name", "head_sha", "status", "conclusion", "run_attempt",
        "head_branch", "path", "event", "run_started_at", "updated_at",
    )
    # A JSON boolean must not silently compare equal to an integer attempt.
    return tuple((type(run.get(name)), run.get(name)) for name in fields)


def audit_historical_artifact_inventory(
    *,
    fetch_json: Callable[[str], object] = _fetch_json,
    checked_at: datetime | None = None,
) -> dict:
    """Pin run identity and single UTC inventory time before interpreting listings."""
    if checked_at is None:
        checked_at = datetime.now(timezone.utc)
    if not isinstance(checked_at, datetime) or checked_at.tzinfo is None or (
        checked_at.utcoffset() is None
    ):
        raise ArtifactInventoryError("inventory checked_at must be timezone-aware")
    checked_at = checked_at.astimezone(timezone.utc)
    # Check our retained provider snapshot before any live GitHub metadata read;
    # otherwise stale or modified local evidence could escape notice when an
    # artifact is absent and the hard-coded candidate identity is never used.
    _verify_retained_canonical_metadata_file()
    receipts = {}
    for role, run_id, workflow_name, commit, conclusion, expected_name in HISTORICAL_RUNS:
        path = f"/repos/{REPOSITORY}/actions/runs/{run_id}"
        run = _require_object(fetch_json(path), label=f"{role} workflow run")
        if (
            type(run.get("id")) is not int
            or run["id"] != run_id
            or run.get("name") != workflow_name
            or run.get("head_sha") != commit
            or run.get("status") != "completed"
            or run.get("conclusion") != conclusion
            or type(run.get("run_attempt")) is not int
            or run["run_attempt"] != 1
            or run.get("head_branch") != HISTORICAL_BRANCH
            or run.get("path") != f".github/workflows/{workflow_name}.yml"
            or run.get("event") != "push"
        ):
            raise ArtifactInventoryError(
                f"{role} workflow identity/status differs from frozen historical anchor"
            )
        started_at = _parse_utc_timestamp(
            run.get("run_started_at"), label=f"{role} workflow start"
        )
        last_updated_at = _parse_utc_timestamp(
            run.get("updated_at"), label=f"{role} workflow last update"
        )
        if last_updated_at < started_at:
            raise ArtifactInventoryError(f"{role} workflow last update precedes start")
        artifacts = _listed_artifacts(
            run_id, expected_head_sha=commit, started_at=started_at,
            last_updated_at=last_updated_at, fetch_json=fetch_json,
        )
        # GitHub's page totals alone cannot detect an ID replacement or changed
        # custody metadata between page reads. Reconcile a second complete scan
        # before asserting that a historical artifact is absent or available.
        second_scan = _listed_artifacts(
            run_id, expected_head_sha=commit, started_at=started_at,
            last_updated_at=last_updated_at, fetch_json=fetch_json,
        )
        if _listing_identity(artifacts) != _listing_identity(second_scan):
            raise ArtifactInventoryError(
                f"{role} artifact listing changed across two complete scans"
            )
        # Matching artifact pages cannot establish an unchanged historical
        # execution if the run itself is rerun/updated between those reads.
        rechecked_run = _require_object(
            fetch_json(path), label=f"{role} workflow run recheck"
        )
        if _workflow_snapshot_identity(rechecked_run) != _workflow_snapshot_identity(run):
            raise ArtifactInventoryError(
                f"{role} workflow metadata changed across artifact scans"
            )
        matching = [item for item in artifacts if item["name"] == expected_name]
        if len(matching) > 1:
            raise ArtifactInventoryError(f"{role} has duplicate expected artifact names")
        upload_pin = HISTORICAL_UPLOAD_PINS.get(role)
        if matching and upload_pin is not None:
            item = matching[0]
            # A same-name ZIP created under the pinned workflow is not enough:
            # require the exact GitHub service-reported original upload identity.
            # Legacy API responses may omit digest; that remains explicitly
            # unverified rather than being invented or treated as a match.
            if (
                item["id"] != upload_pin["artifact_id"]
                or item["size_in_bytes"] != upload_pin["size_bytes"]
                or (
                    item["digest"] is not None
                    and item["digest"] != f"sha256:{upload_pin['zip_sha256']}"
                )
            ):
                raise ArtifactInventoryError(
                    f"{role} named ZIP differs from contemporaneous GitHub upload log"
                )
        if matching and role == "canonical_analysis":
            item = matching[0]
            # Same-name, same-run metadata is not sufficient for the retained
            # canonical ZIP: reconcile with the earlier published provider-
            # observed artifact identity, byte count, and available digest.
            if (
                item["id"] != CANONICAL_ARCHIVE_PIN["artifact_id"]
                or item["size_in_bytes"] != CANONICAL_ARCHIVE_PIN["size_bytes"]
                or (
                    item["digest"] is not None
                    and item["digest"] != f"sha256:{CANONICAL_ARCHIVE_PIN['zip_sha256']}"
                )
            ):
                raise ArtifactInventoryError(
                    "canonical_analysis named ZIP differs from retained provider-observed "
                    "canonical archive metadata"
                )
        eligible = [
            item for item in matching
            if item["expired"] is False
            and _parse_expiry_utc(item["expires_at"]) > checked_at
        ]
        elapsed_expiry = bool(
            matching
            and matching[0]["expired"] is False
            and _parse_expiry_utc(matching[0]["expires_at"]) <= checked_at
        )
        receipts[role] = {
            "run_id": run_id,
            "workflow_name": workflow_name,
            "head_sha": commit,
            "workflow_conclusion": conclusion,
            "workflow_attempt": 1,
            "workflow_started_at": started_at.isoformat(),
            "workflow_last_updated_at": last_updated_at.isoformat(),
            "expected_artifact_name": expected_name,
            "total_artifacts_listed": len(artifacts),
            "listing_reconciliation": "two_matching_full_passes",
            "historical_github_upload_log_concordance": (
                "id_size_and_api_digest_match_logged_upload"
                if upload_pin is not None and matching and matching[0]["digest"] is not None
                else "id_size_match_logged_upload_api_digest_unavailable"
                if upload_pin is not None and matching
                else "named_zip_not_listed" if upload_pin is not None
                else "not_applicable_to_canonical_analysis"
            ),
            "retained_canonical_archive_metadata_concordance": (
                "id_size_and_api_digest_match_retained_provider_metadata"
                if role == "canonical_analysis" and matching and matching[0]["digest"] is not None
                else "id_size_match_retained_provider_metadata_api_digest_unavailable"
                if role == "canonical_analysis" and matching
                else "named_zip_not_listed" if role == "canonical_analysis"
                else "not_applicable"
            ),
            "workflow_reconciliation": "two_matching_execution_snapshots",
            "expected_artifact": (
                {
                    "id": matching[0]["id"],
                    "name": matching[0]["name"],
                    "expired": matching[0]["expired"],
                    "expires_at": matching[0]["expires_at"],
                    "created_at": matching[0]["created_at"],
                    "updated_at": matching[0]["updated_at"],
                    "expiry_elapsed_at_check": elapsed_expiry,
                    "zip_size_in_bytes": matching[0]["size_in_bytes"],
                    "github_zip_digest": matching[0].get("digest"),
                    "archive_download_url": matching[0]["archive_download_url"],
                }
                if matching else None
            ),
            "listing_status": (
                "named_nonexpired_artifact_listed_not_download_verified"
                if eligible else
                "named_artifact_listed_elapsed_expiry" if elapsed_expiry else
                "named_artifact_listed_expired" if matching else
                "named_artifact_not_listed"
            ),
        }
    has_both_original_candidates = all(
        receipts[name]["listing_status"]
        == "named_nonexpired_artifact_listed_not_download_verified"
        for name in ("original_treatment", "evaluator_recovery")
    )
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "checked_at_utc": checked_at.isoformat(),
        "repository": REPOSITORY,
        "status": (
            "original_artifact_candidates_listed_not_authenticated"
            if has_both_original_candidates
            else "blocked_original_artifact_listings"
        ),
        "historical_runs": receipts,
        "historical_evidence_authenticated": False,
        "human_evaluation_ready": False,
        "treatments_rerun": False,
        "evaluator_rerun": False,
        "human_ratings_used": False,
        "interpretation": (
            "Run-scoped GitHub Actions metadata and creation-window/source-identity "
            "consistency only. An absent/expired listing "
            "does not prove evidence was destroyed or that offline backups do not exist. "
            "A listed nonexpired artifact requires a positive ZIP size and an expiry "
            "deadline later than checked_at_utc; its GitHub-supplied digest (when "
            "present) is metadata, not an independent archive pin. No listing "
            "proves a successful ZIP download or historical custody. When listed, "
            "the named treatment/recovery ZIP must match GitHub upload-log ID, "
            "size and any present GitHub API digest; the named canonical ZIP "
            "must match its retained provider-observed ID, size, and any "
            "present API digest. Neither metadata source establishes "
            "independent historical custody. The original "
            "trace/report and blinded human-evaluation gates remain mandatory."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    del args
    try:
        result = audit_historical_artifact_inventory()
    except (ArtifactInventoryError, OSError) as exc:
        parser.exit(1, f"VERA HISTORICAL ARTIFACT INVENTORY: FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
