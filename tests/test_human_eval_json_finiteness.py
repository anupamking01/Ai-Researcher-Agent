"""Synthetic-only regressions for finite canonical human-analysis JSON.

No human ratings, treatments, evaluator calls, or research results are created.
"""
import json

import pytest

from scripts import analyze_human_eval as publisher
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verifier


def _synthetic_payload():
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_validation_analysis",
        "analysis_scope": "complementary_not_main_confirmatory",
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests": "none_predeclared_for_human_validation",
        "variants": list(core.VARIANTS),
        "dimensions": list(core.DIMS),
        "variant_summary": {
            variant: {field: {"mean_report_score": 3.0} for field in core.DIMS}
            for variant in core.VARIANTS
        },
    }


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_cannot_publish_nonfinite_human_analysis(tmp_path, invalid):
    payload = _synthetic_payload()
    payload["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = invalid
    output_root = tmp_path / "human-analysis"
    with pytest.raises(ValueError, match="non-finite human-analysis values"):
        publisher.write_bundle(payload, output_root)
    assert not output_root.exists()


def _rewrite_and_rehash(output_root, canonical, markdown):
    (output_root / publisher.ANALYSIS_JSON).write_bytes(canonical)
    (output_root / publisher.ANALYSIS_MARKDOWN).write_bytes(markdown)
    path = output_root / publisher.ANALYSIS_MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["artifacts"]["canonical_analysis"].update(
        publisher._fingerprint_bytes(canonical)
    )
    manifest["artifacts"]["manuscript_rendering"].update(
        publisher._fingerprint_bytes(markdown)
    )
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_rehashed_nonfinite_bundle_fails_independent_verification(tmp_path, invalid):
    output_root = tmp_path / "human-analysis"
    publisher.write_bundle(_synthetic_payload(), output_root)
    payload = _synthetic_payload()
    payload["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = invalid
    canonical = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    markdown = publisher.render_markdown(payload).encode("utf-8")
    _rewrite_and_rehash(output_root, canonical, markdown)
    with pytest.raises(ValueError, match="non-finite numeric value"):
        verifier.verify_bundle(output_root)


def test_json_exponent_overflow_is_rejected_even_after_rehash(tmp_path):
    output_root = tmp_path / "human-analysis"
    publisher.write_bundle(_synthetic_payload(), output_root)
    payload = _synthetic_payload()
    payload["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = float("inf")
    canonical = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    assert b"Infinity" in canonical
    canonical = canonical.replace(b"Infinity", b"1e400", 1)
    markdown = publisher.render_markdown(payload).encode("utf-8")
    _rewrite_and_rehash(output_root, canonical, markdown)
    with pytest.raises(ValueError, match="non-finite numeric value"):
        verifier.verify_bundle(output_root)


def test_missing_human_score_uses_json_null_and_roundtrips(tmp_path):
    payload = _synthetic_payload()
    payload["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = None
    output_root = tmp_path / "human-analysis"
    receipt = publisher.write_bundle(payload, output_root)
    assert receipt["status"] == "human_validation_analysis_bundle_verified"
    stored = (output_root / publisher.ANALYSIS_JSON).read_text(encoding="utf-8")
    assert '"mean_report_score": null' in stored
