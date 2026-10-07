"""Synthetic-only checks for reconciliation output attestation.

These fixtures are not collected human ratings or study findings.
"""
import json

import pytest

from scripts import reconcile_human_automated as reconcile
from scripts import verify_human_reconciliation_outputs as verify
from scripts import verify_human_reconciliation_readiness as readiness


def _payload():
    task_ids = ["main-01", "main-02"]
    block = {
        "n_comparable_tasks": 2,
        "task_ids_included": task_ids,
        "missing_pair_tasks": [],
        "direction_category_counts": {
            "concordant_positive": 1,
            "concordant_negative": 1,
            "discordant": 0,
            "automated_tie": 0,
            "human_tie": 0,
            "both_tie": 0,
        },
        "non_tie_directional_concordance": 1.0,
        "mean_automated_difference_on_comparable_tasks": 0.0,
        "mean_human_difference_on_comparable_tasks": 0.0,
        "mean_direction_category": "both_tie",
        "taskwise": [
            {
                "task_id": "main-01",
                "automated_difference": 0.5,
                "human_difference": 1.0,
                "direction_category": "concordant_positive",
            },
            {
                "task_id": "main-02",
                "automated_difference": -0.5,
                "human_difference": -1.0,
                "direction_category": "concordant_negative",
            },
        ],
    }
    results = {
        contrast: {dimension: dict(block) for dimension in readiness.DIMS}
        for contrast in readiness.CONTRASTS
    }
    return {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "status": "automated_human_descriptive_reconciliation",
        "analysis_scope": "descriptive_reconciliation_only",
        "primary_outcome": "strict_support_rate",
        "human_dimensions": list(readiness.DIMS),
        "contrasts": list(readiness.CONTRASTS),
        "task_ids": task_ids,
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests_added": False,
        "method": {
            "task_pairing": "same_frozen_task_id",
            "missingness": "preserve_missing_human_pairs_without_imputation",
            "direction_categories": list(reconcile.CATEGORIES),
            "non_tie_directional_concordance_denominator": (
                "concordant_positive + concordant_negative + discordant"
            ),
            "inference": "descriptive_only",
        },
        "results": results,
        "verified_input_fingerprints": {
            "automated_analysis": {"bytes": 100, "sha256": "a" * 64},
            "automated_provenance": {"bytes": 101, "sha256": "b" * 64},
            "human_analysis": {"bytes": 102, "sha256": "c" * 64},
            "human_manifest": {"bytes": 103, "sha256": "d" * 64},
            "reconciliation_contract": {"bytes": 104, "sha256": "e" * 64},
        },
        "verification": {
            "automated_provenance_verified": True,
            "automated_output_consistency_verified": True,
            "human_analysis_bundle_verified": True,
            "cross_analysis_identity_verified": True,
            "inputs_stable_during_verification": True,
            "reconciliation_inputs_bound_to_readiness_receipt": True,
        },
    }


def _patch_recomputation(monkeypatch, payload):
    monkeypatch.setattr(reconcile, "reconcile_verified", lambda **kwargs: payload)
    monkeypatch.setattr(reconcile, "_producer_commit", lambda root: "a" * 40)


def test_write_bundle_is_create_only_and_independently_verified(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"

    receipt = reconcile.write_bundle(payload, output, root=tmp_path)

    assert receipt["status"] == "automated_human_reconciliation_bundle_verified"
    assert receipt["independent_recomputation_verified"] is True
    manifest = json.loads(
        (output / reconcile.RECONCILIATION_MANIFEST).read_text(encoding="utf-8")
    )
    assert manifest["verified_input_fingerprints"] == payload["verified_input_fingerprints"]
    assert set(manifest["implementation"]) == {"reconciler", "readiness_gate"}

    with pytest.raises(ValueError, match="refusing to overwrite reconciliation output"):
        reconcile.write_bundle(payload, output, root=tmp_path)


def test_invalid_payload_does_not_reserve_publication_path(tmp_path):
    payload = _payload()
    payload.pop("verified_input_fingerprints")
    output = tmp_path / "reconciliation"

    with pytest.raises(ValueError, match="lacks verified input fingerprints"):
        reconcile.write_bundle(payload, output, root=tmp_path)

    assert not output.exists()


def test_provenance_preflight_failure_does_not_reserve_publication_path(
    tmp_path, monkeypatch
):
    payload = _payload()
    output = tmp_path / "reconciliation"

    def fail_git_provenance(root):
        raise ValueError("synthetic git provenance failure")

    monkeypatch.setattr(reconcile, "_producer_commit", fail_git_provenance)
    with pytest.raises(ValueError, match="synthetic git provenance failure"):
        reconcile.write_bundle(payload, output, root=tmp_path)

    assert not output.exists()


def test_rejects_hand_edited_markdown(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    markdown = output / reconcile.RECONCILIATION_MARKDOWN
    markdown.write_text(
        markdown.read_text(encoding="utf-8").replace("1.000", "0.000", 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match canonical JSON"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_posthoc_result_edit_even_if_artifact_hash_is_rewritten(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    changed = json.loads(
        (output / reconcile.RECONCILIATION_JSON).read_text(encoding="utf-8")
    )
    changed["posthoc_p_value"] = 0.01
    json_bytes = (json.dumps(changed, indent=2, sort_keys=True) + "\n").encode("utf-8")
    markdown_bytes = reconcile.render_markdown(changed).encode("utf-8")
    (output / reconcile.RECONCILIATION_JSON).write_bytes(json_bytes)
    (output / reconcile.RECONCILIATION_MARKDOWN).write_bytes(markdown_bytes)

    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["canonical_reconciliation"].update(
        reconcile._fingerprint_bytes(json_bytes)
    )
    manifest["artifacts"]["manuscript_rendering"].update(
        reconcile._fingerprint_bytes(markdown_bytes)
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="independently recomputed reconciliation mismatch"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_upstream_fingerprint_drift(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["verified_input_fingerprints"]["human_analysis"]["sha256"] = "f" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest verified input fingerprints mismatch"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_reconciler_implementation_drift(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    changed = tmp_path / "reconcile_human_automated.py"
    changed.write_text("# changed implementation\n", encoding="utf-8")
    monkeypatch.setattr(reconcile, "__file__", str(changed))

    with pytest.raises(ValueError, match="reconciler implementation fingerprint"):
        verify.verify_bundle(output, root=tmp_path)
