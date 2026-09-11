"""Run the predeclared low-cost main study with an agent-phase spend guard.

This runner is intentionally separate from the five-task pilot. It executes the
frozen 10-task D3/D6/P6/P6V matrix and stops before starting another treatment
run if provider-reported spend from completed treatment runs has already reached
``--max-agent-cost-usd``. The default $3.00 treatment cap leaves a separate
reserve for common post-hoc evaluation under the user's fixed API-credit limit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REQUIRED_ENV = ("OPENAI_API_KEY", "SMART_LLM_MODEL", "FAST_LLM_MODEL", "TEMPERATURE")
DEFAULT_TASK_FILE = REPO_ROOT / "experiments" / "main_budget_tasks.json"
PRICING_FILE = REPO_ROOT / "experiments" / "openai_pricing_2026-09-08.json"
TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
VARIANTS = ("D3", "D6", "P6", "P6V")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_environment() -> None:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise SystemExit(f"Missing required experiment environment variables: {', '.join(missing)}")
    float(os.environ["TEMPERATURE"])


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unavailable"


def _load_task_file(path: Path) -> tuple[str, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if not tasks:
        raise SystemExit(f"No tasks found in {path}")
    return str(payload["task_set_id"]), tasks


def _load_pricing() -> dict:
    return json.loads(PRICING_FILE.read_text(encoding="utf-8"))


def _trace_cost_usd(path: Path, pricing: dict) -> float:
    from scripts.summarize_pilot import _estimate_reported_token_cost

    payload = json.loads(path.read_text(encoding="utf-8"))
    trace = payload.get("trace", {})
    cost, status = _estimate_reported_token_cost(trace.get("provider_usage_by_model", {}), pricing)
    if cost is None:
        raise RuntimeError(f"Cannot cost {path}: {status}")
    return float(cost)


def _current_treatment_cost(pricing: dict) -> float:
    if not TRACE_ROOT.exists():
        return 0.0
    return sum(_trace_cost_usd(path, pricing) for path in TRACE_ROOT.glob("*/*.json"))


def _write_json(name: str, payload: dict) -> Path:
    path = REPO_ROOT / "outputs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


class ConsoleWebSocket:
    async def send_json(self, payload):
        if payload.get("type") == "logs":
            print(payload.get("output", ""), flush=True)

    async def send_text(self, text):
        print(text, end="", flush=True)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", type=Path, default=DEFAULT_TASK_FILE)
    parser.add_argument("--max-agent-cost-usd", type=float, default=3.00)
    parser.add_argument("--task-id", action="append")
    args = parser.parse_args()
    if args.max_agent_cost_usd <= 0:
        raise SystemExit("--max-agent-cost-usd must be positive")

    _check_environment()
    task_set_id, tasks = _load_task_file(args.task_file)
    if args.task_id:
        requested = set(args.task_id)
        tasks = [task for task in tasks if task["id"] in requested]
        missing = requested - {task["id"] for task in tasks}
        if missing:
            raise SystemExit(f"Unknown task IDs: {sorted(missing)}")

    from logic.experiment import ExperimentConfig
    from logic.run import run_agent

    pricing = _load_pricing()
    base = ExperimentConfig.from_variant("D3")
    manifest = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "task_set_id": task_set_id,
        "task_ids": [task["id"] for task in tasks],
        "variants": list(VARIANTS),
        "expected_runs": len(tasks) * len(VARIANTS),
        "smart_model": os.environ["SMART_LLM_MODEL"],
        "fast_model": os.environ["FAST_LLM_MODEL"],
        "temperature": float(os.environ["TEMPERATURE"]),
        "git_commit": _git_commit(),
        "started_at_utc": _utc_now(),
        "max_agent_cost_usd": args.max_agent_cost_usd,
        "posthoc_evaluation_reserved_cost_usd": 1.25,
        "maximum_planned_study_cost_usd": args.max_agent_cost_usd + 1.25,
        "browse_timeout_seconds": base.browse_timeout_seconds,
        "run_timeout_seconds": base.run_timeout_seconds,
        "max_concurrent_browses": base.max_concurrent_browses,
        "pricing_file": str(PRICING_FILE.relative_to(REPO_ROOT)),
        "budget_note": "Treatment cap and evaluator reserve are separate safeguards; both use frozen uncached rates.",
    }
    _write_json("main_study_manifest.json", manifest)

    progress = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "task_set_id": task_set_id,
        "total_expected_runs": len(tasks) * len(VARIANTS),
        "attempted_runs": 0,
        "completed_runs": 0,
        "failed_runs": 0,
        "timeout_runs": 0,
        "estimated_treatment_cost_usd": 0.0,
        "events": [],
        "current": None,
        "started_at_utc": _utc_now(),
    }
    _write_json("main_study_progress.json", progress)
    socket = ConsoleWebSocket()

    # Interleave variants by task. If the spend guard stops the study, the
    # completed prefix contains matched treatment observations rather than many
    # tasks for only one variant.
    for task in tasks:
        for variant_id in VARIANTS:
            current_cost = _current_treatment_cost(pricing)
            progress["estimated_treatment_cost_usd"] = current_cost
            _write_json("main_study_progress.json", progress)
            if current_cost >= args.max_agent_cost_usd:
                raise SystemExit(
                    f"Treatment spend guard reached ${current_cost:.4f} before "
                    f"{variant_id}/{task['id']}; cap=${args.max_agent_cost_usd:.2f}"
                )

            base_config = ExperimentConfig.from_variant(variant_id)
            config = replace(base_config, task_set_id=task_set_id, task_id=task["id"])
            started = _utc_now()
            progress["current"] = {
                "variant": variant_id,
                "task_id": task["id"],
                "started_at_utc": started,
            }
            _write_json("main_study_progress.json", progress)
            print(f"\n=== {variant_id}/{task['id']} ===\n{task['question']}", flush=True)

            status = "completed"
            error = None
            try:
                await run_agent(
                    task=task["question"],
                    report_type="research_report",
                    agent="Academic Research Agent",
                    agent_role_prompt=None,
                    websocket=socket,
                    experiment_config=config,
                )
            except Exception as exc:
                status = "timeout" if isinstance(exc, TimeoutError) else "failed"
                error = f"{type(exc).__name__}: {str(exc)[:800]}"

            progress["attempted_runs"] += 1
            progress[f"{status}_runs"] += 1
            event = {
                "variant": variant_id,
                "task_id": task["id"],
                "status": status,
                "started_at_utc": started,
                "finished_at_utc": _utc_now(),
            }
            if error:
                event["error"] = error
            progress["events"].append(event)
            progress["current"] = None
            progress["estimated_treatment_cost_usd"] = _current_treatment_cost(pricing)
            _write_json("main_study_progress.json", progress)

            if status != "completed":
                raise SystemExit(f"Main study stopped after {variant_id}/{task['id']} status={status}: {error}")

    progress["finished_at_utc"] = _utc_now()
    progress["estimated_treatment_cost_usd"] = _current_treatment_cost(pricing)
    _write_json("main_study_progress.json", progress)
    print(
        f"MAIN TREATMENT COMPLETE: {progress['completed_runs']}/{progress['total_expected_runs']} "
        f"estimated_cost=${progress['estimated_treatment_cost_usd']:.4f}",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
