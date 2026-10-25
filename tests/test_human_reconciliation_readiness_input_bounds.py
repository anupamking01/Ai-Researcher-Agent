"""Synthetic safety tests for bounded human-reconciliation readiness capture.

No human ratings or treatment artifacts are generated or modified.
"""
import os

import pytest

from scripts import verify_human_reconciliation_readiness as readiness


def _capture(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        return readiness._snapshot_regular_descriptor(
            descriptor, label="synthetic readiness input"
        )
    finally:
        os.close(descriptor)


def test_small_regular_readiness_input_round_trips(tmp_path, monkeypatch):
    path = tmp_path / "small.json"
    path.write_bytes(b'{"ok":true}')
    monkeypatch.setattr(readiness, "MAX_READINESS_INPUT_BYTES", 32)
    content, identity = _capture(path)
    assert content == b'{"ok":true}'
    assert identity[2] == len(content)


def test_exact_byte_limit_remains_accepted(tmp_path, monkeypatch):
    path = tmp_path / "boundary.json"
    path.write_bytes(b"12345678")
    monkeypatch.setattr(readiness, "MAX_READINESS_INPUT_BYTES", 8)
    content, identity = _capture(path)
    assert content == b"12345678"
    assert identity[2] == 8


def test_oversized_sparse_input_rejected_before_pread(tmp_path, monkeypatch):
    path = tmp_path / "oversize.json"
    with path.open("wb") as handle:
        handle.truncate(1024 * 1024 * 64)
    monkeypatch.setattr(readiness, "MAX_READINESS_INPUT_BYTES", 32)

    def must_not_read(*args, **kwargs):
        pytest.fail("oversized readiness input must be rejected before I/O")

    monkeypatch.setattr(readiness.os, "pread", must_not_read)
    with pytest.raises(ValueError, match="byte readiness input limit"):
        _capture(path)


def test_concurrent_growth_is_bounded_before_buffering(tmp_path, monkeypatch):
    path = tmp_path / "growth.json"
    path.write_bytes(b"0123456789abcd")
    monkeypatch.setattr(readiness, "MAX_READINESS_INPUT_BYTES", 16)
    original_pread = os.pread
    called = False
    requests = []

    def append_before_read(descriptor, amount, offset):
        nonlocal called
        requests.append(amount)
        if not called:
            called = True
            with path.open("ab") as handle:
                handle.write(b"EXTRA-BYTES")
        return original_pread(descriptor, amount, offset)

    monkeypatch.setattr(readiness.os, "pread", append_before_read)
    with pytest.raises(ValueError, match="byte readiness input limit"):
        _capture(path)
    assert called
    assert max(requests) <= 17


def test_readiness_contract_limit_checked_before_other_inputs(tmp_path, monkeypatch):
    contract = tmp_path / "oversized-contract.md"
    contract.write_bytes(b"not a full contract")
    monkeypatch.setattr(readiness, "MAX_READINESS_INPUT_BYTES", 8)
    with pytest.raises(ValueError, match="reconciliation_contract exceeds"):
        readiness.verify_readiness(
            root=tmp_path,
            human_root=tmp_path / "no-human-analysis",
            contract=contract,
        )


def test_captured_input_recheck_rejects_growth_after_initial_scan(
    tmp_path, monkeypatch
):
    path = tmp_path / "human-analysis.json"
    path.write_bytes(b"1234")
    monkeypatch.setattr(readiness, "MAX_READINESS_INPUT_BYTES", 8)
    with pytest.raises(ValueError, match="byte readiness input limit"):
        with readiness._capture_regular_inputs({"human_analysis": path}) as captured:
            assert captured["human_analysis"] == b"1234"
            with path.open("ab") as handle:
                handle.write(b"another eight bytes")
