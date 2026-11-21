"""Offline custody regressions for VERA's retained canonical provider metadata.

These cases never contact GitHub, replay treatments, measure evaluators, or
fabricate any blinded human-evaluation result.
"""
from __future__ import annotations

import os

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
        "missing", "symlink", "hardlink", "directory", "oversize",
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
        target.write_bytes(original + b"\n")
    elif mutation == "truncated":
        target.write_bytes(original[:100])
    elif mutation == "symlink":
        source = tmp_path / "otherwise-valid-metadata.json"
        source.write_bytes(original)
        target.symlink_to(source)
    elif mutation == "hardlink":
        source = tmp_path / "otherwise-valid-hardlinked-metadata.json"
        source.write_bytes(original)
        os.link(source, target)
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



def test_byte_identical_atomic_replacement_is_not_accepted_as_same_source(
    tmp_path, monkeypatch
):
    """Original descriptor and current pathname must denote one file generation."""
    raw = audit.RETAINED_CANONICAL_METADATA_PATH.read_bytes()
    target = tmp_path / "retained-provider-metadata.json"
    target.write_bytes(raw)
    replacement = tmp_path / "replacement.json"
    real_fdopen = os.fdopen

    class ReplacingCapture:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, *args):
            captured = self.stream.read(*args)
            replacement.write_bytes(raw)
            os.replace(replacement, target)
            return captured

    def fdopen_swapping_after_read(fd, mode):
        return ReplacingCapture(real_fdopen(fd, mode))

    monkeypatch.setattr(audit, "RETAINED_CANONICAL_METADATA_PATH", target)
    monkeypatch.setattr(audit.os, "fdopen", fdopen_swapping_after_read)
    requests = []

    def no_network(path):
        requests.append(path)
        raise AssertionError("source was replaced before metadata API request")

    with pytest.raises(audit.ArtifactInventoryError, match="retained canonical metadata"):
        audit.audit_historical_artifact_inventory(fetch_json=no_network)
    assert requests == []
