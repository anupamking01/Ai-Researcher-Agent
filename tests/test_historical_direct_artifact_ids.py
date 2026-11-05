"""Synthetic offline regression coverage for historical direct-ID access triage."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError

import pytest

from scripts import audit_historical_direct_artifact_ids as audit

NOW = datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc)


def _candidate(pin):
    run_id, head_sha = audit.RUN_SOURCES[pin["role"]]
    url = f"{audit.API_BASE}/repos/{audit.REPOSITORY}/actions/artifacts/{pin['artifact_id']}"
    return {
        "id": pin["artifact_id"],
        "name": pin["artifact_name"],
        "url": url,
        "archive_download_url": url + "/zip",
        "size_in_bytes": pin["size_bytes"],
        "digest": "sha256:" + pin["zip_sha256"],
        "expired": False,
        "created_at": "2026-09-11T12:00:00Z",
        "updated_at": "2026-09-11T12:01:00Z",
        "expires_at": "2026-12-23T23:03:46Z",
        "workflow_run": {
            "id": run_id,
            "head_sha": head_sha,
            "head_branch": audit.inventory.HISTORICAL_BRANCH,
            "repository_id": audit.inventory.HISTORICAL_REPOSITORY_ID,
            "head_repository_id": audit.inventory.HISTORICAL_REPOSITORY_ID,
        },
    }


def _client(values):
    def fetch(ident):
        return copy.deepcopy(values[ident])
    return fetch


def test_unavailable_ids_are_only_404_observations_not_evidence_destruction():
    receipt = audit.audit_direct_artifact_ids(
        fetch_artifact=lambda ident: None, checked_at=NOW
    )
    assert all(
        item["status"] == "http_404_at_both_observations_not_proof_of_destruction"
        for item in receipt["historical_artifacts"].values()
    )
    assert all(not item["github_upload_log_id_size_concordance"]
               for item in receipt["historical_artifacts"].values())
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert receipt["experimental_treatments_rerun"] is False
    assert receipt["human_ratings_generated"] is False


def test_listed_metadata_matches_pins_but_never_claims_authentication():
    originals = {p["artifact_id"]: _candidate(p) for p in audit.ORIGINAL_PINS}
    receipt = audit.audit_direct_artifact_ids(fetch_artifact=_client(originals), checked_at=NOW)
    assert all(
        item["status"] == "original_upload_metadata_listed_not_download_verified"
        and item["github_upload_log_id_size_concordance"]
        and item["github_upload_log_zip_digest_concordance"]
        for item in receipt["historical_artifacts"].values()
    )
    assert receipt["historical_evidence_authenticated"] is False


def test_missing_provider_digest_is_not_invented():
    originals = {p["artifact_id"]: _candidate(p) for p in audit.ORIGINAL_PINS}
    originals[audit.ORIGINAL_PINS[0]["artifact_id"]]["digest"] = None
    receipt = audit.audit_direct_artifact_ids(fetch_artifact=_client(originals), checked_at=NOW)
    assert receipt["historical_artifacts"]["original_treatment"]["github_upload_log_zip_digest_concordance"] is False


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(id=True),
    lambda x: x.update(size_in_bytes=True),
    lambda x: x.update(name="substituted"),
    lambda x: x.update(digest="sha256:" + "0" * 64),
    lambda x: x.update(archive_download_url="https://example.com/zip"),
    lambda x: x.update(url="https://example.com/metadata"),
    lambda x: x.update(expired=0),
    lambda x: x["workflow_run"].update(id=x["workflow_run"]["id"] + 1),
    lambda x: x["workflow_run"].update(head_sha="0" * 40),
    lambda x: x["workflow_run"].update(repository_id=True),
    lambda x: x.update(expires_at="not-a-date"),
    lambda x: x.update(updated_at="2026-09-10T12:01:00Z"),
])
def test_forged_or_ambiguous_direct_id_metadata_fails_closed(mutation):
    originals = {p["artifact_id"]: _candidate(p) for p in audit.ORIGINAL_PINS}
    mutation(originals[audit.ORIGINAL_PINS[0]["artifact_id"]])
    with pytest.raises(audit.DirectArtifactAuditError):
        audit.audit_direct_artifact_ids(fetch_artifact=_client(originals), checked_at=NOW)


def test_access_change_between_two_reads_fails_closed():
    original = _candidate(audit.ORIGINAL_PINS[0])
    calls = {}
    def unstable(ident):
        calls[ident] = calls.get(ident, 0) + 1
        return None if calls[ident] == 1 else copy.deepcopy(original)
    with pytest.raises(audit.DirectArtifactAuditError, match="changed between observations"):
        audit.audit_direct_artifact_ids(fetch_artifact=unstable, checked_at=NOW)


def test_expired_and_elapsed_expiry_are_distinct_from_missing():
    originals = {p["artifact_id"]: _candidate(p) for p in audit.ORIGINAL_PINS}
    originals[audit.ORIGINAL_PINS[0]["artifact_id"]]["expired"] = True
    originals[audit.ORIGINAL_PINS[1]["artifact_id"]]["expires_at"] = "2026-10-12T00:00:00Z"
    result = audit.audit_direct_artifact_ids(fetch_artifact=_client(originals), checked_at=NOW)
    assert result["historical_artifacts"]["original_treatment"]["status"].endswith("expired_not_download_verified")
    assert result["historical_artifacts"]["evaluator_recovery"]["status"].endswith("elapsed_expiry_not_download_verified")


def test_unauthorized_or_rate_limited_is_not_an_absence_observation(monkeypatch):
    def forbidden(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden", {}, BytesIO())
    monkeypatch.setattr(audit, "urlopen", forbidden)
    with pytest.raises(audit.DirectArtifactAuditError, match="HTTP 403"):
        audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"])


def test_only_true_http_404_is_recorded_as_inaccessible(monkeypatch):
    def missing(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", {}, BytesIO())
    monkeypatch.setattr(audit, "urlopen", missing)
    assert audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"]) is None


class _Response:
    def __init__(self, url, raw):
        self.url, self.raw = url, raw
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def geturl(self):
        return self.url
    def read(self, length):
        return self.raw[:length]


@pytest.mark.parametrize("raw", [
    b'{"a":1,"a":2}', b'{"n":NaN}', b'[]', b'not json',
    bytes([255]), b'x' * (audit.MAX_METADATA_BYTES + 1),
])
def test_bad_metadata_body_is_rejected_before_any_custody_claim(monkeypatch, raw):
    monkeypatch.setattr(audit, "urlopen", lambda request, timeout: _Response(request.full_url, raw))
    with pytest.raises(audit.DirectArtifactAuditError):
        audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"])


def test_redirected_metadata_endpoint_is_not_accepted(monkeypatch):
    monkeypatch.setattr(audit, "urlopen", lambda request, timeout: _Response("https://other.example/", b'{}'))
    with pytest.raises(audit.DirectArtifactAuditError, match="redirected"):
        audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"])


def test_unknown_id_rejected_without_network(monkeypatch):
    monkeypatch.setattr(audit, "urlopen", lambda *args, **kwargs: pytest.fail("unexpected network request"))
    with pytest.raises(audit.DirectArtifactAuditError, match="unrecognized"):
        audit.fetch_direct_metadata(999)
