"""Run the frozen five-task research pilot for one or more variants.

Example:
    OPENAI_API_KEY=... \
    SMART_LLM_MODEL=<exact-model-id> \
    FAST_LLM_MODEL=<exact-model-id> \
    TEMPERATURE=0 \
    python scripts/run_pilot.py --variants D6 P6 P6V

No API keys or model IDs are stored in the repository. The script deliberately
requires explicit model environment variables so an experiment cannot silently
fall back to the application's legacy defaults.
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


REQUIRED_ENV = (
    "OPENAI_API_KEY",
    "SMART_LLM_MODEL",
    "FAST_LLM_MODEL",
    "TEMPERATURE",
)


class ConsoleWebSocket:
    """Minimal websocket-compatible sink for running the agent from a shell."""

    async def send_json(self, payload):
        if payload.get("type") == "logs":
            print(payload.get("output", ""))
        elif payload.get("type") == "path":
            print(f"report_path={payload.get('output')}")

    async def send_text(self, text):
        print(text, end="", flush=True)


def _check_environment():
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(
            "Pilot aborted. Set explicit experiment environment variables: "
            f"{names}. Do not rely on application defaults for paper results."
        )
    try:
        float(os.environ["TEMPERATURE"])
    except ValueError as exc:
        raise SystemExit("TEMPERATURE must be a numeric value") from exc


def _load_tasks(task_file: Path):
    payload = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if not tasks:
        raise SystemExit(f"No tasks found in {task_file}")
    return payload["task_set_id"], tasks


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unavailable"


def _write_manifest(task_set_id, tasks, variants):
    output_root = REPO_ROOT / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "task_set_id": task_set_id,
        "task_ids": [task["id"] for task in tasks],
        "variants": list(variants),
        "smart_model": os.environ["SMART_LLM_MODEL"],
        "fast_model": os.environ["FAST_LLM_MODEL"],
        "temperature": float(os.environ["TEMPERATURE"]),
        "git_commit": _git_commit(),
        "provider": "OpenAI ChatCompletion via pinned openai client",
        "cost_accounting": "not_computed_without_frozen_pricing_table",
    }
    path = output_root / "pilot_manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


async def _run_variant(variant_id, tasks, task_set_id):
    # Import after environment validation so Config reads explicit model IDs.
    from logic.experiment import ExperimentConfig
    from logic.run import run_agent

    base_config = ExperimentConfig.from_variant(variant_id)
    socket = ConsoleWebSocket()

    for task in tasks:
        config = replace(
            base_config,
            task_set_id=task_set_id,
            task_id=task["id"],
        )
        print("\n" + "=" * 80)
        print(f"variant={config.variant_id} task={task['id']}")
        print(task["question"])
        print("=" * 80)

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
            # run_agent persists a failed trace before re-raising.
            print(f"FAILED {task['id']}: {type(exc).__name__}: {exc}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["D6", "P6", "P6V"],
        choices=["D6", "P6", "P6V"],
        help="Pilot variants to execute.",
    )
    parser.add_argument(
        "--task-file",
        type=Path,
        default=REPO_ROOT / "experiments" / "pilot_tasks.json",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        help="Optionally run only selected task IDs; may be supplied repeatedly.",
    )
    args = parser.parse_args()

    _check_environment()
    task_set_id, tasks = _load_tasks(args.task_file)
    if args.task_id:
        selected = set(args.task_id)
        tasks = [task for task in tasks if task["id"] in selected]
        missing = selected - {task["id"] for task in tasks}
        if missing:
            raise SystemExit(f"Unknown task IDs: {sorted(missing)}")

    manifest_path = _write_manifest(task_set_id, tasks, args.variants)
    print(f"task_set={task_set_id}")
    print(f"smart_model={os.environ['SMART_LLM_MODEL']}")
    print(f"fast_model={os.environ['FAST_LLM_MODEL']}")
    print(f"temperature={os.environ['TEMPERATURE']}")
    print(f"manifest={manifest_path}")

    for variant_id in args.variants:
        await _run_variant(variant_id, tasks, task_set_id)

    print("\nPilot execution finished. Summarize with:")
    print("python scripts/summarize_pilot.py")


if __name__ == "__main__":
    asyncio.run(main())
