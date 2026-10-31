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
import hashlib
import io
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
TASK_FILE = REPO_ROOT / "experiments" / "main_budget_tasks.json"
VARIANTS = ("D3", "D6", "P6", "P6V")
MAX_CLAIMS = 12
STUDY_ID = "budget-main-v1"
NONCANONICAL_EVALUATOR_REPLAY_ACK = "NONCANONICAL_EVALUATOR_RECOVERY"
ORIGINAL_EVALUATOR_RECOVERY_ACTIONS_RUN_ID = 34783525480
ORIGINAL_TREATMENT_ACTIONS_RUN_ID = 34620917346
FROZEN_EVALUATOR_MODEL = "gpt-5.6-terra"
FROZEN_EVALUATOR_TEMPERATURE = 1.0
NO_EVIDENCE_SENTINEL = (
    "[NO RETRIEVED EVIDENCE WAS AVAILABLE FOR THIS TREATMENT RUN. "
    "The run recorded zero successful retrieved sources. Do not use outside knowledge.]"
)


def _require_noncanonical_evaluator_replay_ack(value: str | None) -> None:
    """Refuse historical-looking remeasurement before credential or source access."""
    if value != NONCANONICAL_EVALUATOR_REPLAY_ACK:
        raise SystemExit(
            "Refusing evaluator replay without explicit noncanonical acknowledgement: "
            "--noncanonical-evaluator-replay-ack NONCANONICAL_EVALUATOR_RECOVERY. "
            "New measurements cannot replace the frozen historical evaluator results."
        )


def _noncanonical_evaluator_replay_provenance() -> dict:
    """Label newly produced measurements without authenticating reused caches."""
    return {
        "classification": "noncanonical_evaluator_replay",
        "original_frozen_study_id": STUDY_ID,
        "original_actions_evaluator_recovery_run_id": ORIGINAL_EVALUATOR_RECOVERY_ACTIONS_RUN_ID,
        "original_actions_treatment_run_id": ORIGINAL_TREATMENT_ACTIONS_RUN_ID,
        "can_replace_original_evaluator_evidence": False,
        "historical_archive_custody_authenticated": False,
    }


def _validate_frozen_evaluator_config(model: str, temperature: float) -> None:
    """Require the evaluator configuration frozen before main-study recovery."""
    if model != FROZEN_EVALUATOR_MODEL:
        raise SystemExit(
            "SMART_LLM_MODEL must equal frozen evaluator model "
            f"{FROZEN_EVALUATOR_MODEL}"
        )
    if temperature != FROZEN_EVALUATOR_TEMPERATURE:
        raise SystemExit(
            "TEMPERATURE must equal frozen evaluator temperature "
            f"{FROZEN_EVALUATOR_TEMPERATURE}"
        )


def _require_regular_file(path: Path, *, label: str) -> None:
    path = Path(path)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise SystemExit(
            f"{label} directory must be a regular non-symlink directory: "
            f"{path.parent}"
        )
    if path.is_symlink() or not path.is_file():
        raise SystemExit(
            f"{label} must be a regular non-symlink file: {path}"
        )


def _read_regular_bytes(path: Path, *, label: str) -> bytes:
    path = Path(path)
    _require_regular_file(path, label=label)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"Cannot read {label} {path}: {exc}") from exc


def _read_regular_text(path: Path, *, label: str) -> str:
    raw = _read_regular_bytes(path, label=label)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"{label} must contain valid UTF-8: {path}") from exc


def _text_fingerprint(text: str) -> dict:
    content = text.encode("utf-8")
    return {
        "byte_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _evaluator_input_fingerprints(
    *, question: str, report: str, evidence: str, prompt: str
) -> dict:
    return {
        "algorithm": "sha256",
        "encoding": "utf-8",
        "question": _text_fingerprint(question),
        "report": _text_fingerprint(report),
        "evidence": _text_fingerprint(evidence),
        "prompt": _text_fingerprint(prompt),
    }


def _load_json(path: Path) -> dict:
    from scripts.run_budget_main_study import _reject_duplicate_json_keys

    try:
        raw = _read_regular_bytes(path, label="JSON input")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"Invalid JSON file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid JSON file {path}: top level must be an object")
    return payload


def _load_frozen_task_contract(
    path: Path | None = None,
) -> tuple[str, dict[str, str]]:
    """Load the exact task-set identity and question bound to each task ID."""
    from scripts.run_budget_main_study import _load_task_file

    task_set_id, tasks, _snapshot = _load_task_file(
        TASK_FILE if path is None else Path(path)
    )
    return task_set_id, {task["id"]: task["question"] for task in tasks}


def _validate_trace_task_contract(
    payload: dict,
    *,
    path: Path,
    expected_task_set_id: str,
    expected_questions: dict[str, str],
) -> None:
    """Bind a captured trace to the frozen task set and exact question text."""
    experiment = payload.get("experiment")
    trace = payload.get("trace")
    if not isinstance(experiment, dict) or not isinstance(trace, dict):
        raise SystemExit(f"Treatment trace must contain object metadata: {path}")

    if (
        experiment.get("task_set_id") != expected_task_set_id
        or trace.get("task_set_id") != expected_task_set_id
    ):
        raise SystemExit(
            f"Treatment trace {path} task_set_id must match frozen task set "
            f"{expected_task_set_id}"
        )

    task_id = trace.get("task_id")
    expected_question = expected_questions.get(task_id)
    if expected_question is None:
        raise SystemExit(
            f"Treatment trace {path} task_id is absent from frozen task set: "
            f"{task_id}"
        )
    if trace.get("question") != expected_question:
        raise SystemExit(
            f"Treatment trace {path} question must match frozen task definition "
            f"for {task_id}"
        )


def _require_complete_frozen_treatment_matrix(
    expected: list[tuple[str, Path, dict, str, str]],
    expected_questions: dict[str, str],
) -> None:
    """Reject partial, repeated, or substituted frozen cells before API calls.

    This is structural preflight for an acknowledged *noncanonical* replay;
    it does not authenticate original treatment traces or evaluator results.
    """
    frozen_ids = {f"main-{index:02d}" for index in range(1, 11)}
    if set(expected_questions) != frozen_ids:
        raise SystemExit(
            "Refusing evaluator replay: expected exactly the ten frozen "
            "main-01..main-10 task identifiers"
        )

    required = {(variant, task_id) for variant in VARIANTS for task_id in frozen_ids}
    found: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    seen_run_ids: set[str] = set()
    repeated_run_ids: set[str] = set()
    for variant, _trace_path, _trace, task_id, run_id in expected:
        cell = (variant, task_id)
        if cell in found:
            duplicates.add(cell)
        found.add(cell)
        if run_id in seen_run_ids:
            repeated_run_ids.add(run_id)
        seen_run_ids.add(run_id)

    missing = required - found
    unexpected = found - required
    if missing or unexpected or duplicates or repeated_run_ids:
        raise SystemExit(
            "Refusing evaluator replay: incomplete or ambiguous frozen "
            "40-cell treatment matrix; "
            f"missing={sorted(missing)} unexpected={sorted(unexpected)} "
            f"duplicate_cells={sorted(duplicates)} "
            f"reused_run_ids={sorted(repeated_run_ids)}"
        )


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


def _stage_durable_output(path: Path, content: bytes) -> Path:
    """Write and sync one complete output beside its final destination."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
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
    except BaseException:
        staging_path.unlink(missing_ok=True)
        raise
    return staging_path


def _publish_aggregate_outputs(
    summary_path: Path,
    csv_path: Path,
    summary: dict,
    rows: list[dict],
) -> None:
    """Stage every aggregate artifact before replacing either final file."""
    fieldnames = [
        "variant_id",
        "task_id",
        "run_id",
        "evidence_status",
        "claims_checked",
        "supported",
        "partially_supported",
        "unsupported",
        "contradicted",
        "strict_support_rate",
        "total_tokens",
        "estimated_cost_usd",
    ]
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in fieldnames})
    csv_content = csv_buffer.getvalue().encode("utf-8")
    summary["posthoc_support_runs_sha256"] = hashlib.sha256(
        csv_content
    ).hexdigest()

    outputs = [
        (
            Path(summary_path),
            json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"),
        ),
        (Path(csv_path), csv_content),
    ]
    staged: list[tuple[Path, Path]] = []
    try:
        for final_path, content in outputs:
            staged.append((final_path, _stage_durable_output(final_path, content)))
        for final_path, staging_path in staged:
            os.replace(staging_path, final_path)

        for directory in {path.parent for path, _staging in staged}:
            directory_descriptor = os.open(
                directory,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        for _final_path, staging_path in staged:
            staging_path.unlink(missing_ok=True)


def _verify_aggregate_outputs(summary_path: Path, csv_path: Path) -> None:
    """Require the aggregate summary to bind the exact run-level CSV bytes."""
    summary = _load_json(Path(summary_path))
    expected = summary.get("posthoc_support_runs_sha256")
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        raise SystemExit(
            "Post-hoc aggregate summary lacks a valid CSV generation fingerprint"
        )
    observed = hashlib.sha256(
        _read_regular_bytes(Path(csv_path), label="post-hoc aggregate CSV")
    ).hexdigest()
    if observed != expected:
        raise SystemExit(
            "post-hoc aggregate generation mismatch: summary binds CSV "
            f"{expected}, observed {observed}"
        )


def _normalize_evaluator_output(raw_result: str) -> dict:
    from logic.experiment import normalize_verifier_output

    return normalize_verifier_output(raw_result, max_claims=MAX_CLAIMS)



def _require_zero_evidence_classifications(
    record: dict, *, evidence_status: str, label: str
) -> None:
    """Enforce the frozen evidence-only rubric for a zero-source sentinel.

    Without retrieved evidence, a factual claim cannot be supported, partially
    supported, or contradicted *by that evidence*. Keep the original report
    and its valid zero-source outcome; reject an incoherent measurement rather
    than silently inflating support or rerunning the treatment/evaluator.
    """
    if evidence_status != "zero_successful_sources":
        return
    checked = record.get("claims_checked")
    if (
        type(checked) is not int
        or checked <= 0
        or type(record.get("unsupported")) is not int
        or record["unsupported"] != checked
        or any(
            type(record.get(field)) is not int or record[field] != 0
            for field in ("supported", "partially_supported", "contradicted")
        )
    ):
        raise SystemExit(
            f"{label}: zero successful sources requires every evaluated "
            "claim to be unsupported under the evidence-only rubric"
        )

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
    expected_input_fingerprints: dict | None = None,
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
        expected_input_fingerprints=expected_input_fingerprints,
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
    expected_input_fingerprints: dict | None = None,
) -> dict:
    """Validate one already-captured evaluator record against its bound cell."""
    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise SystemExit(
            f"Cached post-hoc evaluation {path} schema_version must equal 1 or 2"
        )
    if schema_version == 1:
        if "input_fingerprints" in payload:
            raise SystemExit(
                f"Cached post-hoc evaluation {path} schema_version 1 must not "
                "declare input_fingerprints"
            )
    else:
        fingerprints = payload.get("input_fingerprints")
        valid_fingerprints = (
            isinstance(fingerprints, dict)
            and set(fingerprints)
            == {"algorithm", "encoding", "question", "report", "evidence", "prompt"}
            and fingerprints.get("algorithm") == "sha256"
            and fingerprints.get("encoding") == "utf-8"
        )
        if valid_fingerprints:
            for name in ("question", "report", "evidence", "prompt"):
                entry = fingerprints.get(name)
                if not (
                    isinstance(entry, dict)
                    and set(entry) == {"byte_size", "sha256"}
                    and type(entry.get("byte_size")) is int
                    and entry["byte_size"] >= 0
                    and isinstance(entry.get("sha256"), str)
                    and len(entry["sha256"]) == 64
                    and all(char in "0123456789abcdef" for char in entry["sha256"])
                ):
                    valid_fingerprints = False
                    break
        if not valid_fingerprints:
            raise SystemExit(
                f"Cached post-hoc evaluation {path} input_fingerprints are invalid"
            )
        if (
            expected_input_fingerprints is not None
            and fingerprints != expected_input_fingerprints
        ):
            raise SystemExit(
                f"Cached post-hoc evaluation {path} input_fingerprints must match "
                "the current evaluator prompt inputs"
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
    if (
        recorded_evidence_status != expected_evidence_status
        and not (schema_version == 1 and recorded_evidence_status is None)
    ):
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
    _require_zero_evidence_classifications(
        payload,
        evidence_status=expected_evidence_status,
        label=f"Cached post-hoc evaluation {path}",
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
            f"Cached post-hoc evaluation {path} evaluator_model must equal frozen "
            f"evaluator model {expected_evaluator_model}"
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


def _research_context(run_id: str, *, root: Path | None = None) -> str:
    root = REPO_ROOT if root is None else Path(root)
    run_dir = root / "outputs" / run_id
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise SystemExit(
            "Evaluator run directory must be a regular non-symlink directory: "
            f"{run_dir}"
        )
    parts = []
    for path in sorted(run_dir.glob("research-query-*.txt")):
        text = _read_regular_text(path, label="Evaluator evidence").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _report_text(run_id: str, *, root: Path | None = None) -> str:
    root = REPO_ROOT if root is None else Path(root)
    path = root / "outputs" / run_id / "research_report.md"
    return _read_regular_text(path, label="Evaluator report")


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


def _evidence_for_trace(
    trace: dict,
    variant: str,
    task_id: str,
    run_id: str,
    *,
    root: Path | None = None,
) -> tuple[str, str]:
    evidence = _research_context(run_id, root=root)
    if evidence.strip():
        return evidence, "retrieved_evidence"

    successful_sources = int(trace.get("successful_source_count", 0) or 0)
    if successful_sources == 0:
        return NO_EVIDENCE_SENTINEL, "zero_successful_sources"

    raise SystemExit(
        f"Saved evidence missing for {variant}/{task_id} despite "
        f"successful_source_count={successful_sources}"
    )


def _prepare_evaluator_input(
    trace: dict,
    variant: str,
    task_id: str,
    run_id: str,
    *,
    root: Path | None = None,
) -> dict:
    from logic.prompts import generate_verification_prompt

    evidence, evidence_status = _evidence_for_trace(
        trace,
        variant,
        task_id,
        run_id,
        root=root,
    )
    report = _report_text(run_id, root=root)
    question = str(trace.get("question", ""))
    prompt = generate_verification_prompt(
        question, report, evidence, max_claims=MAX_CLAIMS
    )
    return {
        "evidence_status": evidence_status,
        "prompt": prompt,
        "input_fingerprints": _evaluator_input_fingerprints(
            question=question,
            report=report,
            evidence=evidence,
            prompt=prompt,
        ),
    }


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
        prepared = _prepare_evaluator_input(trace, variant, task_id, run_id)
        evidence_status = prepared["evidence_status"]
        prompt = prepared["prompt"]
        input_fingerprints = prepared["input_fingerprints"]
        out_path = EVAL_ROOT / variant / f"{task_id}.json"
        if out_path.exists() or out_path.is_symlink():
            _require_regular_file(out_path, label="Evaluator cache")
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
                    expected_input_fingerprints=input_fingerprints,
                )
            )
            continue
        pending.append(
            {
                "variant": variant,
                "task_id": task_id,
                "run_id": run_id,
                "out_path": out_path,
                "evidence_status": evidence_status,
                "prompt": prompt,
                "input_fingerprints": input_fingerprints,
            }
        )
    return rows, pending


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-evaluator-cost-usd", type=float, default=1.25)
    parser.add_argument("--noncanonical-evaluator-replay-ack", default=None)
    args = parser.parse_args()
    _require_noncanonical_evaluator_replay_ack(args.noncanonical_evaluator_replay_ack)
    print(
        "NONCANONICAL EVALUATOR REPLAY: new measurements cannot replace frozen "
        "historical recovery or authenticate missing treatment evidence.",
        flush=True,
    )
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
    task_set_id, expected_questions = _load_frozen_task_contract()
    evaluator_model = os.environ["SMART_LLM_MODEL"]
    evaluator_temperature = float(os.environ["TEMPERATURE"])
    if not math.isfinite(evaluator_temperature):
        raise SystemExit("TEMPERATURE must be finite")
    _validate_frozen_evaluator_config(evaluator_model, evaluator_temperature)
    expected = []
    selected_trace_paths: set[Path] = set()
    for variant in VARIANTS:
        for trace_path in sorted((TRACE_ROOT / variant).glob("*.json")):
            selected_trace_paths.add(trace_path)
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
            _validate_trace_task_contract(
                payload,
                path=trace_path,
                expected_task_set_id=task_set_id,
                expected_questions=expected_questions,
            )
            if not completed:
                raise SystemExit(
                    "Refusing evaluator replay: incomplete treatment trace "
                    f"{trace_path}"
                )
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

    unexpected_trace_paths = sorted(
        set(TRACE_ROOT.glob("*/*.json")) - selected_trace_paths
    )
    if unexpected_trace_paths:
        raise SystemExit(
            "Refusing evaluator replay: unselected treatment trace files: "
            + ", ".join(str(path) for path in unexpected_trace_paths)
        )
    _require_complete_frozen_treatment_matrix(expected, expected_questions)

    rows, pending = _preflight_evaluator_resume(
        expected,
        pricing=pricing,
        evaluator_model=evaluator_model,
        evaluator_temperature=evaluator_temperature,
    )
    spent = sum(float(row["estimated_cost_usd"]) for row in rows)

    from agent.llm_utils import UsageTracker, create_chat_completion
    for item in pending:
        variant = item["variant"]
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

        evidence_status = item["evidence_status"]

        tracker = UsageTracker()
        prompt = item["prompt"]
        raw = create_chat_completion(
            model=evaluator_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=evaluator_temperature,
            usage_tracker=tracker,
            request_timeout_seconds=120,
        )
        result = _normalize_evaluator_output(raw)
        _require_zero_evidence_classifications(
            result,
            evidence_status=evidence_status,
            label=f"Common evaluator {variant}/{task_id}",
        )
        usage = tracker.snapshot()
        if int(result.get("claims_checked", 0) or 0) <= 0:
            raise SystemExit(f"Common evaluator checked zero claims for {variant}/{task_id}")
        if int(usage.get("unavailable_calls", 0) or 0) != 0:
            raise SystemExit(f"Provider usage missing for common evaluator {variant}/{task_id}")

        cost = _cost_usage(usage.get("by_model", {}), pricing)
        record = {
            "schema_version": 2,
            "study_id": STUDY_ID,
            "variant_id": variant,
            "task_id": task_id,
            "run_id": run_id,
            "evaluator_model": evaluator_model,
            "temperature": evaluator_temperature,
            "max_claims": MAX_CLAIMS,
            "evidence_status": evidence_status,
            "input_fingerprints": item["input_fingerprints"],
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
        record["replay_provenance"] = _noncanonical_evaluator_replay_provenance()
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
        "replay_provenance": {
            **_noncanonical_evaluator_replay_provenance(),
            "reused_cached_measurements": len(rows) - len(pending),
            "new_noncanonical_measurements": len(pending),
        },
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
    csv_path = REPO_ROOT / "outputs" / "posthoc_support_runs.csv"
    _publish_aggregate_outputs(summary_path, csv_path, summary, rows)
    _verify_aggregate_outputs(summary_path, csv_path)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
