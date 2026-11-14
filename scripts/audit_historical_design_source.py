"""Bind VERA's retrospective treatment/position rank result to its original runner.

Reads only a pinned Git blob and Git ancestry; never imports or runs the runner,
reads outcome data, or authenticates the missing original experiment artifacts.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.audit_main_study_design_identifiability import (
    HISTORICAL_RUNNER_COMMIT, HISTORICAL_SCHEDULE, VARIANTS, analyze_schedule,
)

RUNNER_PATH = "scripts/run_budget_main_study.py"
# Original Git blob identity, independently retrieved from the historical commit.
RUNNER_BLOB_SHA = "1e509f8e2abbd2cf7601eafa06f4e20588bf7ff5"


class HistoricalDesignSourceError(ValueError):
    """The immutable source cannot support the claimed planned execution order."""


def inspect_runner_source(raw: bytes) -> tuple[str, ...]:
    """Validate literal variants and unconditional task-then-variant loop shape.

    Deliberately restricted AST contract; this is not a general-purpose proof
    of runtime behavior, and never evaluates or imports historical Python.
    """
    try:
        module = ast.parse(raw.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise HistoricalDesignSourceError("historical runner is not valid UTF-8 Python") from exc

    declarations = [node for node in module.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "VARIANTS"
                            for target in node.targets)]
    if len(declarations) != 1:
        raise HistoricalDesignSourceError("expected exactly one top-level VARIANTS declaration")
    try:
        arms = ast.literal_eval(declarations[0].value)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as exc:
        raise HistoricalDesignSourceError("VARIANTS must be a literal tuple") from exc
    if not isinstance(arms, tuple) or arms != VARIANTS:
        raise HistoricalDesignSourceError("historical runner treatment tuple differs from audit")

    mains = [node for node in module.body
             if isinstance(node, ast.AsyncFunctionDef) and node.name == "main"]
    if len(mains) != 1:
        raise HistoricalDesignSourceError("missing unique historical async main")
    main = mains[0]
    task_loops = [node for node in main.body
                  if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                  and node.target.id == "task" and isinstance(node.iter, ast.Name)
                  and node.iter.id == "tasks"]
    if len(task_loops) != 1:
        raise HistoricalDesignSourceError("missing unique top-level task iteration")
    task_loop = task_loops[0]
    arm_loops = [node for node in task_loop.body
                 if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                 and node.target.id == "variant_id" and isinstance(node.iter, ast.Name)
                 and node.iter.id == "VARIANTS"]
    if len(arm_loops) != 1:
        raise HistoricalDesignSourceError("treatments are not directly nested within tasks")

    def is_agent_call(node: ast.AST) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run_agent"

    all_calls = [node for node in ast.walk(main) if is_agent_call(node)]
    nested_calls = [node for node in ast.walk(arm_loops[0]) if is_agent_call(node)]
    if len(all_calls) != 1 or len(nested_calls) != 1:
        raise HistoricalDesignSourceError("expected exactly one treatment call inside task/variant loops")
    if not any(isinstance(node, ast.Await) and node.value is nested_calls[0]
               for node in ast.walk(arm_loops[0])):
        raise HistoricalDesignSourceError("treatment call is not awaited inside variant loop")
    return arms


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args],
                            capture_output=True, check=False)
    if result.returncode:
        raise HistoricalDesignSourceError(
            f"git {args[0]} failed (exit {result.returncode}); full history is required"
        )
    return result.stdout


def audit_checkout(root: Path) -> dict:
    """Verify pinned historical Git blob is in this checkout's ancestry."""
    root = root.resolve()
    if _git(root, "rev-parse", "--show-toplevel").decode().strip() != str(root):
        raise HistoricalDesignSourceError("expected repository root")
    if _git(root, "rev-parse", "--is-shallow-repository").decode().strip() != "false":
        raise HistoricalDesignSourceError("shallow Git checkout is not accepted")
    resolved = _git(root, "rev-parse", f"{HISTORICAL_RUNNER_COMMIT}^{{commit}}").decode().strip()
    if resolved != HISTORICAL_RUNNER_COMMIT:
        raise HistoricalDesignSourceError("historical runner commit differs from pin")
    _git(root, "merge-base", "--is-ancestor", HISTORICAL_RUNNER_COMMIT, "HEAD")
    blob = _git(root, "rev-parse", f"{HISTORICAL_RUNNER_COMMIT}:{RUNNER_PATH}").decode().strip()
    if blob != RUNNER_BLOB_SHA:
        raise HistoricalDesignSourceError("historical runner Git blob differs from pin")
    source = _git(root, "show", f"{HISTORICAL_RUNNER_COMMIT}:{RUNNER_PATH}")
    if not source:
        raise HistoricalDesignSourceError("historical runner blob is empty")
    arms = inspect_runner_source(source)
    result = analyze_schedule(HISTORICAL_SCHEDULE)
    if (result["rank_task_plus_treatment_plus_position"] != 13
            or result["additional_position_rank_after_treatment"] != 0
            or result["additional_treatment_rank_after_position"] != 0):
        raise HistoricalDesignSourceError("pinned schedule is not treatment/position aliased")
    return {
        "schema_version": 1,
        "status": "historical_source_bound_planned_design_nonidentifiability",
        "historical_runner_commit": HISTORICAL_RUNNER_COMMIT,
        "historical_runner_path": RUNNER_PATH,
        "historical_runner_blob_sha": blob,
        "historical_runner_sha256": hashlib.sha256(source).hexdigest(),
        "historical_runner_task_then_variant_ast_checked": True,
        "historical_runner_awaited_agent_call_checked": True,
        "source_linked_variant_order": list(arms),
        "historical_expected_cells": result["planned_cells"],
        "design_rank_task_treatment_position": result["rank_task_plus_treatment_plus_position"],
        "position_effect_separable_from_treatment": False,
        "original_treatment_execution_authenticated": False,
        "actual_run_timestamps_authenticated": False,
        "time_varying_web_conditions_measured": False,
        "causal_effects_identified": False,
        "human_ratings_collected": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(audit_checkout(args.root), indent=2, sort_keys=True))
    except HistoricalDesignSourceError as exc:
        parser.exit(1, f"historical design source audit failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
