"""Regression coverage for blinded human-freeze source hardlink custody.

These tests exercise only local synthetic bytes; no human ratings are created.
"""
import os

import pytest

from scripts import freeze_human_eval_ratings as freeze


def test_capture_accepts_single_link_source(tmp_path):
    source = tmp_path / "source.csv"
    payload = b"synthetic-blinded-source\n"
    source.write_bytes(payload)
    assert freeze._capture_regular_input(source, label="synthetic rating source") == payload


@pytest.mark.parametrize("source_name", [
    "synthetic-annotator.csv",
    "synthetic-annotator-attestations.csv",
])
def test_capture_rejects_preexisting_hardlink(tmp_path, source_name):
    source = tmp_path / source_name
    source.write_bytes(b"synthetic-source\n")
    os.link(source, tmp_path / "extra-alias.csv")
    with pytest.raises(ValueError, match="exactly one filesystem link"):
        freeze._capture_regular_input(source, label="blinded human input")


def test_capture_rejects_link_created_during_byte_read(tmp_path, monkeypatch):
    source = tmp_path / "original.csv"
    source.write_bytes(b"synthetic-source\n")
    alias = tmp_path / "late-alias.csv"
    original_pread = os.pread
    observed = {"created": False}

    def introduce_alias(fd, count, offset):
        if not observed["created"]:
            os.link(source, alias)
            observed["created"] = True
        return original_pread(fd, count, offset)

    monkeypatch.setattr(freeze.os, "pread", introduce_alias)
    with pytest.raises(ValueError, match="changed while it was being read"):
        freeze._capture_regular_input(source, label="blinded human input")
    assert observed["created"]
