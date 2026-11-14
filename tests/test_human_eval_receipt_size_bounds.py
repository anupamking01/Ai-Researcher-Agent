"""Bounded-read regression checks for retained blinded preflight receipts."""
from __future__ import annotations

import os

import pytest

from scripts import verify_human_eval_submission_preflight as verify


def test_oversized_receipt_rejected_before_open(tmp_path, monkeypatch):
    receipt_root = tmp_path / "receipt"
    receipt_root.mkdir()
    (receipt_root / verify.RECEIPT_NAME).write_bytes(
        b"x" * (verify.MAX_RECEIPT_BYTES + 1)
    )
    original_open = verify.os.open

    def prevent_receipt_open(path, *args, **kwargs):
        if path == verify.RECEIPT_NAME:
            raise AssertionError("oversized retained receipt was opened")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(verify.os, "open", prevent_receipt_open)
    with pytest.raises(ValueError, match="receipt exceeds"):
        with verify._retained_receipt_window(receipt_root):
            pass


def test_receipt_reader_accepts_exact_byte_limit(tmp_path):
    content = b"x" * verify.MAX_RECEIPT_BYTES
    receipt = tmp_path / "bounded.json"
    receipt.write_bytes(content)
    descriptor = os.open(receipt, os.O_RDONLY)
    try:
        assert verify._read_descriptor_bytes(descriptor) == content
    finally:
        os.close(descriptor)


def test_receipt_growth_after_preflight_is_bounded(tmp_path, monkeypatch):
    receipt_root = tmp_path / "receipt"
    receipt_root.mkdir()
    receipt = receipt_root / verify.RECEIPT_NAME
    receipt.write_bytes(b" " * (verify.MAX_RECEIPT_BYTES - 4))
    original_read = verify.os.read
    appended = []

    def append_during_first_read(descriptor, size):
        chunk = original_read(descriptor, size)
        if chunk and not appended:
            with receipt.open("ab") as output:
                output.write(b"extra")
            appended.append(True)
        return chunk

    monkeypatch.setattr(verify.os, "read", append_during_first_read)
    with pytest.raises(ValueError, match="receipt exceeds"):
        with verify._retained_receipt_window(receipt_root):
            pass
    assert appended == [True]
