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
    browsing during one run.  This is intentionally an attempted-browse
    budget rather than a successful-source target so variants receive the
    same maximum number of external browsing calls even when some pages fail.
    """

    variant_id: str = "P6"
    planning_mode: str = "planner"
    source_budget: int = 6
    verification_mode: str = "none"
    trace_root: str = "outputs/experiment_traces"

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

    @classmethod
    def from_variant(cls, variant_id: str) -> "ExperimentConfig":
        """Return one of the initial pilot variants used by the paper."""
        variants = {
            "D6": cls(
                variant_id="D6",
                planning_mode="direct",
                source_budget=6,
                verification_mode="none",
            ),
            "P6": cls(
                variant_id="P6",
                planning_mode="planner",
                source_budget=6,
                verification_mode="none",
            ),
            "P6V": cls(
                variant_id="P6V",
                planning_mode="planner",
                source_budget=6,
                verification_mode="verify",
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
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": config.to_dict(),
        "trace": trace,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return os.fspath(output_path)
