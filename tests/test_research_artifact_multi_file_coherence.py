"""Synthetic multi-file consistency tests; no research treatments or ratings run."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import fingerprint_research_artifacts as producer
from scripts import verify_research_artifact_manifest as verifier


@pytest.mark.parametrize("caller", ["generator", "verifier"])
@pytest.mark.parametrize("mutation", ["same_length_rewrite", "same_bytes_replacement"])
def test_rejects_earlier_input_changed_while_scanning_later_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caller: str, mutation: str
) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_bytes(b"ORIGINAL")
    second.write_bytes(b"SECOND!!")
    # Construct a valid baseline before injecting concurrent changes.
    manifest = producer.build_manifest([first, second], root=tmp_path)
    target_module = producer if caller == "generator" else verifier
    original_reader = target_module.fingerprint_regular_file_with_identity
    triggered = False

    def mutate_after_second_read(path: Path):
        nonlocal triggered
        result = original_reader(path)
        if Path(path) == second and not triggered:
            triggered = True
            if mutation == "same_length_rewrite":
                first.write_bytes(b"MUTATED!")
            else:
                substitute = tmp_path / "replacement.tmp"
                substitute.write_bytes(b"ORIGINAL")
                os.replace(substitute, first)
        return result

    monkeypatch.setattr(
        target_module,
        "fingerprint_regular_file_with_identity",
        mutate_after_second_read,
    )
    with pytest.raises(ValueError, match="changed across manifest capture: first.csv"):
        if caller == "generator":
            producer.build_manifest([first, second], root=tmp_path)
        else:
            verifier.verify_manifest(manifest, root=tmp_path)
    assert triggered


def test_unmodified_distinct_artifacts_still_round_trip(tmp_path: Path) -> None:
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    first.write_bytes(b"same bytes")
    second.write_bytes(b"same bytes")
    manifest = producer.build_manifest([second, first], root=tmp_path)
    assert [entry["path"] for entry in verifier.verify_manifest(manifest, root=tmp_path)] == [
        "a.csv",
        "b.csv",
    ]
