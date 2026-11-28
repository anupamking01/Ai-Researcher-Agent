"""Validation helpers for reproducible research experiment metadata.

Experiment results are only interpretable when the configuration that produced
them is recorded. This module provides a dependency-free manifest with explicit
required fields and deterministic serialization suitable for archiving beside
raw traces.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import isfinite
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class ExperimentManifest:
    """Configuration provenance required to reproduce an agent experiment."""

    experiment_id: str
    git_commit_sha: str
    task_set_version: str
    provider: str
    model: str
    prompt_version: str
    search_provider: str
    max_source_budget: int
    temperature: float = 0.0
    seed: int | None = None

    def validate(self) -> None:
        required_text = {
            "experiment_id": self.experiment_id,
            "git_commit_sha": self.git_commit_sha,
            "task_set_version": self.task_set_version,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "search_provider": self.search_provider,
        }
        for name, value in required_text.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.git_commit_sha):
            raise ValueError(
                "git_commit_sha must be a full lowercase Git object ID"
            )
        if (
            isinstance(self.max_source_budget, bool)
            or not isinstance(self.max_source_budget, int)
            or self.max_source_budget <= 0
        ):
            raise ValueError("max_source_budget must be a positive integer")
        if isinstance(self.temperature, bool) or not isinstance(
            self.temperature, (int, float)
        ):
            raise ValueError("temperature must be a finite number")
        try:
            temperature_is_finite = isfinite(self.temperature)
        except OverflowError as exc:
            raise ValueError("temperature must be finite") from exc
        if not temperature_is_finite:
            raise ValueError("temperature must be finite")
        if self.temperature < 0:
            raise ValueError("temperature must be non-negative")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer or null")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def to_json(self) -> str:
        """Return stable JSON so manifests can be diffed and checksummed."""
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ExperimentManifest":
        manifest = cls(**data)
        manifest.validate()
        return manifest
