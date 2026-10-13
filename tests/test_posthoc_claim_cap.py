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


def _configure_resume_main(tmp_path, monkeypatch, task_ids=("main-01", "main-02")):
    trace_root = tmp_path / "outputs" / "experiment_traces"
    eval_root = tmp_path / "outputs" / "posthoc_evaluations"
    pricing_file = tmp_path / "experiments" / "pricing.json"
    pricing_file.parent.mkdir(parents=True)
    pricing_file.write_text(json.dumps(PRICING), encoding="utf-8")

    for task_id in task_ids:
        run_id = f"run-d3-{task_id}"
        trace_path = trace_root / "D3" / f"{run_id}.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_payload = _completed_trace_payload(
            task_id=task_id,
            run_id=run_id,
            question=f"Question for {task_id}",
            successful_source_count=0,
        )
        trace_payload["experiment"]["task_id"] = task_id
        trace_path.write_text(
            json.dumps(trace_payload),
            encoding="utf-8",
        )
        report_path = tmp_path / "outputs" / run_id / "research_report.md"
        report_path.parent.mkdir(parents=True)
        report_path.write_text(f"Report for {task_id}\n", encoding="utf-8")

    monkeypatch.setattr(evaluate_posthoc_support, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(evaluate_posthoc_support, "TRACE_ROOT", trace_root)
    monkeypatch.setattr(evaluate_posthoc_support, "EVAL_ROOT", eval_root)
    monkeypatch.setattr(evaluate_posthoc_support, "PRICING_FILE", pricing_file)
    monkeypatch.setattr(evaluate_posthoc_support, "VARIANTS", ("D3",))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SMART_LLM_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("TEMPERATURE", "1")
    monkeypatch.setattr(
        evaluate_posthoc_support.sys,
        "argv",
        ["evaluate_posthoc_support.py", "--max-evaluator-cost-usd", "1.25"],
    )
    return eval_root


def test_resume_preflights_later_cached_identity_before_first_model_call(
    tmp_path, monkeypatch
):
    eval_root = _configure_resume_main(tmp_path, monkeypatch)
    invalid_cache = eval_root / "D3" / "main-02.json"
    invalid_cache.parent.mkdir(parents=True)
    invalid_cache.write_text(
        json.dumps(
            _cached_evaluation(
                task_id="main-99",
                run_id="run-d3-main-02",
            )
        ),
        encoding="utf-8",
    )

    model_calls = []

    def fail_if_called(**kwargs):
        model_calls.append(kwargs)
        raise AssertionError("model call occurred before cache preflight completed")

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        fail_if_called,
    )

    with pytest.raises(SystemExit, match="task_id must equal main-02"):
        evaluate_posthoc_support.main()

    assert model_calls == []


def test_resume_preflight_rejects_cached_files_outside_trace_matrix(
    tmp_path, monkeypatch
):
    eval_root = tmp_path / "outputs" / "posthoc_evaluations"
    unexpected = eval_root / "D6" / "main-99.json"
    unexpected.parent.mkdir(parents=True)
    unexpected.write_text(json.dumps(_cached_evaluation()), encoding="utf-8")

    run_id = "run-d3-main-01"
    report_path = tmp_path / "outputs" / run_id / "research_report.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("Report for main-01\n", encoding="utf-8")
    expected = [
        (
            "D3",
            tmp_path / "outputs" / "experiment_traces" / "D3" / f"{run_id}.json",
            {
                "run_id": run_id,
                "question": "Question for main-01",
                "successful_source_count": 0,
            },
            "main-01",
            run_id,
        )
    ]

    monkeypatch.setattr(evaluate_posthoc_support, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(evaluate_posthoc_support, "EVAL_ROOT", eval_root)

    with pytest.raises(SystemExit, match="Unexpected cached post-hoc evaluation"):
        evaluate_posthoc_support._preflight_evaluator_resume(
            expected,
            pricing=PRICING,
            evaluator_model="gpt-5.6-terra",
            evaluator_temperature=1.0,
        )


def test_resume_preflight_rejects_duplicate_evaluator_destination(
    tmp_path, monkeypatch
):
    eval_root = tmp_path / "outputs" / "posthoc_evaluations"
    expected = []
    for suffix in ("a", "b"):
        run_id = f"run-d3-main-01-{suffix}"
        report_path = tmp_path / "outputs" / run_id / "research_report.md"
        report_path.parent.mkdir(parents=True)
        report_path.write_text(f"Report {suffix}\n", encoding="utf-8")
        expected.append(
            (
                "D3",
                tmp_path / "outputs" / "experiment_traces" / "D3" / f"{run_id}.json",
                {
                    "run_id": run_id,
                    "question": "Question for main-01",
                    "successful_source_count": 0,
                },
                "main-01",
                run_id,
            )
        )

    monkeypatch.setattr(evaluate_posthoc_support, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(evaluate_posthoc_support, "EVAL_ROOT", eval_root)

    with pytest.raises(SystemExit, match="duplicate evaluator destination"):
        evaluate_posthoc_support._preflight_evaluator_resume(
            expected,
            pricing=PRICING,
            evaluator_model="gpt-5.6-terra",
            evaluator_temperature=1.0,
        )


def _record_evaluator_usage(kwargs):
    kwargs["usage_tracker"].record_response(
        "gpt-5.6-terra",
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            }
        },
    )


def _evaluator_result(supported=7):
    return json.dumps(
        {
            "claims_checked": 12,
            "supported": supported,
            "partially_supported": 12 - supported,
            "unsupported": 0,
            "contradicted": 0,
            "examples": [],
        }
    )


def test_resume_fails_closed_if_later_cache_appears_after_preflight(
    tmp_path, monkeypatch
):
    eval_root = _configure_resume_main(tmp_path, monkeypatch)
    later_cache = eval_root / "D3" / "main-02.json"
    model_calls = []

    def publish_later_cache(**kwargs):
        model_calls.append(kwargs)
        _record_evaluator_usage(kwargs)
        if len(model_calls) == 1:
            later_cache.parent.mkdir(parents=True, exist_ok=True)
            later_cache.write_text(
                json.dumps(
                    _cached_evaluation(
                        task_id="main-02",
                        run_id="run-d3-main-02",
                    )
                ),
                encoding="utf-8",
            )
        return _evaluator_result()

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        publish_later_cache,
    )

    with pytest.raises(SystemExit, match="resume state changed after preflight"):
        evaluate_posthoc_support.main()

    assert len(model_calls) == 1
    assert json.loads(later_cache.read_text(encoding="utf-8"))["supported"] == 8


def test_resume_never_overwrites_cache_published_during_model_call(
    tmp_path, monkeypatch
):
    eval_root = _configure_resume_main(tmp_path, monkeypatch, task_ids=("main-01",))
    concurrent_cache = eval_root / "D3" / "main-01.json"

    def publish_current_cache(**kwargs):
        _record_evaluator_usage(kwargs)
        concurrent_cache.parent.mkdir(parents=True, exist_ok=True)
        concurrent_cache.write_text(
            json.dumps(_cached_evaluation()),
            encoding="utf-8",
        )
        return _evaluator_result()

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        publish_current_cache,
    )

    with pytest.raises(SystemExit, match="cache appeared during model call"):
        evaluate_posthoc_support.main()

    assert json.loads(concurrent_cache.read_text(encoding="utf-8"))["supported"] == 8
