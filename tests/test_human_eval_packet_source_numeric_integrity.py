"""Synthetic-only source JSON numeric-integrity tests for blinded packet creation.

No archived treatment evidence, human rating, or API outcome is generated.
"""
import pytest

from scripts import build_human_eval_packet as packet


@pytest.mark.parametrize(
    "raw,reason",
    [
        (b'{"unused":NaN}', "nonstandard JSON constant"),
        (b'{"unused":Infinity}', "nonstandard JSON constant"),
        (b'{"unused":-Infinity}', "nonstandard JSON constant"),
        (b'{"unused":1e400}', "nonfinite JSON numeric value"),
        (b'{"unused":-1e400}', "nonfinite JSON numeric value"),
        (b'{"nested":[{"not_scored":1e400}]}', "nonfinite JSON numeric value"),
        (
            b'{"unused":' + b"9" * (packet.MAX_SOURCE_JSON_NUMBER_TOKEN_CHARS + 1) + b"}",
            "oversized JSON numeric token",
        ),
        (
            b'{"unused":0.' + b"1" * packet.MAX_SOURCE_JSON_NUMBER_TOKEN_CHARS + b"}",
            "oversized JSON numeric token",
        ),
        (
            b'{"unused":1e+' + b"0" * packet.MAX_SOURCE_JSON_NUMBER_TOKEN_CHARS + b"}",
            "oversized JSON numeric token",
        ),
    ],
)
def test_rejects_nonstandard_nonfinite_or_oversized_numbers_at_any_depth(raw, reason):
    with pytest.raises(ValueError, match=reason):
        packet._load_json_object(raw, label="synthetic trace")


def test_accepts_finite_json_numbers_and_null_without_changing_values():
    raw = b'{"records":[{"count":0,"cost":2.5e-6},' \
          b'{"count":-4,"cost":-0.0}],"missing":null,"science":1e308}'
    result = packet._load_json_object(raw, label="synthetic trace")
    assert result["records"] == [
        {"count": 0, "cost": 2.5e-6},
        {"count": -4, "cost": -0.0},
    ]
    assert result["science"] == 1e308
    assert result["missing"] is None


def test_duplicate_keys_still_rejected_in_nested_source():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        packet._load_json_object(
            b'{"trace":{"a":1,"a":2}}', label="synthetic trace"
        )


def test_frozen_task_manifest_does_not_ignore_nonfinite_auxiliary_metadata(tmp_path):
    source = tmp_path / "tasks.json"
    source.write_bytes(
        b'{"frozen_before_execution":true,"task_set_id":"synthetic",'
        b'"tasks":[{"id":"task-01","question":"Synthetic question"}],'
        b'"optional_metadata":{"unused_numeric_value":1e400}}'
    )
    with pytest.raises(ValueError, match="nonfinite JSON numeric value"):
        packet._load_task_manifest(source)


def test_deeply_nested_untrusted_json_is_a_clean_validation_failure():
    content = b'{"nested":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"
    with pytest.raises(ValueError, match="valid bounded UTF-8 JSON"):
        packet._load_json_object(content, label="synthetic trace")
