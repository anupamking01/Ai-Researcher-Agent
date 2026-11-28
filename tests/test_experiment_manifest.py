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


@pytest.mark.parametrize("value", [None, 7, True])
def test_manifest_rejects_non_string_required_metadata(value):
    with pytest.raises(ValueError, match="provider must be a non-empty string"):
        manifest(provider=value).validate()


@pytest.mark.parametrize(
    "git_commit_sha",
    [
        "8476e91",
        "g" * 40,
        "8476E9135502C1CD938D6748510D2A78A628E533",
        "0" * 39,
        "0" * 41,
    ],
)
def test_manifest_rejects_noncanonical_git_commit_ids(git_commit_sha):
    with pytest.raises(ValueError, match="git_commit_sha must be a full lowercase"):
        manifest(git_commit_sha=git_commit_sha).validate()


def test_manifest_accepts_sha256_git_commit_ids():
    assert manifest(git_commit_sha="a" * 64).to_dict()["git_commit_sha"] == "a" * 64


def test_manifest_rejects_invalid_source_budget():
    with pytest.raises(ValueError, match="max_source_budget"):
        manifest(max_source_budget=0).validate()


@pytest.mark.parametrize("max_source_budget", [True, 1.5, "8"])
def test_manifest_rejects_non_integer_source_budget(max_source_budget):
    with pytest.raises(ValueError, match="max_source_budget must be a positive integer"):
        manifest(max_source_budget=max_source_budget).validate()


def test_manifest_rejects_negative_temperature():
    with pytest.raises(ValueError, match="temperature"):
        manifest(temperature=-0.1).validate()


@pytest.mark.parametrize("temperature", [float("nan"), float("inf"), float("-inf")])
def test_manifest_rejects_non_finite_temperature(temperature):
    invalid = manifest(temperature=temperature)

    with pytest.raises(ValueError, match="temperature must be finite"):
        invalid.validate()
    with pytest.raises(ValueError, match="temperature must be finite"):
        invalid.to_json()


@pytest.mark.parametrize("temperature", [True, "0.1", None])
def test_manifest_rejects_non_numeric_temperature(temperature):
    with pytest.raises(ValueError, match="temperature must be a finite number"):
        manifest(temperature=temperature).validate()


def test_manifest_rejects_unrepresentable_temperature():
    with pytest.raises(ValueError, match="temperature must be finite"):
        manifest(temperature=10**400).validate()


@pytest.mark.parametrize("seed", [True, 1.5, "42", float("inf")])
def test_manifest_rejects_non_integer_seed(seed):
    with pytest.raises(ValueError, match="seed must be an integer or null"):
        manifest(seed=seed).validate()
