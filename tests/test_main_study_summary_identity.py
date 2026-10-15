import json

import pytest

from scripts import summarize_budget_main_study


def _trace_payload(*, task_id="main-01", run_id="run-d3-main-01"):
    return {
        "experiment": {"variant_id": "D3", "task_id": task_id},
        "trace": {
            "completed": True,
            "variant_id": "D3",
            "task_id": task_id,
            "run_id": run_id,
            "provider_usage_by_model": {},
        },
    }


def _evaluation_payload(**overrides):
    payload = {
        "variant_id": "D3",
        "task_id": "main-01",
        "run_id": "run-d3-main-01",
        "claims_checked": 4,
        "strict_support_rate": 0.5,
        "estimated_cost_usd": 0.001,
    }
    payload.update(overrides)
    return payload


def _configure_summary(tmp_path, monkeypatch, *, traces, evaluations):
    trace_root = tmp_path / "outputs" / "experiment_traces"
    eval_root = tmp_path / "outputs" / "posthoc_evaluations"
    for filename, payload in traces:
        path = trace_root / "D3" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    for variant, filename, payload in evaluations:
        path = eval_root / variant / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    pricing_file = tmp_path / "experiments" / "pricing.json"
    pricing_file.parent.mkdir(parents=True)
    pricing_file.write_text(json.dumps({"models": {}}), encoding="utf-8")

    monkeypatch.setattr(summarize_budget_main_study, "TRACE_ROOT", trace_root)
    monkeypatch.setattr(summarize_budget_main_study, "EVAL_ROOT", eval_root)
    monkeypatch.setattr(summarize_budget_main_study, "PRICING_FILE", pricing_file)
    monkeypatch.setattr(summarize_budget_main_study, "VARIANTS", ("D3",))
    monkeypatch.setattr(
        summarize_budget_main_study,
        "OUT_JSON",
        tmp_path / "outputs" / "main_study_summary.json",
    )
    monkeypatch.setattr(
        summarize_budget_main_study,
        "OUT_CSV",
        tmp_path / "outputs" / "main_study_runs.csv",
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"variant_id": "D6"}, "variant_id does not match cache path"),
        ({"task_id": "main-02"}, "task_id does not match cache path"),
        ({"run_id": "other-run"}, "run_id does not match treatment trace"),
    ],
)
def test_summary_rejects_misbound_evaluator_cache_before_outputs(
    tmp_path, monkeypatch, overrides, message
):
    _configure_summary(
        tmp_path,
        monkeypatch,
        traces=[("run-d3-main-01.json", _trace_payload())],
        evaluations=[
            ("D3", "main-01.json", _evaluation_payload(**overrides)),
        ],
    )

    with pytest.raises(SystemExit, match=message):
        summarize_budget_main_study.main()

    assert not summarize_budget_main_study.OUT_JSON.exists()
    assert not summarize_budget_main_study.OUT_CSV.exists()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["trace"].update(variant_id="D6"),
            "variant_id does not match trace path",
        ),
        (
            lambda payload: payload["experiment"].update(task_id="main-02"),
            "task_id differs between experiment and trace",
        ),
        (
            lambda payload: payload["trace"].update(run_id="other-run"),
            "run_id does not match trace filename",
        ),
    ],
)
def test_summary_rejects_misbound_treatment_trace_before_outputs(
    tmp_path, monkeypatch, mutate, message
):
    trace = _trace_payload()
    mutate(trace)
    _configure_summary(
        tmp_path,
        monkeypatch,
        traces=[("run-d3-main-01.json", trace)],
        evaluations=[("D3", "main-01.json", _evaluation_payload())],
    )

    with pytest.raises(SystemExit, match=message):
        summarize_budget_main_study.main()

    assert not summarize_budget_main_study.OUT_JSON.exists()
    assert not summarize_budget_main_study.OUT_CSV.exists()


def test_summary_rejects_missing_evaluation_for_completed_trace_before_outputs(
    tmp_path, monkeypatch
):
    _configure_summary(
        tmp_path,
        monkeypatch,
        traces=[("run-d3-main-01.json", _trace_payload())],
        evaluations=[],
    )

    with pytest.raises(SystemExit, match="missing evaluator cache for completed trace"):
        summarize_budget_main_study.main()

    assert not summarize_budget_main_study.OUT_JSON.exists()
    assert not summarize_budget_main_study.OUT_CSV.exists()


def test_summary_rejects_duplicate_treatment_cell_before_outputs(
    tmp_path, monkeypatch
):
    _configure_summary(
        tmp_path,
        monkeypatch,
        traces=[
            ("run-d3-main-01.json", _trace_payload()),
            (
                "duplicate-run.json",
                _trace_payload(run_id="duplicate-run"),
            ),
        ],
        evaluations=[("D3", "main-01.json", _evaluation_payload())],
    )

    with pytest.raises(SystemExit, match="duplicate treatment cell"):
        summarize_budget_main_study.main()

    assert not summarize_budget_main_study.OUT_JSON.exists()
    assert not summarize_budget_main_study.OUT_CSV.exists()


def test_summary_rejects_orphan_evaluator_cache_before_outputs(tmp_path, monkeypatch):
    _configure_summary(
        tmp_path,
        monkeypatch,
        traces=[("run-d3-main-01.json", _trace_payload())],
        evaluations=[
            ("D3", "main-01.json", _evaluation_payload()),
            (
                "D3",
                "main-02.json",
                _evaluation_payload(
                    task_id="main-02",
                    run_id="run-d3-main-02",
                ),
            ),
        ],
    )

    with pytest.raises(SystemExit, match="has no matching treatment trace"):
        summarize_budget_main_study.main()

    assert not summarize_budget_main_study.OUT_JSON.exists()
    assert not summarize_budget_main_study.OUT_CSV.exists()


def test_summary_accepts_one_fully_bound_treatment_evaluator_cell(
    tmp_path, monkeypatch
):
    _configure_summary(
        tmp_path,
        monkeypatch,
        traces=[("run-d3-main-01.json", _trace_payload())],
        evaluations=[("D3", "main-01.json", _evaluation_payload())],
    )

    assert summarize_budget_main_study.main() == 0

    summary = json.loads(
        summarize_budget_main_study.OUT_JSON.read_text(encoding="utf-8")
    )
    assert summary["n_runs"] == 1
    assert summary["n_posthoc_evaluations"] == 1
