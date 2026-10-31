import asyncio

import pytest

from scripts import evaluate_posthoc_support, run_budget_main_study


@pytest.mark.parametrize("raw_cap", ["nan", "inf", "-inf"])
def test_treatment_runner_rejects_nonfinite_budget_before_environment(
    monkeypatch, raw_cap
):
    monkeypatch.setattr(
        run_budget_main_study.sys,
        "argv",
        ["run_budget_main_study.py", "--noncanonical-replication-ack",
         run_budget_main_study.NONCANONICAL_REPLICATION_ACK,
         f"--max-agent-cost-usd={raw_cap}"],
    )
    for name in run_budget_main_study.REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(
        SystemExit, match=r"--max-agent-cost-usd must be finite and positive"
    ):
        asyncio.run(run_budget_main_study.main())


@pytest.mark.parametrize("raw_cap", ["nan", "inf", "-inf"])
def test_evaluator_runner_rejects_nonfinite_budget_before_environment(
    monkeypatch, raw_cap
):
    monkeypatch.setattr(
        evaluate_posthoc_support.sys,
        "argv",
        ["evaluate_posthoc_support.py", f"--max-evaluator-cost-usd={raw_cap}"],
    )
    for name in ("OPENAI_API_KEY", "SMART_LLM_MODEL", "TEMPERATURE"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(
        SystemExit, match=r"--max-evaluator-cost-usd must be finite and positive"
    ):
        evaluate_posthoc_support.main()
