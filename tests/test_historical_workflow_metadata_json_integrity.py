"""Synthetic-only HTTP metadata parser regression cases for historical inventory.

All responses are in memory. No GitHub requests, treatment runs, evaluator
calls, archive downloads, or human annotations are made.
"""
from __future__ import annotations

import json

import pytest

from scripts import audit_historical_workflow_artifacts as inventory


def _decode(monkeypatch, payload: bytes):
    path = f"/repos/{inventory.REPOSITORY}/actions/runs/34620917346"
    url = inventory.API_BASE + path

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def geturl(self):
            return url

        def read(self, count):
            return payload[:count]

    def fake_open(request, *, timeout):
        assert request.full_url == url
        assert timeout == 15
        return Response()

    monkeypatch.setattr(inventory, "_open_inventory_metadata", fake_open)
    return inventory._fetch_json(path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b'{"total_count":' + b"9" * 21 + b',"artifacts":[]}', "integer exceeds digit"),
        (b'{"total_count":-' + b"9" * 21 + b'}', "integer exceeds digit"),
        (b'{"extra":1.25}', "floating-point"),
        (b'{"extra":1e999999999999999999}', "floating-point"),
        (b'{"depth":' + b"[" * 65 + b"0" + b"]" * 65 + b"}", "nesting limit"),
        (b'{"extra":1,"extra":2}', "duplicate API JSON"),
        (b'{"extra":NaN}', "non-finite API JSON"),
        (b'{"extra":Infinity}', "non-finite API JSON"),
        (b'{"extra":\xff}', "bounded valid UTF-8 JSON"),
        (b'{"extra":0' + b" " * (inventory.MAX_RESPONSE_BYTES + 1), "exceeds size limit"),
    ],
)
def test_fail_closed_on_untrusted_run_scoped_metadata(monkeypatch, payload, message):
    with pytest.raises(inventory.ArtifactInventoryError, match=message):
        _decode(monkeypatch, payload)


def test_brackets_and_escaped_quotes_inside_strings_are_not_nesting(monkeypatch):
    value = {
        "total_count": 0,
        "artifacts": [],
        "note": 'a "[\\\\ bracket" and ' + "[" * 100 + "]" * 100,
        "max_signed_api_integer": 99999999999999999999,
    }
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    assert _decode(monkeypatch, raw) == value


def test_bounded_nested_metadata_remains_parseable(monkeypatch):
    raw = b'{"value":' + b"[" * inventory.MAX_API_JSON_DEPTH + b"0" + b"]" * inventory.MAX_API_JSON_DEPTH + b"}"
    # The surrounding JSON object consumes one level, so allow 63 arrays.
    raw = b'{"value":' + b"[" * (inventory.MAX_API_JSON_DEPTH - 1) + b"0" + b"]" * (inventory.MAX_API_JSON_DEPTH - 1) + b"}"
    assert _decode(monkeypatch, raw)["value"][0] is not None
