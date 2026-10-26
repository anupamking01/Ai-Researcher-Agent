"""Synthetic regressions for exhaustive exploratory task influence only."""
import copy
import json
import statistics

import pytest

from scripts import analyze_main_study_task_influence as influence


def _payload(differences=None):
    tasks = [f"task-{i:02d}" for i in range(10)]
    values = ([0.2, -0.1, 0.0, 0.3, -0.2, 0.1, -0.1, 0.0, 0.2, -0.1]
              if differences is None else differences)
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "n_tasks": 10,
        "task_ids": tasks,
        "primary_contrasts": {
            name: {
                "task_differences": list(values),
                "mean_difference": statistics.mean(values),
            }
            for _, _, name in influence.analyze_main_study.PRIMARY_CONTRASTS
        },
    }


def test_every_frozen_task_and_contrast_included_without_selection():
    payload = _payload()
    diagnostic = influence.diagnostic(payload)
    assert diagnostic["status"] == "post_hoc_exploratory_task_influence_only"
    assert diagnostic["confirmatory_analysis_replaced"] is False
    assert diagnostic["human_validation_performed"] is False
    assert diagnostic["inferential_p_values_or_intervals_added"] is False
    assert set(diagnostic["results"]) == set(payload["primary_contrasts"])
    for result in diagnostic["results"].values():
        entries = result["all_task_omissions"]
        assert [e["omitted_task_id"] for e in entries] == payload["task_ids"]
        assert all(e["remaining_pairs"] == 9 for e in entries)
        assert statistics.mean(
            e["mean_difference_without_task"] for e in entries
        ) == pytest.approx(result["full_sample_mean_difference"])
        assert result["loo_mean_min"] == min(
            e["mean_difference_without_task"] for e in entries
        )
        assert result["loo_mean_max"] == max(
            e["mean_difference_without_task"] for e in entries
        )


def test_one_extreme_task_is_reported_but_never_dropped_from_full_estimate():
    payload = _payload([1.0] + [0.0] * 9)
    diagnostic = influence.diagnostic(payload)
    for result in diagnostic["results"].values():
        assert result["full_sample_mean_difference"] == pytest.approx(0.1)
        assert result["all_task_omissions"][0]["mean_difference_without_task"] == 0
        assert result["all_task_omissions"][0]["change_from_full_mean"] == pytest.approx(-0.1)
        assert result["all_task_omissions"][1]["mean_difference_without_task"] == pytest.approx(1 / 9)


def test_deterministic_and_does_not_mutate_canonical_payload():
    payload = _payload()
    original = copy.deepcopy(payload)
    assert influence.diagnostic(payload) == influence.diagnostic(payload)
    assert payload == original


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(schema_version=True),
    lambda p: p.update(study_id="pilot-v1"),
    lambda p: p.update(n_tasks=9),
    lambda p: p["task_ids"].__setitem__(1, p["task_ids"][0]),
    lambda p: p["task_ids"].__setitem__(0, ""),
    lambda p: p["task_ids"].pop(),
    lambda p: p["primary_contrasts"].pop(next(iter(p["primary_contrasts"]))),
    lambda p: p["primary_contrasts"][next(iter(p["primary_contrasts"]))].update(
        mean_difference=0.7
    ),
    lambda p: p["primary_contrasts"][next(iter(p["primary_contrasts"]))][
        "task_differences"
    ].__setitem__(0, True),
    lambda p: p["primary_contrasts"][next(iter(p["primary_contrasts"]))][
        "task_differences"
    ].__setitem__(0, float("nan")),
    lambda p: p["primary_contrasts"][next(iter(p["primary_contrasts"]))][
        "task_differences"
    ].__setitem__(0, 1.1),
])
def test_wrong_identity_denominator_or_measurement_fails_closed(mutation):
    payload = _payload()
    mutation(payload)
    with pytest.raises(ValueError):
        influence.diagnostic(payload)


def test_nonstandard_and_duplicate_json_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        influence._parse_analysis(b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="non-JSON"):
        influence._parse_analysis(b'{"x":NaN}')


def test_normal_verification_is_mandatory_and_happens_before_analysis(tmp_path, monkeypatch):
    root = tmp_path
    (root / "outputs").mkdir()
    (root / "outputs" / "main_study_inference.json").write_text(json.dumps(_payload()))
    (root / "outputs" / "main_study_analysis_provenance.json").write_text(json.dumps({"verified_execution": {}}))
    calls = []
    monkeypatch.setattr(
        influence.verify_main_study_execution, "verify_execution_receipt",
        lambda *a, **k: calls.append("execution"),
    )
    monkeypatch.setattr(
        influence.verify_analysis_provenance, "verify_recomputed_outputs",
        lambda *a, **k: calls.append("recompute"),
    )
    monkeypatch.setattr(
        influence.verify_main_study_outputs, "verify_outputs",
        lambda **k: calls.append("markdown"),
    )
    out = influence.run_verified(root)
    assert calls == ["execution", "recompute", "markdown"]
    assert len(out["verified_canonical_inference_sha256"]) == 64
    assert len(out["verified_provenance_receipt_sha256"]) == 64
    assert out["source_provenance_independently_recomputed"] is True


def test_missing_execution_binding_fails_before_diagnostic(tmp_path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "main_study_inference.json").write_text(json.dumps(_payload()))
    (tmp_path / "outputs" / "main_study_analysis_provenance.json").write_text("{}")
    with pytest.raises(ValueError, match="must include verified treatment execution"):
        influence.run_verified(tmp_path)


def test_failed_upstream_verification_prevents_diagnostic(tmp_path, monkeypatch):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "main_study_inference.json").write_text(json.dumps(_payload()))
    (tmp_path / "outputs" / "main_study_analysis_provenance.json").write_text(json.dumps({"verified_execution": {}}))
    def reject(*a, **k):
        raise ValueError("source not independently verified")
    monkeypatch.setattr(influence.verify_main_study_execution, "verify_execution_receipt", reject)
    with pytest.raises(ValueError, match="source not independently verified"):
        influence.run_verified(tmp_path)


def test_observed_input_replacement_during_verification_fails_closed(tmp_path, monkeypatch):
    (tmp_path / "outputs").mkdir()
    source = tmp_path / "outputs" / "main_study_inference.json"
    source.write_text(json.dumps(_payload()))
    (tmp_path / "outputs" / "main_study_analysis_provenance.json").write_text(json.dumps({"verified_execution": {}}))
    monkeypatch.setattr(
        influence.verify_main_study_execution, "verify_execution_receipt", lambda *a, **k: None
    )
    def mutate(*a, **k):
        source.write_text(json.dumps(_payload([0.5] * 10)))
    monkeypatch.setattr(
        influence.verify_analysis_provenance, "verify_recomputed_outputs", mutate
    )
    monkeypatch.setattr(
        influence.verify_main_study_outputs, "verify_outputs", lambda **k: None
    )
    with pytest.raises(ValueError, match="changed during influence analysis"):
        influence.run_verified(tmp_path)


def test_symlinked_or_oversize_source_not_read(tmp_path):
    actual = tmp_path / "real.json"
    actual.write_text(json.dumps({"verified_execution": {}}))
    link = tmp_path / "alias.json"
    link.symlink_to(actual)
    with pytest.raises(ValueError, match="regular"):
        influence._read_regular_bounded(link, label="analysis")
    oversized = tmp_path / "big.json"
    oversized.write_bytes(b"x" * (influence.MAX_SOURCE_BYTES + 1))
    with pytest.raises(ValueError, match="source-byte limit"):
        influence._read_regular_bounded(oversized, label="analysis")
