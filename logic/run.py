import asyncio
import datetime
import time

from typing import Dict, List
from fastapi import WebSocket

from agent.llm_utils import UsageTracker
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
    every attempted run, including failed and timed-out runs.
    """
    check_openai_api_key()
    config = experiment_config or ExperimentConfig()
    start_time = datetime.datetime.now(datetime.timezone.utc)
    start_clock = time.perf_counter()
    usage_tracker = UsageTracker()

    assistant = ResearchAgent(
        task,
        agent,
        agent_role_prompt,
        websocket,
        experiment_config=config,
        usage_tracker=usage_tracker,
    )

    report = ""
    path = None
    run_error = None

    async def _execute_run():
        await assistant.conduct_research()
        return await assistant.write_report(report_type, websocket)

    try:
        report, path = await asyncio.wait_for(
            _execute_run(),
            timeout=config.run_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        run_error = TimeoutError(
            f"Experiment exceeded {config.run_timeout_seconds:.0f}s run timeout"
        )
        run_error.__cause__ = exc
    except Exception as exc:  # Trace the failure, then preserve existing behavior.
        run_error = exc
    finally:
        latency_seconds = time.perf_counter() - start_clock
        verification = assistant.verification_result or {}
        usage = usage_tracker.snapshot()
        model_calls = int(usage.get("model_calls", 0) or 0)
        unavailable_usage_calls = int(usage.get("unavailable_calls", 0) or 0)
        if model_calls > 0 and unavailable_usage_calls == 0:
            usage_status = "provider_usage_complete"
        elif model_calls > unavailable_usage_calls:
            usage_status = "provider_usage_partial"
        else:
            usage_status = "provider_usage_unavailable"

        trace = RunTrace(
            run_id=str(assistant.directory_name),
            completed=bool(report) and run_error is None,
            source_count=assistant.browse_attempt_count,
            failed_source_count=assistant.browse_failure_count,
            citation_count=int(verification.get("claims_checked", 0) or 0),
            unsupported_claim_count=int(verification.get("unsupported", 0) or 0),
            latency_seconds=latency_seconds,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            estimated_cost_usd=0.0,
            variant_id=config.variant_id,
            task_set_id=config.task_set_id,
            task_id=config.task_id,
            question=task,
            planning_mode=config.planning_mode,
            verification_mode=config.verification_mode,
            source_budget=config.source_budget,
            query_count=len(assistant.search_queries),
            search_call_count=assistant.search_call_count,
            model_call_count=model_calls,
            unavailable_usage_call_count=unavailable_usage_calls,
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
            usage_accounting_status=usage_status,
            cost_accounting_status="not_computed_without_frozen_pricing_table",
        )
        trace_payload = trace.to_dict()
        trace_payload["started_at_utc"] = start_time.isoformat()
        trace_payload["verification_status"] = verification.get(
            "status", "not_requested"
        )
        trace_payload["search_queries"] = list(assistant.search_queries)
        trace_payload["search_records"] = list(assistant.search_records)
        trace_payload["scheduled_urls"] = list(assistant.scheduled_urls)
        trace_payload["successful_urls"] = list(assistant.successful_urls)
        trace_payload["failed_urls"] = list(assistant.failed_urls)
        trace_payload["provider_usage_by_model"] = usage.get("by_model", {})
        trace_payload["research_context_words"] = len(
            assistant.research_summary.split()
        )
        trace_payload["report_words"] = len(report.split()) if report else 0
        trace_payload["report_path"] = path
        trace_payload["browse_timeout_seconds"] = config.browse_timeout_seconds
        trace_payload["run_timeout_seconds"] = config.run_timeout_seconds
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
                        f"Provider tokens: {usage.get('total_tokens', 0)}\n"
                    ),
                }
            )

    if run_error is not None:
        raise run_error

    if websocket is not None and hasattr(websocket, "send_json"):
        await websocket.send_json({"type": "path", "output": path})

    return report, path
