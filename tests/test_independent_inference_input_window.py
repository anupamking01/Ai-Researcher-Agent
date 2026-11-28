"""Synthetic-only regressions for the independent audit's three-source window.

These fixtures never run treatments, evaluators, or human annotation.
"""
from __future__ import annotations

import os

import pytest

from scripts import audit_primary_inference_independently as audit


def _sources(tmp_path):
    main = tmp_path / "main.csv"
    support = tmp_path / "support.csv"
    inference = tmp_path / "inference.json"
    main.write_bytes(b"variant_id,task_id\nD3,synthetic-main\n")
    support.write_bytes(b"variant_id,task_id\nD3,synthetic-support\n")
    inference.write_bytes(b'{"synthetic":true}\n')
    return {"treatment": main, "evaluator": support, "inference": inference}


def _audit(paths):
    return audit.audit_files(
        paths["treatment"], paths["evaluator"], paths["inference"]
    )


def test_unchanged_triple_is_read_only(tmp_path, monkeypatch):
    paths = _sources(tmp_path)
    before = {key: path.read_bytes() for key, path in paths.items()}
    monkeypatch.setattr(
        audit, "audit_primary", lambda *_args: {"status": "synthetic"}
    )
    assert _audit(paths) == {"status": "synthetic"}
    assert {key: path.read_bytes() for key, path in paths.items()} == before


@pytest.mark.parametrize("source", ["treatment", "evaluator", "inference"])
def test_rejects_source_changed_during_arithmetic(tmp_path, monkeypatch, source):
    paths = _sources(tmp_path)

    def change_after_capture(*_args):
        path = paths[source]
        path.write_bytes(path.read_bytes() + b" ")
        return {"status": "synthetic"}

    monkeypatch.setattr(audit, "audit_primary", change_after_capture)
    with pytest.raises(ValueError, match="changed during independent inference audit"):
        _audit(paths)


def test_rejects_same_byte_path_replacement_during_arithmetic(tmp_path, monkeypatch):
    paths = _sources(tmp_path)

    def swap_after_capture(*_args):
        target = paths["inference"]
        replacement = tmp_path / "replacement.json"
        replacement.write_bytes(target.read_bytes())
        os.replace(replacement, target)
        return {"status": "synthetic"}

    monkeypatch.setattr(audit, "audit_primary", swap_after_capture)
    with pytest.raises(ValueError, match="inference JSON changed during"):
        _audit(paths)
