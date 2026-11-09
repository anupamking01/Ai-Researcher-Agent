"""Synthetic-only bounded JSON decoder tests for blinded-freeze custody."""

import json

import pytest

from scripts import verify_human_eval_freeze as verifier


@pytest.mark.parametrize("container", ("array", "object"))
def test_freeze_json_rejects_excessive_nesting_before_decoder(container):
    if container == "array":
        raw = ('{"item":' + "[" * 32 + "0" + "]" * 32 + "}").encode()
    else:
        raw = ('{"item":' + '{"a":' * 32 + "0" + "}" * 32 + "}").encode()
    with pytest.raises(ValueError, match="synthetic manifest exceeds 32-level JSON nesting"):
        verifier._load_json_bytes(raw, label="synthetic manifest")


def test_freeze_json_accepts_exact_nesting_boundary():
    # The root object counts as level one.
    raw = ('{"item":' + "[" * 31 + "0" + "]" * 31 + "}").encode()
    value = verifier._load_json_bytes(raw, label="synthetic agreement")
    cursor = value["item"]
    for _ in range(30):
        assert isinstance(cursor, list) and len(cursor) == 1
        cursor = cursor[0]
    assert cursor == [0]


def test_freeze_json_does_not_count_brackets_in_quoted_text():
    content = {"text": ('{"[}]' * 40)}
    raw = json.dumps(content).encode()
    assert verifier._load_json_bytes(raw, label="synthetic manifest") == content


def test_freeze_json_escaped_quote_and_backslash_do_not_change_nesting():
    content = {"text": '\\\"[{}]' * 30}
    raw = json.dumps(content).encode()
    assert verifier._load_json_bytes(raw, label="synthetic agreement") == content


@pytest.mark.parametrize("integer", ("1" * 21, "-" + "9" * 21))
def test_freeze_json_rejects_oversized_integer_tokens(integer):
    raw = ('{"rated_count":' + integer + "}").encode()
    with pytest.raises(ValueError, match="synthetic manifest exceeds 20-digit JSON integer"):
        verifier._load_json_bytes(raw, label="synthetic manifest")


def test_freeze_json_accepts_in_domain_integer_and_original_numeric_guard():
    assert verifier._load_json_bytes(
        b'{"n":40,"agreement":0.75}', label="synthetic agreement"
    ) == {"n": 40, "agreement": 0.75}
    with pytest.raises(ValueError, match="non-finite JSON number"):
        verifier._load_json_bytes(
            b'{"agreement":1e999}', label="synthetic agreement"
        )
