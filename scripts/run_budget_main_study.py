"""Run the predeclared low-cost main study with an agent-phase spend guard.

This runner is intentionally separate from the five-task pilot. It executes the
frozen 10-task D3/D6/P6/P6V matrix and stops before starting another treatment
run if provider-reported spend from completed treatment runs has already reached
``--max-agent-cost-usd``. The default $3.00 treatment cap leaves a separate
reserve for common post-hoc evaluation under the user's fixed API-credit limit.

All execution from this updated runner is noncanonical replication, requiring
an explicit command-line acknowledgment before credentials or agent modules
are accessed. The output manifest identifies new runs as noncanonical, while
retaining the legacy study ID for compatibility. If a prior main-study manifest,
progress record, or treatment trace exists, the runner stops before importing
model code or replacing artifacts. Recovery of measurement may use the separate
evaluator-recovery workflow; treatment outputs require explicit adjudication and
must never be silently rerun or selected for a better observed outcome.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REQUIRED_ENV = ("OPENAI_API_KEY", "SMART_LLM_MODEL", "FAST_LLM_MODEL", "TEMPERATURE")
DEFAULT_TASK_FILE = REPO_ROOT / "experiments" / "main_budget_tasks.json"
PRICING_FILE = REPO_ROOT / "experiments" / "openai_pricing_2026-09-08.json"
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"
CI_REQUIREMENTS_FILE = REPO_ROOT / "requirements-ci.lock"
TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
VARIANTS = ("D3", "D6", "P6", "P6V")
VARIANT_SOURCE_BUDGETS = {"D3": 3, "D6": 6, "P6": 6, "P6V": 6}
NONCANONICAL_REPLICATION_ACK = "NONCANONICAL_REPLICATION"
ORIGINAL_MAIN_STUDY_ACTIONS_RUN_ID = 34620917346
ORIGINAL_MAIN_STUDY_RUNNER_COMMIT = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_noncanonical_replication_ack(value: str | None) -> None:
    """Block unacknowledged direct reruns of the already-frozen study."""
    if value != NONCANONICAL_REPLICATION_ACK:
        raise SystemExit(
            "The original budget-main-v1 treatments are frozen. Any new "
            "execution is a noncanonical replication, never replacement "
            "evidence. Explicitly pass --noncanonical-replication-ack "
            "NONCANONICAL_REPLICATION before running the treatment agent."
        )


def _noncanonical_replication_provenance() -> dict:
    """Label new manifest bytes without changing the legacy study ID."""
    return {
        "classification": "noncanonical_replication",
        "original_frozen_study_id": "budget-main-v1",
        "original_actions_treatment_run_id": ORIGINAL_MAIN_STUDY_ACTIONS_RUN_ID,
        "original_runner_commit": ORIGINAL_MAIN_STUDY_RUNNER_COMMIT,
        "can_replace_original_treatment_evidence": False,
    }


def _check_environment() -> None:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise SystemExit(f"Missing required experiment environment variables: {', '.join(missing)}")
    float(os.environ["TEMPERATURE"])


@contextlib.contextmanager
def _repository_bytecode_isolation():
    """Compile imports from source using a fresh cache for the whole run."""
    try:
        cache_guard = tempfile.TemporaryDirectory(prefix="vera-main-study-bytecode-")
    except OSError as exc:
        raise SystemExit(
            "Cannot isolate Python bytecode for main-study execution"
        ) from exc
    previous_prefix = sys.pycache_prefix
    previous_write_setting = sys.dont_write_bytecode
    previous_search_path = list(sys.path)
    had_pythonpath = "PYTHONPATH" in os.environ
    previous_pythonpath = os.environ.get("PYTHONPATH")
    try:
        sys.pycache_prefix = cache_guard.name
        sys.dont_write_bytecode = True
        yield
    finally:
        sys.pycache_prefix = previous_prefix
        sys.dont_write_bytecode = previous_write_setting
        sys.path[:] = previous_search_path
        if had_pythonpath:
            os.environ["PYTHONPATH"] = previous_pythonpath
        else:
            os.environ.pop("PYTHONPATH", None)
        importlib.invalidate_caches()
        cache_guard.cleanup()


def _prioritize_repository_imports() -> None:
    """Put the attested checkout first and remove inherited PYTHONPATH roots."""
    repository_path = REPO_ROOT.resolve()
    inherited_roots = set()
    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            inherited_roots.add(Path(entry).resolve())
        except OSError as exc:
            raise SystemExit(
                "Cannot isolate repository imports for main-study execution"
            ) from exc

    sanitized_path = [str(repository_path)]
    for entry in sys.path:
        try:
            resolved_entry = Path(entry or os.getcwd()).resolve()
        except OSError as exc:
            raise SystemExit(
                "Cannot isolate repository imports for main-study execution"
            ) from exc
        if resolved_entry == repository_path or resolved_entry in inherited_roots:
            continue
        sanitized_path.append(entry)
    sys.path[:] = sanitized_path
    os.environ.pop("PYTHONPATH", None)
    importlib.invalidate_caches()


def _verify_repository_module_origin(module, relative_path: str) -> None:
    """Require an imported treatment module to originate at its attested path."""
    expected_path = (REPO_ROOT.resolve() / relative_path).resolve()
    module_path = getattr(module, "__file__", None)
    try:
        actual_path = Path(module_path).resolve() if module_path else None
    except OSError as exc:
        raise SystemExit(
            "Cannot verify treatment module origin for main-study execution"
        ) from exc
    if actual_path != expected_path:
        raise SystemExit(
            "Treatment module did not load from the attested repository; "
            "refusing main-study execution"
        )


def _git_source_state() -> dict:
    """Return immutable source identifiers only for a clean Git checkout."""
    git_environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_")
    }
    try:
        repository_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=REPO_ROOT,
            env=git_environment,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=REPO_ROOT,
            env=git_environment,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        tree = subprocess.check_output(
            ["git", "rev-parse", "--verify", "HEAD^{tree}"],
            cwd=REPO_ROOT,
            env=git_environment,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=REPO_ROOT,
            env=git_environment,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        index_entries = subprocess.check_output(
            ["git", "ls-files", "-v", "-z"],
            cwd=REPO_ROOT,
            env=git_environment,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        tree_entries = subprocess.check_output(
            ["git", "ls-tree", "-r", "-z", "HEAD"],
            cwd=REPO_ROOT,
            env=git_environment,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit("Cannot record Git source state for main study") from exc

    if Path(repository_root).resolve() != REPO_ROOT.resolve():
        raise SystemExit("Git repository root does not match main-study repository root")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise SystemExit("Cannot record Git source state: invalid commit identifier")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tree):
        raise SystemExit("Cannot record Git source state: invalid tree identifier")
    if status:
        raise SystemExit("Git working tree is not clean; refusing main-study execution")
    if any(
        entry[:1] == "S" or entry[:1].islower()
        for entry in index_entries.split("\0")
        if entry
    ):
        raise SystemExit(
            "Git index hides tracked source state; refusing main-study execution"
        )

    repository_path = REPO_ROOT.resolve()
    for entry in tree_entries.split(b"\0"):
        if not entry:
            continue
        try:
            header, relative_path_bytes = entry.split(b"\t", 1)
            mode, object_type, object_id_bytes = header.split(b" ", 2)
        except ValueError as exc:
            raise SystemExit(
                "Cannot attest exact Git source bytes for main study"
            ) from exc
        if mode not in {b"100644", b"100755"} or object_type != b"blob":
            raise SystemExit(
                "Git tracked source entry is not a regular blob; "
                "refusing main-study execution"
            )
        if not re.fullmatch(rb"[0-9a-f]{40}|[0-9a-f]{64}", object_id_bytes):
            raise SystemExit(
                "Cannot attest exact Git source bytes for main study"
            )

        relative_path = os.fsdecode(relative_path_bytes)
        source_path = repository_path / relative_path
        descriptor = None
        try:
            descriptor = os.open(
                source_path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("tracked source is not a regular file")
            with os.fdopen(descriptor, "rb") as source_handle:
                descriptor = None
                source_bytes = source_handle.read()
        except OSError as exc:
            raise SystemExit(
                "Cannot attest exact Git source bytes for main study"
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

        algorithm = "sha1" if len(object_id_bytes) == 40 else "sha256"
        worktree_object = hashlib.new(algorithm)
        worktree_object.update(
            b"blob " + str(len(source_bytes)).encode("ascii") + b"\0" + source_bytes
        )
        if worktree_object.hexdigest().encode("ascii") != object_id_bytes:
            raise SystemExit(
                "Git tracked source bytes do not match HEAD; "
                "refusing main-study execution"
            )
    return {"commit": commit, "tree": tree}


def _read_tracked_requirements_lock(lock_path: Path, expected_path: str) -> bytes:
    """Read one exact tracked regular-file requirements blob at ``HEAD``."""
    repository_root = REPO_ROOT.resolve()
    requirements_path = Path(os.path.abspath(lock_path))
    tracked_file_error = (
        f"Repository requirements lock {expected_path} must be a tracked "
        "regular file at HEAD"
    )
    try:
        relative_path = requirements_path.relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise SystemExit(tracked_file_error) from exc
    if relative_path != expected_path:
        raise SystemExit(tracked_file_error)

    git_environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_")
    }
    try:
        tree_record = subprocess.check_output(
            ["git", "ls-tree", "-z", "HEAD", "--", relative_path],
            cwd=repository_root,
            env=git_environment,
            stderr=subprocess.DEVNULL,
        )
        committed_bytes = subprocess.check_output(
            ["git", "show", f"HEAD:{relative_path}"],
            cwd=repository_root,
            env=git_environment,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(tracked_file_error) from exc
    if not re.fullmatch(
        rb"100(?:644|755) blob [0-9a-f]{40}(?:[0-9a-f]{24})?\t"
        + re.escape(expected_path.encode("utf-8"))
        + rb"\x00",
        tree_record,
    ):
        raise SystemExit(tracked_file_error)

    descriptor = None
    try:
        descriptor = os.open(
            requirements_path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("requirements lock is not a regular file")
        with os.fdopen(descriptor, "rb") as requirements_handle:
            descriptor = None
            requirements_raw = requirements_handle.read()
    except OSError as exc:
        raise SystemExit(tracked_file_error) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)

    if requirements_raw != committed_bytes:
        raise SystemExit(
            f"Repository requirements lock {expected_path} bytes do not match "
            "the recorded HEAD blob"
        )
    return requirements_raw


def _read_requirements_lock() -> bytes:
    """Read the exact tracked application requirements blob at ``HEAD``."""
    return _read_tracked_requirements_lock(REQUIREMENTS_FILE, "requirements.txt")


def _read_ci_requirements_lock() -> bytes:
    """Read the exact tracked workflow-environment requirements blob at ``HEAD``."""
    return _read_tracked_requirements_lock(
        CI_REQUIREMENTS_FILE,
        "requirements-ci.lock",
    )


def _parse_exact_distribution_pins(lock_raw: bytes, lock_label: str) -> dict[str, str]:
    try:
        lock_text = lock_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"Cannot decode {lock_label} for main study") from exc

    required_versions = {}
    for line_number, raw_line in enumerate(lock_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*"
            r"([A-Za-z0-9][A-Za-z0-9.!+_-]*)",
            line,
        )
        if not match:
            raise SystemExit(
                f"{lock_label} line {line_number} must contain only exact "
                "name==version pins"
            )
        name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        version = match.group(2)
        if name in required_versions:
            raise SystemExit(
                f"{lock_label} contains duplicate normalized distribution pin: "
                f"{name}"
            )
        required_versions[name] = version
    if not required_versions:
        raise SystemExit(f"{lock_label} contains no distribution pins")
    return required_versions


def _execution_environment() -> dict:
    """Validate and capture the interpreter and distributions used by treatments."""
    try:
        pinned_python = PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SystemExit(
            "Cannot read the repository Python version pin for main study"
        ) from exc
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", pinned_python):
        raise SystemExit("Invalid repository Python version pin for main study")

    active_python = platform.python_version()
    pinned_parts = pinned_python.split(".")
    if active_python.split(".")[: len(pinned_parts)] != pinned_parts:
        raise SystemExit(
            f"Active Python {active_python} does not match repository pin "
            f"{pinned_python}; refusing main-study execution"
        )

    requirements_raw = _read_requirements_lock()
    ci_requirements_raw = _read_ci_requirements_lock()
    required_versions = {}
    for lock_label, lock_raw in (
        ("Repository requirements", requirements_raw),
        ("Repository CI requirements", ci_requirements_raw),
    ):
        parsed_versions = _parse_exact_distribution_pins(lock_raw, lock_label)
        duplicate_names = sorted(required_versions.keys() & parsed_versions.keys())
        if duplicate_names:
            raise SystemExit(
                "Repository dependency locks contain duplicate normalized "
                f"distribution pin: {duplicate_names[0]}"
            )
        required_versions.update(parsed_versions)

    distributions = []
    for distribution in importlib.metadata.distributions():
        name = str(distribution.metadata.get("Name") or "").strip()
        version = str(distribution.version or "").strip()
        if not name or not version:
            raise SystemExit(
                "Cannot record treatment execution environment: installed "
                "distribution metadata is missing a name or version"
            )
        distributions.append((re.sub(r"[-_.]+", "-", name).lower(), version))

    installed_versions = {}
    for name, version in distributions:
        installed_versions.setdefault(name, set()).add(version)
    for name, required_version in sorted(required_versions.items()):
        versions = installed_versions.get(name)
        if not versions:
            raise SystemExit(
                f"Treatment environment is missing required distribution "
                f"{name}=={required_version}"
            )
        if versions != {required_version}:
            raise SystemExit(
                f"Repository requires {name}=={required_version}, found "
                f"{', '.join(sorted(versions))}; refusing main-study execution"
            )

    return {
        "python_implementation": platform.python_implementation(),
        "python_version_pin": pinned_python,
        "python_version": active_python,
        "platform": platform.platform(),
        "installed_distributions": [
            {"name": name, "version": version}
            for name, version in sorted(distributions)
        ],
        "requirements_file": _file_label(REQUIREMENTS_FILE),
        "requirements_file_sha256": hashlib.sha256(requirements_raw).hexdigest(),
        "ci_requirements_file": _file_label(CI_REQUIREMENTS_FILE),
        "ci_requirements_file_sha256": hashlib.sha256(
            ci_requirements_raw
        ).hexdigest(),
        "required_distributions": [
            {"name": name, "version": version}
            for name, version in sorted(required_versions.items())
        ],
    }


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

    completed = trace.get("completed")
    if type(completed) is not bool:
        raise SystemExit(
            f"Invalid treatment trace {path}: completed must be a boolean"
        )

    experiment_source_budget = experiment.get("source_budget")
    source_budget = trace.get("source_budget")
    if (
        type(experiment_source_budget) is not int
        or experiment_source_budget <= 0
        or type(source_budget) is not int
        or source_budget != experiment_source_budget
    ):
        raise SystemExit(
            f"Invalid treatment trace {path}: source_budget must match experiment"
        )
    if source_budget != VARIANT_SOURCE_BUDGETS[expected_variant]:
        raise SystemExit(
            f"Invalid treatment trace {path}: source_budget must match frozen variant"
        )

    count_fields = (
        "source_count",
        "successful_source_count",
        "failed_source_count",
        "query_count",
        "search_call_count",
        "report_words",
    )
    for field in count_fields:
        value = trace.get(field)
        if type(value) is not int or value < 0:
            raise SystemExit(
                f"Invalid treatment trace {path}: {field} must be a "
                "non-negative integer"
            )

    source_count = trace["source_count"]
    if source_count > source_budget:
        raise SystemExit(
            f"Invalid treatment trace {path}: source_count must not exceed "
            "source_budget"
        )
    classified_source_count = (
        trace["successful_source_count"] + trace["failed_source_count"]
    )
    if classified_source_count > source_count or (
        completed and classified_source_count != source_count
    ):
        raise SystemExit(
            f"Invalid treatment trace {path}: source count ledger mismatch"
        )
    if trace["search_call_count"] > trace["query_count"]:
        raise SystemExit(
            f"Invalid treatment trace {path}: search_call_count must not exceed "
            "query_count"
        )

    url_fields = ("scheduled_urls", "successful_urls", "failed_urls")
    url_ledgers = {}
    for field in url_fields:
        urls = trace.get(field)
        if not isinstance(urls, list) or any(
            not isinstance(url, str) or not url.strip() or url != url.strip()
            for url in urls
        ):
            raise SystemExit(
                f"Invalid treatment trace {path}: source URL ledger mismatch"
            )
        url_ledgers[field] = urls

    scheduled_urls = url_ledgers["scheduled_urls"]
    successful_urls = url_ledgers["successful_urls"]
    failed_urls = url_ledgers["failed_urls"]
    scheduled_set = set(scheduled_urls)
    successful_set = set(successful_urls)
    failed_set = set(failed_urls)
    if (
        len(scheduled_urls) != source_count
        or len(successful_urls) != trace["successful_source_count"]
        or len(failed_urls) != trace["failed_source_count"]
        or len(scheduled_set) != len(scheduled_urls)
        or len(successful_set) != len(successful_urls)
        or len(failed_set) != len(failed_urls)
        or successful_set & failed_set
        or not (successful_set | failed_set) <= scheduled_set
        or (completed and scheduled_set != successful_set | failed_set)
    ):
        raise SystemExit(
            f"Invalid treatment trace {path}: source URL ledger mismatch"
        )

    latency_seconds = trace.get("latency_seconds")
    if (
        isinstance(latency_seconds, bool)
        or not isinstance(latency_seconds, (int, float))
        or not math.isfinite(latency_seconds)
        or latency_seconds < 0
    ):
        raise SystemExit(
            f"Invalid treatment trace {path}: latency_seconds must be a finite "
            "non-negative number"
        )
    if completed and trace["report_words"] <= 0:
        raise SystemExit(
            f"Invalid treatment trace {path}: completed trace must have positive "
            "report_words"
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


async def _run_main_study() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-file", type=Path, default=DEFAULT_TASK_FILE)
    parser.add_argument("--max-agent-cost-usd", type=float, default=3.00)
    parser.add_argument("--task-id", action="append")
    parser.add_argument("--noncanonical-replication-ack", default=None)
    args = parser.parse_args()
    _require_noncanonical_replication_ack(args.noncanonical_replication_ack)
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
    source_state = _git_source_state()
    execution_environment = _execution_environment()

    experiment_module = importlib.import_module("logic.experiment")
    run_module = importlib.import_module("logic.run")
    _verify_repository_module_origin(experiment_module, "logic/experiment.py")
    _verify_repository_module_origin(run_module, "logic/run.py")
    ExperimentConfig = experiment_module.ExperimentConfig
    run_agent = run_module.run_agent

    base = ExperimentConfig.from_variant("D3")
    if _git_source_state() != source_state:
        raise SystemExit(
            "Git source state changed while loading treatment code; "
            "refusing main-study execution"
        )
    manifest = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "replication_provenance": _noncanonical_replication_provenance(),
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
        "git_commit": source_state["commit"],
        "git_tree": source_state["tree"],
        "execution_environment": execution_environment,
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


async def main() -> None:
    with _repository_bytecode_isolation():
        _prioritize_repository_imports()
        await _run_main_study()


if __name__ == "__main__":
    asyncio.run(main())
