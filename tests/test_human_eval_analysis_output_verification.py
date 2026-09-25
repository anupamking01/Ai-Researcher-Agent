"""Synthetic checks for human-analysis output attestation.

These fixtures are not collected human ratings or study findings.
"""
import json

import pytest

from scripts import analyze_human_eval
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verify


def _payload():
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
        "variant_summary": summary,
    }


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


def test_rejects_missing_manifest(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    (output / analyze_human_eval.ANALYSIS_MANIFEST).unlink()

    with pytest.raises(ValueError, match="output manifest must be a regular file"):
        verify.verify_bundle(output)
