import json

import pytest

from scripts import evaluate_posthoc_support


PRICING = {
    "models": {
        "gpt-5.6-terra": {"input": 2.0, "output": 12.0},
    }
}
EXPECTED_COST = (100 / 1_000_000) * 2.0 + (20 / 1_000_000) * 12.0


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
        "evaluator_model": "gpt-5.6-terra",
        "temperature": 1.0,
        "evidence_status": "retrieved_evidence",
        "provider_usage_by_model": {
            "gpt-5.6-terra": {
                "model_calls": 1,
                "unavailable_calls": 0,
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            }
        },
        "total_tokens": 120,
        "estimated_cost_usd": EXPECTED_COST,
        "cost_method": "frozen uncached rates",
    }
    payload.update(overrides)
    return payload


def _load_cached(path, **overrides):
    kwargs = {
        "expected_variant": "D3",
        "expected_task_id": "main-01",
        "expected_run_id": "run-d3-main-01",
        "expected_evaluator_model": "gpt-5.6-terra",
        "expected_temperature": 1.0,
        "expected_evidence_status": "retrieved_evidence",
        "pricing": PRICING,
    }
    kwargs.update(overrides)
    return evaluate_posthoc_support._load_cached_evaluation(path, **kwargs)


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
        _load_cached(path)


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
        _load_cached(path)


def test_cached_posthoc_evaluation_accepts_valid_record(tmp_path):
    expected = _cached_evaluation()
    path = tmp_path / "cached.json"
    path.write_text(json.dumps(expected), encoding="utf-8")

    assert _load_cached(path) == expected


def test_cached_posthoc_evaluation_derives_missing_legacy_evidence_status(tmp_path):
    expected = _cached_evaluation()
    expected.pop("evidence_status")
    path = tmp_path / "cached.json"
    path.write_text(json.dumps(expected), encoding="utf-8")

    loaded = _load_cached(path)

    assert loaded["evidence_status"] == "retrieved_evidence"


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
        _load_cached(path)


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
        _load_cached(path)


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
        _load_cached(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("evaluator_model", "gpt-5.6-luna", "evaluator_model must equal"),
        ("temperature", True, "temperature must equal"),
        ("temperature", "1", "temperature must equal"),
        ("temperature", 0.0, "temperature must equal"),
        ("evidence_status", "zero_successful_sources", "evidence_status must equal"),
        ("cost_method", "provider invoice", "cost_method must equal"),
        ("total_tokens", True, "total_tokens must equal provider usage"),
        ("total_tokens", 121, "total_tokens must equal provider usage"),
        ("estimated_cost_usd", True, "estimated_cost_usd must equal recomputed cost"),
        ("estimated_cost_usd", -1.0, "estimated_cost_usd must equal recomputed cost"),
        ("estimated_cost_usd", EXPECTED_COST + 1e-12, "estimated_cost_usd must equal recomputed cost"),
    ],
)
def test_cached_posthoc_evaluation_rejects_provenance_or_cost_drift(
    tmp_path, field, value, message
):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(_cached_evaluation(**{field: value})),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match=message):
        _load_cached(path)


@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"gpt-5.6-luna": {"model_calls": 1, "unavailable_calls": 0, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
        {"gpt-5.6-terra": {"model_calls": True, "unavailable_calls": 0, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
        {"gpt-5.6-terra": {"model_calls": 1, "unavailable_calls": 1, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
        {"gpt-5.6-terra": {"model_calls": 1, "unavailable_calls": 0, "prompt_tokens": -1, "completion_tokens": 20, "total_tokens": 19}},
        {"gpt-5.6-terra": {"model_calls": 1, "unavailable_calls": 0, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 999}},
    ],
)
def test_cached_posthoc_evaluation_rejects_invalid_provider_usage(tmp_path, usage):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(_cached_evaluation(provider_usage_by_model=usage)),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="provider_usage_by_model is invalid"):
        _load_cached(path)


def test_existing_evaluator_cost_rejects_invalid_cached_accounting(
    tmp_path, monkeypatch
):
    root = tmp_path / "posthoc_evaluations"
    path = root / "D3" / "main-01.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(_cached_evaluation(estimated_cost_usd=-1.0)),
        encoding="utf-8",
    )
    monkeypatch.setattr(evaluate_posthoc_support, "EVAL_ROOT", root)

    with pytest.raises(SystemExit, match="estimated_cost_usd must equal recomputed cost"):
        evaluate_posthoc_support._existing_evaluator_cost(
            PRICING,
            expected_evaluator_model="gpt-5.6-terra",
            expected_temperature=1.0,
        )
