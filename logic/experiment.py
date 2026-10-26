"""Configuration and trace persistence for reproducible research-agent runs."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_VALID_PLANNING_MODES = {"direct", "planner"}
_VALID_VERIFICATION_MODES = {"none", "verify"}


def _require_positive_finite_timeout(value: int | float, *, field: str) -> None:
    """Reject nonnumeric, non-finite or unusably large runtime timeout values."""
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be a positive finite number")
    try:
        valid = value > 0 and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{field} must be a positive finite number")


@dataclass(frozen=True)
class ExperimentConfig:
    """Controls one experimental agent variant.

    ``source_budget`` is the maximum number of unique URLs scheduled for
    browsing during one run. This is an attempted-browse budget rather than a
    successful-source target so variants receive the same maximum number of
    external browsing calls even when some pages fail.

    Timeout and browser-concurrency values are infrastructure guardrails rather
    than experimental treatments. They are persisted in every trace so stalled
    websites, renderer exhaustion, or model calls cannot hold an entire pilot
    indefinitely and the guardrails remain auditable when results are compared.
    """

    variant_id: str = "P6"
    planning_mode: str = "planner"
    source_budget: int = 6
    verification_mode: str = "none"
    trace_root: str = "outputs/experiment_traces"
    task_set_id: str = ""
    task_id: str = ""
    stream_report: bool = True
    search_candidate_multiplier: int = 3
    browse_timeout_seconds: float = 60.0
    run_timeout_seconds: float = 480.0
    max_concurrent_browses: int = 2

    def __post_init__(self) -> None:
        if self.planning_mode not in _VALID_PLANNING_MODES:
            raise ValueError(
                f"planning_mode must be one of {sorted(_VALID_PLANNING_MODES)}"
            )
        if self.verification_mode not in _VALID_VERIFICATION_MODES:
            raise ValueError(
                "verification_mode must be one of "
                f"{sorted(_VALID_VERIFICATION_MODES)}"
            )
        if type(self.source_budget) is not int or self.source_budget <= 0:
            raise ValueError("source_budget must be a positive integer")
        if not self.variant_id.strip():
            raise ValueError("variant_id must be non-empty")
        if type(self.search_candidate_multiplier) is not int or self.search_candidate_multiplier <= 0:
            raise ValueError("search_candidate_multiplier must be a positive integer")
        _require_positive_finite_timeout(
            self.browse_timeout_seconds, field="browse_timeout_seconds"
        )
        _require_positive_finite_timeout(
            self.run_timeout_seconds, field="run_timeout_seconds"
        )
        if type(self.max_concurrent_browses) is not int or self.max_concurrent_browses <= 0:
            raise ValueError("max_concurrent_browses must be a positive integer")

    @classmethod
    def from_variant(cls, variant_id: str) -> "ExperimentConfig":
        """Return a predeclared research variant used by the study."""
        variants = {
            "D3": cls(
                variant_id="D3",
                planning_mode="direct",
                source_budget=3,
                verification_mode="none",
                stream_report=False,
            ),
            "D6": cls(
                variant_id="D6",
                planning_mode="direct",
                source_budget=6,
                verification_mode="none",
                stream_report=False,
            ),
            "P6": cls(
                variant_id="P6",
                planning_mode="planner",
                source_budget=6,
                verification_mode="none",
                stream_report=False,
            ),
            "P6V": cls(
                variant_id="P6V",
                planning_mode="planner",
                source_budget=6,
                verification_mode="verify",
                stream_report=False,
            ),
        }
        try:
            return variants[variant_id.upper()]
        except KeyError as exc:
            raise ValueError(
                f"Unknown research variant {variant_id!r}; choose D3, D6, P6, or P6V"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def allocate_source_budgets(total_budget: int, n_queries: int) -> list[int]:
    """Spread a fixed external browsing-call budget across planned queries."""
    if type(total_budget) is not int or total_budget < 0:
        raise ValueError("total_budget must be a non-negative integer")
    if type(n_queries) is not int or n_queries < 0:
        raise ValueError("n_queries must be a non-negative integer")
    if n_queries == 0:
        return []

    base, remainder = divmod(total_budget, n_queries)
    return [base + (1 if index < remainder else 0) for index in range(n_queries)]


def _unique_verifier_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous object members at every depth of model JSON."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Verifier output contains duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_verifier_json_constant(token: str) -> None:
    """Python's default JSON decoder otherwise accepts NaN/Infinity extensions."""
    raise ValueError(f"Verifier output contains non-finite JSON token {token!r}")


def _finite_verifier_json_float(token: str) -> float:
    """Also reject finite-looking JSON exponent syntax that overflows to infinity."""
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"Verifier output contains non-finite JSON number {token!r}")
    return value


def normalize_verifier_output(
    raw_result: str, *, max_claims: int = 20
) -> dict[str, Any]:
    """Parse unambiguous finite JSON, then enforce the bounded verification rubric."""
    if (
        isinstance(max_claims, bool)
        or not isinstance(max_claims, int)
        or max_claims <= 0
    ):
        raise ValueError("max_claims must be a positive integer")

    text = (raw_result or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Parse model text strictly *before* keeping only the normalized counts.
    # Last-key-wins parsing would silently erase a conflicting classification;
    # NaN/Infinity can also survive in retained illustrative examples.
    data = json.loads(
        text,
        object_pairs_hook=_unique_verifier_json_object,
        parse_constant=_reject_nonfinite_verifier_json_constant,
        parse_float=_finite_verifier_json_float,
    )
    if not isinstance(data, dict):
        raise ValueError("Verifier output must be a JSON object")

    labels = (
        "supported",
        "partially_supported",
        "unsupported",
        "contradicted",
    )
    normalized: dict[str, Any] = {}
    for label in ("claims_checked", *labels):
        if label not in data:
            raise ValueError(f"Verifier output missing required count {label!r}")
        value = data[label]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"Verifier output {label} must be a non-negative integer"
            )
        normalized[label] = value

    if sum(normalized[label] for label in labels) != normalized["claims_checked"]:
        raise ValueError("Verifier label counts must sum to claims_checked")
    if normalized["claims_checked"] > max_claims:
        raise ValueError(
            "Verifier claims_checked "
            f"{normalized['claims_checked']} exceeds max_claims={max_claims}"
        )

    if "examples" not in data:
        raise ValueError("Verifier output missing required field 'examples'")
    examples = data["examples"]
    if not isinstance(examples, list):
        raise ValueError("Verifier output examples must be a JSON list")
    normalized["examples"] = examples[:8]
    return normalized


def save_run_trace(
    *,
    trace: dict[str, Any],
    config: ExperimentConfig,
    run_id: str,
) -> str:
    """Persist one trace as deterministic, human-readable JSON."""
    root = Path(config.trace_root) / config.variant_id
    root.mkdir(parents=True, exist_ok=True)
    output_path = root / f"{run_id}.json"

    payload = {
        "schema_version": 2,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": config.to_dict(),
        "trace": trace,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return os.fspath(output_path)
