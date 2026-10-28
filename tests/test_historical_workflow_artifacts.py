"""Synthetic-only tests for the read-only historical Actions inventory.

No GitHub network requests, experiments, artifacts or human ratings are used.
"""
from __future__ import annotations

import copy
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
        }
        entries = artifact_map.get(run_id, [])
        results[
            f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}/artifacts"
            "?per_page=100&page=1"
        ] = {"total_count": len(entries), "artifacts": entries}
    return results


def _artifact(run_id, name, *, expired=False, ident=1001):
    return {
        "id": ident, "name": name, "expired": expired,
        "expires_at": "2026-12-23T23:03:46Z",
        "workflow_run": {"id": run_id},
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
