"""Synthetic-only checks for reconciliation output attestation.

These fixtures are not collected human ratings or study findings.
"""
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
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
    monkeypatch.setattr(
        verify,
        "_verify_producer_commit_environment",
        lambda producer, environment, *, root: None,
        raising=False,
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
    (scripts / "verify_human_reconciliation_outputs.py").write_bytes(
        Path(verify.__file__).read_bytes()
    )
    (root / "requirements.txt").write_bytes((reconcile.ROOT / "requirements.txt").read_bytes())
    (root / "requirements-ci.lock").write_bytes(
        (reconcile.ROOT / "requirements-ci.lock").read_bytes()
    )
    (root / ".python-version").write_bytes((reconcile.ROOT / ".python-version").read_bytes())
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Synthetic Test"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "synthetic@example.invalid"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "add",
            "scripts",
            "requirements.txt",
            "requirements-ci.lock",
            ".python-version",
        ],
        cwd=root,
        check=True,
    )
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
        "reconciliation_verifier": {
            "path": "scripts/verify_human_reconciliation_outputs.py",
            **reconcile._fingerprint_bytes(Path(verify.__file__).read_bytes()),
        },
    }


def _expected_analysis_environment():
    requirements = (reconcile.ROOT / "requirements.txt").read_bytes()
    ci_requirements = (reconcile.ROOT / "requirements-ci.lock").read_bytes()
    python_version = (reconcile.ROOT / ".python-version").read_bytes()
    return {
        "requirements": {
            "path": "requirements.txt",
            **reconcile._fingerprint_bytes(requirements),
        },
        "ci_requirements": {
            "path": "requirements-ci.lock",
            **reconcile._fingerprint_bytes(ci_requirements),
        },
        "python_version": {
            "path": ".python-version",
            **reconcile._fingerprint_bytes(python_version),
        },
        "runtime": {
            "schema_version": 1,
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
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


def test_rejects_producer_commit_with_different_verifier_bytes(
    tmp_path, monkeypatch
):
    payload = _payload()
    root = _producer_repo(tmp_path)
    monkeypatch.setattr(reconcile, "reconcile_verified", lambda **kwargs: payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=root)

    verifier = root / "scripts" / "verify_human_reconciliation_outputs.py"
    verifier.write_text("# substituted verifier\n", encoding="utf-8")
    subprocess.run(["git", "add", str(verifier)], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "substitute verifier implementation"],
        cwd=root,
        check=True,
    )
    substituted_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _rewrite_producer_commit(output, substituted_commit)

    with pytest.raises(
        ValueError,
        match="producer reconciliation_verifier fingerprint mismatch",
    ):
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


@pytest.mark.parametrize(
    ("filename", "error_match"),
    [
        (
            "requirements.txt",
            "producer requirements fingerprint mismatch",
        ),
        (
            "requirements-ci.lock",
            "producer ci_requirements fingerprint mismatch",
        ),
    ],
)
def test_git_replacement_ref_cannot_substitute_producer_environment(
    tmp_path, filename, error_match
):
    root = _producer_repo(tmp_path)
    good_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    requirements = root / filename
    requirements.write_text("substituted==0.0.0\n", encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "substitute environment"], cwd=root, check=True
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

    with pytest.raises(ValueError, match=error_match):
        verify._verify_producer_commit_environment(
            substituted_commit,
            _expected_analysis_environment(),
            root=root,
        )


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


def test_partial_clone_does_not_fetch_missing_environment_blobs(tmp_path):
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
    partial = tmp_path / "partial-environment-clone"
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
    pack_root = partial / ".git" / "objects" / "pack"
    before = {path.name for path in pack_root.iterdir()}

    with pytest.raises(ValueError, match="producer requirements cannot be read"):
        verify._verify_producer_commit_environment(
            producer,
            _expected_analysis_environment(),
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


def test_mismatched_producer_environment_does_not_reserve_publication_path(
    tmp_path, monkeypatch
):
    payload = _payload()
    root = _producer_repo(tmp_path)
    requirements = root / "requirements.txt"
    requirements.write_text("substituted==0.0.0\n", encoding="utf-8")
    subprocess.run(["git", "add", "requirements.txt"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "substitute environment"], cwd=root, check=True
    )
    monkeypatch.setattr(reconcile, "reconcile_verified", lambda **kwargs: payload)
    output = tmp_path / "reconciliation"

    with pytest.raises(ValueError, match="producer requirements fingerprint mismatch"):
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
    assert receipt["analysis_environment_bound"] is True
    assert receipt["producer_commit_environment_bound"] is True
    assert receipt["outputs_stable_during_independent_recomputation"] is True
    manifest = json.loads(
        (output / reconcile.RECONCILIATION_MANIFEST).read_text(encoding="utf-8")
    )
    assert manifest["verified_input_fingerprints"] == payload["verified_input_fingerprints"]
    assert set(manifest["implementation"]) == {
        "reconciler",
        "readiness_gate",
        "reconciliation_verifier",
    }
    assert manifest["implementation"]["reconciliation_verifier"] == {
        "path": "scripts/verify_human_reconciliation_outputs.py",
        **reconcile._fingerprint_bytes(Path(verify.__file__).read_bytes()),
    }
    assert manifest["analysis_environment"] == _expected_analysis_environment()

    with pytest.raises(ValueError, match="refusing to overwrite reconciliation output"):
        reconcile.write_bundle(payload, output, root=tmp_path)


def test_rejects_undeclared_reconciliation_bundle_entry(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    (output / "unreviewed_conclusions.md").write_text(
        "This undeclared file is not part of the verified bundle.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="bundle layout"):
        verify.verify_bundle(output, root=tmp_path)


def test_verifier_rejects_fifo_output_without_blocking(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    artifact = output / reconcile.RECONCILIATION_JSON
    artifact.unlink()
    os.mkfifo(artifact)
    script = (
        "from pathlib import Path; "
        "from scripts import verify_human_reconciliation_outputs as verify; "
        "verify.verify_bundle(Path(__import__('sys').argv[1]), "
        "root=Path(__import__('sys').argv[2]))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script, str(output), str(tmp_path)],
        cwd=reconcile.ROOT,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(reconcile.ROOT)},
        text=True,
        timeout=5,
    )

    assert completed.returncode != 0
    assert "must be a regular file" in completed.stderr


def test_verifier_rejects_fifo_before_read_open(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    artifact = output / reconcile.RECONCILIATION_JSON
    artifact.unlink()
    os.mkfifo(artifact)
    real_open = verify.os.open

    def reject_special_file_open(path, flags, *args, **kwargs):
        if path == reconcile.RECONCILIATION_JSON:
            raise AssertionError("non-regular artifact reached os.open")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(verify.os, "open", reject_special_file_open)

    with pytest.raises(ValueError, match="must be a regular file"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_bundle_entry_added_during_initial_capture(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    original_open = verify._open_regular_snapshot_at
    inserted = False

    def insert_undeclared_entry(*args, **kwargs):
        nonlocal inserted
        if not inserted:
            inserted = True
            (output / "late_conclusions.md").write_text(
                "This entry appeared after the bundle layout check.\n",
                encoding="utf-8",
            )
        return original_open(*args, **kwargs)

    monkeypatch.setattr(verify, "_open_regular_snapshot_at", insert_undeclared_entry)
    with pytest.raises(ValueError, match="changed during initial capture"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_output_bytes_changed_during_independent_recomputation(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    def mutate_output(**kwargs):
        (output / reconcile.RECONCILIATION_JSON).write_text(
            '{"status":"replacement"}\n', encoding="utf-8"
        )
        return payload

    monkeypatch.setattr(reconcile, "reconcile_verified", mutate_output)
    with pytest.raises(ValueError, match="changed during independent recomputation"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_output_symlinked_during_independent_recomputation(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    json_path = output / reconcile.RECONCILIATION_JSON
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(json_path.read_bytes())

    def replace_with_symlink(**kwargs):
        json_path.unlink()
        json_path.symlink_to(replacement)
        return payload

    monkeypatch.setattr(reconcile, "reconcile_verified", replace_with_symlink)
    with pytest.raises(ValueError, match="regular file|changed during"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_output_directory_replaced_during_independent_recomputation(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    detached = tmp_path / "detached-reconciliation"

    def replace_directory(**kwargs):
        output.rename(detached)
        shutil.copytree(detached, output)
        return payload

    monkeypatch.setattr(reconcile, "reconcile_verified", replace_directory)
    with pytest.raises(ValueError, match="output root changed"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_earlier_output_changed_during_final_snapshot_pass(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    real_snapshot = verify._regular_snapshot_from_descriptor
    calls = 0

    def mutate_after_json_recheck(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 5:
            (output / reconcile.RECONCILIATION_JSON).write_text(
                '{"status":"late replacement"}\n', encoding="utf-8"
            )
        return real_snapshot(*args, **kwargs)

    monkeypatch.setattr(
        verify,
        "_regular_snapshot_from_descriptor",
        mutate_after_json_recheck,
    )
    with pytest.raises(ValueError, match="changed during independent recomputation"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_output_directory_replaced_during_final_snapshot_pass(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    detached = tmp_path / "late-detached-reconciliation"
    real_snapshot = verify._regular_snapshot_from_descriptor
    calls = 0

    def replace_after_root_recheck(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 5:
            output.rename(detached)
            shutil.copytree(detached, output)
        return real_snapshot(*args, **kwargs)

    monkeypatch.setattr(
        verify,
        "_regular_snapshot_from_descriptor",
        replace_after_root_recheck,
    )
    with pytest.raises(ValueError, match="output root changed"):
        verify.verify_bundle(output, root=tmp_path)


def test_recomputation_failure_closes_output_directory_descriptor(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    def fail_recomputation(**kwargs):
        raise ValueError("synthetic reconciliation recomputation failure")

    monkeypatch.setattr(reconcile, "reconcile_verified", fail_recomputation)
    before = len(list(Path("/proc/self/fd").iterdir()))
    with pytest.raises(ValueError, match="synthetic reconciliation recomputation failure"):
        verify.verify_bundle(output, root=tmp_path)
    after = len(list(Path("/proc/self/fd").iterdir()))

    assert after == before


def test_rejects_missing_reconciliation_analysis_environment(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("analysis_environment", None)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="analysis environment"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_undeclared_reconciliation_manifest_field(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["posthoc_interpretation"] = "undeclared"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest schema"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_falsified_reconciliation_integrity_note(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["integrity_note"] = "Results may be edited after publication."
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="integrity note"):
        verify.verify_bundle(output, root=tmp_path)


@pytest.mark.parametrize(
    ("section", "entry", "field", "replacement", "error_match"),
    [
        (
            "artifacts",
            "canonical_reconciliation",
            "bytes",
            "matching_float",
            "integer bytes",
        ),
        (
            "implementation",
            "reconciler",
            "unexpected",
            "undeclared",
            "manifest entry must contain exactly",
        ),
    ],
)
def test_rejects_non_exact_reconciliation_provenance_entry_schema(
    tmp_path, monkeypatch, section, entry, field, replacement, error_match
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    provenance_entry = manifest[section][entry]
    if replacement == "matching_float":
        replacement = float(provenance_entry[field])
    provenance_entry[field] = replacement
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=error_match):
        verify.verify_bundle(output, root=tmp_path)


@pytest.mark.parametrize(
    ("entry", "error_match"),
    [
        ("requirements", "analysis requirements fingerprint"),
        ("ci_requirements", "analysis CI requirements fingerprint"),
    ],
)
def test_rejects_tampered_reconciliation_environment_pin(
    tmp_path, monkeypatch, entry, error_match
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["analysis_environment"][entry]["sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=error_match):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_nonregular_current_reconciliation_environment_pin(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    target = tmp_path / "requirements-target.txt"
    target.write_bytes((reconcile.ROOT / "requirements.txt").read_bytes())
    symlink = tmp_path / "requirements.txt"
    symlink.symlink_to(target)
    monkeypatch.setattr(reconcile, "ANALYSIS_REQUIREMENTS", symlink)

    with pytest.raises(ValueError, match="current analysis requirements must be a regular file"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_reconciliation_runtime_drift(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    expected = _expected_analysis_environment()["runtime"]
    monkeypatch.setattr(
        reconcile,
        "analysis_runtime_contract",
        lambda: {**expected, "python_version": "0.0.0-drifted"},
        raising=False,
    )

    with pytest.raises(ValueError, match="analysis runtime contract"):
        verify.verify_bundle(output, root=tmp_path)


@pytest.mark.parametrize(
    ("target", "field", "malformed"),
    [
        ("runtime", "schema_version", True),
        ("requirements", "bytes", "matching_float"),
        ("requirements", "unexpected", "undeclared"),
    ],
)
def test_rejects_non_exact_reconciliation_environment_schema(
    tmp_path, monkeypatch, target, field, malformed
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    manifest_path = output / reconcile.RECONCILIATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["analysis_environment"][target]
    if malformed == "matching_float":
        malformed = float(entry[field])
    entry[field] = malformed
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="analysis (runtime contract|requirements manifest entry)"):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_producer_commit_with_different_environment_bytes(
    tmp_path, monkeypatch
):
    payload = _payload()
    root = _producer_repo(tmp_path)
    monkeypatch.setattr(reconcile, "reconcile_verified", lambda **kwargs: payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=root)

    requirements = root / "requirements.txt"
    requirements.write_text("substituted==0.0.0\n", encoding="utf-8")
    subprocess.run(["git", "add", "requirements.txt"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "substitute environment"], cwd=root, check=True
    )
    substituted_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _rewrite_producer_commit(output, substituted_commit)

    with pytest.raises(ValueError, match="producer requirements fingerprint mismatch"):
        verify.verify_bundle(output, root=root)


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


def test_failed_candidate_verification_never_publishes_final_directory(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"

    def fail_verification(*args, **kwargs):
        raise ValueError("synthetic candidate verification failure")

    monkeypatch.setattr(verify, "verify_bundle", fail_verification)
    with pytest.raises(ValueError, match="synthetic candidate verification failure"):
        reconcile.write_bundle(payload, output, root=tmp_path)

    assert not output.exists()
    staging = list(tmp_path.glob(".reconciliation.staging-*"))
    assert len(staging) == 1
    candidate = staging[0] / "candidate"
    assert {
        reconcile.RECONCILIATION_JSON,
        reconcile.RECONCILIATION_MARKDOWN,
        reconcile.RECONCILIATION_MANIFEST,
    } == {path.name for path in candidate.iterdir()}


def test_reconciliation_publication_syncs_files_and_rename_before_success(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    events = []
    real_fsync = os.fsync
    real_publish = reconcile._publish_directory_noreplace

    def observe_fsync(descriptor):
        mode = os.fstat(descriptor).st_mode
        events.append("file-sync" if stat.S_ISREG(mode) else "directory-sync")
        return real_fsync(descriptor)

    def observe_publish(*args, **kwargs):
        events.append("publish")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(reconcile.os, "fsync", observe_fsync)
    monkeypatch.setattr(
        reconcile,
        "_publish_directory_noreplace",
        observe_publish,
    )

    receipt = reconcile.write_bundle(payload, output, root=tmp_path)

    assert receipt["status"] == "automated_human_reconciliation_bundle_verified"
    publish_index = events.index("publish")
    assert events[:publish_index].count("file-sync") == 3
    assert events[:publish_index].count("directory-sync") >= 2
    assert events[publish_index + 1 :].count("directory-sync") >= 2


def test_staging_path_replacement_cannot_publish_replacement_directory(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    real_publish = reconcile._publish_directory_noreplace
    detached = []

    def replace_before_publish(
        source_parent_fd,
        source_name,
        destination_parent_fd,
        destination_name,
        *,
        output_root,
    ):
        staging_root = Path(f"/proc/self/fd/{source_parent_fd}").resolve()
        moved = staging_root.with_name(f"{staging_root.name}-detached")
        staging_root.rename(moved)
        staging_root.mkdir()
        detached.append(moved)
        return real_publish(
            source_parent_fd,
            source_name,
            destination_parent_fd,
            destination_name,
            output_root=output_root,
        )

    monkeypatch.setattr(
        reconcile, "_publish_directory_noreplace", replace_before_publish
    )
    receipt = reconcile.write_bundle(payload, output, root=tmp_path)

    assert receipt["status"] == "automated_human_reconciliation_bundle_verified"
    assert (output / reconcile.RECONCILIATION_MANIFEST).is_file()
    assert len(detached) == 1
    assert list(detached[0].iterdir()) == []


def test_destination_parent_replacement_is_detected_without_touching_replacement(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "published-parent" / "reconciliation"
    real_publish = reconcile._publish_directory_noreplace
    detached = []

    def replace_parent_before_publish(*args, output_root, **kwargs):
        parent = output_root.parent
        moved = parent.with_name(f"{parent.name}-detached")
        parent.rename(moved)
        parent.mkdir()
        detached.append(moved)
        return real_publish(*args, output_root=output_root, **kwargs)

    monkeypatch.setattr(
        reconcile, "_publish_directory_noreplace", replace_parent_before_publish
    )
    with pytest.raises(ValueError, match="output parent changed"):
        reconcile.write_bundle(payload, output, root=tmp_path)

    assert not output.exists()
    assert list(output.parent.iterdir()) == []
    assert len(detached) == 1
    assert (
        detached[0] / output.name / reconcile.RECONCILIATION_MANIFEST
    ).is_file()


def test_destination_parent_replacement_before_staging_is_rejected(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "published-parent" / "reconciliation"
    real_mkdtemp = reconcile.tempfile.mkdtemp
    detached = []

    def replace_parent_before_staging(*args, dir, **kwargs):
        parent = output.parent
        moved = parent.with_name(f"{parent.name}-detached")
        parent.rename(moved)
        parent.mkdir()
        detached.append(moved)
        return real_mkdtemp(*args, dir=dir, **kwargs)

    monkeypatch.setattr(reconcile.tempfile, "mkdtemp", replace_parent_before_staging)

    with pytest.raises(ValueError, match="output parent changed"):
        reconcile.write_bundle(payload, output, root=tmp_path)

    assert not output.exists()
    assert list(output.parent.iterdir()) == []
    assert len(detached) == 1
    staging = list(detached[0].glob(".reconciliation.staging-*"))
    assert len(staging) == 1
    assert list(staging[0].iterdir()) == []


def test_setup_failure_closes_previously_opened_directory_descriptors(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    real_open = reconcile._open_bound_directory
    calls = 0

    def fail_second_open(path, *, dir_fd=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("synthetic staging-container open failure")
        return real_open(path, dir_fd=dir_fd)

    before = len(list(Path("/proc/self/fd").iterdir()))
    monkeypatch.setattr(reconcile, "_open_bound_directory", fail_second_open)
    with pytest.raises(ValueError, match="synthetic staging-container open failure"):
        reconcile.write_bundle(payload, output, root=tmp_path)
    after = len(list(Path("/proc/self/fd").iterdir()))

    assert after == before


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


def test_rejects_reconciliation_verifier_implementation_drift(tmp_path, monkeypatch):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)

    changed = tmp_path / "verify_human_reconciliation_outputs.py"
    changed.write_text("# changed verifier implementation\n", encoding="utf-8")
    monkeypatch.setattr(verify, "__file__", str(changed))

    with pytest.raises(
        ValueError,
        match="reconciliation verifier implementation fingerprint",
    ):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_same_byte_reconciler_replacement_during_recomputation(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    source = tmp_path / "reconcile_human_automated.py"
    source.write_bytes(Path(reconcile.__file__).read_bytes())
    detached = tmp_path / "detached-reconcile_human_automated.py"
    monkeypatch.setattr(reconcile, "__file__", str(source))

    def replace_reconciler(**kwargs):
        content = source.read_bytes()
        source.rename(detached)
        source.write_bytes(content)
        return payload

    monkeypatch.setattr(reconcile, "reconcile_verified", replace_reconciler)

    with pytest.raises(
        ValueError,
        match="reconciler implementation changed during independent recomputation",
    ):
        verify.verify_bundle(output, root=tmp_path)


def test_rejects_same_byte_requirements_replacement_during_recomputation(
    tmp_path, monkeypatch
):
    payload = _payload()
    _patch_recomputation(monkeypatch, payload)
    output = tmp_path / "reconciliation"
    reconcile.write_bundle(payload, output, root=tmp_path)
    requirements = tmp_path / "requirements.txt"
    requirements.write_bytes(reconcile.ANALYSIS_REQUIREMENTS.read_bytes())
    detached = tmp_path / "detached-requirements.txt"
    monkeypatch.setattr(reconcile, "ANALYSIS_REQUIREMENTS", requirements)

    def replace_requirements(**kwargs):
        content = requirements.read_bytes()
        requirements.rename(detached)
        requirements.write_bytes(content)
        return payload

    monkeypatch.setattr(reconcile, "reconcile_verified", replace_requirements)

    with pytest.raises(
        ValueError,
        match="analysis requirements changed during independent recomputation",
    ):
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
