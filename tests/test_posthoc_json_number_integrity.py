"""Strict numeric parsing of untrusted local post-hoc evaluator JSON.

Every input is synthetic. No evaluator or treatment is invoked.
"""
import json

import pytest

from scripts import evaluate_posthoc_support as evaluator


@pytest.mark.parametrize(
    ("number", "reason"),
    [
        ("NaN", "nonstandard JSON numeric constant"),
        ("Infinity", "nonstandard JSON numeric constant"),
        ("-Infinity", "nonstandard JSON numeric constant"),
        ("1e400", "nonfinite JSON numeric value"),
        ("-1e400", "nonfinite JSON numeric value"),
        ("9" * 129, "oversized JSON numeric token"),
        ("1e" + "9" * 127, "oversized JSON numeric token"),
        ("0." + "1" * 127, "oversized JSON numeric token"),
    ],
)
def test_invalid_nested_numeric_token_rejected(tmp_path, number, reason):
    path = tmp_path / "trace.json"
    path.write_text(
        '{"experiment": {"unused_nested_metadata": [{"value": ' + number + '}]}}',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match=reason):
        evaluator._load_json(path)


def test_deeply_nested_json_exits_with_source_error(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text('{"meta": ' + "[" * 1100 + "0" + "]" * 1100 + "}", encoding="utf-8")
    with pytest.raises(SystemExit, match="Invalid JSON file"):
        evaluator._load_json(path)


def test_valid_finite_json_numbers_remain_unchanged(tmp_path):
    expected = {
        "meta": {
            "counts": [0, 10, -2],
            "finite": [1.0, 1e-100, -1e100, 1.234],
            "flag": False,
        }
    }
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(expected), encoding="utf-8")
    assert evaluator._load_json(path) == expected


def test_nonobject_top_level_rejected(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(SystemExit, match="top level must be an object"):
        evaluator._load_json(path)


def test_duplicate_keys_still_rejected(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text('{"meta": {"cost": 1, "cost": 2}}', encoding="utf-8")
    with pytest.raises(SystemExit, match="duplicate JSON key"):
        evaluator._load_json(path)


def test_numeric_gate_is_before_any_model_import():
    source = open(evaluator.__file__, encoding="utf-8").read()
    assert (
        source.index("payload, trace_sha256 = _load_json(trace_path, include_sha256=True)")
        < source.index("from agent.llm_utils import UsageTracker")
    )
