"""Apply one common post-hoc support evaluator to every completed main-study report.

The evaluator is measurement-only. It does not repair reports and it evaluates
all variants with the same prompt, model, 12-claim cap, evidence restriction,
and frozen cost accounting. A separate $1.25 evaluator spend guard preserves
the user's fixed remaining API-credit budget.

A completed treatment run with zero successful retrieved sources is a valid
experimental outcome, not missing data. For that edge case the evaluator gets
an explicit no-evidence sentinel so it can identify report claims under the
same rubric while being prohibited from using outside knowledge. If a trace
claims successful sources but its saved evidence is missing, evaluation still
fails as a provenance error.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
EVAL_ROOT = REPO_ROOT / "outputs" / "posthoc_evaluations"
PRICING_FILE = REPO_ROOT / "experiments" / "openai_pricing_2026-09-08.json"
VARIANTS = ("D3", "D6", "P6", "P6V")
MAX_CLAIMS = 12
STUDY_ID = "budget-main-v1"
NO_EVIDENCE_SENTINEL = (
    "[NO RETRIEVED EVIDENCE WAS AVAILABLE FOR THIS TREATMENT RUN. "
    "The run recorded zero successful retrieved sources. Do not use outside knowledge.]"
)


def _load_json(path: Path) -> dict:
    from scripts.run_budget_main_study import _reject_duplicate_json_keys

    try:
        raw = path.read_bytes()
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Invalid JSON file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid JSON file {path}: top level must be an object")
    return payload


def _publish_evaluation_cache(path: Path, record: dict) -> None:
    """Durably publish one evaluator result without exposing partial bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    staging_path = Path(staging_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(staging_path, path)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        staging_path.unlink(missing_ok=True)


def _normalize_evaluator_output(raw_result: str) -> dict:
    from logic.experiment import normalize_verifier_output

    return normalize_verifier_output(raw_result, max_claims=MAX_CLAIMS)


def _load_cached_evaluation(
    path: Path,
    *,
    expected_variant: str,
    expected_task_id: str,
    expected_run_id: str,
    expected_evaluator_model: str,
    expected_temperature: float,
    expected_evidence_status: str,
    pricing: dict,
) -> dict:
    payload = _load_json(path)
    return _validate_cached_evaluation(
        payload,
        path=path,
        expected_variant=expected_variant,
        expected_task_id=expected_task_id,
        expected_run_id=expected_run_id,
        expected_evaluator_model=expected_evaluator_model,
        expected_temperature=expected_temperature,
        expected_evidence_status=expected_evidence_status,
        pricing=pricing,
    )


def _validate_cached_evaluation(
    payload: dict,
    *,
    path: Path,
    expected_variant: str,
    expected_task_id: str,
    expected_run_id: str,
    expected_evaluator_model: str,
    expected_temperature: float,
    expected_evidence_status: str,
    pricing: dict,
) -> dict:
    """Validate one already-captured evaluator record against its bound cell."""
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        raise SystemExit(
            f"Cached post-hoc evaluation {path} schema_version must equal 1"
        )
    expected_identity = {
        "study_id": STUDY_ID,
        "variant_id": expected_variant,
        "task_id": expected_task_id,
        "run_id": expected_run_id,
    }
    for field, expected_value in expected_identity.items():
        if payload.get(field) != expected_value:
            raise SystemExit(
                f"Cached post-hoc evaluation {path} {field} must equal "
                f"{expected_value}"
            )

    recorded_evidence_status = payload.get("evidence_status")
    if recorded_evidence_status not in (None, expected_evidence_status):
        raise SystemExit(
            f"Cached post-hoc evaluation {path} evidence_status must equal "
            f"{expected_evidence_status}"
        )
    if recorded_evidence_status is None:
        payload = dict(payload)
        payload["evidence_status"] = expected_evidence_status

    declared_cap = payload.get("max_claims")
    if (
        isinstance(declared_cap, bool)
        or not isinstance(declared_cap, int)
        or declared_cap != MAX_CLAIMS
    ):
        raise SystemExit(
            f"Cached post-hoc evaluation {path} max_claims metadata must equal "
            f"{MAX_CLAIMS}"
        )
    try:
        _normalize_evaluator_output(json.dumps(payload))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"Cached post-hoc evaluation {path} is invalid: {exc}"
        ) from exc

    claims_checked = payload["claims_checked"]
    if claims_checked <= 0:
        raise SystemExit(
            f"Cached post-hoc evaluation {path} claims_checked must be positive"
        )
    expected_rate = payload["supported"] / claims_checked
    stored_rate = payload.get("strict_support_rate")
    if (
        isinstance(stored_rate, bool)
        or not isinstance(stored_rate, (int, float))
        or not math.isfinite(stored_rate)
        or float(stored_rate) != expected_rate
    ):
        raise SystemExit(
            f"Cached post-hoc evaluation {path} strict_support_rate must equal "
            "supported / claims_checked"
        )
    _validated_cache_accounting(
        payload,
        path=path,
        pricing=pricing,
        expected_evaluator_model=expected_evaluator_model,
        expected_temperature=expected_temperature,
    )
    return payload


def _validated_completed_trace(
    path: Path,
    payload: dict,
    *,
    expected_variant: str,
) -> tuple[dict, str, str]:
    experiment = payload.get("experiment")
    trace = payload.get("trace")
    if not isinstance(experiment, dict) or not isinstance(trace, dict):
        raise SystemExit(f"Completed trace must contain object metadata: {path}")
    if trace.get("completed") is not True:
        raise SystemExit(f"Trace is not completed: {path}")

    identities: dict[str, str] = {}
    for field in ("variant_id", "task_id"):
        experiment_value = experiment.get(field)
        trace_value = trace.get(field)
        if not isinstance(experiment_value, str) or not experiment_value.strip():
            raise SystemExit(f"Completed trace missing {field} in experiment: {path}")
        if not isinstance(trace_value, str) or not trace_value.strip():
            raise SystemExit(f"Completed trace missing {field} in trace: {path}")
        if experiment_value != experiment_value.strip() or trace_value != trace_value.strip():
            raise SystemExit(f"Completed trace invalid {field} whitespace: {path}")
        if experiment_value != trace_value:
            raise SystemExit(f"Completed trace {field} mismatch: {path}")
        identities[field] = trace_value

    if identities["variant_id"] != expected_variant or path.parent.name != expected_variant:
        raise SystemExit(f"Completed trace variant_id mismatch: {path}")

    run_id = trace.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise SystemExit(f"Completed trace missing run_id: {path}")
    if run_id != run_id.strip():
        raise SystemExit(f"Completed trace invalid run_id whitespace: {path}")
    if path.stem != run_id:
        raise SystemExit(f"Completed trace filename does not match run_id: {path}")

    return trace, identities["task_id"], run_id


def _cost_usage(usage_by_model: dict, pricing: dict) -> float:
    from scripts.summarize_pilot import _estimate_reported_token_cost

    cost, status = _estimate_reported_token_cost(usage_by_model, pricing)
    if cost is None:
        raise RuntimeError(f"Evaluator cost unavailable: {status}")
    return float(cost)


def _validated_cache_accounting(
    payload: dict,
    *,
    path: Path,
    pricing: dict,
    expected_evaluator_model: str,
    expected_temperature: float,
) -> float:
    if payload.get("evaluator_model") != expected_evaluator_model:
        raise SystemExit(
            f"Cached post-hoc evaluation {path} evaluator_model must equal "
            f"{expected_evaluator_model}"
        )

    temperature = payload.get("temperature")
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not math.isfinite(temperature)
        or float(temperature) != expected_temperature
    ):
        raise SystemExit(
            f"Cached post-hoc evaluation {path} temperature must equal "
            f"{expected_temperature}"
        )
    if payload.get("cost_method") != "frozen uncached rates":
        raise SystemExit(
            f"Cached post-hoc evaluation {path} cost_method must equal "
            "frozen uncached rates"
        )

    usage_by_model = payload.get("provider_usage_by_model")
    valid_usage = (
        isinstance(usage_by_model, dict)
        and set(usage_by_model) == {expected_evaluator_model}
        and isinstance(usage_by_model.get(expected_evaluator_model), dict)
    )
    if valid_usage:
        usage = usage_by_model[expected_evaluator_model]
        required_fields = (
            "model_calls",
            "unavailable_calls",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        )
        valid_usage = all(
            type(usage.get(field)) is int and usage[field] >= 0
            for field in required_fields
        )
        if valid_usage:
            prompt_tokens = usage["prompt_tokens"]
            completion_tokens = usage["completion_tokens"]
            expected_total = prompt_tokens + completion_tokens
            valid_usage = (
                usage["model_calls"] == 1
                and usage["unavailable_calls"] == 0
                and expected_total > 0
                and usage["total_tokens"] == expected_total
            )
    if not valid_usage:
        raise SystemExit(
            f"Cached post-hoc evaluation {path} provider_usage_by_model is invalid"
        )

    total_tokens = payload.get("total_tokens")
    if type(total_tokens) is not int or total_tokens != expected_total:
        raise SystemExit(
            f"Cached post-hoc evaluation {path} total_tokens must equal provider usage"
        )

    try:
        recomputed_cost = _cost_usage(usage_by_model, pricing)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"Cached post-hoc evaluation {path} cost cannot be recomputed: {exc}"
        ) from exc
    stored_cost = payload.get("estimated_cost_usd")
    if (
        isinstance(stored_cost, bool)
        or not isinstance(stored_cost, (int, float))
        or not math.isfinite(stored_cost)
        or float(stored_cost) != recomputed_cost
    ):
        raise SystemExit(
            f"Cached post-hoc evaluation {path} estimated_cost_usd must equal "
            "recomputed cost"
        )
    return recomputed_cost


def _research_context(run_id: str) -> str:
    run_dir = REPO_ROOT / "outputs" / run_id
    parts = []
    for path in sorted(run_dir.glob("research-query-*.txt")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _report_text(run_id: str) -> str:
    path = REPO_ROOT / "outputs" / run_id / "research_report.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing report markdown for run {run_id}: {path}")
    return path.read_text(encoding="utf-8")


def _existing_evaluator_cost(
    pricing: dict,
    *,
    expected_evaluator_model: str,
    expected_temperature: float,
) -> float:
    total = 0.0
    if not EVAL_ROOT.exists():
        return total
    for path in EVAL_ROOT.glob("*/*.json"):
        payload = _load_json(path)
        total += _validated_cache_accounting(
            payload,
            path=path,
            pricing=pricing,
            expected_evaluator_model=expected_evaluator_model,
            expected_temperature=expected_temperature,
        )
    return total


def _evidence_for_trace(trace: dict, variant: str, task_id: str, run_id: str) -> tuple[str, str]:
    evidence = _research_context(run_id)
    if evidence.strip():
        return evidence, "retrieved_evidence"

    successful_sources = int(trace.get("successful_source_count", 0) or 0)
    if successful_sources == 0:
        return NO_EVIDENCE_SENTINEL, "zero_successful_sources"

    raise SystemExit(
        f"Saved evidence missing for {variant}/{task_id} despite "
        f"successful_source_count={successful_sources}"
    )


def _preflight_evaluator_resume(
    expected: list[tuple[str, Path, dict, str, str]],
    *,
    pricing: dict,
    evaluator_model: str,
    evaluator_temperature: float,
) -> tuple[list[dict], list[dict]]:
    """Snapshot and validate the entire resume state before any model call."""
    expected_paths: set[Path] = set()
    for variant, trace_path, _trace, task_id, run_id in expected:
        out_path = EVAL_ROOT / variant / f"{task_id}.json"
        if out_path in expected_paths:
            raise SystemExit(
                "Completed traces map to duplicate evaluator destination "
                f"{out_path}: {variant}/{task_id}/{run_id} ({trace_path})"
            )
        expected_paths.add(out_path)
    existing_paths = set(EVAL_ROOT.glob("*/*.json")) if EVAL_ROOT.exists() else set()
    unexpected_paths = sorted(existing_paths - expected_paths)
    if unexpected_paths:
        raise SystemExit(
            "Unexpected cached post-hoc evaluation files: "
            + ", ".join(str(path) for path in unexpected_paths)
        )

    rows: list[dict] = []
    pending: list[dict] = []
    for variant, _trace_path, trace, task_id, run_id in expected:
        evidence, evidence_status = _evidence_for_trace(
            trace, variant, task_id, run_id
        )
        report = _report_text(run_id)
        out_path = EVAL_ROOT / variant / f"{task_id}.json"
        if out_path.is_file():
            rows.append(
                _load_cached_evaluation(
                    out_path,
                    expected_variant=variant,
                    expected_task_id=task_id,
                    expected_run_id=run_id,
                    expected_evaluator_model=evaluator_model,
                    expected_temperature=evaluator_temperature,
                    expected_evidence_status=evidence_status,
                    pricing=pricing,
                )
            )
            continue
        pending.append(
            {
                "variant": variant,
                "trace": trace,
                "task_id": task_id,
                "run_id": run_id,
                "out_path": out_path,
                "evidence": evidence,
                "evidence_status": evidence_status,
                "report": report,
            }
        )
    return rows, pending


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-evaluator-cost-usd", type=float, default=1.25)
    args = parser.parse_args()
    if (
        not math.isfinite(args.max_evaluator_cost_usd)
        or args.max_evaluator_cost_usd <= 0
    ):
        raise SystemExit("--max-evaluator-cost-usd must be finite and positive")
    for name in ("OPENAI_API_KEY", "SMART_LLM_MODEL", "TEMPERATURE"):
        if not os.getenv(name):
            raise SystemExit(f"Missing required environment variable: {name}")

    from scripts.run_budget_main_study import _load_pricing, _validated_trace_cost

    pricing, _pricing_snapshot = _load_pricing(PRICING_FILE)
    evaluator_model = os.environ["SMART_LLM_MODEL"]
    evaluator_temperature = float(os.environ["TEMPERATURE"])
    if not math.isfinite(evaluator_temperature):
        raise SystemExit("TEMPERATURE must be finite")
    expected = []
    for variant in VARIANTS:
        for trace_path in sorted((TRACE_ROOT / variant).glob("*.json")):
            payload = _load_json(trace_path)
            raw_trace = payload.get("trace")
            if not isinstance(raw_trace, dict):
                raise SystemExit(f"Trace metadata must be an object: {trace_path}")
            completed = raw_trace.get("completed")
            if type(completed) is not bool:
                raise SystemExit(
                    f"Invalid treatment trace {trace_path}: completed must be a "
                    "boolean"
                )
            if not completed:
                continue
            _validated_trace_cost(
                payload,
                path=trace_path,
                pricing=pricing,
            )
            trace, task_id, run_id = _validated_completed_trace(
                trace_path,
                payload,
                expected_variant=variant,
            )
            expected.append((variant, trace_path, trace, task_id, run_id))

    if not expected:
        raise SystemExit("No completed main-study traces found")

    rows, pending = _preflight_evaluator_resume(
        expected,
        pricing=pricing,
        evaluator_model=evaluator_model,
        evaluator_temperature=evaluator_temperature,
    )
    spent = sum(float(row["estimated_cost_usd"]) for row in rows)

    from agent.llm_utils import UsageTracker, create_chat_completion
    from logic.prompts import generate_verification_prompt

    for item in pending:
        variant = item["variant"]
        trace = item["trace"]
        task_id = item["task_id"]
        run_id = item["run_id"]
        out_path = item["out_path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() or out_path.is_symlink():
            raise SystemExit(
                "Evaluator resume state changed after preflight: "
                f"cache now exists for {variant}/{task_id}: {out_path}"
            )
        if spent >= args.max_evaluator_cost_usd:
            raise SystemExit(
                f"Evaluator spend guard reached ${spent:.4f} before {variant}/{task_id}; "
                f"cap=${args.max_evaluator_cost_usd:.2f}"
            )

        evidence = item["evidence"]
        evidence_status = item["evidence_status"]
        report = item["report"]

        tracker = UsageTracker()
        prompt = generate_verification_prompt(
            str(trace.get("question", "")), report, evidence, max_claims=MAX_CLAIMS
        )
        raw = create_chat_completion(
            model=evaluator_model,
            messages=[{"role": "user", "content": prompt}],
            usage_tracker=tracker,
            request_timeout_seconds=120,
        )
        result = _normalize_evaluator_output(raw)
        usage = tracker.snapshot()
        if int(result.get("claims_checked", 0) or 0) <= 0:
            raise SystemExit(f"Common evaluator checked zero claims for {variant}/{task_id}")
        if int(usage.get("unavailable_calls", 0) or 0) != 0:
            raise SystemExit(f"Provider usage missing for common evaluator {variant}/{task_id}")

        cost = _cost_usage(usage.get("by_model", {}), pricing)
        record = {
            "schema_version": 1,
            "study_id": STUDY_ID,
            "variant_id": variant,
            "task_id": task_id,
            "run_id": run_id,
            "evaluator_model": evaluator_model,
            "temperature": evaluator_temperature,
            "max_claims": MAX_CLAIMS,
            "evidence_status": evidence_status,
            "claims_checked": result["claims_checked"],
            "supported": result["supported"],
            "partially_supported": result["partially_supported"],
            "unsupported": result["unsupported"],
            "contradicted": result["contradicted"],
            "strict_support_rate": result["supported"] / result["claims_checked"],
            "examples": result.get("examples", []),
            "provider_usage_by_model": usage.get("by_model", {}),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "estimated_cost_usd": cost,
            "cost_method": "frozen uncached rates",
        }
        try:
            _publish_evaluation_cache(out_path, record)
        except FileExistsError as exc:
            raise SystemExit(
                "Evaluator cache appeared during model call; refusing to overwrite "
                f"{variant}/{task_id}: {out_path}"
            ) from exc
        rows.append(record)
        spent += cost
        print(
            f"evaluated {variant}/{task_id}: evidence={evidence_status} "
            f"claims={result['claims_checked']} support={record['strict_support_rate']:.3f} "
            f"cost=${cost:.4f}",
            flush=True,
        )

    rows = sorted(rows, key=lambda r: (r["task_id"], VARIANTS.index(r["variant_id"])))
    summary = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "n_evaluations": len(rows),
        "expected_evaluations": len(expected),
        "max_claims_per_report": MAX_CLAIMS,
        "estimated_evaluator_cost_usd": sum(float(r["estimated_cost_usd"]) for r in rows),
        "zero_evidence_evaluations": sum(
            1 for r in rows if r.get("evidence_status") == "zero_successful_sources"
        ),
        "variant_summary": {},
    }
    for variant in VARIANTS:
        items = [r for r in rows if r["variant_id"] == variant]
        summary["variant_summary"][variant] = {
            "n": len(items),
            "claims_checked": sum(r["claims_checked"] for r in items),
            "supported": sum(r["supported"] for r in items),
            "partially_supported": sum(r["partially_supported"] for r in items),
            "unsupported": sum(r["unsupported"] for r in items),
            "contradicted": sum(r["contradicted"] for r in items),
            "macro_strict_support_rate": (
                sum(r["strict_support_rate"] for r in items) / len(items) if items else None
            ),
        }

    if len(rows) != len(expected):
        raise SystemExit(f"Post-hoc evaluator incomplete: {len(rows)}/{len(expected)}")
    if summary["estimated_evaluator_cost_usd"] > args.max_evaluator_cost_usd:
        raise SystemExit(
            f"Evaluator completed but exceeded cap: ${summary['estimated_evaluator_cost_usd']:.4f} "
            f"> ${args.max_evaluator_cost_usd:.2f}"
        )

    summary_path = REPO_ROOT / "outputs" / "posthoc_support_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    csv_path = REPO_ROOT / "outputs" / "posthoc_support_runs.csv"
    fieldnames = [
        "variant_id", "task_id", "run_id", "evidence_status", "claims_checked", "supported",
        "partially_supported", "unsupported", "contradicted", "strict_support_rate",
        "total_tokens", "estimated_cost_usd",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
