"""Configuration and trace persistence for reproducible research-agent runs."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_VALID_PLANNING_MODES = {"direct", "planner"}
_VALID_VERIFICATION_MODES = {"none", "verify"}


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
        if self.source_budget <= 0:
            raise ValueError("source_budget must be a positive integer")
        if not self.variant_id.strip():
            raise ValueError("variant_id must be non-empty")
        if self.search_candidate_multiplier <= 0:
            raise ValueError("search_candidate_multiplier must be positive")
        if self.browse_timeout_seconds <= 0:
            raise ValueError("browse_timeout_seconds must be positive")
        if self.run_timeout_seconds <= 0:
            raise ValueError("run_timeout_seconds must be positive")
        if self.max_concurrent_browses <= 0:
            raise ValueError("max_concurrent_browses must be positive")

    @classmethod
    def from_variant(cls, variant_id: str) -> "ExperimentConfig":
        """Return one of the frozen initial pilot variants used by the paper."""
        variants = {
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
                f"Unknown pilot variant {variant_id!r}; choose D6, P6, or P6V"
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def allocate_source_budgets(total_budget: int, n_queries: int) -> list[int]:
    """Spread a fixed external browsing-call budget across planned queries."""
    if total_budget < 0:
        raise ValueError("total_budget cannot be negative")
    if n_queries < 0:
        raise ValueError("n_queries cannot be negative")
    if n_queries == 0:
        return []

    base, remainder = divmod(total_budget, n_queries)
    return [base + (1 if index < remainder else 0) for index in range(n_queries)]


def normalize_verifier_output(raw_result: str) -> dict[str, Any]:
    """Parse and normalize the bounded verifier's JSON response."""
    text = (raw_result or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Verifier output must be a JSON object")

    labels = (
        "supported",
        "partially_supported",
        "unsupported",
        "contradicted",
    )
    normalized: dict[str, Any] = {}
    for label in labels:
        value = int(data.get(label, 0))
        normalized[label] = max(value, 0)

    normalized["claims_checked"] = sum(normalized[label] for label in labels)
    examples = data.get("examples", [])
    normalized["examples"] = examples[:8] if isinstance(examples, list) else []
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
