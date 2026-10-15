import hashlib
import json

import pytest

from scripts import evaluate_posthoc_support


PRICING = {
    "unit": "per_1m_text_tokens",
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


def _fingerprint_text(text):
    content = text.encode("utf-8")
    return {
        "byte_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _input_fingerprints(*, question, report, evidence, prompt):
    return {
        "algorithm": "sha256",
        "encoding": "utf-8",
        "question": _fingerprint_text(question),
        "report": _fingerprint_text(report),
        "evidence": _fingerprint_text(evidence),
        "prompt": _fingerprint_text(prompt),
    }


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


def test_cached_posthoc_evaluation_rejects_symlinked_input(tmp_path):
    target = tmp_path / "outside-cache.json"
    target.write_text(json.dumps(_cached_evaluation()), encoding="utf-8")
    path = tmp_path / "cached.json"
    path.symlink_to(target)

    with pytest.raises(SystemExit, match="must be a regular non-symlink file"):
        _load_cached(path)


def test_cached_posthoc_evaluation_derives_missing_legacy_evidence_status(tmp_path):
    expected = _cached_evaluation()
    expected.pop("evidence_status")
    path = tmp_path / "cached.json"
    path.write_text(json.dumps(expected), encoding="utf-8")

    loaded = _load_cached(path)

    assert loaded["evidence_status"] == "retrieved_evidence"


def test_schema_v2_cache_requires_explicit_evidence_status(tmp_path):
    question = "Question"
    report = "Report\n"
    evidence = "Evidence\n"
    from logic.prompts import generate_verification_prompt

    prompt = generate_verification_prompt(
        question,
        report,
        evidence,
        max_claims=evaluate_posthoc_support.MAX_CLAIMS,
    )
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(
            _cached_evaluation(
                schema_version=2,
                evidence_status=None,
                input_fingerprints=_input_fingerprints(
                    question=question,
                    report=report,
                    evidence=evidence,
                    prompt=prompt,
                ),
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="evidence_status must equal"):
        _load_cached(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", 3, "schema_version must equal 1 or 2"),
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
        "source_budget": 3,
        "source_count": 0,
        "successful_source_count": 0,
        "failed_source_count": 0,
        "query_count": 1,
        "search_call_count": 1,
        "scheduled_urls": [],
        "successful_urls": [],
        "failed_urls": [],
        "latency_seconds": 1.0,
        "report_words": 100,
        "usage_accounting_status": "provider_usage_complete",
        "provider_usage_by_model": {
            "gpt-5.6-terra": {
                "model_calls": 1,
                "unavailable_calls": 0,
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            }
        },
        "model_call_count": 1,
        "unavailable_usage_call_count": 0,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }
    trace.update(trace_overrides)
    return {
        "schema_version": 2,
        "experiment": {
            "variant_id": "D3",
            "task_id": "main-01",
            "source_budget": 3,
        },
        "trace": trace,
    }


def test_cached_posthoc_evaluation_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "cached.json"
    raw = json.dumps(_cached_evaluation())
    raw = raw.replace(
        '"task_id": "main-01"',
        '"task_id": "main-99", "task_id": "main-01"',
        1,
    )
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(SystemExit, match="duplicate JSON key: task_id"):
        _load_cached(path)


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


def test_resume_preflights_nonregular_later_cache_before_first_model_call(
    tmp_path, monkeypatch
):
    eval_root = _configure_resume_main(tmp_path, monkeypatch)
    invalid_cache = eval_root / "D3" / "main-02.json"
    invalid_cache.mkdir(parents=True)

    model_calls = []

    def fail_if_called(**kwargs):
        model_calls.append(kwargs)
        raise AssertionError("model call occurred before cache preflight completed")

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        fail_if_called,
    )

    with pytest.raises(SystemExit, match="must be a regular non-symlink file"):
        evaluate_posthoc_support.main()

    assert model_calls == []


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda trace: trace.update(source_count=1),
            "source count ledger mismatch",
        ),
        (
            lambda trace: trace.update(completed=1),
            "completed must be a boolean",
        ),
    ],
)
def test_resume_preflights_treatment_ledgers_before_first_model_call(
    tmp_path, monkeypatch, mutate, message
):
    _configure_resume_main(tmp_path, monkeypatch, task_ids=("main-01",))
    trace_path = (
        tmp_path
        / "outputs"
        / "experiment_traces"
        / "D3"
        / "run-d3-main-01.json"
    )
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    mutate(payload["trace"])
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    model_calls = []

    def fail_if_called(**kwargs):
        model_calls.append(kwargs)
        raise AssertionError("model call occurred before trace preflight completed")

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        fail_if_called,
    )

    with pytest.raises(SystemExit, match=message):
        evaluate_posthoc_support.main()

    assert model_calls == []


def test_resume_rejects_symlinked_report_before_first_model_call(
    tmp_path, monkeypatch
):
    _configure_resume_main(tmp_path, monkeypatch, task_ids=("main-01",))
    report_path = (
        tmp_path
        / "outputs"
        / "run-d3-main-01"
        / "research_report.md"
    )
    outside_report = tmp_path / "outside-report.md"
    outside_report.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    report_path.unlink()
    report_path.symlink_to(outside_report)

    model_calls = []

    def fail_if_called(**kwargs):
        model_calls.append(kwargs)
        raise AssertionError("model call occurred before report preflight completed")

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        fail_if_called,
    )

    with pytest.raises(SystemExit, match="report must be a regular non-symlink file"):
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


def test_new_cache_binds_exact_evaluator_prompt_inputs(tmp_path, monkeypatch):
    eval_root = _configure_resume_main(tmp_path, monkeypatch, task_ids=("main-01",))
    captured = []

    def complete_evaluation(**kwargs):
        captured.append(kwargs["messages"][0]["content"])
        _record_evaluator_usage(kwargs)
        return _evaluator_result()

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        complete_evaluation,
    )

    assert evaluate_posthoc_support.main() == 0

    cache = json.loads(
        (eval_root / "D3" / "main-01.json").read_text(encoding="utf-8")
    )
    question = "Question for main-01"
    report = "Report for main-01\n"
    evidence = evaluate_posthoc_support.NO_EVIDENCE_SENTINEL
    assert cache["schema_version"] == 2
    assert cache["input_fingerprints"] == _input_fingerprints(
        question=question,
        report=report,
        evidence=evidence,
        prompt=captured[0],
    )


def test_resume_rejects_cache_bound_to_different_report_before_model_call(
    tmp_path, monkeypatch
):
    eval_root = _configure_resume_main(tmp_path, monkeypatch, task_ids=("main-01",))
    question = "Question for main-01"
    original_report = "Original report\n"
    evidence = evaluate_posthoc_support.NO_EVIDENCE_SENTINEL
    from logic.prompts import generate_verification_prompt

    original_prompt = generate_verification_prompt(
        question,
        original_report,
        evidence,
        max_claims=evaluate_posthoc_support.MAX_CLAIMS,
    )
    cache_path = eval_root / "D3" / "main-01.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        json.dumps(
            _cached_evaluation(
                schema_version=2,
                input_fingerprints=_input_fingerprints(
                    question=question,
                    report=original_report,
                    evidence=evidence,
                    prompt=original_prompt,
                ),
            )
        ),
        encoding="utf-8",
    )

    model_calls = []

    def fail_if_called(**kwargs):
        model_calls.append(kwargs)
        raise AssertionError("model call occurred before cache input validation")

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        fail_if_called,
    )

    with pytest.raises(SystemExit, match="input_fingerprints must match"):
        evaluate_posthoc_support.main()

    assert model_calls == []


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


def test_overspend_preserves_cell_cache_without_publishing_aggregate_outputs(
    tmp_path, monkeypatch
):
    eval_root = _configure_resume_main(tmp_path, monkeypatch, task_ids=("main-01",))
    monkeypatch.setattr(
        evaluate_posthoc_support.sys,
        "argv",
        ["evaluate_posthoc_support.py", "--max-evaluator-cost-usd", "0.0001"],
    )

    def complete_evaluation(**kwargs):
        _record_evaluator_usage(kwargs)
        return _evaluator_result()

    monkeypatch.setattr(
        "agent.llm_utils.create_chat_completion",
        complete_evaluation,
    )

    with pytest.raises(SystemExit, match="Evaluator completed but exceeded cap"):
        evaluate_posthoc_support.main()

    cached = eval_root / "D3" / "main-01.json"
    assert json.loads(cached.read_text(encoding="utf-8"))["task_id"] == "main-01"
    assert not (tmp_path / "outputs" / "posthoc_support_summary.json").exists()
    assert not (tmp_path / "outputs" / "posthoc_support_runs.csv").exists()


def test_cache_publication_is_invisible_until_atomic_commit(tmp_path, monkeypatch):
    path = tmp_path / "posthoc_evaluations" / "D3" / "main-01.json"
    expected = _cached_evaluation()
    real_link = evaluate_posthoc_support.os.link
    observed = []

    def inspect_then_link(source, destination):
        observed.append(
            {
                "destination_absent": not path.exists(),
                "staged_payload": json.loads(source.read_text(encoding="utf-8")),
            }
        )
        real_link(source, destination)

    monkeypatch.setattr(evaluate_posthoc_support.os, "link", inspect_then_link)

    evaluate_posthoc_support._publish_evaluation_cache(path, expected)

    assert observed == [
        {"destination_absent": True, "staged_payload": expected}
    ]
    assert json.loads(path.read_text(encoding="utf-8")) == expected
    assert list(path.parent.glob(".main-01.json.*.tmp")) == []


def test_cache_publication_preserves_concurrent_winner(tmp_path, monkeypatch):
    path = tmp_path / "posthoc_evaluations" / "D3" / "main-01.json"
    winner = b'{"owner":"concurrent evaluator"}\n'

    def publish_winner_then_collide(_source, destination):
        destination.write_bytes(winner)
        raise FileExistsError(destination)

    monkeypatch.setattr(
        evaluate_posthoc_support.os,
        "link",
        publish_winner_then_collide,
    )

    with pytest.raises(FileExistsError):
        evaluate_posthoc_support._publish_evaluation_cache(
            path,
            _cached_evaluation(),
        )

    assert path.read_bytes() == winner
    assert list(path.parent.glob(".main-01.json.*.tmp")) == []


def test_cache_publication_cleans_staging_after_write_sync_failure(
    tmp_path, monkeypatch
):
    path = tmp_path / "posthoc_evaluations" / "D3" / "main-01.json"

    def fail_sync(_descriptor):
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(evaluate_posthoc_support.os, "fsync", fail_sync)

    with pytest.raises(OSError, match="synthetic fsync failure"):
        evaluate_posthoc_support._publish_evaluation_cache(
            path,
            _cached_evaluation(),
        )

    assert not path.exists()
    assert list(path.parent.glob(".main-01.json.*.tmp")) == []
