"""Read-only GitHub Actions artifact inventory for VERA's three historical runs.

This is an availability diagnostic, not retrieval of reports, a historical
custody proof, a treatment/evaluator rerun, or a human-evaluation result.
Only the exact historically named artifacts count as candidates.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY = "anupamking01/Ai-Researcher-Agent"
API_BASE = "https://api.github.com"
PAGE_SIZE = 100
MAX_PAGES = 20
MAX_RESPONSE_BYTES = 512 * 1024
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


class ArtifactInventoryError(ValueError):
    """A source or listing could not support an affirmative inventory claim."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactInventoryError(f"duplicate API JSON member: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ArtifactInventoryError(f"non-finite API JSON constant: {value}")


def _fetch_json(path: str) -> object:
    """Read bounded JSON from the fixed public GitHub API host, never download ZIPs."""
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
    request = Request(API_BASE + path, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        # Do not turn network/auth/rate-limit failures into "artifact absent".
        raise ArtifactInventoryError(
            f"GitHub Actions metadata query failed for {path}: {type(exc).__name__}"
        ) from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ArtifactInventoryError("GitHub Actions metadata response exceeds size limit")
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactInventoryError("GitHub Actions response is not valid UTF-8 JSON") from exc


def _require_object(value: object, *, label: str) -> dict:
    if type(value) is not dict:
        raise ArtifactInventoryError(f"{label} must be a JSON object")
    return value


def _listed_artifacts(
    run_id: int, *, fetch_json: Callable[[str], object]
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
                not isinstance(artifact.get("name"), str)
                or not artifact["name"]
                or type(artifact.get("expired")) is not bool
                or not isinstance(artifact.get("expires_at"), str)
            ):
                raise ArtifactInventoryError("artifact listing has invalid name/expiry metadata")
            source = artifact.get("workflow_run")
            if source is not None:
                if type(source) is not dict or source.get("id") != run_id:
                    raise ArtifactInventoryError("artifact belongs to a different workflow run")
            found.append(artifact)
        if len(found) == total:
            return found
        if len(entries) != PAGE_SIZE:
            raise ArtifactInventoryError("artifact listing ended before declared total_count")
    raise ArtifactInventoryError("artifact listing exceeds bounded pagination limit")


def audit_historical_artifact_inventory(
    *, fetch_json: Callable[[str], object] = _fetch_json
) -> dict:
    """Pin run identity before interpreting artifact listing metadata."""
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
        ):
            raise ArtifactInventoryError(
                f"{role} workflow identity/status differs from frozen historical anchor"
            )
        artifacts = _listed_artifacts(run_id, fetch_json=fetch_json)
        matching = [item for item in artifacts if item["name"] == expected_name]
        if len(matching) > 1:
            raise ArtifactInventoryError(f"{role} has duplicate expected artifact names")
        eligible = [item for item in matching if item["expired"] is False]
        receipts[role] = {
            "run_id": run_id,
            "workflow_name": workflow_name,
            "head_sha": commit,
            "workflow_conclusion": conclusion,
            "expected_artifact_name": expected_name,
            "total_artifacts_listed": len(artifacts),
            "expected_artifact": (
                {
                    "id": matching[0]["id"],
                    "name": matching[0]["name"],
                    "expired": matching[0]["expired"],
                    "expires_at": matching[0]["expires_at"],
                }
                if matching else None
            ),
            "listing_status": (
                "named_nonexpired_artifact_listed_not_download_verified"
                if eligible else
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
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
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
            "Run-scoped GitHub Actions metadata only. An absent/expired listing "
            "does not prove evidence was destroyed or that offline backups do not exist. "
            "A listed nonexpired artifact is neither a successful ZIP download nor "
            "independent historical custody authentication. The separate original "
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
