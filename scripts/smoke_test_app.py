"""End-to-end smoke client for the FastAPI research application.

This starts from the same public HTTP/WebSocket contract used by the browser UI.
It does not bypass the application by calling ResearchAgent directly.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

import websockets


@dataclass(frozen=True)
class SmokeResult:
    report_chunks: int
    report_chars: int
    output_path: str


def validate_messages(messages: Iterable[dict[str, Any]]) -> SmokeResult:
    """Validate that one WebSocket run produced report content and an artifact path."""
    report_chunks = 0
    report_chars = 0
    output_path = ""
    initiated = False

    for message in messages:
        message_type = message.get("type")
        output = message.get("output")
        if message_type == "logs" and "Initiated an Agent:" in str(output or ""):
            initiated = True
        elif message_type == "report" and str(output or "").strip():
            report_chunks += 1
            report_chars += len(str(output))
        elif message_type == "path" and str(output or "").strip():
            output_path = str(output)

    if not initiated:
        raise ValueError("WebSocket run did not emit the agent-initiation log")
    if report_chunks == 0 or report_chars == 0:
        raise ValueError("WebSocket run did not emit any non-empty report content")
    if not output_path:
        raise ValueError("WebSocket run did not emit a terminal output artifact path")

    return SmokeResult(
        report_chunks=report_chunks,
        report_chars=report_chars,
        output_path=output_path,
    )


def resolve_output_path(output_path: str, repo_root: Path) -> Path:
    """Resolve a browser-facing output path while refusing paths outside outputs/."""
    parsed = urlsplit(output_path)
    if parsed.scheme or parsed.netloc:
        raise ValueError("output artifact must be a local application path")

    decoded = unquote(parsed.path).replace("\\", "/")
    while decoded.startswith("./"):
        decoded = decoded[2:]
    if decoded.startswith("/"):
        raise ValueError("output artifact must be relative to the repository")

    candidate = (repo_root / decoded).resolve()
    output_root = (repo_root / "outputs").resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError as exc:
        raise ValueError("output artifact must remain inside outputs/") from exc
    return candidate


def _get_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - localhost smoke target
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def _get_text(url: str, timeout_seconds: float) -> str:
    with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - localhost smoke target
        if response.status != 200:
            raise RuntimeError(f"GET {url} returned HTTP {response.status}")
        return response.read().decode("utf-8")


async def _run_websocket(
    ws_url: str,
    *,
    task: str,
    report_type: str,
    agent: str,
    timeout_seconds: float,
) -> tuple[list[dict[str, Any]], SmokeResult]:
    messages: list[dict[str, Any]] = []
    request = {
        "task": task,
        "report_type": report_type,
        "agent": agent,
    }

    async with websockets.connect(ws_url, open_timeout=20) as websocket:
        await websocket.send("start " + json.dumps(request))
        async with asyncio.timeout(timeout_seconds):
            while True:
                raw_message = await websocket.recv()
                message = json.loads(raw_message)
                if not isinstance(message, dict):
                    raise ValueError("WebSocket message must be a JSON object")
                messages.append(message)

                message_type = message.get("type")
                if message_type == "logs":
                    print(message.get("output", ""), flush=True)
                elif message_type == "path":
                    break

    return messages, validate_messages(messages)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--task",
        default=(
            "What does the official Python documentation say about Python context "
            "managers? Give a concise source-grounded summary."
        ),
    )
    parser.add_argument("--report-type", default="research_report")
    parser.add_argument("--agent", default="Default Agent")
    parser.add_argument("--timeout-seconds", type=float, default=520.0)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    parsed_base = urlsplit(base_url)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        raise ValueError("--base-url must be an http(s) URL")

    health = _get_json(f"{base_url}/health", timeout_seconds=15)
    if health != {"status": "ok"}:
        raise RuntimeError(f"unexpected health response: {health!r}")

    root_html = _get_text(f"{base_url}/", timeout_seconds=15)
    for marker in ("AI Research Hub", 'name="task"', 'name="report_type"'):
        if marker not in root_html:
            raise RuntimeError(f"root UI is missing expected marker: {marker}")

    ws_scheme = "wss" if parsed_base.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{parsed_base.netloc}/ws"
    messages, result = asyncio.run(
        _run_websocket(
            ws_url,
            task=args.task,
            report_type=args.report_type,
            agent=args.agent,
            timeout_seconds=args.timeout_seconds,
        )
    )

    repo_root = Path.cwd().resolve()
    artifact = resolve_output_path(result.output_path, repo_root)
    if not artifact.is_file() or artifact.stat().st_size <= 0:
        raise RuntimeError(f"reported output artifact is missing or empty: {artifact}")

    run_id = artifact.parent.name
    trace_candidates = list((repo_root / "outputs" / "experiment_traces").glob(f"*/{run_id}.json"))
    if len(trace_candidates) != 1:
        raise RuntimeError(
            f"expected exactly one trace for run {run_id}; found {len(trace_candidates)}"
        )
    trace_payload = json.loads(trace_candidates[0].read_text(encoding="utf-8"))
    trace = trace_payload.get("trace", {})
    if trace.get("completed") is not True:
        raise RuntimeError(f"trace did not record a completed run: {trace_candidates[0]}")

    summary = {
        "status": "ok",
        "health": health,
        "websocket_messages": len(messages),
        "report_chunks": result.report_chunks,
        "report_chars": result.report_chars,
        "artifact": str(artifact.relative_to(repo_root)),
        "artifact_bytes": artifact.stat().st_size,
        "trace": str(trace_candidates[0].relative_to(repo_root)),
        "browse_attempts": trace.get("source_count"),
        "model_calls": trace.get("model_call_count"),
    }
    print("SMOKE_OK " + json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
