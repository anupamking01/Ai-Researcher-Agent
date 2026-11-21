import importlib
import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import app, manager


def test_health_endpoint_reports_ready():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_page_loads_research_ui():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "AI Research Hub" in response.text
    assert 'name="task"' in response.text
    assert 'name="report_type"' in response.text


def test_websocket_accepts_frontend_start_contract(monkeypatch):
    async def fake_start_streaming(
        task,
        report_type,
        agent,
        agent_role_prompt,
        websocket,
        experiment_config=None,
    ):
        assert task == "smoke test question"
        assert report_type == "research_report"
        assert agent == "Default Agent"
        await websocket.send_json({"type": "report", "output": "Smoke report body"})
        await websocket.send_json(
            {"type": "path", "output": "./outputs/smoke/research_report.md"}
        )
        return "Smoke report body", "./outputs/smoke/research_report.md"

    monkeypatch.setattr(manager, "start_streaming", fake_start_streaming)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(
                "start "
                + json.dumps(
                    {
                        "task": "smoke test question",
                        "report_type": "research_report",
                        "agent": "Default Agent",
                    }
                )
            )

            initiated = websocket.receive_json()
            report = websocket.receive_json()
            path = websocket.receive_json()

    assert initiated["type"] == "logs"
    assert "Default Agent" in initiated["output"]
    assert report == {"type": "report", "output": "Smoke report body"}
    assert path == {"type": "path", "output": "./outputs/smoke/research_report.md"}


def test_websocket_reports_research_failure_without_abrupt_disconnect(monkeypatch):
    async def failing_start_streaming(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(manager, "start_streaming", failing_start_streaming)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(
                "start "
                + json.dumps(
                    {
                        "task": "smoke test question",
                        "report_type": "research_report",
                        "agent": "Default Agent",
                    }
                )
            )

            initiated = websocket.receive_json()
            error = websocket.receive_json()

    assert initiated["type"] == "logs"
    assert error["type"] == "error"
    assert "RuntimeError" in error["output"]
    assert "provider unavailable" in error["output"]


def _load_smoke_module():
    spec = importlib.util.find_spec("scripts.smoke_test_app")
    assert spec is not None, "scripts.smoke_test_app must implement the live smoke client"
    return importlib.import_module("scripts.smoke_test_app")


def test_smoke_client_validates_terminal_websocket_messages():
    smoke = _load_smoke_module()
    messages = [
        {"type": "logs", "output": "Initiated an Agent: Default Agent"},
        {"type": "report", "output": "A source-grounded report."},
        {"type": "path", "output": "./outputs/abc/research_report.pdf"},
    ]

    result = smoke.validate_messages(messages)

    assert result.report_chunks == 1
    assert result.report_chars > 0
    assert result.output_path == "./outputs/abc/research_report.pdf"


def test_smoke_client_rejects_missing_report():
    smoke = _load_smoke_module()
    messages = [
        {"type": "logs", "output": "Initiated an Agent: Default Agent"},
        {"type": "path", "output": "./outputs/abc/research_report.pdf"},
    ]

    try:
        smoke.validate_messages(messages)
    except ValueError as exc:
        assert "report" in str(exc).lower()
    else:
        raise AssertionError("missing report messages must fail the smoke test")


def test_smoke_client_surfaces_server_error_message():
    smoke = _load_smoke_module()
    messages = [
        {"type": "logs", "output": "Initiated an Agent: Default Agent"},
        {
            "type": "error",
            "output": "Research run failed: RateLimitError: You have no credits remaining.",
        },
    ]

    try:
        smoke.validate_messages(messages)
    except RuntimeError as exc:
        assert "RateLimitError" in str(exc)
        assert "no credits remaining" in str(exc)
    else:
        raise AssertionError("server error messages must fail the smoke test explicitly")


def test_smoke_client_resolves_only_output_artifacts():
    smoke = _load_smoke_module()

    safe = smoke.resolve_output_path("./outputs/abc/research_report.pdf", Path.cwd())
    assert safe == (Path.cwd() / "outputs/abc/research_report.pdf").resolve()

    for unsafe in ("/tmp/report.pdf", "../secret.txt", "https://example.com/report.pdf"):
        try:
            smoke.resolve_output_path(unsafe, Path.cwd())
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe output path should be rejected: {unsafe}")
