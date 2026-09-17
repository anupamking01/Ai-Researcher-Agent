"""Validation helpers for reproducible research experiment metadata.

Experiment results are only interpretable when the configuration that produced
them is recorded. This module provides a dependency-free manifest with explicit
required fields and deterministic serialization suitable for archiving beside
raw traces.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
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
        missing = [name for name, value in required_text.items() if not value.strip()]
        if missing:
            raise ValueError(f"manifest fields must be non-empty: {', '.join(missing)}")
        if self.max_source_budget <= 0:
            raise ValueError("max_source_budget must be positive")
        if self.temperature < 0:
            raise ValueError("temperature must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def to_json(self) -> str:
        """Return stable JSON so manifests can be diffed and checksummed."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ExperimentManifest":
        manifest = cls(**data)
        manifest.validate()
        return manifest
