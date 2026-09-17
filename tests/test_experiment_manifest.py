import json

import pytest

from logic.experiment_manifest import ExperimentManifest


def manifest(**overrides):
    values = {
        "experiment_id": "ablation-001",
        "git_commit_sha": "8476e9135502c1cd938d6748510d2a78a628e533",
        "task_set_version": "v1",
        "provider": "example-provider",
        "model": "example-model",
        "prompt_version": "v2",
        "search_provider": "example-search",
        "max_source_budget": 8,
        "temperature": 0.0,
        "seed": 42,
    }
    values.update(overrides)
    return ExperimentManifest(**values)


def test_manifest_round_trip_and_stable_json():
    original = manifest()
    encoded = original.to_json()
    restored = ExperimentManifest.from_mapping(json.loads(encoded))

    assert restored == original
    assert encoded == original.to_json()
    assert encoded.startswith('{"experiment_id":')


def test_manifest_rejects_blank_required_metadata():
    with pytest.raises(ValueError, match="provider"):
        manifest(provider="   ").validate()


def test_manifest_rejects_invalid_source_budget():
    with pytest.raises(ValueError, match="max_source_budget"):
        manifest(max_source_budget=0).validate()


def test_manifest_rejects_negative_temperature():
    with pytest.raises(ValueError, match="temperature"):
        manifest(temperature=-0.1).validate()
