"""Audit the historical D3/D6/P6/P6V factor mapping without executing treatments.

This source-bound, outcome-free check verifies the original variant factory and
its handoff to the original treatment runner. It is not evidence of execution.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

from scripts import audit_historical_design_source as design
from scripts.audit_main_study_design_identifiability import HISTORICAL_RUNNER_COMMIT

CONFIG_PATH = "logic/experiment.py"
CONFIG_BLOB_SHA = "c98916c4a0aa17a94c38dd981489693bec5b87a7"
EXPECTED_FACTORS = {
    "D3": {"planning_mode": "direct", "source_budget": 3,
           "verification_mode": "none", "stream_report": False},
    "D6": {"planning_mode": "direct", "source_budget": 6,
           "verification_mode": "none", "stream_report": False},
    "P6": {"planning_mode": "planner", "source_budget": 6,
           "verification_mode": "none", "stream_report": False},
    "P6V": {"planning_mode": "planner", "source_budget": 6,
            "verification_mode": "verify", "stream_report": False},
}


class HistoricalFactorError(ValueError):
    """Historical source does not support the declared planned factor matrix."""


def _parse_source(raw: bytes) -> ast.Module:
    try:
        return ast.parse(raw.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise HistoricalFactorError("source must be UTF-8 Python") from exc


def inspect_variant_factory(raw: bytes) -> dict[str, dict]:
    """Accept only the historical literal from_variant dictionary/lookup shape."""
    module = _parse_source(raw)
    classes = [n for n in module.body if isinstance(n, ast.ClassDef)
               and n.name == "ExperimentConfig"]
    if len(classes) != 1:
        raise HistoricalFactorError("expected exactly one ExperimentConfig class")
    methods = [n for n in classes[0].body if isinstance(n, ast.FunctionDef)
               and n.name == "from_variant"]
    if len(methods) != 1 or not any(isinstance(d, ast.Name) and d.id == "classmethod"
                                   for d in methods[0].decorator_list):
        raise HistoricalFactorError("expected one classmethod variant factory")
    method = methods[0]
    assignments = [n for n in ast.walk(method) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "variants"
                           for t in n.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Dict):
        raise HistoricalFactorError("expected a literal variants dictionary")
    mapping: dict[str, dict] = {}
    for key_node, value_node in zip(assignments[0].value.keys,
                                    assignments[0].value.values):
        if key_node is None or not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            raise HistoricalFactorError("variant keys must be literal strings")
        key = key_node.value
        if key in mapping:
            raise HistoricalFactorError("duplicate variant key")
        if not (isinstance(value_node, ast.Call)
                and isinstance(value_node.func, ast.Name)
                and value_node.func.id == "cls" and not value_node.args
                and all(kw.arg is not None for kw in value_node.keywords)):
            raise HistoricalFactorError("variant must use keyword-only cls constructor")
        params = {}
        for kw in value_node.keywords:
            if kw.arg in params or not isinstance(kw.value, ast.Constant):
                raise HistoricalFactorError("duplicate or dynamic variant parameter")
            params[kw.arg] = kw.value.value
        if set(params) != {"variant_id", *EXPECTED_FACTORS["D3"].keys()}:
            raise HistoricalFactorError("unexpected or missing variant parameters")
        if type(params["variant_id"]) is not str or params["variant_id"] != key:
            raise HistoricalFactorError("variant key differs from constructor identity")
        mapping[key] = {k: params[k] for k in EXPECTED_FACTORS["D3"]}
    if mapping != EXPECTED_FACTORS:
        raise HistoricalFactorError("historical treatment-factor matrix differs from predeclared contrasts")
    # Do not infer that a dictionary is used merely because it is declared.
    returns = [n for n in ast.walk(method) if isinstance(n, ast.Return)]
    if len(returns) != 1:
        raise HistoricalFactorError("expected a unique factory return")
    expected_return = ast.parse("def _f():\n    return variants[variant_id.upper()]").body[0].body[0].value
    if ast.dump(returns[0].value) != ast.dump(expected_return):
        raise HistoricalFactorError("variant factory does not select dictionary by variant ID")
    return mapping


def inspect_runner_factor_handoff(raw: bytes) -> None:
    """Check the exact source route from variant_id to run_agent config."""
    design.inspect_runner_source(raw)  # also enforces awaited task/variant loops
    module = _parse_source(raw)
    main = next(n for n in module.body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == "main")
    task_loop = next(n for n in main.body if isinstance(n, ast.For)
                     and isinstance(n.target, ast.Name) and n.target.id == "task")
    arm_loop = next(n for n in task_loop.body if isinstance(n, ast.For)
                    and isinstance(n.target, ast.Name) and n.target.id == "variant_id")
    expected_statements = [
        ast.parse("base_config = ExperimentConfig.from_variant(variant_id)").body[0],
        ast.parse('config = replace(base_config, task_set_id=task_set_id, task_id=task["id"])').body[0],
    ]
    for expected in expected_statements:
        matching = [n for n in arm_loop.body if isinstance(n, ast.Assign)
                    and ast.dump(n) == ast.dump(expected)]
        if len(matching) != 1:
            raise HistoricalFactorError("runner does not preserve expected factor construction/handoff")
    calls = [n for n in ast.walk(arm_loop) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "run_agent"]
    if len(calls) != 1:
        raise HistoricalFactorError("expected one treatment call")
    arguments = [kw.value for kw in calls[0].keywords if kw.arg == "experiment_config"]
    if len(arguments) != 1 or not isinstance(arguments[0], ast.Name) or arguments[0].id != "config":
        raise HistoricalFactorError("treatment call is not passed the constructed config")
    # Reject other assignments to either intermediary inside the loop (including
    # inside conditionals/try bodies) that would defeat the source route.
    for n in ast.walk(arm_loop):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            if any(isinstance(t, ast.Name) and t.id in {"base_config", "config"}
                   for t in targets) and n not in arm_loop.body:
                raise HistoricalFactorError("nested configuration reassignment")
    for var in ("base_config", "config"):
        count = sum(isinstance(t, ast.Name) and t.id == var
                    for n in arm_loop.body if isinstance(n, ast.Assign)
                    for t in n.targets)
        if count != 1:
            raise HistoricalFactorError("ambiguous configuration assignment")


def audit_checkout(root: Path) -> dict:
    root = root.resolve()
    original_design = design.audit_checkout(root)
    historical_blob = design._git(root, "rev-parse", f"{HISTORICAL_RUNNER_COMMIT}:{CONFIG_PATH}").decode().strip()
    if historical_blob != CONFIG_BLOB_SHA:
        raise HistoricalFactorError("historical ExperimentConfig blob differs from pinned identity")
    config_source = design._git(root, "show", f"{HISTORICAL_RUNNER_COMMIT}:{CONFIG_PATH}")
    runner_source = design._git(root, "show", f"{HISTORICAL_RUNNER_COMMIT}:{design.RUNNER_PATH}")
    if not config_source or not runner_source:
        raise HistoricalFactorError("historical source blob is empty")
    factors = inspect_variant_factory(config_source)
    inspect_runner_factor_handoff(runner_source)
    return {
        "schema_version": 1,
        "status": "historical_source_bound_planned_factor_matrix_only",
        "original_runner_commit": HISTORICAL_RUNNER_COMMIT,
        "original_runner_blob": original_design["historical_runner_blob_sha"],
        "historical_config_path": CONFIG_PATH,
        "historical_config_blob": historical_blob,
        "historical_config_sha256": hashlib.sha256(config_source).hexdigest(),
        "source_linked_factor_matrix": factors,
        "runner_config_handoff_ast_checked": True,
        "original_treatment_execution_authenticated": False,
        "original_report_trace_custody_authenticated": False,
        "actual_factor_values_in_original_traces_verified": False,
        "equal_total_compute_established": False,
        "causal_effects_identified": False,
        "human_validation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(audit_checkout(args.root), sort_keys=True, indent=2))
    except (HistoricalFactorError, design.HistoricalDesignSourceError) as exc:
        parser.exit(1, f"historical factor audit failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
