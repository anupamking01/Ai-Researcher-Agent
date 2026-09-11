"""Apply one common post-hoc support evaluator to every completed main-study report.

The evaluator is measurement-only. It does not repair reports and it evaluates
all variants with the same prompt, model, 12-claim cap, evidence restriction,
and frozen cost accounting. A separate $1.25 evaluator spend guard preserves
the user's fixed remaining API-credit budget.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TRACE_ROOT = REPO_ROOT / "outputs" / "experiment_traces"
EVAL_ROOT = REPO_ROOT / "outputs" / "posthoc_evaluations"
PRICING_FILE = REPO_ROOT / "experiments" / "openai_pricing_2026-09-08.json"
VARIANTS = ("D3", "D6", "P6", "P6V")
MAX_CLAIMS = 12


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cost_usage(usage_by_model: dict, pricing: dict) -> float:
    from scripts.summarize_pilot import _estimate_reported_token_cost

    cost, status = _estimate_reported_token_cost(usage_by_model, pricing)
    if cost is None:
        raise RuntimeError(f"Evaluator cost unavailable: {status}")
    return float(cost)


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


def _existing_evaluator_cost(pricing: dict) -> float:
    total = 0.0
    if not EVAL_ROOT.exists():
        return total
    for path in EVAL_ROOT.glob("*/*.json"):
        payload = _load_json(path)
        total += float(payload.get("estimated_cost_usd", 0.0) or 0.0)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-evaluator-cost-usd", type=float, default=1.25)
    args = parser.parse_args()
    if args.max_evaluator_cost_usd <= 0:
        raise SystemExit("--max-evaluator-cost-usd must be positive")
    for name in ("OPENAI_API_KEY", "SMART_LLM_MODEL", "TEMPERATURE"):
        if not os.getenv(name):
            raise SystemExit(f"Missing required environment variable: {name}")

    from agent.llm_utils import UsageTracker, create_chat_completion
    from logic.experiment import normalize_verifier_output
    from logic.prompts import generate_verification_prompt

    pricing = _load_json(PRICING_FILE)
    rows = []
    expected = []
    for variant in VARIANTS:
        for trace_path in sorted((TRACE_ROOT / variant).glob("*.json")):
            payload = _load_json(trace_path)
            trace = payload.get("trace", {})
            if trace.get("completed") is not True:
                continue
            expected.append((variant, trace_path, trace))

    if not expected:
        raise SystemExit("No completed main-study traces found")

    for variant, trace_path, trace in expected:
        task_id = str(trace.get("task_id", ""))
        run_id = str(trace.get("run_id", trace_path.stem))
        out_path = EVAL_ROOT / variant / f"{task_id}.json"
        if out_path.is_file():
            rows.append(_load_json(out_path))
            continue

        spent = _existing_evaluator_cost(pricing)
        if spent >= args.max_evaluator_cost_usd:
            raise SystemExit(
                f"Evaluator spend guard reached ${spent:.4f} before {variant}/{task_id}; "
                f"cap=${args.max_evaluator_cost_usd:.2f}"
            )

        evidence = _research_context(run_id)
        report = _report_text(run_id)
        if not evidence.strip():
            raise SystemExit(f"No saved evidence context for {variant}/{task_id}")

        tracker = UsageTracker()
        prompt = generate_verification_prompt(
            str(trace.get("question", "")), report, evidence, max_claims=MAX_CLAIMS
        )
        raw = create_chat_completion(
            model=os.environ["SMART_LLM_MODEL"],
            messages=[{"role": "user", "content": prompt}],
            usage_tracker=tracker,
            request_timeout_seconds=120,
        )
        result = normalize_verifier_output(raw)
        usage = tracker.snapshot()
        if int(result.get("claims_checked", 0) or 0) <= 0:
            raise SystemExit(f"Common evaluator checked zero claims for {variant}/{task_id}")
        if int(usage.get("unavailable_calls", 0) or 0) != 0:
            raise SystemExit(f"Provider usage missing for common evaluator {variant}/{task_id}")

        cost = _cost_usage(usage.get("by_model", {}), pricing)
        record = {
            "schema_version": 1,
            "study_id": "budget-main-v1",
            "variant_id": variant,
            "task_id": task_id,
            "run_id": run_id,
            "evaluator_model": os.environ["SMART_LLM_MODEL"],
            "temperature": float(os.environ["TEMPERATURE"]),
            "max_claims": MAX_CLAIMS,
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
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        rows.append(record)
        print(
            f"evaluated {variant}/{task_id}: claims={result['claims_checked']} "
            f"support={record['strict_support_rate']:.3f} cost=${cost:.4f}",
            flush=True,
        )

    rows = sorted(rows, key=lambda r: (r["task_id"], VARIANTS.index(r["variant_id"])))
    summary = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "n_evaluations": len(rows),
        "expected_evaluations": len(expected),
        "max_claims_per_report": MAX_CLAIMS,
        "estimated_evaluator_cost_usd": sum(float(r["estimated_cost_usd"]) for r in rows),
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

    summary_path = REPO_ROOT / "outputs" / "posthoc_support_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    csv_path = REPO_ROOT / "outputs" / "posthoc_support_runs.csv"
    fieldnames = [
        "variant_id", "task_id", "run_id", "claims_checked", "supported",
        "partially_supported", "unsupported", "contradicted", "strict_support_rate",
        "total_tokens", "estimated_cost_usd",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})

    if len(rows) != len(expected):
        raise SystemExit(f"Post-hoc evaluator incomplete: {len(rows)}/{len(expected)}")
    if summary["estimated_evaluator_cost_usd"] > args.max_evaluator_cost_usd:
        raise SystemExit(
            f"Evaluator completed but exceeded cap: ${summary['estimated_evaluator_cost_usd']:.4f} "
            f"> ${args.max_evaluator_cost_usd:.2f}"
        )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
