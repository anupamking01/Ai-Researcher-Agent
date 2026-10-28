"""Synthetic-only tests for the read-only historical Actions inventory.

No GitHub network requests, experiments, artifacts or human ratings are used.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import pytest

from scripts import audit_historical_workflow_artifacts as audit


def _responses(artifacts=None):
    artifact_map = artifacts or {}
    results = {}
    for role, run_id, name, sha, conclusion, _ in audit.HISTORICAL_RUNS:
        del role
        results[f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"] = {
            "id": run_id, "name": name, "head_sha": sha,
            "status": "completed", "conclusion": conclusion,
            "run_attempt": 1, "head_branch": audit.HISTORICAL_BRANCH,
            "path": f".github/workflows/{name}.yml", "event": "push",
            "run_started_at": "2026-09-24T23:00:00Z",
            "updated_at": "2026-09-24T23:05:00Z",
        }
        entries = artifact_map.get(run_id, [])
        results[
            f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}/artifacts"
            "?per_page=100&page=1"
        ] = {"total_count": len(entries), "artifacts": entries}
    return results


def _artifact(run_id, name, *, expired=False, ident=1001):
    head_sha = next(
        (sha for _, anchored_id, _, sha, _, _ in audit.HISTORICAL_RUNS
         if anchored_id == run_id), "0" * 40
    )
    return {
        "id": ident, "name": name, "expired": expired,
        "created_at": "2026-09-24T23:03:00Z",
        "updated_at": "2026-09-24T23:03:00Z",
        "expires_at": "2099-12-23T23:03:46Z",
        "size_in_bytes": 10270,
        "digest": "sha256:" + "a" * 64,
        "archive_download_url": (
            f"https://api.github.com/repos/{audit.REPOSITORY}"
            f"/actions/artifacts/{ident}/zip"
        ),
        "workflow_run": {
            "id": run_id, "head_sha": head_sha,
            "head_branch": audit.HISTORICAL_BRANCH,
            "repository_id": audit.HISTORICAL_REPOSITORY_ID,
            "head_repository_id": audit.HISTORICAL_REPOSITORY_ID,
        },
    }


def _client(responses):
    def fetch(path):
        return copy.deepcopy(responses[path])
    return fetch


def test_missing_original_artifacts_are_not_mistaken_for_destroyed_evidence():
    canonical = audit.HISTORICAL_RUNS[2]
    responses = _responses({
        canonical[1]: [_artifact(canonical[1], canonical[5])]
    })
    result = audit.audit_historical_artifact_inventory(fetch_json=_client(responses))
    assert result["status"] == "blocked_original_artifact_listings"
    assert result["historical_runs"]["original_treatment"]["listing_status"] == (
        "named_artifact_not_listed"
    )
    assert result["historical_runs"]["canonical_analysis"]["listing_status"] == (
        "named_nonexpired_artifact_listed_not_download_verified"
    )
    assert result["historical_evidence_authenticated"] is False
    assert result["human_evaluation_ready"] is False
    assert result["treatments_rerun"] is False
    assert result["human_ratings_used"] is False


def test_other_artifacts_cannot_impersonate_original_run_evidence():
    original = audit.HISTORICAL_RUNS[0]
    result = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses({
            original[1]: [_artifact(original[1], "unrelated-debug-log")]
        }))
    )
    assert result["historical_runs"]["original_treatment"]["total_artifacts_listed"] == 1
    assert result["historical_runs"]["original_treatment"]["expected_artifact"] is None


def test_expired_named_artifacts_cannot_claim_nonexpired_listing():
    matches = {
        run_id: [_artifact(run_id, expected, expired=True, ident=run_id)]
        for _, run_id, _, _, _, expected in audit.HISTORICAL_RUNS
    }
    receipt = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses(matches))
    )
    assert receipt["status"] == "blocked_original_artifact_listings"
    assert all(
        r["listing_status"] == "named_artifact_listed_expired"
        for r in receipt["historical_runs"].values()
    )


def test_two_named_artifact_candidates_still_do_not_authenticate_evidence():
    matches = {
        run_id: [_artifact(run_id, expected, ident=run_id)]
        for _, run_id, _, _, _, expected in audit.HISTORICAL_RUNS
    }
    result = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses(matches))
    )
    assert result["status"] == "original_artifact_candidates_listed_not_authenticated"
    assert result["historical_evidence_authenticated"] is False
    assert result["human_evaluation_ready"] is False


@pytest.mark.parametrize("field,bad", [
    ("head_sha", "0" * 40),
    ("name", "unrelated-workflow"),
    ("conclusion", "success"),
    ("status", "queued"),
    ("id", 10),
])
def test_historical_workflow_identity_mismatch_fails_closed(field, bad):
    responses = _responses()
    first = audit.HISTORICAL_RUNS[0][1]
    responses[f"/repos/{audit.REPOSITORY}/actions/runs/{first}"][field] = bad
    with pytest.raises(audit.ArtifactInventoryError, match="identity/status"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


def test_cross_run_artifact_association_is_rejected():
    first = audit.HISTORICAL_RUNS[0]
    responses = _responses({
        first[1]: [_artifact(12345, first[5], ident=12)]
    })
    with pytest.raises(audit.ArtifactInventoryError, match="different workflow run"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


def test_repeated_artifact_ids_fail_closed():
    first = audit.HISTORICAL_RUNS[0]
    entry = _artifact(first[1], first[5], ident=333)
    responses = _responses({first[1]: [entry, dict(entry, name="other")]})
    with pytest.raises(audit.ArtifactInventoryError, match="repeated artifact ID"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


def test_incomplete_pagination_is_not_interpreted_as_missing_artifacts():
    first = audit.HISTORICAL_RUNS[0]
    responses = _responses()
    path = (
        f"/repos/{audit.REPOSITORY}/actions/runs/{first[1]}"
        "/artifacts?per_page=100&page=1"
    )
    responses[path] = {"total_count": 2, "artifacts": []}
    with pytest.raises(audit.ArtifactInventoryError, match="ended before"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


def test_artifact_listing_total_change_between_pages_fails_closed():
    first = audit.HISTORICAL_RUNS[0]
    responses = _responses()
    path = (
        f"/repos/{audit.REPOSITORY}/actions/runs/{first[1]}"
        "/artifacts?per_page=100&page="
    )
    responses[path + "1"] = {
        "total_count": 101,
        "artifacts": [
            _artifact(first[1], f"other-{i}", ident=10000+i)
            for i in range(100)
        ],
    }
    responses[path + "2"] = {"total_count": 100, "artifacts": []}
    with pytest.raises(audit.ArtifactInventoryError, match="changed during pagination"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


def test_correct_second_page_is_included():
    first = audit.HISTORICAL_RUNS[0]
    responses = _responses()
    path = (
        f"/repos/{audit.REPOSITORY}/actions/runs/{first[1]}"
        "/artifacts?per_page=100&page="
    )
    responses[path + "1"] = {
        "total_count": 101,
        "artifacts": [
            _artifact(first[1], f"other-{i}", ident=10000+i)
            for i in range(100)
        ],
    }
    responses[path + "2"] = {
        "total_count": 101,
        "artifacts": [_artifact(first[1], first[5], ident=20001)],
    }
    result = audit.audit_historical_artifact_inventory(fetch_json=_client(responses))
    assert result["historical_runs"]["original_treatment"]["total_artifacts_listed"] == 101
    assert result["historical_runs"]["original_treatment"]["expected_artifact"]["id"] == 20001


def test_source_unavailability_is_an_error_not_a_missing_archive_claim():
    def inaccessible(path):
        raise audit.ArtifactInventoryError("GitHub returned rate-limit response")
    with pytest.raises(audit.ArtifactInventoryError, match="rate-limit"):
        audit.audit_historical_artifact_inventory(fetch_json=inaccessible)


def test_listed_original_zip_metadata_is_explicitly_unverified():
    matches = {
        run_id: [_artifact(run_id, expected, ident=run_id)]
        for _, run_id, _, _, _, expected in audit.HISTORICAL_RUNS
    }
    inventory = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses(matches)),
        checked_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    candidate = inventory["historical_runs"]["original_treatment"]["expected_artifact"]
    assert candidate["zip_size_in_bytes"] == 10270
    assert candidate["github_zip_digest"] == "sha256:" + "a" * 64
    assert candidate["archive_download_url"].endswith(
        f"/actions/artifacts/{audit.HISTORICAL_RUNS[0][1]}/zip"
    )
    assert candidate["expiry_elapsed_at_check"] is False
    assert inventory["historical_evidence_authenticated"] is False
    assert inventory["human_evaluation_ready"] is False


def test_elapsed_expiry_flag_cannot_claim_downloadable_candidate():
    role, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    candidate = _artifact(run_id, expected, ident=501)
    candidate["expires_at"] = "2026-10-28T12:00:00Z"
    inventory = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses({run_id: [candidate]})),
        checked_at=datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc),
    )
    receipt = inventory["historical_runs"][role]
    assert receipt["listing_status"] == "named_artifact_listed_elapsed_expiry"
    assert receipt["expected_artifact"]["expiry_elapsed_at_check"] is True
    assert inventory["status"] == "blocked_original_artifact_listings"


@pytest.mark.parametrize("bad_size", [0, -1, True, 10.2, "10270"])
def test_invalid_or_empty_zip_size_fails_closed(bad_size):
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    candidate = _artifact(run_id, expected)
    candidate["size_in_bytes"] = bad_size
    with pytest.raises(audit.ArtifactInventoryError, match="byte size"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


@pytest.mark.parametrize("bad_digest", ["sha256:xyz", "sha1:" + "a" * 40, 123])
def test_bad_github_zip_digest_fails_closed(bad_digest):
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    candidate = _artifact(run_id, expected)
    candidate["digest"] = bad_digest
    with pytest.raises(audit.ArtifactInventoryError, match="ZIP digest"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


def test_missing_legacy_github_digest_is_not_a_historical_authentication_claim():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    candidate = _artifact(run_id, expected)
    candidate["digest"] = None
    result = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses({run_id: [candidate]}))
    )
    assert result["historical_runs"]["original_treatment"]["expected_artifact"]["github_zip_digest"] is None
    assert result["historical_evidence_authenticated"] is False


@pytest.mark.parametrize("bad_expiry", [
    "tomorrow", "2026-02-30T00:00:00Z", "2026-12-23T23:03:46",
    "2026-12-23T23:03:46+01:00",
])
def test_malformed_or_ambiguous_artifact_expiry_fails_closed(bad_expiry):
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    candidate = _artifact(run_id, expected)
    candidate["expires_at"] = bad_expiry
    with pytest.raises(audit.ArtifactInventoryError, match="expir"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


def test_unscoped_download_endpoint_fails_closed():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    candidate = _artifact(run_id, expected)
    candidate["archive_download_url"] = "https://example.com/artifact.zip"
    with pytest.raises(audit.ArtifactInventoryError, match="download URL"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


def test_naive_inventory_clock_fails_closed():
    with pytest.raises(audit.ArtifactInventoryError, match="timezone-aware"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses()),
            checked_at=datetime(2026, 10, 28),
        )


@pytest.mark.parametrize("field,bad", [
    ("run_attempt", 2),
    ("run_attempt", True),
    ("head_branch", "main"),
    ("path", ".github/workflows/unrelated.yml"),
    ("event", "workflow_dispatch"),
])
def test_artifact_inventory_rejects_different_historical_workflow_attempt(field, bad):
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    responses = _responses({run_id: [_artifact(run_id, expected)]})
    responses[f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"][field] = bad
    with pytest.raises(audit.ArtifactInventoryError, match="identity/status"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


@pytest.mark.parametrize("field,bad", [
    ("head_sha", "f" * 40),
    ("head_branch", "main"),
    ("repository_id", 999),
    ("head_repository_id", 999),
    ("head_repository_id", None),
])
def test_artifact_inventory_rejects_cross_source_artifact_metadata(field, bad):
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    candidate = _artifact(run_id, expected)
    candidate["workflow_run"][field] = bad
    with pytest.raises(audit.ArtifactInventoryError, match="source identity"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


def test_artifact_without_workflow_source_metadata_fails_closed():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    candidate = _artifact(run_id, expected)
    candidate.pop("workflow_run")
    with pytest.raises(audit.ArtifactInventoryError, match="different workflow run"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


@pytest.mark.parametrize("created", [
    "2026-09-24T22:59:59Z", "2026-09-24T23:05:01Z",
    "2026-09-24T23:03:00+01:00",
])
def test_artifact_created_outside_historical_run_or_ambiguous_timestamp_fails(created):
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    candidate = _artifact(run_id, expected)
    candidate["created_at"] = created
    with pytest.raises(audit.ArtifactInventoryError, match="creation"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


def test_artifact_updated_before_its_creation_fails():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    candidate = _artifact(run_id, expected)
    candidate["updated_at"] = "2026-09-24T23:02:00Z"
    with pytest.raises(audit.ArtifactInventoryError, match="update precedes"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


def test_artifact_expiring_before_creation_fails():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    candidate = _artifact(run_id, expected)
    candidate["expires_at"] = "2026-09-24T23:02:00Z"
    with pytest.raises(audit.ArtifactInventoryError, match="expiry must follow"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


@pytest.mark.parametrize("field,bad", [
    ("run_started_at", "not-a-time"),
    ("updated_at", "2026-09-24T23:05:00+01:00"),
])
def test_historical_run_malformed_clock_fails_closed(field, bad):
    _, run_id, _, _, _, _ = audit.HISTORICAL_RUNS[2]
    responses = _responses()
    responses[f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"][field] = bad
    with pytest.raises(audit.ArtifactInventoryError, match="workflow"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


def test_workflow_completion_before_start_fails():
    _, run_id, _, _, _, _ = audit.HISTORICAL_RUNS[2]
    responses = _responses()
    responses[f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"][
        "updated_at"
    ] = "2026-09-24T22:59:59Z"
    with pytest.raises(audit.ArtifactInventoryError, match="completion precedes"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


def test_valid_artifact_receipt_preserves_temporal_and_source_custody_metadata():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    receipt = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses({run_id: [_artifact(run_id, expected)]}))
    )["historical_runs"]["canonical_analysis"]
    assert receipt["workflow_attempt"] == 1
    assert receipt["workflow_started_at"] == "2026-09-24T23:00:00+00:00"
    assert receipt["workflow_completed_at"] == "2026-09-24T23:05:00+00:00"
    assert receipt["expected_artifact"]["created_at"] == "2026-09-24T23:03:00Z"
    assert receipt["expected_artifact"]["updated_at"] == "2026-09-24T23:03:00Z"
