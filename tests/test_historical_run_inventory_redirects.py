"""Offline origin/custody regression tests for historical run-scoped API reads."""
from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from scripts import audit_historical_workflow_artifacts as audit


PATH = f"/repos/{audit.REPOSITORY}/actions/runs/{audit.HISTORICAL_RUNS[0][1]}"
ORIGIN = audit.API_BASE + PATH


class _Response:
    def __init__(self, url, raw):
        self.url = url
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, limit):
        return self.raw[:limit]


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_run_scoped_metadata_refuses_redirect_before_following_it(status):
    handler = audit._RejectInventoryRedirects()
    with pytest.raises(audit.ArtifactInventoryError, match="redirected"):
        handler.redirect_request(
            None, None, status, "Moved",
            {"Location": "https://elsewhere.invalid/"},
            "https://elsewhere.invalid/metadata",
        )


def test_run_scoped_metadata_rejects_redirected_success_body(monkeypatch):
    # Even a plausible final JSON response does not carry original endpoint custody.
    monkeypatch.setattr(
        audit, "_open_inventory_metadata",
        lambda request, *, timeout: _Response(
            "https://elsewhere.invalid/metadata", b'{"total_count":0,"artifacts":[]}'
        ),
    )
    with pytest.raises(audit.ArtifactInventoryError, match="redirected"):
        audit._fetch_json(PATH)


def test_redirect_destination_http_404_is_not_a_historical_run_observation(monkeypatch):
    def redirected(request, *, timeout):
        raise HTTPError(
            "https://elsewhere.invalid/missing", 404, "Not Found", {}, BytesIO()
        )
    monkeypatch.setattr(audit, "_open_inventory_metadata", redirected)
    with pytest.raises(audit.ArtifactInventoryError, match="redirected"):
        audit._fetch_json(PATH)


def test_pinned_origin_http_404_is_failure_not_an_empty_inventory(monkeypatch):
    def origin_404(request, *, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", {}, BytesIO())
    monkeypatch.setattr(audit, "_open_inventory_metadata", origin_404)
    with pytest.raises(audit.ArtifactInventoryError, match="HTTP 404"):
        audit._fetch_json(PATH)


def test_origin_bound_json_remains_supported(monkeypatch):
    def origin_response(request, *, timeout):
        assert request.full_url == ORIGIN
        assert timeout == 15
        return _Response(request.full_url, b'{"total_count":0,"artifacts":[]}')
    monkeypatch.setattr(audit, "_open_inventory_metadata", origin_response)
    assert audit._fetch_json(PATH) == {"total_count": 0, "artifacts": []}


def test_origin_transport_failure_cannot_be_misreported_as_empty(monkeypatch):
    def transport_failure(request, *, timeout):
        raise URLError("network unavailable")
    monkeypatch.setattr(audit, "_open_inventory_metadata", transport_failure)
    with pytest.raises(audit.ArtifactInventoryError, match="URLError"):
        audit._fetch_json(PATH)
