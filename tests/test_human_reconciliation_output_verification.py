"""Synthetic-only checks for reconciliation output attestation.

These fixtures are not collected human ratings or study findings.
"""
import json
import subprocess
from pathlib import Path

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
    monkeypatch.setattr(
        verify,
        "_verify_producer_commit_implementation",
        lambda producer, implementation, *, root: None,
    )


def _producer_repo(tmp_path):
    root = tmp_path / "producer-repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "reconcile_human_automated.py").write_bytes(
        Path(reconcile.__file__).read_bytes()
    )
    (scripts / "verify_human_reconciliation_readiness.py").write_bytes(
        Path(readiness.__file__).read_bytes()
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Synthetic Test"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "synthetic@example.invalid"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "add", "scripts"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "bound implementation"], cwd=root, check=True)
    return root


def _implementation_manifest():
    return {
        "reconciler": {
            "path": "scripts/reconcile_human_automated.py",
            **reconcile._fingerprint_bytes(Path(reconcile.__file__).read_bytes()),
        },
        "readiness_gate": {
            "path": "scripts/verify_human_reconciliation_readiness.py",
            **reconcile._fingerprint_bytes(Path(readiness.__file__).read_bytes()),
        },
    }


def _rewrite_producer_commit(output, producer):
    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["producer_git_commit"] = producer
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_rejects_unresolvable_producer_commit(tmp_path, monkeypatch):
    payload = _payload()
    root = _producer_repo(tmp_path)
    monkeypatch.setattr(reconcile, "reconcile_verified", lambda **kwargs: payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=root)
    _rewrite_producer_commit(output, "f" * 40)

    with pytest.raises(ValueError, match="producer Git commit cannot be resolved"):
        verify.verify_bundle(output, root=root)


def test_rejects_producer_commit_with_different_implementation_bytes(
    tmp_path, monkeypatch
):
    payload = _payload()
    root = _producer_repo(tmp_path)
    monkeypatch.setattr(reconcile, "reconcile_verified", lambda **kwargs: payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=root)

    reconciler = root / "scripts" / "reconcile_human_automated.py"
    reconciler.write_text("# substituted reconciler\n", encoding="utf-8")
    subprocess.run(["git", "add", str(reconciler)], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "substitute implementation"], cwd=root, check=True
    )
    substituted_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _rewrite_producer_commit(output, substituted_commit)

    with pytest.raises(ValueError, match="producer reconciler fingerprint mismatch"):
        verify.verify_bundle(output, root=root)


def test_git_replacement_ref_cannot_substitute_producer_commit(tmp_path, monkeypatch):
    payload = _payload()
    root = _producer_repo(tmp_path)
    good_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.setattr(reconcile, "reconcile_verified", lambda **kwargs: payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=root)

    reconciler = root / "scripts" / "reconcile_human_automated.py"
    reconciler.write_text("# substituted reconciler\n", encoding="utf-8")
    subprocess.run(["git", "add", str(reconciler)], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "substitute implementation"], cwd=root, check=True
    )
    substituted_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "replace", substituted_commit, good_commit], cwd=root, check=True
    )
    _rewrite_producer_commit(output, substituted_commit)

    with pytest.raises(ValueError, match="producer reconciler fingerprint mismatch"):
        verify.verify_bundle(output, root=root)


def test_partial_clone_does_not_fetch_missing_producer_blobs(tmp_path):
    source = _producer_repo(tmp_path)
    producer = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "config", "uploadpack.allowFilter", "true"], cwd=source, check=True
    )
    partial = tmp_path / "partial-clone"
    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--no-checkout",
            "--filter=blob:none",
            source.resolve().as_uri(),
            str(partial),
        ],
        check=True,
    )
    missing = subprocess.run(
        ["git", "rev-list", "--objects", "--missing=print", "HEAD"],
        cwd=partial,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "?" in missing
    pack_root = partial / ".git" / "objects" / "pack"
    before = {path.name for path in pack_root.iterdir()}

    with pytest.raises(ValueError, match="producer reconciler cannot be read"):
        verify._verify_producer_commit_implementation(
            producer,
            _implementation_manifest(),
            root=partial,
        )

    assert {path.name for path in pack_root.iterdir()} == before


def test_annotated_tag_object_is_not_accepted_as_producer_commit(tmp_path):
    root = _producer_repo(tmp_path)
    subprocess.run(
        ["git", "tag", "-a", "producer-tag", "-m", "synthetic producer tag"],
        cwd=root,
        check=True,
    )
    tag_object = subprocess.run(
        ["git", "rev-parse", "refs/tags/producer-tag"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(ValueError, match="must identify a commit object"):
        verify._verify_producer_commit_implementation(
            tag_object,
            _implementation_manifest(),
            root=root,
        )


def test_mismatched_producer_does_not_reserve_publication_path(tmp_path, monkeypatch):
    payload = _payload()
    root = _producer_repo(tmp_path)
    reconciler = root / "scripts" / "reconcile_human_automated.py"
    reconciler.write_text("# substituted reconciler\n", encoding="utf-8")
    subprocess.run(["git", "add", str(reconciler)], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "substitute implementation"], cwd=root, check=True
    )
    monkeypatch.setattr(reconcile, "reconcile_verified", lambda **kwargs: payload)
    output = tmp_path / "reconciliation"

    with pytest.raises(ValueError, match="producer reconciler fingerprint mismatch"):
        reconcile.write_bundle(payload, output, root=root)

    assert not output.exists()


def test_write_bundle_is_create_only_and_independently_verified(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"

    receipt = reconcile.write_bundle(payload, output, root=tmp_path)

    assert receipt["status"] == "automated_human_reconciliation_bundle_verified"
    assert receipt["independent_recomputation_verified"] is True
    assert receipt["producer_commit_implementation_bound"] is True
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


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_rejects_nonfinite_reconciliation_before_publication(tmp_path, invalid):
    payload = _payload()
    payload["results"][readiness.CONTRASTS[0]][readiness.DIMS[0]]["taskwise"][0][
        "human_difference"
    ] = invalid
    output = tmp_path / "reconciliation"

    with pytest.raises(ValueError, match="non-finite reconciliation"):
        reconcile.write_bundle(payload, output, root=tmp_path)

    assert not output.exists()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"nested": {"value": NaN}}',
        b'{"nested": [Infinity]}',
        b'{"nested": [-Infinity]}',
        b'{"nested": {"value": 1e400}}',
    ],
)
def test_verifier_rejects_nonfinite_json_values_including_overflow(raw):
    with pytest.raises(ValueError, match="non-finite JSON numbers"):
        verify._load_json(raw, label="synthetic reconciliation artifact")


def test_verifier_preserves_valid_json_null():
    assert verify._load_json(b'{"missing": null}', label="synthetic artifact") == {
        "missing": None
    }


@pytest.mark.parametrize(
    "raw",
    [
        b'{"nested":{"status":"ambiguous","status":"valid"}}',
        b'{"nested":{"st\\u0061tus":"ambiguous","status":"valid"}}',
    ],
)
def test_verifier_rejects_recursive_duplicate_json_members(raw):
    with pytest.raises(
        ValueError,
        match="synthetic reconciliation artifact.*duplicate JSON key.*status",
    ):
        verify._load_json(raw, label="synthetic reconciliation artifact")


@pytest.mark.parametrize("duplicate_name", ["status", r"st\u0061tus"])
def test_rejects_rehashed_canonical_json_with_duplicate_member(
    tmp_path, monkeypatch, duplicate_name
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    canonical_path = output / reconcile.RECONCILIATION_JSON
    original = canonical_path.read_text(encoding="utf-8")
    canonical_bytes = (
        '{"' + duplicate_name + '":"ambiguous",' + original.lstrip()[1:]
    ).encode("utf-8")
    canonical_path.write_bytes(canonical_bytes)

    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["canonical_reconciliation"].update(
        reconcile._fingerprint_bytes(canonical_bytes)
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="canonical reconciliation JSON.*duplicate JSON key.*status",
    ):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_nonfinite_tampering_even_after_hash_update(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    canonical_path = output / reconcile.RECONCILIATION_JSON
    tampered = json.loads(canonical_path.read_text(encoding="utf-8"))
    tampered["results"][readiness.CONTRASTS[0]][readiness.DIMS[0]]["taskwise"][
        0
    ]["human_difference"] = float("nan")
    canonical_bytes = (
        json.dumps(tampered, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    canonical_path.write_bytes(canonical_bytes)

    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["canonical_reconciliation"].update(
        reconcile._fingerprint_bytes(canonical_bytes)
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-finite JSON numbers"):
        verify.verify_bundle(output, root=tmp_path)
