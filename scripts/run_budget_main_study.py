"""Run the predeclared low-cost main study with an agent-phase spend guard.

This runner is intentionally separate from the five-task pilot. It executes the
frozen 10-task D3/D6/P6/P6V matrix and stops before starting another treatment
run if provider-reported spend from completed treatment runs has already reached
``--max-agent-cost-usd``. The default $3.00 treatment cap leaves a separate
reserve for common post-hoc evaluation under the user's fixed API-credit limit.

Treatment execution is deliberately start-only. If a prior main-study manifest,
progress record, or treatment trace exists, the runner stops before importing
model code or replacing artifacts. Recovery of measurement may use the separate
evaluator-recovery workflow; treatment outputs require explicit adjudication and
must never be silently rerun or selected for a better observed outcome.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import secrets
import stat
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


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict:
    payload = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def _file_label(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _load_task_file(path: Path) -> tuple[str, list[dict], dict]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"Cannot read task file {path}: {exc}") from exc
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Invalid task file {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid task file {path}: top level must be an object")
    task_set_id = payload.get("task_set_id")
    if not isinstance(task_set_id, str) or not task_set_id.strip():
        raise SystemExit(
            f"Invalid task file {path}: task_set_id must be a non-empty string"
        )
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise SystemExit(f"Invalid task file {path}: tasks must be a non-empty list")

    task_ids = set()
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise SystemExit(f"Invalid task file {path}: task {index} must be an object")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*", task_id
        ):
            raise SystemExit(
                f"Invalid task file {path}: task {index} id must be a safe non-empty identifier"
            )
        if task_id in task_ids:
            raise SystemExit(f"Invalid task file {path}: duplicate task id: {task_id}")
        task_ids.add(task_id)
        for field in ("category", "question"):
            value = task.get(field)
            if not isinstance(value, str) or not value.strip():
                raise SystemExit(
                    f"Invalid task file {path}: task {index} {field} must be a non-empty string"
                )

    snapshot = {
        "path": _file_label(path),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return task_set_id, tasks, snapshot


def _load_pricing(path: Path) -> tuple[dict, dict]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"Cannot read pricing file {path}: {exc}") from exc
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Invalid pricing file {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid pricing file {path}: top level must be an object")
    if payload.get("unit") != "per_1m_text_tokens":
        raise SystemExit(
            f"Invalid pricing file {path}: unit must equal per_1m_text_tokens"
        )
    models = payload.get("models")
    if not isinstance(models, dict) or not models:
        raise SystemExit(
            f"Invalid pricing file {path}: models must be a non-empty object"
        )
    for model, rates in models.items():
        if not isinstance(model, str) or not model.strip() or model != model.strip():
            raise SystemExit(
                f"Invalid pricing file {path}: model name must be a non-empty "
                "string without surrounding whitespace"
            )
        if not isinstance(rates, dict):
            raise SystemExit(
                f"Invalid pricing file {path}: model {model} must be an object"
            )
        for field in ("input", "output"):
            value = rates.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise SystemExit(
                    f"Invalid pricing file {path}: model {model} {field} must be "
                    "a finite non-negative number"
                )
        if "cached_input" in rates:
            value = rates["cached_input"]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise SystemExit(
                    f"Invalid pricing file {path}: model {model} cached_input "
                    "must be a finite non-negative number"
                )

    snapshot = {
        "path": _file_label(path),
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return payload, snapshot


def _trace_cost_usd(path: Path, pricing: dict) -> float:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise SystemExit(
            f"Invalid treatment trace directory {path.parent}: must be a regular directory"
        )
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"Invalid treatment trace {path}: must be a regular file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"Cannot read treatment trace {path}: {exc}") from exc
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Invalid treatment trace {path}: {exc}") from exc

    return _validated_trace_cost(payload, path=path, pricing=pricing)


def _validated_trace_cost(payload: dict, *, path: Path, pricing: dict) -> float:
    """Validate one captured treatment trace and recompute its frozen cost."""

    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid treatment trace {path}: top level must be an object")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 2:
        raise SystemExit(
            f"Invalid treatment trace {path}: schema_version must equal 2"
        )
    experiment = payload.get("experiment")
    trace = payload.get("trace")
    if not isinstance(experiment, dict) or not isinstance(trace, dict):
        raise SystemExit(
            f"Invalid treatment trace {path}: experiment and trace must be objects"
        )

    expected_variant = path.parent.name
    experiment_variant = experiment.get("variant_id")
    trace_variant = trace.get("variant_id")
    if (
        expected_variant not in VARIANTS
        or experiment_variant != expected_variant
        or trace_variant != expected_variant
    ):
        raise SystemExit(
            f"Invalid treatment trace {path}: variant_id identity mismatch"
        )
    experiment_task = experiment.get("task_id")
    trace_task = trace.get("task_id")
    if (
        not isinstance(experiment_task, str)
        or not experiment_task.strip()
        or experiment_task != experiment_task.strip()
        or experiment_task != trace_task
    ):
        raise SystemExit(f"Invalid treatment trace {path}: task_id identity mismatch")
    run_id = trace.get("run_id")
    if not isinstance(run_id, str) or run_id != path.stem:
        raise SystemExit(
            f"Invalid treatment trace {path}: run_id must match filename"
        )
    if trace.get("usage_accounting_status") != "provider_usage_complete":
        raise SystemExit(
            f"Invalid treatment trace {path}: usage_accounting_status must equal "
            "provider_usage_complete"
        )

    usage_by_model = trace.get("provider_usage_by_model")
    if not isinstance(usage_by_model, dict) or not usage_by_model:
        raise SystemExit(
            f"Invalid treatment trace {path}: provider_usage_by_model must be a "
            "non-empty object"
        )

    total_model_calls = 0
    total_unavailable_calls = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    cost_parts = []
    for model, usage in usage_by_model.items():
        if not isinstance(model, str) or not model.strip() or model != model.strip():
            raise SystemExit(
                f"Invalid treatment trace {path}: model name must be a non-empty "
                "string without surrounding whitespace"
            )
        rates = pricing["models"].get(model)
        if rates is None:
            raise SystemExit(
                f"Invalid treatment trace {path}: model {model} has no frozen price"
            )
        if not isinstance(usage, dict):
            raise SystemExit(
                f"Invalid treatment trace {path}: usage for {model} must be an object"
            )
        required_fields = (
            "model_calls",
            "unavailable_calls",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        )
        for field in required_fields:
            value = usage.get(field)
            if type(value) is not int or value < 0:
                raise SystemExit(
                    f"Invalid treatment trace {path}: {model} {field} must be a "
                    "non-negative integer"
                )
        if usage["model_calls"] <= 0:
            raise SystemExit(
                f"Invalid treatment trace {path}: {model} model_calls must be positive"
            )
        if usage["unavailable_calls"] != 0:
            raise SystemExit(
                f"Invalid treatment trace {path}: complete provider accounting "
                "requires zero unavailable calls"
            )
        if usage["total_tokens"] != (
            usage["prompt_tokens"] + usage["completion_tokens"]
        ):
            raise SystemExit(
                f"Invalid treatment trace {path}: {model} total_tokens must equal "
                "prompt_tokens + completion_tokens"
            )

        total_model_calls += usage["model_calls"]
        total_unavailable_calls += usage["unavailable_calls"]
        total_prompt_tokens += usage["prompt_tokens"]
        total_completion_tokens += usage["completion_tokens"]
        cost_parts.extend(
            (
                (usage["prompt_tokens"] / 1_000_000) * rates["input"],
                (usage["completion_tokens"] / 1_000_000) * rates["output"],
            )
        )

    expected_total_tokens = total_prompt_tokens + total_completion_tokens
    token_fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    aggregate_tokens = (
        trace.get("prompt_tokens"),
        trace.get("completion_tokens"),
        trace.get("total_tokens"),
    )
    if (
        not all(type(trace.get(field)) is int for field in token_fields)
        or aggregate_tokens
        != (total_prompt_tokens, total_completion_tokens, expected_total_tokens)
        or expected_total_tokens <= 0
    ):
        raise SystemExit(
            f"Invalid treatment trace {path}: aggregate token ledger mismatch"
        )
    call_fields = ("model_call_count", "unavailable_usage_call_count")
    if (
        not all(type(trace.get(field)) is int for field in call_fields)
        or trace.get("model_call_count") != total_model_calls
        or trace.get("unavailable_usage_call_count") != total_unavailable_calls
        or total_unavailable_calls != 0
    ):
        raise SystemExit(
            f"Invalid treatment trace {path}: aggregate call ledger mismatch"
        )

    cost = math.fsum(cost_parts)
    if not math.isfinite(cost) or cost < 0:
        raise SystemExit(f"Invalid treatment trace {path}: computed cost is invalid")
    return cost


def _treatment_trace_paths() -> tuple[Path, ...]:
    if TRACE_ROOT.is_symlink():
        raise SystemExit(f"Invalid treatment trace root: {TRACE_ROOT}")
    if not TRACE_ROOT.exists():
        return ()
    if not TRACE_ROOT.is_dir():
        raise SystemExit(f"Invalid treatment trace root: {TRACE_ROOT}")
    for variant in VARIANTS:
        variant_dir = TRACE_ROOT / variant
        if variant_dir.is_symlink() or (
            variant_dir.exists() and not variant_dir.is_dir()
        ):
            raise SystemExit(
                f"Invalid treatment trace directory {variant_dir}: "
                "must be a regular directory"
            )
    return tuple(sorted(TRACE_ROOT.glob("*/*.json")))


def _current_treatment_cost(pricing: dict) -> float:
    return math.fsum(
        _trace_cost_usd(path, pricing)
        for path in _treatment_trace_paths()
    )


def _preflight_new_study_state(pricing: dict) -> float:
    outputs_root = REPO_ROOT / "outputs"
    if outputs_root.is_symlink() or (
        outputs_root.exists() and not outputs_root.is_dir()
    ):
        raise SystemExit(
            f"Invalid main-study outputs root {outputs_root}: "
            "must be a regular directory"
        )

    trace_paths = _treatment_trace_paths()
    treatment_cost = math.fsum(
        _trace_cost_usd(path, pricing) for path in trace_paths
    )
    for name in ("main_study_manifest.json", "main_study_progress.json"):
        path = outputs_root / name
        if path.is_symlink() or path.exists():
            raise SystemExit(
                f"Refusing to overwrite existing main-study state: {path}"
            )
    if trace_paths:
        noun = "trace" if len(trace_paths) == 1 else "traces"
        raise SystemExit(
            f"Refusing to rerun treatments: {len(trace_paths)} existing {noun}"
        )
    return treatment_cost


def _open_outputs_root_fd() -> int:
    outputs_root = REPO_ROOT / "outputs"
    if outputs_root.is_symlink():
        raise SystemExit(f"Invalid main-study outputs root: {outputs_root}")
    try:
        outputs_root.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        directory_fd = os.open(outputs_root, flags)
    except OSError as exc:
        raise SystemExit(f"Invalid main-study outputs root: {outputs_root}") from exc
    if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
        os.close(directory_fd)
        raise SystemExit(f"Invalid main-study outputs root: {outputs_root}")
    return directory_fd


def _write_json(name: str, payload: dict, *, create_only: bool = False) -> Path:
    path = REPO_ROOT / "outputs" / name
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    directory_fd = _open_outputs_root_fd()
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    tmp_name = None
    try:
        for _ in range(100):
            candidate = f".{name}.{secrets.token_hex(8)}.tmp"
            try:
                file_fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
                    0o666,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            tmp_name = candidate
            break
        else:
            raise SystemExit(f"Cannot allocate staging file for main-study state {path}")

        try:
            with os.fdopen(file_fd, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            if create_only:
                try:
                    os.link(
                        tmp_name,
                        name,
                        src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as exc:
                    raise SystemExit(
                        f"Refusing to overwrite existing main-study state: {path}"
                    ) from exc
                os.fsync(directory_fd)
                os.unlink(tmp_name, dir_fd=directory_fd)
                tmp_name = None
            else:
                os.replace(
                    tmp_name,
                    name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                )
                tmp_name = None
            os.fsync(directory_fd)
        except OSError as exc:
            raise SystemExit(f"Cannot write main-study state {path}: {exc}") from exc
        return path
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


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
    if not math.isfinite(args.max_agent_cost_usd) or args.max_agent_cost_usd <= 0:
        raise SystemExit("--max-agent-cost-usd must be finite and positive")

    _check_environment()
    task_set_id, tasks, task_snapshot = _load_task_file(args.task_file)
    if args.task_id:
        requested = set(args.task_id)
        tasks = [task for task in tasks if task["id"] in requested]
        missing = requested - {task["id"] for task in tasks}
        if missing:
            raise SystemExit(f"Unknown task IDs: {sorted(missing)}")

    pricing, pricing_snapshot = _load_pricing(PRICING_FILE)
    for env_name in ("SMART_LLM_MODEL", "FAST_LLM_MODEL"):
        model = os.environ[env_name]
        if model not in pricing["models"]:
            raise SystemExit(
                f"Pricing file {PRICING_FILE} has no rate for {env_name}={model}"
            )

    initial_treatment_cost = _preflight_new_study_state(pricing)

    from logic.experiment import ExperimentConfig
    from logic.run import run_agent

    base = ExperimentConfig.from_variant("D3")
    manifest = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "task_set_id": task_set_id,
        "task_ids": [task["id"] for task in tasks],
        "task_file": task_snapshot["path"],
        "task_file_size_bytes": task_snapshot["size_bytes"],
        "task_file_sha256": task_snapshot["sha256"],
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
        "pricing_file": pricing_snapshot["path"],
        "pricing_file_size_bytes": pricing_snapshot["size_bytes"],
        "pricing_file_sha256": pricing_snapshot["sha256"],
        "budget_note": "Treatment cap and evaluator reserve are separate safeguards; both use frozen uncached rates.",
    }
    _write_json("main_study_manifest.json", manifest, create_only=True)

    progress = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "task_set_id": task_set_id,
        "total_expected_runs": len(tasks) * len(VARIANTS),
        "attempted_runs": 0,
        "completed_runs": 0,
        "failed_runs": 0,
        "timeout_runs": 0,
        "estimated_treatment_cost_usd": initial_treatment_cost,
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
