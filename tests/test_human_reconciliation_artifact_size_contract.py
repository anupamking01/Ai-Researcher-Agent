"""Synthetic-only resource-bound tests for reconciliation publication and verification.

These files are not real human annotations or scientific findings.
"""
import json
import os

import pytest

from scripts import reconcile_human_automated as reconcile
from scripts import verify_human_reconciliation_outputs as verify


def _synthetic_payload():
    return {
        "study_id": "synthetic-not-a-study-result",
        "verified_input_fingerprints": {
            "synthetic_source": {"bytes": 1, "sha256": "0" * 64}
        },
    }


def test_verifier_and_producer_use_the_same_artifact_limit():
    assert reconcile.MAX_RECONCILIATION_ARTIFACT_BYTES == 16 * 1024 * 1024
    assert verify.reconcile.MAX_RECONCILIATION_ARTIFACT_BYTES == (
        reconcile.MAX_RECONCILIATION_ARTIFACT_BYTES
    )


def test_verifier_rejects_oversized_sparse_file_before_pread(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(reconcile, "MAX_RECONCILIATION_ARTIFACT_BYTES", 32)
    path = tmp_path / "oversized.json"
    with path.open("wb") as stream:
        stream.truncate(33)

    def forbid_read(*args, **kwargs):
        raise AssertionError("oversized source reached os.pread")

    monkeypatch.setattr(verify.os, "pread", forbid_read)
    descriptor = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(ValueError, match="exceeds 32 byte reconciliation artifact limit"):
            verify._regular_snapshot_from_descriptor(descriptor, label="synthetic output")
    finally:
        os.close(descriptor)


def test_verifier_accepts_exact_boundary_and_preserves_bytes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(reconcile, "MAX_RECONCILIATION_ARTIFACT_BYTES", 32)
    original = b"v" * 32
    path = tmp_path / "exact-boundary.json"
    path.write_bytes(original)
    descriptor = os.open(path, os.O_RDONLY)
    try:
        data, identity = verify._regular_snapshot_from_descriptor(
            descriptor, label="synthetic output"
        )
        assert data == original
        assert identity[2] == 32
    finally:
        os.close(descriptor)


def test_verifier_rejects_growth_past_budget_during_read(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(reconcile, "MAX_RECONCILIATION_ARTIFACT_BYTES", 8)
    path = tmp_path / "growing.json"
    path.write_bytes(b"12345678")
    descriptor = os.open(path, os.O_RDONLY)
    actual_pread = os.pread
    mutated = False

    def append_before_read(fd, length, offset):
        nonlocal mutated
        if fd == descriptor and not mutated:
            mutated = True
            with path.open("ab") as stream:
                stream.write(b"9")
        return actual_pread(fd, length, offset)

    monkeypatch.setattr(verify.os, "pread", append_before_read)
    try:
        with pytest.raises(ValueError, match="exceeds 8 byte reconciliation artifact limit"):
            verify._regular_snapshot_from_descriptor(descriptor, label="synthetic output")
        assert mutated
    finally:
        os.close(descriptor)


def test_verifier_rejects_short_read_even_without_size_growth(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(reconcile, "MAX_RECONCILIATION_ARTIFACT_BYTES", 32)
    path = tmp_path / "short-read.json"
    path.write_bytes(b"12345678")
    descriptor = os.open(path, os.O_RDONLY)
    actual_pread = os.pread
    checked = False

    def simulate_short_read(fd, length, offset):
        nonlocal checked
        if fd == descriptor and offset == 4:
            checked = True
            return b""
        if fd == descriptor and offset == 0:
            return actual_pread(fd, 4, offset)
        return actual_pread(fd, length, offset)

    monkeypatch.setattr(verify.os, "pread", simulate_short_read)
    try:
        with pytest.raises(ValueError, match="changed while it was being read"):
            verify._regular_snapshot_from_descriptor(descriptor, label="synthetic output")
        assert checked
    finally:
        os.close(descriptor)


@pytest.mark.parametrize("oversized_part", ["json", "markdown"])
def test_producer_rejects_oversized_serialization_without_reserving_path(
    tmp_path, monkeypatch, oversized_part
):
    payload = _synthetic_payload()
    json_size = len(
        (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    if oversized_part == "json":
        limit = json_size - 1
        monkeypatch.setattr(reconcile, "render_markdown", lambda _payload: "# synthetic\n")
    else:
        limit = json_size
        monkeypatch.setattr(reconcile, "render_markdown", lambda _payload: "m" * (limit + 1))
    monkeypatch.setattr(reconcile, "MAX_RECONCILIATION_ARTIFACT_BYTES", limit)
    monkeypatch.setattr(
        reconcile,
        "_producer_commit",
        lambda root: (_ for _ in ()).throw(AssertionError("unexpected Git probe")),
    )
    output = tmp_path / "absent-parent" / "reconciliation-v1"
    with pytest.raises(ValueError, match="reconciliation artifact limit"):
        reconcile.write_bundle(payload, output, root=tmp_path)
    assert not output.parent.exists()


def test_producer_rejects_oversized_manifest_without_reserving_path(
    tmp_path, monkeypatch
):
    payload = _synthetic_payload()
    json_size = len(
        (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    )
    monkeypatch.setattr(reconcile, "MAX_RECONCILIATION_ARTIFACT_BYTES", json_size)
    monkeypatch.setattr(reconcile, "render_markdown", lambda _payload: "# synthetic\n")
    monkeypatch.setattr(reconcile, "_producer_commit", lambda root: "a" * 40)
    monkeypatch.setattr(reconcile, "implementation_source_specs", lambda _path: ())
    monkeypatch.setattr(
        reconcile,
        "_implementation_fingerprint",
        lambda path, *, logical_path: {
            "path": logical_path, "bytes": 1, "sha256": "0" * 64
        },
    )
    output = tmp_path / "absent-parent" / "reconciliation-v1"
    with pytest.raises(ValueError, match="reconciliation output manifest exceeds"):
        reconcile.write_bundle(payload, output, root=tmp_path)
    assert not output.parent.exists()
