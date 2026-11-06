"""Synthetic-only source-snapshot guards for the independent inference auditor.

No treatment/evaluator is run; retained experimental outputs are read-only.
"""
import os

import pytest

from scripts import audit_primary_inference_independently as audit


def test_shallow_json_parser_ignores_brackets_in_escaped_strings():
    parsed = audit._decode_inference_json(
        b'{"example":"\\\"[[{ still a string }]\\\"","value":1}'
    )
    assert parsed["value"] == 1
    assert "still a string" in parsed["example"]


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        (b"[" * 33 + b"0" + b"]" * 33, "nesting limit"),
        (b'{"number":1e99999}', "non-finite numeric"),
        (b'{"number":' + b"9" * 129 + b"}", "numeric token"),
        (b'{"number":' + b"1." + b"0" * 130 + b"}", "numeric token"),
    ],
)
def test_adversarial_inference_json_is_rejected_before_arithmetic(raw, error):
    with pytest.raises(ValueError, match=error):
        audit._decode_inference_json(raw)


def test_inference_capture_rejects_hardlinked_source(tmp_path):
    original = tmp_path / "original.json"
    original.write_text('{"status":"synthetic"}')
    alias = tmp_path / "linked.json"
    os.link(original, alias)
    with pytest.raises(ValueError, match="single-link regular"):
        audit._capture_inference_bytes(original)


def test_inference_capture_rejects_symlinked_parent(tmp_path):
    source = tmp_path / "genuine"
    source.mkdir()
    (source / "test.json").write_text('{"status":"synthetic"}')
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked parent"):
        audit._capture_inference_bytes(alias / "test.json")


def test_inference_capture_rejects_oversized_file_before_read(tmp_path):
    candidate = tmp_path / "large.json"
    with candidate.open("wb") as output:
        output.truncate(audit.MAX_INFERENCE_BYTES + 1)
    with pytest.raises(ValueError, match="size limit"):
        audit._capture_inference_bytes(candidate)


def test_inference_capture_rejects_growth_after_size_reservation(tmp_path, monkeypatch):
    candidate = tmp_path / "growing.json"
    candidate.write_text('{"status":"synthetic"}')
    original_read = os.read
    changed = False

    def grow_once(fd, count):
        nonlocal changed
        if not changed:
            changed = True
            with candidate.open("ab") as output:
                output.write(b" ")
        return original_read(fd, count)

    monkeypatch.setattr(audit.os, "read", grow_once)
    with pytest.raises(ValueError, match="changed during bounded capture"):
        audit._capture_inference_bytes(candidate)
    assert changed


def test_inference_capture_preserves_exact_stable_bytes(tmp_path):
    candidate = tmp_path / "stable.json"
    expected = b'{"synthetic": [true, false, null]}'
    candidate.write_bytes(expected)
    assert audit._capture_inference_bytes(candidate) == expected
    assert audit._decode_inference_json(expected) == {"synthetic": [True, False, None]}
