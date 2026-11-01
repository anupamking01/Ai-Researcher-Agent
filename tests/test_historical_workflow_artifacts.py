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


def _artifact(run_id, name, *, expired=False, ident=None):
    pin = next(
        (item for item in audit.HISTORICAL_UPLOAD_PINS.values()
         if item["run_id"] == run_id and item["artifact_name"] == name),
        None,
    )
    if (
        pin is None
        and run_id == audit.HISTORICAL_RUNS[2][1]
        and name == audit.HISTORICAL_RUNS[2][5]
    ):
        pin = audit.CANONICAL_ARCHIVE_PIN
    if ident is None:
        ident = pin["artifact_id"] if pin else 1001
    head_sha = next(
        (sha for _, anchored_id, _, sha, _, _ in audit.HISTORICAL_RUNS
         if anchored_id == run_id), "0" * 40
    )
    return {
        "id": ident, "name": name, "expired": expired,
        "created_at": "2026-09-24T23:03:00Z",
        "updated_at": "2026-09-24T23:03:00Z",
        "expires_at": "2099-12-23T23:03:46Z",
        "size_in_bytes": pin["size_bytes"] if pin else 10270,
        "digest": "sha256:" + (pin["zip_sha256"] if pin else "a" * 64),
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
        run_id: [_artifact(run_id, expected, expired=True)]
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
        run_id: [_artifact(run_id, expected)]
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
        "artifacts": [_artifact(first[1], first[5])],
    }
    result = audit.audit_historical_artifact_inventory(fetch_json=_client(responses))
    assert result["historical_runs"]["original_treatment"]["total_artifacts_listed"] == 101
    assert result["historical_runs"]["original_treatment"]["expected_artifact"]["id"] == audit.HISTORICAL_UPLOAD_PINS["original_treatment"]["artifact_id"]


def test_source_unavailability_is_an_error_not_a_missing_archive_claim():
    def inaccessible(path):
        raise audit.ArtifactInventoryError("GitHub returned rate-limit response")
    with pytest.raises(audit.ArtifactInventoryError, match="rate-limit"):
        audit.audit_historical_artifact_inventory(fetch_json=inaccessible)


def test_listed_original_zip_metadata_is_explicitly_unverified():
    matches = {
        run_id: [_artifact(run_id, expected)]
        for _, run_id, _, _, _, expected in audit.HISTORICAL_RUNS
    }
    inventory = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses(matches)),
        checked_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    candidate = inventory["historical_runs"]["original_treatment"]["expected_artifact"]
    pin = audit.HISTORICAL_UPLOAD_PINS["original_treatment"]
    assert candidate["id"] == pin["artifact_id"]
    assert candidate["zip_size_in_bytes"] == pin["size_bytes"]
    assert candidate["github_zip_digest"] == "sha256:" + pin["zip_sha256"]
    assert candidate["archive_download_url"].endswith(
        f"/actions/artifacts/{pin['artifact_id']}/zip"
    )
    assert inventory["historical_runs"]["original_treatment"][
        "historical_github_upload_log_concordance"
    ] == "id_size_and_api_digest_match_logged_upload"
    assert candidate["expiry_elapsed_at_check"] is False
    assert inventory["historical_evidence_authenticated"] is False
    assert inventory["human_evaluation_ready"] is False


def test_elapsed_expiry_flag_cannot_claim_downloadable_candidate():
    role, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    candidate = _artifact(run_id, expected)
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


def test_workflow_last_update_before_start_fails():
    _, run_id, _, _, _, _ = audit.HISTORICAL_RUNS[2]
    responses = _responses()
    responses[f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"][
        "updated_at"
    ] = "2026-09-24T22:59:59Z"
    with pytest.raises(audit.ArtifactInventoryError, match="last update precedes"):
        audit.audit_historical_artifact_inventory(fetch_json=_client(responses))


def test_valid_artifact_receipt_preserves_temporal_and_source_custody_metadata():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    receipt = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses({run_id: [_artifact(run_id, expected)]}))
    )["historical_runs"]["canonical_analysis"]
    assert receipt["workflow_attempt"] == 1
    assert receipt["workflow_started_at"] == "2026-09-24T23:00:00+00:00"
    assert receipt["workflow_last_updated_at"] == "2026-09-24T23:05:00+00:00"
    assert receipt["expected_artifact"]["created_at"] == "2026-09-24T23:03:00Z"
    assert receipt["expected_artifact"]["updated_at"] == "2026-09-24T23:03:00Z"


def _changing_listing(responses, run_id, first_entries, second_entries):
    """Return different complete page-one snapshots without any real GitHub I/O."""
    path = (
        f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"
        "/artifacts?per_page=100&page=1"
    )
    calls = []

    def fetch(requested):
        if requested == path:
            calls.append(requested)
            entries = first_entries if len(calls) == 1 else second_entries
            return {"total_count": len(entries), "artifacts": copy.deepcopy(entries)}
        return copy.deepcopy(responses[requested])

    return fetch, calls


def test_reconciliation_rejects_artifact_added_after_initial_empty_listing():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    fetch, calls = _changing_listing(
        _responses(), run_id, [], [_artifact(run_id, expected, ident=8121)]
    )
    with pytest.raises(audit.ArtifactInventoryError, match="two complete scans"):
        audit.audit_historical_artifact_inventory(fetch_json=fetch)
    assert len(calls) == 2


def test_reconciliation_rejects_artifact_id_swap_at_unchanged_total_count():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    first = _artifact(run_id, "unrelated-debug-log", ident=8122)
    second = _artifact(run_id, expected, ident=8123)
    fetch, _ = _changing_listing(_responses(), run_id, [first], [second])
    with pytest.raises(audit.ArtifactInventoryError, match="two complete scans"):
        audit.audit_historical_artifact_inventory(fetch_json=fetch)


@pytest.mark.parametrize("field,new_value", [
    ("name", "other-artifact"),
    ("expired", True),
    ("updated_at", "2026-09-24T23:04:00Z"),
    ("size_in_bytes", 10271),
    ("digest", "sha256:" + "b" * 64),
    ("expires_at", "2099-12-24T23:03:46Z"),
])
def test_reconciliation_rejects_same_id_with_changed_source_metadata(field, new_value):
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[0]
    first = _artifact(run_id, expected, ident=8124)
    second = copy.deepcopy(first)
    second[field] = new_value
    fetch, _ = _changing_listing(_responses(), run_id, [first], [second])
    with pytest.raises(audit.ArtifactInventoryError, match="two complete scans"):
        audit.audit_historical_artifact_inventory(fetch_json=fetch)


def test_reconciliation_ignores_only_volatile_download_count_changes():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    first = _artifact(run_id, expected)
    first["download_count"] = 1
    second = copy.deepcopy(first)
    second["download_count"] = 99
    fetch, calls = _changing_listing(_responses(), run_id, [first], [second])
    result = audit.audit_historical_artifact_inventory(fetch_json=fetch)
    receipt = result["historical_runs"]["canonical_analysis"]
    assert receipt["listing_reconciliation"] == "two_matching_full_passes"
    assert receipt["expected_artifact"]["id"] == audit.CANONICAL_ARCHIVE_PIN["artifact_id"]
    assert len(calls) == 2


def test_reconciliation_accepts_same_ids_reordered_across_pages():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    first = [
        _artifact(run_id, f"other-{i}", ident=9000 + i)
        for i in range(100)
    ]
    tail = _artifact(run_id, expected)
    page_prefix = (
        f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"
        "/artifacts?per_page=100&page="
    )
    page_calls = {1: 0, 2: 0}
    responses = _responses()

    def fetch(path):
        if path.startswith(page_prefix):
            page = int(path[len(page_prefix):])
            page_calls[page] += 1
            if page == 1:
                entries = first if page_calls[page] == 1 else first[:-1] + [tail]
            else:
                entries = [tail] if page_calls[page] == 1 else [first[-1]]
            return {"total_count": 101, "artifacts": copy.deepcopy(entries)}
        return copy.deepcopy(responses[path])

    receipt = audit.audit_historical_artifact_inventory(fetch_json=fetch)[
        "historical_runs"
    ]["canonical_analysis"]
    assert receipt["expected_artifact"]["id"] == audit.CANONICAL_ARCHIVE_PIN["artifact_id"]
    assert receipt["listing_reconciliation"] == "two_matching_full_passes"
    assert page_calls == {1: 2, 2: 2}


@pytest.mark.parametrize("field,changed", [
    ("run_attempt", 2),
    ("run_attempt", True),  # bool and int compare equal without a type guard.
    ("status", "in_progress"),
    ("conclusion", "cancelled"),
    ("head_sha", "f" * 40),
    ("updated_at", "2026-09-24T23:06:00Z"),
])
def test_run_reconciliation_fails_on_execution_drift_during_artifact_scan(
    field, changed
):
    """Matching artifact pages cannot authorize a changed workflow execution."""
    _, run_id, _, _, _, _ = audit.HISTORICAL_RUNS[0]
    responses = _responses()
    run_path = f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"
    run_reads = []

    def fetch(path):
        observed = copy.deepcopy(responses[path])
        if path == run_path:
            run_reads.append(path)
            if len(run_reads) == 2:
                observed[field] = changed
        return observed

    with pytest.raises(audit.ArtifactInventoryError, match="workflow metadata changed"):
        audit.audit_historical_artifact_inventory(fetch_json=fetch)
    assert len(run_reads) == 2


def test_reconciliation_rechecks_each_run_after_both_artifact_scans():
    responses = _responses()
    observations = []

    def fetch(path):
        observations.append(path)
        return copy.deepcopy(responses[path])

    receipt = audit.audit_historical_artifact_inventory(fetch_json=fetch)
    for role, run_id, _, _, _, _ in audit.HISTORICAL_RUNS:
        run_path = f"/repos/{audit.REPOSITORY}/actions/runs/{run_id}"
        listing_path = run_path + "/artifacts?per_page=100&page=1"
        assert observations.count(run_path) == 2
        assert observations.count(listing_path) == 2
        assert observations.index(run_path) < observations.index(listing_path)
        assert max(i for i, p in enumerate(observations) if p == listing_path) < max(
            i for i, p in enumerate(observations) if p == run_path
        )
        assert receipt["historical_runs"][role]["workflow_reconciliation"] == (
            "two_matching_execution_snapshots"
        )


@pytest.mark.parametrize("role", ("original_treatment", "evaluator_recovery"))
@pytest.mark.parametrize("mutation", ("artifact_id", "size_in_bytes", "digest"))
def test_named_historical_zip_must_match_contemporaneous_logged_upload(role, mutation):
    """A same-name, same-workflow replacement cannot pass as the original ZIP."""
    pin = audit.HISTORICAL_UPLOAD_PINS[role]
    candidate = _artifact(pin["run_id"], pin["artifact_name"])
    if mutation == "artifact_id":
        candidate["id"] += 1
        candidate["archive_download_url"] = (
            f"https://api.github.com/repos/{audit.REPOSITORY}"
            f"/actions/artifacts/{candidate['id']}/zip"
        )
    elif mutation == "size_in_bytes":
        candidate["size_in_bytes"] += 1
    else:
        candidate["digest"] = "sha256:" + "f" * 64
    with pytest.raises(audit.ArtifactInventoryError, match="contemporaneous GitHub upload log"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({pin["run_id"]: [candidate]}))
        )


def test_named_expired_zip_with_wrong_upload_id_is_not_accepted_as_original():
    pin = audit.HISTORICAL_UPLOAD_PINS["original_treatment"]
    candidate = _artifact(pin["run_id"], pin["artifact_name"], expired=True)
    candidate["id"] += 1
    candidate["archive_download_url"] = (
        f"https://api.github.com/repos/{audit.REPOSITORY}"
        f"/actions/artifacts/{candidate['id']}/zip"
    )
    with pytest.raises(audit.ArtifactInventoryError, match="contemporaneous GitHub upload log"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({pin["run_id"]: [candidate]}))
        )


def test_missing_legacy_api_digest_retains_explicit_partial_concordance():
    pin = audit.HISTORICAL_UPLOAD_PINS["evaluator_recovery"]
    candidate = _artifact(pin["run_id"], pin["artifact_name"])
    candidate["digest"] = None
    receipt = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses({pin["run_id"]: [candidate]}))
    )["historical_runs"]["evaluator_recovery"]
    assert receipt["historical_github_upload_log_concordance"] == (
        "id_size_match_logged_upload_api_digest_unavailable"
    )


@pytest.mark.parametrize("mutation", ("artifact_id", "size_in_bytes", "digest"))
def test_canonical_candidate_must_match_retained_provider_metadata(mutation):
    """A named canonical ZIP cannot be substituted within its historical run."""
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    candidate = _artifact(run_id, expected)
    if mutation == "artifact_id":
        candidate["id"] += 1
        candidate["archive_download_url"] = (
            f"https://api.github.com/repos/{audit.REPOSITORY}"
            f"/actions/artifacts/{candidate['id']}/zip"
        )
    elif mutation == "size_in_bytes":
        candidate["size_in_bytes"] += 1
    else:
        candidate["digest"] = "sha256:" + "f" * 64
    with pytest.raises(audit.ArtifactInventoryError, match="retained provider-observed"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )


def test_canonical_candidate_reports_provider_metadata_concordance_only():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    result = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses({run_id: [_artifact(run_id, expected)]}))
    )
    canonical = result["historical_runs"]["canonical_analysis"]
    assert canonical["retained_canonical_archive_metadata_concordance"] == (
        "id_size_and_api_digest_match_retained_provider_metadata"
    )
    assert result["historical_evidence_authenticated"] is False
    assert result["human_evaluation_ready"] is False


def test_canonical_missing_api_digest_is_explicitly_partial_concordance():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    candidate = _artifact(run_id, expected)
    candidate["digest"] = None
    result = audit.audit_historical_artifact_inventory(
        fetch_json=_client(_responses({run_id: [candidate]}))
    )
    assert result["historical_runs"]["canonical_analysis"][
        "retained_canonical_archive_metadata_concordance"
    ] == "id_size_match_retained_provider_metadata_api_digest_unavailable"


def test_expired_canonical_substitution_is_rejected_too():
    _, run_id, _, _, _, expected = audit.HISTORICAL_RUNS[2]
    candidate = _artifact(run_id, expected, expired=True)
    candidate["size_in_bytes"] += 1
    with pytest.raises(audit.ArtifactInventoryError, match="retained provider-observed"):
        audit.audit_historical_artifact_inventory(
            fetch_json=_client(_responses({run_id: [candidate]}))
        )
