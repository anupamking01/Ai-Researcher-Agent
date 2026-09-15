import asyncio
import json

import pytest

from logic.experiment import ExperimentConfig
from logic.research_agent import ResearchAgent
from scripts.validate_pilot_artifacts import validate_pilot
import scrape.web_scrape as web_scrape
import scrape.web_search as web_search_module
import text_preprocess.text as text_module


def test_missing_overlay_is_optional(monkeypatch, tmp_path):
    class Driver:
        def execute_script(self, script):
            raise AssertionError("overlay script should not be executed when file is absent")

    monkeypatch.setattr(web_scrape, "FILE_DIR", tmp_path)
    web_scrape.add_header(Driver())


def test_overlay_executes_when_present(monkeypatch, tmp_path):
    js_dir = tmp_path / "js"
    js_dir.mkdir()
    (js_dir / "overlay.js").write_text("window.__pilotOverlay = true;", encoding="utf-8")
    seen = []

    class Driver:
        def execute_script(self, script):
            seen.append(script)

    monkeypatch.setattr(web_scrape, "FILE_DIR", tmp_path)
    web_scrape.add_header(Driver())
    assert seen == ["window.__pilotOverlay = true;"]


def test_metasearch_retries_after_transient_empty_results(monkeypatch):
    class FakeDDGS:
        calls = 0

        def __init__(self, timeout):
            self.timeout = timeout

        def text(self, **kwargs):
            FakeDDGS.calls += 1
            # First complete backend round returns no results. The first pool
            # on the second round succeeds.
            if FakeDDGS.calls <= 3:
                return []
            return [{"href": "https://example.com/", "title": "Example"}]

    monkeypatch.setattr(web_search_module, "DDGS", FakeDDGS)
    monkeypatch.setattr(web_search_module.time, "sleep", lambda _: None)

    results = json.loads(web_search_module.web_search("example query", num_results=1))
    assert results[0]["href"] == "https://example.com/"
    assert FakeDDGS.calls == 4


def test_source_text_sampling_is_bounded_and_spans_page():
    text = "A" * 10_000 + "B" * 10_000 + "C" * 10_000
    sampled = text_module.select_source_text(text, max_chars=9_000)

    assert len(sampled) <= 9_000
    assert "A" in sampled
    assert "B" in sampled
    assert "C" in sampled
    assert sampled.count("[...source text omitted...]") == 2


def test_source_summary_uses_exactly_one_bounded_model_call(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return "bounded evidence summary"

    monkeypatch.setattr(text_module, "create_chat_completion", fake_completion)
    very_long_text = "evidence " * 10_000
    result = text_module.summarize_text(
        "https://example.com",
        very_long_text,
        "What does the evidence show?",
    )

    assert result == "bounded evidence summary"
    assert len(calls) == 1
    assert calls[0]["request_timeout_seconds"] == text_module.SOURCE_SUMMARY_REQUEST_TIMEOUT_SECONDS
    prompt = calls[0]["messages"][0]["content"]
    # The wrapper/question text adds a small amount around the bounded source.
    assert len(prompt) < text_module.SOURCE_TEXT_MAX_CHARS + 1_000
    assert text_module.NO_RELEVANT_EVIDENCE in prompt


def test_research_agent_bounds_active_browser_sections(monkeypatch):
    urls = [f"https://example.com/{index}" for index in range(4)]
    monkeypatch.setattr(
        "logic.research_agent.web_search",
        lambda query, num_results: json.dumps([{"href": url} for url in urls]),
    )

    active_browser_sections = 0
    max_active_browser_sections = 0
    active_summaries = 0
    max_active_summaries = 0
    semaphore_ids = set()

    async def fake_browse(*args, **kwargs):
        nonlocal active_browser_sections, max_active_browser_sections
        nonlocal active_summaries, max_active_summaries

        semaphore = kwargs.get("browser_semaphore")
        assert semaphore is not None
        semaphore_ids.add(id(semaphore))

        # Simulate the Selenium-only critical section inside async_browse.
        async with semaphore:
            active_browser_sections += 1
            max_active_browser_sections = max(
                max_active_browser_sections, active_browser_sections
            )
            await asyncio.sleep(0.01)
            active_browser_sections -= 1

        # Simulate source summarization after Chrome has been released. These
        # calls should remain free to overlap and must not hold the semaphore.
        active_summaries += 1
        max_active_summaries = max(max_active_summaries, active_summaries)
        await asyncio.sleep(0.02)
        active_summaries -= 1
        return "Information gathered from url: useful evidence"

    monkeypatch.setattr("logic.research_agent.async_browse", fake_browse)

    config = ExperimentConfig(
        variant_id="D4",
        planning_mode="direct",
        source_budget=4,
        verification_mode="none",
        max_concurrent_browses=2,
    )
    agent = ResearchAgent(
        question="test",
        agent="test-agent",
        agent_role_prompt="test-role",
        websocket=None,
        experiment_config=config,
    )

    responses = asyncio.run(agent.async_search("test", max_sources=4))
    assert len(responses) == 4
    assert agent.browse_attempt_count == 4
    assert agent.browse_success_count == 4
    assert len(semaphore_ids) == 1
    assert max_active_browser_sections == 2
    assert max_active_summaries > max_active_browser_sections


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_valid_artifacts(tmp_path):
    _write_json(
        tmp_path / "pilot_manifest.json",
        {
            "variants": ["D6"],
            "task_ids": ["pilot-01"],
            "smart_model": "gpt-5.6-terra",
            "fast_model": "gpt-5.6-luna",
            "temperature": 1.0,
        },
    )
    _write_json(
        tmp_path / "pilot_progress.json",
        {
            "total_expected_runs": 1,
            "attempted_runs": 1,
            "completed_runs": 1,
            "failed_runs": 0,
            "timeout_runs": 0,
        },
    )
    _write_json(
        tmp_path / "pilot_summary.json",
        {
            "n_trace_files": 1,
            "variant_summary": {"D6": {"n_runs": 1, "n_completed": 1}},
        },
    )
    _write_json(
        tmp_path / "experiment_traces" / "D6" / "run-1.json",
        {
            "experiment": {
                "variant_id": "D6",
                "task_id": "pilot-01",
                "source_budget": 6,
            },
            "trace": {
                "variant_id": "D6",
                "task_id": "pilot-01",
                "completed": True,
                "source_budget": 6,
                "source_count": 6,
                "successful_source_count": 5,
                "failed_source_count": 1,
                "scheduled_urls": [f"https://e/{i}" for i in range(6)],
                "successful_urls": [f"https://e/{i}" for i in range(5)],
                "failed_urls": ["https://e/5"],
                "planning_mode": "direct",
                "query_count": 1,
                "search_call_count": 1,
                "research_context_words": 500,
                "report_words": 1000,
                "model_call_count": 3,
                "total_tokens": 2000,
                "usage_accounting_status": "provider_usage_complete",
                "smart_model": "gpt-5.6-terra",
                "fast_model": "gpt-5.6-luna",
                "temperature": 1.0,
                "verification_mode": "none",
                "verification_status": "not_requested",
            },
        },
    )


def test_pilot_artifact_validator_accepts_valid_run(tmp_path):
    _make_valid_artifacts(tmp_path)
    assert validate_pilot(tmp_path) == []


def test_pilot_artifact_validator_rejects_zero_evidence(tmp_path):
    _make_valid_artifacts(tmp_path)
    trace_path = tmp_path / "experiment_traces" / "D6" / "run-1.json"
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["trace"]["successful_source_count"] = 0
    payload["trace"]["successful_urls"] = []
    payload["trace"]["failed_source_count"] = 6
    payload["trace"]["failed_urls"] = [f"https://e/{i}" for i in range(6)]
    trace_path.write_text(json.dumps(payload), encoding="utf-8")

    errors = validate_pilot(tmp_path)
    assert any("no successfully processed evidence sources" in error for error in errors)


def test_max_concurrent_browses_must_be_positive():
    with pytest.raises(ValueError):
        ExperimentConfig(max_concurrent_browses=0)
