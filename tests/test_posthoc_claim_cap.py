import json

import pytest

from scripts import evaluate_posthoc_support


def _cached_evaluation(**overrides):
    payload = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "variant_id": "D3",
        "task_id": "main-01",
        "run_id": "run-d3-main-01",
        "max_claims": 12,
        "claims_checked": 12,
        "supported": 8,
        "partially_supported": 2,
        "unsupported": 1,
        "contradicted": 1,
        "strict_support_rate": 8 / 12,
        "examples": [],
    }
    payload.update(overrides)
    return payload


def test_posthoc_normalizer_enforces_frozen_claim_cap():
    raw = json.dumps(
        _cached_evaluation(
            claims_checked=13,
            supported=9,
        )
    )

    with pytest.raises(ValueError, match="exceeds max_claims=12"):
        evaluate_posthoc_support._normalize_evaluator_output(raw)


def test_cached_posthoc_evaluation_rejects_claims_above_cap(tmp_path):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(
            _cached_evaluation(
                claims_checked=13,
                supported=9,
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="exceeds max_claims=12"):
        evaluate_posthoc_support._load_cached_evaluation(
            path,
            expected_variant="D3",
            expected_task_id="main-01",
            expected_run_id="run-d3-main-01",
        )


@pytest.mark.parametrize("declared_cap", [None, True, 11, 13, "12"])
def test_cached_posthoc_evaluation_requires_frozen_cap_metadata(
    tmp_path, declared_cap
):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(_cached_evaluation(max_claims=declared_cap)),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="max_claims metadata must equal 12"):
        evaluate_posthoc_support._load_cached_evaluation(
            path,
            expected_variant="D3",
            expected_task_id="main-01",
            expected_run_id="run-d3-main-01",
        )


def test_cached_posthoc_evaluation_accepts_valid_record(tmp_path):
    expected = _cached_evaluation()
    path = tmp_path / "cached.json"
    path.write_text(json.dumps(expected), encoding="utf-8")

    assert evaluate_posthoc_support._load_cached_evaluation(
        path,
        expected_variant="D3",
        expected_task_id="main-01",
        expected_run_id="run-d3-main-01",
    ) == expected


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 2, "schema_version must equal 1"),
        ("schema_version", True, "schema_version must equal 1"),
        ("schema_version", 1.0, "schema_version must equal 1"),
        ("study_id", "other-study", "study_id must equal budget-main-v1"),
        ("variant_id", "D6", "variant_id must equal D3"),
        ("task_id", "main-02", "task_id must equal main-01"),
        ("run_id", "other-run", "run_id must equal run-d3-main-01"),
    ],
)
def test_cached_posthoc_evaluation_is_bound_to_expected_trace_identity(
    tmp_path, field, value, message
):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(_cached_evaluation(**{field: value})),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=message):
        evaluate_posthoc_support._load_cached_evaluation(
            path,
            expected_variant="D3",
            expected_task_id="main-01",
            expected_run_id="run-d3-main-01",
        )


@pytest.mark.parametrize(
    "rate", [None, True, "0.6667", -0.1, 0.7, (8 / 12) + 5e-13]
)
def test_cached_posthoc_evaluation_rejects_invalid_or_inconsistent_rate(
    tmp_path, rate
):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(_cached_evaluation(strict_support_rate=rate)),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="strict_support_rate must equal supported / claims_checked"):
        evaluate_posthoc_support._load_cached_evaluation(
            path,
            expected_variant="D3",
            expected_task_id="main-01",
            expected_run_id="run-d3-main-01",
        )


def _completed_trace_payload(**trace_overrides):
    trace = {
        "completed": True,
        "variant_id": "D3",
        "task_id": "main-01",
        "run_id": "run-d3-main-01",
    }
    trace.update(trace_overrides)
    return {
        "experiment": {"variant_id": "D3", "task_id": "main-01"},
        "trace": trace,
    }


def test_completed_trace_identity_is_bound_to_directory_filename_and_metadata(
    tmp_path
):
    path = tmp_path / "D3" / "run-d3-main-01.json"

    trace, task_id, run_id = evaluate_posthoc_support._validated_completed_trace(
        path,
        _completed_trace_payload(),
        expected_variant="D3",
    )

    assert trace["completed"] is True
    assert task_id == "main-01"
    assert run_id == "run-d3-main-01"


@pytest.mark.parametrize(
    ("path_variant", "filename", "expected_variant", "payload", "message"),
    [
        (
            "D3",
            "run-d3-main-01.json",
            "D3",
            _completed_trace_payload(variant_id="D6"),
            "variant_id mismatch",
        ),
        (
            "D3",
            "run-d3-main-01.json",
            "D3",
            {
                **_completed_trace_payload(),
                "experiment": {"variant_id": "D6", "task_id": "main-01"},
            },
            "variant_id mismatch",
        ),
        (
            "D3",
            "run-d3-main-01.json",
            "D3",
            _completed_trace_payload(task_id=None),
            "missing task_id",
        ),
        (
            "D3",
            "wrong-run.json",
            "D3",
            _completed_trace_payload(),
            "filename does not match run_id",
        ),
    ],
)
def test_completed_trace_identity_rejects_misbound_inputs(
    tmp_path, path_variant, filename, expected_variant, payload, message
):
    path = tmp_path / path_variant / filename

    with pytest.raises(SystemExit, match=message):
        evaluate_posthoc_support._validated_completed_trace(
            path,
            payload,
            expected_variant=expected_variant,
        )


def test_cached_posthoc_evaluation_rejects_zero_claims(tmp_path):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(
            _cached_evaluation(
                claims_checked=0,
                supported=0,
                partially_supported=0,
                unsupported=0,
                contradicted=0,
                strict_support_rate=0.0,
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="claims_checked must be positive"):
        evaluate_posthoc_support._load_cached_evaluation(
            path,
            expected_variant="D3",
            expected_task_id="main-01",
            expected_run_id="run-d3-main-01",
        )
