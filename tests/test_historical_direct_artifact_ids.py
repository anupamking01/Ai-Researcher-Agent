"""Synthetic offline regression coverage for historical direct-ID access triage."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError

import pytest

from scripts import audit_historical_direct_artifact_ids as audit

NOW = datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc)


def _candidate(pin):
    run_id, head_sha = audit.RUN_SOURCES[pin["role"]]
    url = f"{audit.API_BASE}/repos/{audit.REPOSITORY}/actions/artifacts/{pin['artifact_id']}"
    # Synthetic metadata represents a creation inside each original run's
    # pinned GitHub Actions start-to-last-update window.
    created_at, updated_at = {
        "original_treatment": ("2026-09-11T17:21:00Z", "2026-09-11T17:21:01Z"),
        "evaluator_recovery": ("2026-09-13T21:21:00Z", "2026-09-13T21:21:01Z"),
    }[pin["role"]]
    return {
        "id": pin["artifact_id"],
        "name": pin["artifact_name"],
        "url": url,
        "archive_download_url": url + "/zip",
        "size_in_bytes": pin["size_bytes"],
        "digest": "sha256:" + pin["zip_sha256"],
        "expired": False,
        "created_at": created_at,
        "updated_at": updated_at,
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
    monkeypatch.setattr(audit, "_open_direct_metadata", forbidden)
    with pytest.raises(audit.DirectArtifactAuditError, match="HTTP 403"):
        audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"])


def test_only_true_http_404_is_recorded_as_inaccessible(monkeypatch):
    def missing(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", {}, BytesIO())
    monkeypatch.setattr(audit, "_open_direct_metadata", missing)
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
    monkeypatch.setattr(audit, "_open_direct_metadata", lambda request, timeout: _Response(request.full_url, raw))
    with pytest.raises(audit.DirectArtifactAuditError):
        audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"])



@pytest.mark.parametrize("raw, message", [
    (b'{"nested":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}", "bounded UTF-8 JSON"),
    (b'{"extra":' + b"9" * 5000 + b"}", "digit limit"),
    (b'{"optional_ratio":1.25}', "floating-point"),
    (b'{"optional_ratio":1e999}', "floating-point"),
])
def test_untrusted_json_is_a_controlled_audit_error(monkeypatch, raw, message):
    """Deep or adversarial JSON must not crash the direct-ID audit."""
    monkeypatch.setattr(
        audit, "_open_direct_metadata",
        lambda request, timeout: _Response(request.full_url, raw),
    )
    with pytest.raises(audit.DirectArtifactAuditError, match=message):
        audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"])


def test_normal_pinned_json_and_bounded_integer_remain_accepted(monkeypatch):
    pin = audit.ORIGINAL_PINS[0]
    candidate = _candidate(pin)
    candidate["unused_counter"] = 12345678901234567890
    raw = json.dumps(candidate).encode("utf-8")
    monkeypatch.setattr(
        audit, "_open_direct_metadata",
        lambda request, timeout: _Response(request.full_url, raw),
    )
    parsed = audit.fetch_direct_metadata(pin["artifact_id"])
    assert parsed == candidate
    assert audit._validate_metadata(parsed, pin)


def test_redirected_metadata_endpoint_is_not_accepted(monkeypatch):
    monkeypatch.setattr(audit, "_open_direct_metadata", lambda request, timeout: _Response("https://other.example/", b'{}'))
    with pytest.raises(audit.DirectArtifactAuditError, match="redirected"):
        audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"])


def test_unknown_id_rejected_without_network(monkeypatch):
    monkeypatch.setattr(audit, "_open_direct_metadata", lambda *args, **kwargs: pytest.fail("unexpected network request"))
    with pytest.raises(audit.DirectArtifactAuditError, match="unrecognized"):
        audit.fetch_direct_metadata(999)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_metadata_redirect_is_refused_before_destination_request(status):
    """A later 404 must never be attributed to the pinned original ID."""
    handler = audit._RejectMetadataRedirects()
    with pytest.raises(audit.DirectArtifactAuditError, match="redirected"):
        handler.redirect_request(
            None, None, status, "Redirect", {"Location": "https://elsewhere.invalid/"},
            "https://elsewhere.invalid/not-found",
        )


def test_redirect_destination_404_cannot_masquerade_as_original_404(monkeypatch):
    def redirected_404(request, *, timeout):
        raise HTTPError(
            "https://elsewhere.invalid/not-found", 404, "Not Found", {}, BytesIO()
        )
    monkeypatch.setattr(audit, "_open_direct_metadata", redirected_404)
    with pytest.raises(audit.DirectArtifactAuditError, match="redirected"):
        audit.fetch_direct_metadata(audit.ORIGINAL_PINS[0]["artifact_id"])


@pytest.mark.parametrize("role", ["original_treatment", "evaluator_recovery"])
@pytest.mark.parametrize("direction", ["before", "after"])
def test_creation_outside_original_workflow_window_fails_closed(role, direction):
    """A same-ID, same-digest ZIP cannot predate or postdate its source run."""
    originals = {p["artifact_id"]: _candidate(p) for p in audit.ORIGINAL_PINS}
    target = next(p for p in audit.ORIGINAL_PINS if p["role"] == role)
    # Keep lifecycle dates internally valid to isolate the workflow-window gate.
    if direction == "before":
        created_at, updated_at = "2026-09-01T00:00:00Z", "2026-09-01T00:00:01Z"
    else:
        created_at, updated_at = "2026-09-14T00:00:00Z", "2026-09-14T00:00:01Z"
    originals[target["artifact_id"]]["created_at"] = created_at
    originals[target["artifact_id"]]["updated_at"] = updated_at
    with pytest.raises(audit.DirectArtifactAuditError, match="outside pinned original workflow window"):
        audit.audit_direct_artifact_ids(fetch_artifact=_client(originals), checked_at=NOW)


@pytest.mark.parametrize("role", ["original_treatment", "evaluator_recovery"])
@pytest.mark.parametrize("boundary_index", [0, 1])
def test_creation_at_original_workflow_boundary_is_allowed(role, boundary_index):
    """The original run window is inclusive, without a guessed grace period."""
    originals = {p["artifact_id"]: _candidate(p) for p in audit.ORIGINAL_PINS}
    target = next(p for p in audit.ORIGINAL_PINS if p["role"] == role)
    stamp = audit.RUN_CREATION_WINDOWS_UTC[role][boundary_index]
    originals[target["artifact_id"]]["created_at"] = stamp
    originals[target["artifact_id"]]["updated_at"] = stamp
    result = audit.audit_direct_artifact_ids(fetch_artifact=_client(originals), checked_at=NOW)
    assert result["historical_artifacts"][role]["github_upload_log_id_size_concordance"] is True



@pytest.mark.parametrize("stamp", [
    "2026-09-11T17:22:43+00:00",
    "2026-09-13T21:21:40+00:00",
    "2026-09-13T21:21:40.999999+00:00",
])
def test_recovery_observation_time_cannot_predate_completed_uploads(stamp):
    """A prior-to-completion 404 is not evidence about post-run availability."""
    requested = []

    def lookup(artifact_id):
        requested.append(artifact_id)
        return None

    with pytest.raises(
        audit.DirectArtifactAuditError, match="predates completion"
    ):
        audit.audit_direct_artifact_ids(
            fetch_artifact=lookup,
            checked_at=datetime.fromisoformat(stamp),
        )
    assert requested == [], "reject incoherent timestamps before API access"


def test_first_full_second_after_both_uploads_is_an_observation_not_custody():
    """Allow the first unambiguous post-run timestamp without promoting 404."""
    checked_at = datetime.fromisoformat("2026-09-13T21:21:41+00:00")
    receipt = audit.audit_direct_artifact_ids(
        fetch_artifact=lambda _artifact_id: None,
        checked_at=checked_at,
    )
    assert receipt["checked_at_utc"] == checked_at.isoformat()
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert all(
        row["status"] == "http_404_at_both_observations_not_proof_of_destruction"
        for row in receipt["historical_artifacts"].values()
    )


@pytest.mark.parametrize("role", ["original_treatment", "evaluator_recovery"])
@pytest.mark.parametrize("future_read", [1, 2])
def test_direct_id_observation_rejects_metadata_updated_in_its_future(
    role, future_read
):
    """An otherwise pinned ZIP must not appear updated after its audit receipt."""
    originals = {p["artifact_id"]: _candidate(p) for p in audit.ORIGINAL_PINS}
    target = next(p for p in audit.ORIGINAL_PINS if p["role"] == role)
    calls = []

    def lookup(artifact_id):
        calls.append(artifact_id)
        candidate = copy.deepcopy(originals[artifact_id])
        target_reads = calls.count(target["artifact_id"])
        if artifact_id == target["artifact_id"] and target_reads == future_read:
            # Creation is still inside the original workflow; all pinned
            # identity, digest and expiry fields remain otherwise consistent.
            candidate["updated_at"] = "2026-11-05T07:00:01Z"
        return candidate

    with pytest.raises(
        audit.DirectArtifactAuditError, match="updated_at postdates observation"
    ):
        audit.audit_direct_artifact_ids(fetch_artifact=lookup, checked_at=NOW)
    # A failed first read must not trigger a redundant second lookup.
    assert calls.count(target["artifact_id"]) == future_read


@pytest.mark.parametrize("role", ["original_treatment", "evaluator_recovery"])
def test_direct_id_metadata_update_at_observation_boundary_is_allowed(role):
    """The comparison rejects the future, not a legitimate exact boundary."""
    originals = {p["artifact_id"]: _candidate(p) for p in audit.ORIGINAL_PINS}
    target = next(p for p in audit.ORIGINAL_PINS if p["role"] == role)
    originals[target["artifact_id"]]["updated_at"] = "2026-11-05T07:00:00Z"
    receipt = audit.audit_direct_artifact_ids(
        fetch_artifact=_client(originals), checked_at=NOW
    )
    assert receipt["historical_artifacts"][role]["github_upload_log_id_size_concordance"]
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
