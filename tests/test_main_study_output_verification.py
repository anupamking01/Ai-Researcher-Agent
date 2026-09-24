"""Tests for canonical JSON-to-manuscript result consistency."""
import json
from pathlib import Path

import pytest

from scripts import analyze_main_study
from scripts.verify_main_study_outputs import verify_outputs


def _payload() -> dict:
    means = {
        "strict_support_rate": 0.5,
        "broad_support_rate": 0.75,
        "successful_sources": 2.0,
        "total_tokens": 100.0,
        "treatment_cost_usd": 0.05,
        "latency_seconds": 1.2,
    }
    variants = {
        variant: {"means": dict(means), "zero_evidence_runs": 0}
        for variant in analyze_main_study.VARIANTS
    }
    contrasts = {}
    for _, _, name in analyze_main_study.PRIMARY_CONTRASTS:
        contrasts[name] = {
            "mean_difference": 0.1,
            "median_difference": 0.1,
            "bootstrap_95pct_ci_mean_difference": [0.0, 0.2],
            "exact_two_sided_signflip_p": 0.5,
            "holm_adjusted_p": 1.0,
            "paired_dz": 0.25,
            "positive_tasks": 6,
            "negative_tasks": 3,
            "tied_tasks": 1,
        }
    return {
        "variant_summary": variants,
        "primary_contrasts": contrasts,
        "cost_quality_pareto": {"frontier": ["D3", "P6"]},
    }


def _write_pair(tmp_path: Path, payload: dict) -> tuple[Path, Path]:
    json_path = tmp_path / "result.json"
    md_path = tmp_path / "result.md"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    # Mirror analyze_main_study.main(): the renderer is written byte-for-byte,
    # without adding a second formatting convention in the test fixture.
    md_path.write_text(analyze_main_study._markdown(payload), encoding="utf-8")
    return json_path, md_path


def test_accepts_exact_deterministic_rendering(tmp_path):
    payload = _payload()
    json_path, md_path = _write_pair(tmp_path, payload)
    verify_outputs(root=tmp_path, json_path=json_path, markdown_path=md_path)

def test_renderer_is_invariant_to_sorted_json_key_order(tmp_path):
    payload = _payload()
    before_serialization = analyze_main_study._markdown(payload)

    json_path = tmp_path / "result.json"
    md_path = tmp_path / "result.md"
    json_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))

    assert list(reloaded["primary_contrasts"]) != [
        name for _, _, name in analyze_main_study.PRIMARY_CONTRASTS
    ]
    assert analyze_main_study._markdown(reloaded) == before_serialization

    md_path.write_text(before_serialization, encoding="utf-8")
    verify_outputs(root=tmp_path, json_path=json_path, markdown_path=md_path)



def test_rejects_trailing_newline_not_emitted_by_canonical_renderer(tmp_path):
    payload = _payload()
    json_path, md_path = _write_pair(tmp_path, payload)
    md_path.write_text(md_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match canonical JSON"):
        verify_outputs(root=tmp_path, json_path=json_path, markdown_path=md_path)


def test_rejects_hand_edited_manuscript_result(tmp_path):
    payload = _payload()
    json_path, md_path = _write_pair(tmp_path, payload)
    md_path.write_text(md_path.read_text(encoding="utf-8").replace("0.5000", "0.9000", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match canonical JSON"):
        verify_outputs(root=tmp_path, json_path=json_path, markdown_path=md_path)


def test_rejects_json_drift_without_markdown_regeneration(tmp_path):
    payload = _payload()
    json_path, md_path = _write_pair(tmp_path, payload)
    payload["variant_summary"]["D3"]["means"]["strict_support_rate"] = 0.9
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match canonical JSON"):
        verify_outputs(root=tmp_path, json_path=json_path, markdown_path=md_path)


def test_rejects_malformed_json(tmp_path):
    json_path = tmp_path / "result.json"
    md_path = tmp_path / "result.md"
    json_path.write_text("{not-json", encoding="utf-8")
    md_path.write_text("anything", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        verify_outputs(root=tmp_path, json_path=json_path, markdown_path=md_path)


def test_rejects_missing_result_artifact(tmp_path):
    with pytest.raises(ValueError, match="JSON is missing"):
        verify_outputs(root=tmp_path, json_path=Path("missing.json"), markdown_path=Path("missing.md"))
