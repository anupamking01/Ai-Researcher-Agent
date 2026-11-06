"""Synthetic regression tests for retained five-file exploratory replay custody."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import verify_exploratory_measurement_bundle as bundle

REPO = "anupamking01/Ai-Researcher-Agent"
SHA = "a" * 40
RUN = "42298467969"
ATTEMPT = "1"


def _json(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def _bundle(tmp_path: Path, monkeypatch) -> Path:
    entries = {
        "retrieval_exposure.json": _json({"synthetic_exposure": 1}),
        "claim_denominators.json": _json({"synthetic_denominators": 2}),
    }
    receipts = {}
    for name, prefix in (
        ("retrieval_exposure.json", "retrieval_exposure"),
        ("claim_denominators.json", "claim_denominators"),
    ):
        receipts[f"{prefix}_verification.json"] = {
            "schema_version": 1,
            "status": f"synthetic_verified_{prefix}",
            "diagnostic_sha256": hashlib.sha256(entries[name]).hexdigest(),
            "cells_checked": 40,
            "paired_contrast_rows_checked": 30,
            "human_validation_performed": False,
            "original_execution_authenticated": False,
        }
    entries.update({name: _json(value) for name, value in receipts.items()})
    index = {
        "schema_version": 2,
        "status": bundle.STATUS,
        "repository": REPO,
        "checkout_commit_sha": SHA,
        "workflow_run_id": RUN,
        "workflow_run_attempt": ATTEMPT,
        "files_sha256": {
            name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(entries.items())
        },
        "frozen_confirmatory_inference_changed": False,
        "original_execution_authenticated": False,
        "human_validation_performed": False,
    }
    entries[bundle.INDEX] = _json(index)
    for name, raw in entries.items():
        (tmp_path / name).write_bytes(raw)
    # The real implementations rederive these receipts from immutable CSVs;
    # synthetic tests isolate the bundle binding with controlled receipts.
    monkeypatch.setattr(bundle.exposure, "verify_published", lambda _: dict(receipts["retrieval_exposure_verification.json"]))
    monkeypatch.setattr(bundle.denominators, "verify_published", lambda _: dict(receipts["claim_denominators_verification.json"]))
    return tmp_path


def _verify(directory, **overrides):
    inputs = dict(repository=REPO, checkout_sha=SHA, run_id=RUN, run_attempt=ATTEMPT)
    inputs.update(overrides)
    return bundle.verify_bundle(directory, **inputs)


def _rewrite_index(directory: Path, mutation):
    index_path = directory / bundle.INDEX
    obj = json.loads(index_path.read_bytes())
    mutation(obj)
    index_path.write_bytes(_json(obj))


def test_valid_synthetic_bundle_recomputes_both_receipts(tmp_path, monkeypatch):
    directory = _bundle(tmp_path, monkeypatch)
    receipt = _verify(directory)
    assert receipt["files_verified"] == 5
    assert receipt["status"] == bundle.STATUS
    assert receipt["original_execution_authenticated"] is False
    assert receipt["human_validation_performed"] is False


@pytest.mark.parametrize("field,bad", [
    ("repository", "someone/unrelated"),
    ("checkout_commit_sha", "b" * 40),
    ("workflow_run_id", "998"),
    ("workflow_run_attempt", "2"),
    ("schema_version", True),
    ("frozen_confirmatory_inference_changed", True),
    ("human_validation_performed", True),
    ("original_execution_authenticated", True),
])
def test_false_index_pins_and_claims_fail(tmp_path, monkeypatch, field, bad):
    directory = _bundle(tmp_path, monkeypatch)
    _rewrite_index(directory, lambda index: index.__setitem__(field, bad))
    with pytest.raises(ValueError):
        _verify(directory)


@pytest.mark.parametrize("name", sorted(bundle.EXPECTED_FILES))
def test_missing_bundle_member_fails(tmp_path, monkeypatch, name):
    directory = _bundle(tmp_path, monkeypatch)
    (directory / name).unlink()
    with pytest.raises(ValueError):
        _verify(directory)


def test_extra_bundle_member_fails(tmp_path, monkeypatch):
    directory = _bundle(tmp_path, monkeypatch)
    (directory / "unexpected.json").write_text("{}")
    with pytest.raises(ValueError):
        _verify(directory)


def test_modified_diagnostic_with_rehashed_index_and_receipt_still_fails(tmp_path, monkeypatch):
    directory = _bundle(tmp_path, monkeypatch)
    diagnostic = directory / "retrieval_exposure.json"
    diagnostic.write_bytes(_json({"synthetic_exposure": 999}))
    receipt_path = directory / "retrieval_exposure_verification.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["diagnostic_sha256"] = hashlib.sha256(diagnostic.read_bytes()).hexdigest()
    receipt_path.write_bytes(_json(receipt))
    _rewrite_index(directory, lambda index: index["files_sha256"].update({
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in bundle.FILES
    }))
    with pytest.raises(ValueError, match="independent replay"):
        _verify(directory)


def test_corrupted_receipt_rehashed_in_index_fails(tmp_path, monkeypatch):
    directory = _bundle(tmp_path, monkeypatch)
    name = "claim_denominators_verification.json"
    (directory / name).write_bytes(_json({"forged": "PASS"}))
    _rewrite_index(directory, lambda index: index["files_sha256"].update({
        name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
    }))
    with pytest.raises(ValueError):
        _verify(directory)


def test_diagnostic_changed_without_rehash_fails(tmp_path, monkeypatch):
    directory = _bundle(tmp_path, monkeypatch)
    (directory / "claim_denominators.json").write_bytes(b"{}")
    with pytest.raises(ValueError):
        _verify(directory)


@pytest.mark.parametrize("file", ["artifact_index.json", "retrieval_exposure_verification.json"])
def test_duplicate_key_rejected(tmp_path, monkeypatch, file):
    directory = _bundle(tmp_path, monkeypatch)
    path = directory / file
    path.write_bytes(b'{"status":"safe","status":"unsafe"}')
    if file != bundle.INDEX:
        _rewrite_index(directory, lambda index: index["files_sha256"].update({
            file: hashlib.sha256(path.read_bytes()).hexdigest()
        }))
    with pytest.raises(ValueError):
        _verify(directory)


@pytest.mark.parametrize("invalid", [b'{"schema_version":1e999}', b'{"schema_version":NaN}', b'{"schema_version":true}'])
def test_invalid_index_numeric_or_type_rejected(tmp_path, monkeypatch, invalid):
    directory = _bundle(tmp_path, monkeypatch)
    (directory / bundle.INDEX).write_bytes(invalid)
    with pytest.raises(ValueError):
        _verify(directory)


def test_symlinked_member_rejected(tmp_path, monkeypatch):
    directory = _bundle(tmp_path, monkeypatch)
    linked = directory / "retrieval_exposure.json"
    original = directory.parent / "original.json"
    original.write_bytes(linked.read_bytes())
    linked.unlink()
    linked.symlink_to(original)
    with pytest.raises((ValueError, bundle.audit.InputIntegrityError)):
        _verify(directory)


def test_hardlinked_member_rejected(tmp_path, monkeypatch):
    import os
    directory = _bundle(tmp_path, monkeypatch)
    os.link(directory / bundle.INDEX, directory.parent / "second-link.json")
    with pytest.raises((ValueError, bundle.audit.InputIntegrityError)):
        _verify(directory)


def test_wrong_external_identity_rejected(tmp_path, monkeypatch):
    directory = _bundle(tmp_path, monkeypatch)
    for changes in (dict(checkout_sha="bad"), dict(run_attempt="0"),
                    dict(run_id="999"), dict(repository="other/repo")):
        with pytest.raises(ValueError):
            _verify(directory, **changes)
