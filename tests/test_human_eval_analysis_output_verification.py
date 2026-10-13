"""Synthetic checks for human-analysis output attestation.

These fixtures are not collected human ratings or study findings.
"""
import hashlib
import json

import pytest

from scripts import analyze_human_eval
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verify


def _payload():
    plan_bytes = core.PLAN.read_bytes()
    summary = {
        variant: {
            field: {"mean_report_score": 3.0}
            for field in core.DIMS
        }
        for variant in core.VARIANTS
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
        "verification": {"analysis_inputs_snapshot_bound": True},
        "provenance": {
            "analysis_plan": {
                "path": core.PLAN.name,
                "bytes": len(plan_bytes),
                "sha256": hashlib.sha256(plan_bytes).hexdigest(),
            }
        },
        "variant_summary": summary,
    }


def _rewrite_and_rehash(output, payload):
    json_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    markdown_bytes = analyze_human_eval.render_markdown(payload).encode("utf-8")
    (output / analyze_human_eval.ANALYSIS_JSON).write_bytes(json_bytes)
    (output / analyze_human_eval.ANALYSIS_MARKDOWN).write_bytes(markdown_bytes)

    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["canonical_analysis"].update(
        analyze_human_eval._fingerprint_bytes(json_bytes)
    )
    manifest["artifacts"]["manuscript_rendering"].update(
        analyze_human_eval._fingerprint_bytes(markdown_bytes)
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_write_bundle_emits_manifest_and_verifies(tmp_path):
    output = tmp_path / "analysis"
    receipt = analyze_human_eval.write_bundle(_payload(), output)

    assert receipt["status"] == "human_validation_analysis_bundle_verified"
    assert receipt["implementation_bound"] is True
    manifest = json.loads(
        (output / analyze_human_eval.ANALYSIS_MANIFEST).read_text(encoding="utf-8")
    )
    assert set(manifest["artifacts"]) == {"canonical_analysis", "manuscript_rendering"}
    assert set(manifest["implementation"]) == {"analysis_core", "analysis_renderer"}


def test_rejects_hand_edited_markdown_even_before_manifest_check(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    markdown = output / analyze_human_eval.ANALYSIS_MARKDOWN
    markdown.write_text(
        markdown.read_text(encoding="utf-8").replace("3.000", "5.000", 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match canonical JSON"):
        verify.verify_bundle(output)


def test_rejects_json_and_markdown_rewrite_that_no_longer_matches_manifest(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)

    changed = _payload()
    changed["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = 4.0
    (output / analyze_human_eval.ANALYSIS_JSON).write_text(
        json.dumps(changed, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / analyze_human_eval.ANALYSIS_MARKDOWN).write_text(
        analyze_human_eval.render_markdown(changed),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="canonical analysis fingerprint"):
        verify.verify_bundle(output)


def test_rejects_forged_output_manifest_hash(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["canonical_analysis"]["sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="canonical analysis fingerprint"):
        verify.verify_bundle(output)


def test_rejects_analysis_implementation_drift(tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)

    changed_core = tmp_path / "human_eval_analysis_core.py"
    changed_core.write_text("# changed implementation\n", encoding="utf-8")
    monkeypatch.setattr(core, "__file__", str(changed_core))

    with pytest.raises(ValueError, match="analysis core implementation fingerprint"):
        verify.verify_bundle(output)


@pytest.mark.parametrize(
    "field,value",
    [
        ("human_ratings_generated", True),
        ("treatment_outputs_rerun", True),
        ("analysis_scope", "confirmatory"),
        ("hypothesis_tests", "p_values_added"),
    ],
)
def test_rejects_result_identity_drift_even_with_rewritten_manifest(tmp_path, field, value):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)

    payload = json.loads(
        (output / analyze_human_eval.ANALYSIS_JSON).read_text(encoding="utf-8")
    )
    payload[field] = value
    json_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    markdown_bytes = analyze_human_eval.render_markdown(payload).encode("utf-8")
    (output / analyze_human_eval.ANALYSIS_JSON).write_bytes(json_bytes)
    (output / analyze_human_eval.ANALYSIS_MARKDOWN).write_bytes(markdown_bytes)

    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["canonical_analysis"].update(
        analyze_human_eval._fingerprint_bytes(json_bytes)
    )
    manifest["artifacts"]["manuscript_rendering"].update(
        analyze_human_eval._fingerprint_bytes(markdown_bytes)
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=f"analysis {field} mismatch"):
        verify.verify_bundle(output)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("bootstrap_seed", core.SEED + 1, "analysis bootstrap_seed mismatch"),
        ("bootstrap_draws", 1, "analysis bootstrap_draws mismatch"),
        (
            "report_score_aggregation",
            "best_observed_rater_score_per_report_dimension",
            "analysis report_score_aggregation mismatch",
        ),
    ],
)
def test_rejects_frozen_analysis_setting_drift_after_rehash(
    tmp_path, field, value, error
):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = json.loads(
        (output / analyze_human_eval.ANALYSIS_JSON).read_text(encoding="utf-8")
    )
    payload[field] = value
    _rewrite_and_rehash(output, payload)

    with pytest.raises(ValueError, match=error):
        verify.verify_bundle(output)


@pytest.mark.parametrize("invalid", [False, 1])
def test_rejects_nonliteral_snapshot_binding_claim_after_rehash(tmp_path, invalid):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = json.loads(
        (output / analyze_human_eval.ANALYSIS_JSON).read_text(encoding="utf-8")
    )
    payload["verification"]["analysis_inputs_snapshot_bound"] = invalid
    _rewrite_and_rehash(output, payload)

    with pytest.raises(ValueError, match="analysis input snapshot binding mismatch"):
        verify.verify_bundle(output)


def test_rejects_analysis_plan_provenance_drift_after_rehash(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = json.loads(
        (output / analyze_human_eval.ANALYSIS_JSON).read_text(encoding="utf-8")
    )
    payload["provenance"]["analysis_plan"]["sha256"] = "0" * 64
    _rewrite_and_rehash(output, payload)

    with pytest.raises(ValueError, match="analysis plan provenance mismatch"):
        verify.verify_bundle(output)


def test_rejects_missing_manifest(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    (output / analyze_human_eval.ANALYSIS_MANIFEST).unlink()

    with pytest.raises(ValueError, match="output manifest must be a regular file"):
        verify.verify_bundle(output)
