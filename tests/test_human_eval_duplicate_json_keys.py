"""Synthetic JSON-ambiguity regression tests; no collected human ratings."""

import json

import pytest

from scripts import analyze_human_eval
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verify


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
            variant: {dim: {"mean_report_score": 3.0} for dim in core.DIMS}
            for variant in core.VARIANTS
        },
    }


@pytest.mark.parametrize(
    "raw",
    [
        b'{"status": "original", "status": "replacement"}',
        b'{"nested": {"score": 2, "score": 4}}',
        b'{"rows": [{"rating": 1, "rating": 5}]}',
        b'{"status": 1, "\\u0073tatus": 2}',
    ],
)
def test_rejects_repeated_decoded_keys_at_any_depth(raw):
    with pytest.raises(ValueError, match="duplicate JSON key"):
        verify._load_json(raw, label="synthetic analysis JSON")


def test_accepts_reused_keys_in_distinct_objects_and_missing_null():
    result = verify._load_json(
        b'{"rows": [{"score": 2}, {"score": 4}], "missing": null}',
        label="synthetic analysis JSON",
    )
    assert result == {"rows": [{"score": 2}, {"score": 4}], "missing": None}


def test_rejects_duplicate_canonical_field_even_when_sha256_is_rewritten(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_synthetic_payload(), output)
    path = output / analyze_human_eval.ANALYSIS_JSON
    original = path.read_bytes()
    field = b'"status": "human_validation_analysis",'
    assert original.count(field) == 1
    corrupted = original.replace(field, field + b'\n  ' + field, 1)
    path.write_bytes(corrupted)

    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["canonical_analysis"].update(
        analyze_human_eval._fingerprint_bytes(corrupted)
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="duplicate JSON key 'status'"):
        verify.verify_bundle(output)


def test_rejects_repeated_manifest_key(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_synthetic_payload(), output)
    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    original = manifest_path.read_bytes()
    field = b'"schema_version": 1,'
    assert original.count(field) == 1
    manifest_path.write_bytes(original.replace(field, field + b'\n  ' + field, 1))

    with pytest.raises(ValueError, match="duplicate JSON key 'schema_version'"):
        verify.verify_bundle(output)
