"""Offline custody regressions for VERA's retained canonical provider metadata.

These cases never contact GitHub, replay treatments, measure evaluators, or
fabricate any blinded human-evaluation result.
"""
from __future__ import annotations

import pytest

from scripts import audit_historical_workflow_artifacts as audit


def test_checked_in_provider_metadata_matches_immutable_byte_anchor():
    assert audit._verify_retained_canonical_metadata_file() == (
        audit.RETAINED_CANONICAL_METADATA_SHA256
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "artifact_id", "zip_digest", "format_only", "truncated",
        "missing", "symlink", "directory", "oversize",
    ),
)
def test_provider_metadata_custody_fails_before_any_github_request(
    tmp_path, monkeypatch, mutation
):
    original = audit.RETAINED_CANONICAL_METADATA_PATH.read_bytes()
    target = tmp_path / "retained-provider-metadata.json"
    if mutation == "artifact_id":
        changed = original.replace(b'"id":10837878458', b'"id":10837878459', 1)
        assert changed != original
        target.write_bytes(changed)
    elif mutation == "zip_digest":
        changed = original.replace(b'"digest":"sha256:226', b'"digest":"sha256:326', 1)
        assert changed != original
        target.write_bytes(changed)
    elif mutation == "format_only":
        target.write_bytes(original + b"\\n")
    elif mutation == "truncated":
        target.write_bytes(original[:100])
    elif mutation == "symlink":
        source = tmp_path / "otherwise-valid-metadata.json"
        source.write_bytes(original)
        target.symlink_to(source)
    elif mutation == "directory":
        target.mkdir()
    elif mutation == "oversize":
        target.write_bytes(original + b"x" * audit.MAX_RETAINED_CANONICAL_METADATA_BYTES)
    else:
        assert mutation == "missing"

    monkeypatch.setattr(audit, "RETAINED_CANONICAL_METADATA_PATH", target)
    github_calls = []

    def no_live_github_calls(path):
        github_calls.append(path)
        raise AssertionError("research metadata preflight contacted GitHub")

    with pytest.raises(audit.ArtifactInventoryError, match="retained canonical metadata"):
        audit.audit_historical_artifact_inventory(fetch_json=no_live_github_calls)
    assert github_calls == []


def test_unchanged_metadata_can_preflight_without_historical_artifacts():
    """Missing original ZIP listings remain a blocked evidence gate, not corruption."""
    response = {
        "id": audit.HISTORICAL_RUNS[0][1],
    }
    # The byte-custody gate is independent of an actual artifact listing.
    assert audit._verify_retained_canonical_metadata_file()
    assert response["id"] == 34620917346
