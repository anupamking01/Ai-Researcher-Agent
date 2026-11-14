"""Run the frozen five-task research pilot for one or more variants.

Example:
    OPENAI_API_KEY=... \
    SMART_LLM_MODEL=<exact-model-id> \
    FAST_LLM_MODEL=<exact-model-id> \
    TEMPERATURE=1 \
    python scripts/run_pilot.py --variants D6 P6 P6V

No API keys or model IDs are stored in the repository. The script deliberately
requires explicit model environment variables so an experiment cannot silently
fall back to the application's legacy defaults.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The live runner must reject ambiguous input *before* any API, model import,
# output publication, or execution. Keep its parser aligned with the offline
# artifact validator rather than reimplementing strict JSON rules here.
from scripts.validate_pilot_artifacts import _load_json as _load_strict_pilot_json


REQUIRED_ENV = (
    "OPENAI_API_KEY",
    "SMART_LLM_MODEL",
    "FAST_LLM_MODEL",
    "TEMPERATURE",
)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class ConsoleWebSocket:
    """Minimal websocket-compatible sink for running the agent from a shell."""

    async def send_json(self, payload):
        if payload.get("type") == "logs":
            print(payload.get("output", ""), flush=True)
        elif payload.get("type") == "path":
            print(f"report_path={payload.get('output')}", flush=True)

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
        temperature = float(os.environ["TEMPERATURE"])
    except (ValueError, OverflowError) as exc:
        raise SystemExit("TEMPERATURE must be a finite numeric value") from exc
    if not math.isfinite(temperature):
        raise SystemExit("TEMPERATURE must be a finite numeric value")


def _validate_run_plan(task_set_id, tasks, variants):
    """Reject ambiguous pilot cells before spending model or browsing budget.

    The execution loop must visit each intended treatment/task cell once.
    Duplicate task IDs or variants otherwise create implicit retries, and a
    later artifact may overwrite the first attempt without an explicit rule.
    """
    if type(task_set_id) is not str or not task_set_id or task_set_id != task_set_id.strip():
        raise ValueError("pilot task_set_id must be a nonempty, unpadded string")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("pilot tasks must be a nonempty list")
    if not isinstance(variants, (list, tuple)) or not variants:
        raise ValueError("pilot variants must be a nonempty list")

    seen_variants = set()
    for variant in variants:
        if type(variant) is not str or variant not in ("D6", "P6", "P6V"):
            raise ValueError(f"unsupported pilot variant: {variant!r}")
        if variant in seen_variants:
            raise ValueError(f"duplicate pilot variant {variant!r}; no implicit reruns")
        seen_variants.add(variant)

    seen_tasks = set()
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise ValueError(f"pilot task {index} must be an object")
        task_id = task.get("id")
        if type(task_id) is not str or not task_id or task_id != task_id.strip():
            raise ValueError(f"pilot task {index} has invalid id")
        if task_id in seen_tasks:
            raise ValueError(f"duplicate pilot task id {task_id!r}; no implicit reruns")
        seen_tasks.add(task_id)
        question = task.get("question")
        if type(question) is not str or not question.strip():
            raise ValueError(f"pilot task {task_id!r} has no question")


def _select_tasks(tasks, requested_task_ids):
    """Preserve frozen task order while refusing duplicate or unknown filters."""
    if not requested_task_ids:
        return tasks
    if len(requested_task_ids) != len(set(requested_task_ids)):
        raise ValueError("duplicate --task-id selection; supply each ID once")
    selected_ids = set(requested_task_ids)
    known_ids = {task["id"] for task in tasks}
    missing = selected_ids - known_ids
    if missing:
        raise ValueError(f"unknown pilot task IDs: {sorted(missing)}")
    return [task for task in tasks if task["id"] in selected_ids]


def _load_tasks(task_file: Path):
    # Reject repeated keys (including nested task identities), nonstandard
    # constants and floating-point overflow, rather than letting json.loads
    # silently replace the frozen task source's earlier values.
    try:
        payload = _load_strict_pilot_json(task_file)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"invalid pilot task manifest {task_file}: {exc}") from exc
    tasks = payload.get("tasks")
    task_set_id = payload.get("task_set_id")
    # Check the complete source manifest before any optional CLI filtering.
    _validate_run_plan(task_set_id, tasks, ("D6",))
    return task_set_id, tasks


def _require_fresh_pilot_workspace(output_root: Path) -> None:
    """Refuse reuse of an output workspace before any provider work or writes.

    Pilot reports, traces, summaries and checkpoints share `outputs/`. A
    second invocation in that directory may replace its manifest/progress or
    mix old and new reports, even when each invocation's plan has unique cells.
    The runner never chooses which historical run to keep.
    """
    if output_root.is_symlink():
        raise ValueError("pilot output root must not be a symlink")
    if not output_root.exists():
        return
    if not output_root.is_dir():
        raise ValueError("pilot output root must be a directory")
    try:
        occupied = next(output_root.iterdir(), None)
    except OSError as exc:
        raise ValueError("cannot inspect pilot output workspace") from exc
    if occupied is not None:
        raise ValueError(
            "pilot output workspace is not empty; preserve earlier artifacts "
            "and use a fresh checkout/workspace for a separate diagnostic run"
        )


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


def _write_manifest(task_set_id, tasks, variants, base_config):
    output_root = REPO_ROOT / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "started_at_utc": _utc_now(),
        "task_set_id": task_set_id,
        "task_ids": [task["id"] for task in tasks],
        "variants": list(variants),
        "smart_model": os.environ["SMART_LLM_MODEL"],
        "fast_model": os.environ["FAST_LLM_MODEL"],
        "temperature": float(os.environ["TEMPERATURE"]),
        "git_commit": _git_commit(),
        "provider": "OpenAI ChatCompletion via pinned openai client",
        "browse_timeout_seconds": base_config.browse_timeout_seconds,
        "run_timeout_seconds": base_config.run_timeout_seconds,
        "max_concurrent_browses": base_config.max_concurrent_browses,
        "cost_accounting": "not_computed_without_frozen_pricing_table",
    }
    path = output_root / "pilot_manifest.json"
    # Exclusive creation also blocks two concurrent pilot processes from
    # silently replacing one another's manifest after both pass preflight.
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest, indent=2, sort_keys=True))
    except FileExistsError as exc:
        raise SystemExit(
            "Pilot aborted: pilot manifest already exists; "
            "preserve the prior run rather than overwriting it"
        ) from exc
    return path


def _write_progress(progress):
    """Atomically persist a small live checkpoint for the current pilot."""
    output_root = REPO_ROOT / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "pilot_progress.json"
    temp_path = output_root / "pilot_progress.json.tmp"
    progress["updated_at_utc"] = _utc_now()
    temp_path.write_text(
        json.dumps(progress, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)
    return path


async def _run_variant(variant_id, tasks, task_set_id, progress):
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
        print("\n" + "=" * 80, flush=True)
        print(f"variant={config.variant_id} task={task['id']}", flush=True)
        print(task["question"], flush=True)
        print("=" * 80, flush=True)

        started_at = _utc_now()
        progress["current"] = {
            "variant": config.variant_id,
            "task_id": task["id"],
            "status": "running",
            "started_at_utc": started_at,
        }
        checkpoint_path = _write_progress(progress)
        print(
            f"CHECKPOINT start variant={config.variant_id} task={task['id']} "
            f"progress={checkpoint_path}",
            flush=True,
        )

        status = "completed"
        error_type = None
        error_message = None
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
            error_type = type(exc).__name__
            error_message = str(exc)[:1000]
            print(
                f"FAILED {task['id']}: {error_type}: {error_message}",
                flush=True,
            )

        progress["attempted_runs"] += 1
        progress[f"{status}_runs"] += 1
        event = {
            "variant": config.variant_id,
            "task_id": task["id"],
            "status": status,
            "started_at_utc": started_at,
            "finished_at_utc": _utc_now(),
        }
        if error_type:
            event["error_type"] = error_type
            event["error_message"] = error_message
        progress["events"].append(event)
        progress["current"] = None
        _write_progress(progress)
        print(
            f"CHECKPOINT finish variant={config.variant_id} task={task['id']} "
            f"status={status} attempted={progress['attempted_runs']}/"
            f"{progress['total_expected_runs']}",
            flush=True,
        )


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

    # Validate source and selected design before writing a manifest, importing
    # the agent, or initiating any paid/live work.
    try:
        task_set_id, tasks = _load_tasks(args.task_file)
        tasks = _select_tasks(tasks, args.task_id)
        _validate_run_plan(task_set_id, tasks, args.variants)
    except ValueError as exc:
        raise SystemExit(f"Pilot aborted: {exc}") from exc
    # Perform the workspace-custody check before importing model code,
    # writing checkpoints or initiating any live/API execution.
    try:
        _require_fresh_pilot_workspace(REPO_ROOT / "outputs")
    except (ValueError, OSError) as exc:
        raise SystemExit(f"Pilot aborted: {exc}") from exc
    _check_environment()

    from logic.experiment import ExperimentConfig

    base_config = ExperimentConfig.from_variant(args.variants[0])
    manifest_path = _write_manifest(task_set_id, tasks, args.variants, base_config)
    progress = {
        "schema_version": 1,
        "started_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "task_set_id": task_set_id,
        "variants": list(args.variants),
        "task_ids": [task["id"] for task in tasks],
        "total_expected_runs": len(args.variants) * len(tasks),
        "attempted_runs": 0,
        "completed_runs": 0,
        "failed_runs": 0,
        "timeout_runs": 0,
        "current": None,
        "events": [],
    }
    progress_path = _write_progress(progress)

    print(f"task_set={task_set_id}", flush=True)
    print(f"smart_model={os.environ['SMART_LLM_MODEL']}", flush=True)
    print(f"fast_model={os.environ['FAST_LLM_MODEL']}", flush=True)
    print(f"temperature={os.environ['TEMPERATURE']}", flush=True)
    print(f"browse_timeout_seconds={base_config.browse_timeout_seconds}", flush=True)
    print(f"run_timeout_seconds={base_config.run_timeout_seconds}", flush=True)
    print(f"max_concurrent_browses={base_config.max_concurrent_browses}", flush=True)
    print(f"manifest={manifest_path}", flush=True)
    print(f"progress={progress_path}", flush=True)

    for variant_id in args.variants:
        await _run_variant(variant_id, tasks, task_set_id, progress)

    progress["finished_at_utc"] = _utc_now()
    _write_progress(progress)
    print("\nPilot execution finished. Summarize with:", flush=True)
    print("python scripts/summarize_pilot.py", flush=True)

    # Do not allow a research-invalid run to appear green in CI. All traces and
    # progress checkpoints remain on disk and are uploaded by the workflow's
    # `if: always()` steps for diagnosis.
    failed = int(progress.get("failed_runs", 0) or 0)
    timed_out = int(progress.get("timeout_runs", 0) or 0)
    if failed or timed_out:
        raise SystemExit(
            f"Pilot completed with {failed} failed and {timed_out} timed-out runs"
        )


if __name__ == "__main__":
    asyncio.run(main())
