"""Synthetic JSON-ambiguity regression tests; no collected human ratings."""

import hashlib
import json

import pytest

from scripts import analyze_human_eval
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verify


def _synthetic_payload():
    plan_bytes = core.PLAN.read_bytes()
    summary_block = {
        "n_reports_total": 1,
        "n_reports_scored": 1,
        "n_raw_scores": 2,
        "mean_report_score": 3.0,
        "median_report_score": 3.0,
        "raw_score_distribution": {"1": 0, "2": 0, "3": 2, "4": 0, "5": 0},
    }
    pair_block = {
        "n_pairs": 1,
        "left_mean": 3.0,
        "right_mean": 3.0,
        "mean_difference": 0.0,
        "median_difference": 0.0,
        "bootstrap_95pct_ci_mean_difference": [0.0, 0.0],
        "paired_dz": None,
        "positive_tasks": 0,
        "negative_tasks": 0,
        "tied_tasks": 1,
        "task_differences": {"task-a": 0.0},
        "task_ids_included": ["task-a"],
        "missing_pair_tasks": [],
    }
    agreement_dimension = {
        "n_double_rated": 1,
        "raw_exact_agreement": 1.0,
        "mean_absolute_difference": 0.0,
        "quadratic_weighted_cohen_kappa": None,
    }
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
        "report_score_aggregation": "mean_observed_rater_scores_per_report_dimension",
        "bootstrap_seed": core.SEED,
        "bootstrap_draws": core.BOOTSTRAP_DRAWS,
        "n_tasks": 1,
        "task_ids": ["task-a"],
        "verification": {"analysis_inputs_snapshot_bound": True},
        "provenance": {
            "analysis_plan": {
                "path": core.PLAN.name,
                "bytes": len(plan_bytes),
                "sha256": hashlib.sha256(plan_bytes).hexdigest(),
            }
        },
        "pre_unblinding_agreement": {
            "status": "pre-unblinding_pairwise_agreement",
            "n_annotators": 2,
            "pairwise": [{
                "annotator_a": "annotator-a",
                "annotator_b": "annotator-b",
                "dimensions": {
                    field: dict(agreement_dimension) for field in core.DIMS
                },
            }],
        },
        "variant_summary": {
            variant: {dim: dict(summary_block) for dim in core.DIMS}
            for variant in core.VARIANTS
        },
        "paired_contrasts": {
            name: {dim: dict(pair_block) for dim in core.DIMS}
            for _, _, name in core.CONTRASTS
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
