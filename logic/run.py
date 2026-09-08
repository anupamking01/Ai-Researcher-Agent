import asyncio
import datetime
import time

from typing import Dict, List
from fastapi import WebSocket

from logic.evaluation import RunTrace
from logic.experiment import ExperimentConfig, save_run_trace
from logic.research_agent import ResearchAgent
from settings import Config, check_openai_api_key


CFG = Config()


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.sender_tasks: Dict[WebSocket, asyncio.Task] = {}
        self.message_queues: Dict[WebSocket, asyncio.Queue] = {}

    async def start_sender(self, websocket: WebSocket):
        queue = self.message_queues[websocket]
        while True:
            message = await queue.get()
            if websocket in self.active_connections:
                await websocket.send_text(message)
            else:
                break

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.message_queues[websocket] = asyncio.Queue()
        self.sender_tasks[websocket] = asyncio.create_task(self.start_sender(websocket))

    async def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        self.sender_tasks[websocket].cancel()
        del self.sender_tasks[websocket]
        del self.message_queues[websocket]

    async def start_streaming(
        self,
        task,
        report_type,
        agent,
        agent_role_prompt,
        websocket,
        experiment_config=None,
    ):
        report, path = await run_agent(
            task,
            report_type,
            agent,
            agent_role_prompt,
            websocket,
            experiment_config=experiment_config,
        )
        return report, path


async def run_agent(
    task,
    report_type,
    agent,
    agent_role_prompt,
    websocket,
    experiment_config=None,
):
    """Run one instrumented research-agent experiment.

    The public return value remains ``(report, path)`` for compatibility with
    the existing web application. A machine-readable trace is persisted for
    every attempted run, including failed runs.
    """
    check_openai_api_key()
    config = experiment_config or ExperimentConfig()
    start_time = datetime.datetime.now(datetime.timezone.utc)
    start_clock = time.perf_counter()

    assistant = ResearchAgent(
        task,
        agent,
        agent_role_prompt,
        websocket,
        experiment_config=config,
    )

    report = ""
    path = None
    run_error = None

    try:
        await assistant.conduct_research()
        report, path = await assistant.write_report(report_type, websocket)
    except Exception as exc:  # Trace the failure, then preserve existing behavior.
        run_error = exc
    finally:
        latency_seconds = time.perf_counter() - start_clock
        verification = assistant.verification_result or {}

        trace = RunTrace(
            run_id=str(assistant.directory_name),
            completed=bool(report) and run_error is None,
            source_count=assistant.browse_attempt_count,
            failed_source_count=assistant.browse_failure_count,
            citation_count=int(verification.get("claims_checked", 0) or 0),
            unsupported_claim_count=int(verification.get("unsupported", 0) or 0),
            latency_seconds=latency_seconds,
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost_usd=0.0,
            variant_id=config.variant_id,
            question=task,
            planning_mode=config.planning_mode,
            verification_mode=config.verification_mode,
            source_budget=config.source_budget,
            query_count=len(assistant.search_queries),
            supported_claim_count=int(verification.get("supported", 0) or 0),
            partially_supported_claim_count=int(
                verification.get("partially_supported", 0) or 0
            ),
            contradicted_claim_count=int(
                verification.get("contradicted", 0) or 0
            ),
            smart_model=CFG.smart_llm_model,
            fast_model=CFG.fast_llm_model,
            temperature=CFG.temperature,
            usage_accounting_status="not_exposed_by_legacy_streaming_adapter",
        )
        trace_payload = trace.to_dict()
        trace_payload["started_at_utc"] = start_time.isoformat()
        trace_payload["verification_status"] = verification.get(
            "status", "not_requested"
        )
        if run_error is not None:
            trace_payload["error_type"] = type(run_error).__name__
            trace_payload["error_message"] = str(run_error)[:1000]

        trace_path = save_run_trace(
            trace=trace_payload,
            config=config,
            run_id=str(assistant.directory_name),
        )

        if websocket is not None and hasattr(websocket, "send_json"):
            await websocket.send_json(
                {
                    "type": "logs",
                    "output": (
                        f"\nExperiment variant: {config.variant_id}\n"
                        f"Trace: {trace_path}\n"
                        f"Total run time: {latency_seconds:.2f}s\n"
                    ),
                }
            )

    if run_error is not None:
        raise run_error

    if websocket is not None and hasattr(websocket, "send_json"):
        await websocket.send_json({"type": "path", "output": path})

    return report, path
