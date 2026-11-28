import asyncio

import pytest

from logic import run
from logic.experiment import ExperimentConfig


def test_failed_run_records_observed_successes_not_unclassified_attempts(monkeypatch):
    captured = {}

    class InterruptedAgent:
        def __init__(self, *args, **kwargs):
            self.directory_name = "run-1"
            self.verification_result = {}
            self.browse_attempt_count = 2
            self.browse_failure_count = 0
            self.browse_success_count = 0
            self.search_queries = ["query"]
            self.search_call_count = 1
            self.search_records = []
            self.scheduled_urls = [
                "https://example.test/a",
                "https://example.test/b",
            ]
            self.successful_urls = []
            self.failed_urls = []
            self.research_summary = ""

        async def conduct_research(self):
            raise RuntimeError("interrupted while browsing")

        async def write_report(self, *args, **kwargs):
            raise AssertionError("write_report should not run")

    def capture_trace(*, trace, config, run_id):
        captured.update(trace)
        return "trace.json"

    monkeypatch.setattr(run, "check_openai_api_key", lambda: None)
    monkeypatch.setattr(run, "ResearchAgent", InterruptedAgent)
    monkeypatch.setattr(run, "save_run_trace", capture_trace)

    config = ExperimentConfig.from_variant("D3")
    with pytest.raises(RuntimeError, match="interrupted while browsing"):
        asyncio.run(
            run.run_agent(
                "question",
                "research_report",
                "researcher",
                "role",
                None,
                experiment_config=config,
            )
        )

    assert captured["completed"] is False
    assert captured["source_count"] == 2
    assert captured["successful_source_count"] == 0
    assert captured["failed_source_count"] == 0
    assert captured["source_success_rate"] == 0.0
