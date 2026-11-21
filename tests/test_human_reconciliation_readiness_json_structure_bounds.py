"""Synthetic-only resource-bound tests for reconciliation-readiness JSON.

No human ratings, new outcomes, or experimental treatment outputs are used.
"""

import json

import pytest

from scripts import verify_human_reconciliation_readiness as readiness


@pytest.mark.parametrize("open_char, close_char", [("[", "]"), ("{", "}")])
def test_json_nesting_beyond_limit_fails_before_recursive_decode(open_char, close_char):
    # JSON object nesting uses one key in each inner object; the limit check
    # is structural and occurs before the decoder can recurse into the body.
    if open_char == "[":
        inner = "[" * readiness.MAX_READINESS_JSON_NESTING_DEPTH + "0" + "]" * readiness.MAX_READINESS_JSON_NESTING_DEPTH
    else:
        inner = '{"x":' * readiness.MAX_READINESS_JSON_NESTING_DEPTH + "0" + "}" * readiness.MAX_READINESS_JSON_NESTING_DEPTH
    content = ('{"payload":' + inner + "}").encode()
    with pytest.raises(ValueError, match="JSON nesting limit"):
        readiness._load(content, "synthetic human analysis")


@pytest.mark.parametrize("open_char, close_char", [("[", "]"), ("{", "}")])
def test_json_nesting_exact_boundary_is_allowed(open_char, close_char):
    # Account for the outer document object: its depth is one.
    inner_depth = readiness.MAX_READINESS_JSON_NESTING_DEPTH - 1
    if open_char == "[":
        inner = "[" * inner_depth + "0" + "]" * inner_depth
    else:
        inner = '{"x":' * inner_depth + "0" + "}" * inner_depth
    content = ('{"payload":' + inner + "}").encode()
    assert "payload" in readiness._load(content, "synthetic human analysis")


def test_brackets_in_escaped_quoted_strings_do_not_count_as_nesting():
    note = r'embedded escaped quote \" and backslash \\ ' + "[{" * 200
    payload = {"note": note, "value": {"items": [0, 1, 2]}}
    assert readiness._load(json.dumps(payload).encode(), "synthetic analysis") == payload


@pytest.mark.parametrize(
    "token",
    [
        "0." + "1" * 127,
        "1e+" + "0" * 126,
        "-0." + "1" * 126,
    ],
)
def test_oversized_finite_float_tokens_are_rejected(token):
    assert len(token) > readiness.MAX_READINESS_JSON_FLOAT_TOKEN_CHARS
    with pytest.raises(ValueError, match="oversized JSON float token"):
        readiness._load(('{"value":' + token + "}").encode(), "synthetic analysis")


@pytest.mark.parametrize(
    "token, expected",
    [
        ("0." + "1" * 126, float("0." + "1" * 126)),
        ("1e+" + "0" * 125, 1.0),
    ],
)
def test_finite_float_tokens_at_boundary_remain_valid(token, expected):
    assert len(token) == readiness.MAX_READINESS_JSON_FLOAT_TOKEN_CHARS
    assert readiness._load(('{"value":' + token + "}").encode(), "synthetic analysis") == {"value": expected}


def test_invalid_json_syntax_retains_controlled_error():
    with pytest.raises(ValueError, match="not valid UTF-8 JSON"):
        readiness._load(b'{"payload": [1, 2,]}', "synthetic analysis")


def test_preserved_automated_analysis_still_decodes_unchanged():
    source = (readiness.ROOT / readiness.AUTO_JSON).read_bytes()
    payload = readiness._load(source, "automated analysis")
    assert payload["study_id"] == readiness.STUDY
    assert payload["primary_outcome"] == "strict_support_rate"
