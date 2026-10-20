"""Synthetic checks for human-analysis output attestation.

These fixtures are not collected human ratings or study findings.
"""
import hashlib
import json
import os
import platform
import shutil
from pathlib import Path

import pytest

from scripts import analyze_human_eval
from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as verify


def _payload():
    plan_bytes = core.PLAN.read_bytes()
    provenance = {
        "analysis_plan": {
            "path": core.PLAN.name,
            "bytes": len(plan_bytes),
            "sha256": hashlib.sha256(plan_bytes).hexdigest(),
        }
    }
    for key, path, logical_path in (
        ("protocol", freeze.DEFAULT_PROTOCOL, "paper/HUMAN_EVAL_PROTOCOL.md"),
        (
            "assignment_plan",
            freeze.DEFAULT_ASSIGNMENT_PLAN,
            "paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
        ),
        (
            "annotator_guide",
            freeze.DEFAULT_ANNOTATOR_GUIDE,
            "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
        ),
    ):
        content = path.read_bytes()
        provenance[key] = {
            "path": logical_path,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    summary = {
        variant: {
            field: {
                "n_reports_total": 2,
                "n_reports_scored": 2,
                "n_raw_scores": 4,
                "mean_report_score": 3.0,
                "median_report_score": 3.0,
                "raw_score_distribution": {
                    "1": 0,
                    "2": 0,
                    "3": 4,
                    "4": 0,
                    "5": 0,
                },
            }
            for field in core.DIMS
        }
        for variant in core.VARIANTS
    }
    contrasts = {
        name: {
            field: {
                "n_pairs": 2,
                "left_mean": 2.5,
                "right_mean": 3.0,
                "mean_difference": 0.5,
                "median_difference": 0.5,
                "bootstrap_95pct_ci_mean_difference": [0.0, 1.0],
                "paired_dz": 0.707,
                "positive_tasks": 1,
                "negative_tasks": 0,
                "tied_tasks": 1,
                "task_differences": {"task-a": 1.0, "task-b": 0.0},
                "task_ids_included": ["task-a", "task-b"],
                "missing_pair_tasks": [],
            }
            for field in core.DIMS
        }
        for _, _, name in core.CONTRASTS
    }
    agreement = {
        "schema_version": 1,
        "status": "pre-unblinding_pairwise_agreement",
        "n_annotators": 2,
        "annotators": ["annotator-a", "annotator-b"],
        "pairwise": [
            {
                "annotator_a": "annotator-a",
                "annotator_b": "annotator-b",
                "n_shared_items": 8,
                "dimensions": {
                    field: {
                        "n_double_rated": 8,
                        "raw_exact_agreement": 0.75,
                        "mean_absolute_difference": 0.25,
                        "quadratic_weighted_cohen_kappa": 0.8,
                    }
                    for field in core.DIMS
                },
            }
        ],
        "requires_predeclared_multi_rater_statistic": False,
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
        "n_tasks": 2,
        "task_ids": ["task-a", "task-b"],
        "verification": {"analysis_inputs_snapshot_bound": True},
        "provenance": provenance,
        "pre_unblinding_agreement": agreement,
        "variant_summary": summary,
        "paired_contrasts": contrasts,
    }


def test_markdown_reports_every_predeclared_descriptive_layer():
    markdown = analyze_human_eval.render_markdown(_payload())

    assert "## Variant summaries" in markdown
    assert "D3 | correctness_1_5 | 2/2 | 4 | 3.000 | 3.000 | 1:0; 2:0; 3:4; 4:0; 5:0" in markdown
    assert "## Paired contrasts" in markdown
    assert "D6_minus_D3_retrieval_depth | correctness_1_5 | task-a, task-b | — | 2.500 | 3.000 | 0.500 | 0.500 | 0.707 | [0.000, 1.000] | 1/0/1 | task-a:1.000; task-b:0.000" in markdown
    assert "## Pre-unblinding agreement" in markdown
    assert "annotator-a / annotator-b | correctness_1_5 | 8 | 0.750 | 0.250 | 0.800" in markdown
    assert "No human-validation null-hypothesis p-values are computed" in markdown


def test_markdown_keeps_missingness_and_undefined_statistics_visible():
    payload = _payload()
    field = core.DIMS[0]
    summary = payload["variant_summary"]["D3"][field]
    summary.update(
        n_reports_scored=0,
        n_raw_scores=0,
        mean_report_score=None,
        median_report_score=None,
        raw_score_distribution={str(score): 0 for score in range(1, 6)},
    )
    contrast = payload["paired_contrasts"][core.CONTRASTS[0][2]][field]
    contrast.update(
        n_pairs=0,
        left_mean=None,
        right_mean=None,
        mean_difference=None,
        median_difference=None,
        bootstrap_95pct_ci_mean_difference=None,
        paired_dz=None,
        positive_tasks=0,
        negative_tasks=0,
        tied_tasks=0,
        task_differences={},
        task_ids_included=[],
        missing_pair_tasks=["task-a", "task-b"],
    )
    payload["pre_unblinding_agreement"]["pairwise"][0]["dimensions"][field][
        "quadratic_weighted_cohen_kappa"
    ] = None

    markdown = analyze_human_eval.render_markdown(payload)

    assert "D3 | correctness_1_5 | 0/2 | 0 | NA | NA | 1:0; 2:0; 3:0; 4:0; 5:0" in markdown
    assert "correctness_1_5 | — | task-a, task-b | NA | NA | NA | NA | NA | NA | 0/0/0 | —" in markdown
    assert "annotator-a / annotator-b | correctness_1_5 | 8 | 0.750 | 0.250 | NA" in markdown


def test_markdown_escapes_data_derived_table_labels():
    payload = _payload()
    field = core.DIMS[0]
    contrast = payload["paired_contrasts"][core.CONTRASTS[0][2]][field]
    unsafe_task = "task|a\\b\ncontinuation"
    contrast["task_ids_included"] = [unsafe_task]
    contrast["task_differences"] = {unsafe_task: 1.0}
    pair = payload["pre_unblinding_agreement"]["pairwise"][0]
    pair["annotator_a"] = "reviewer|a\\b\ncontinuation"

    markdown = analyze_human_eval.render_markdown(payload)

    assert "task\\|a\\\\b continuation" in markdown
    assert "reviewer\\|a\\\\b continuation / annotator-b" in markdown
    assert "\ncontinuation" not in markdown


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
    assert receipt["independent_recomputation_verified"] is False
    manifest = json.loads(
        (output / analyze_human_eval.ANALYSIS_MANIFEST).read_text(encoding="utf-8")
    )
    assert set(manifest["artifacts"]) == {"canonical_analysis", "manuscript_rendering"}
    assert set(manifest["implementation"]) == {
        "analysis_core",
        "analysis_renderer",
        "analysis_verifier",
        "blinded_freeze_verifier",
        "packet_builder",
        "packet_verifier",
        "ratings_freezer",
    }


def _expected_analysis_environment():
    requirements = (core.ROOT / "requirements.txt").read_bytes()
    ci_requirements = (core.ROOT / "requirements-ci.lock").read_bytes()
    python_version = (core.ROOT / ".python-version").read_bytes()
    return {
        "requirements": {
            "path": "requirements.txt",
            **analyze_human_eval._fingerprint_bytes(requirements),
        },
        "ci_requirements": {
            "path": "requirements-ci.lock",
            **analyze_human_eval._fingerprint_bytes(ci_requirements),
        },
        "python_version": {
            "path": ".python-version",
            **analyze_human_eval._fingerprint_bytes(python_version),
        },
        "runtime": {
            "schema_version": 1,
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "random_state_version": core.random.Random.VERSION,
        },
    }


def test_write_bundle_binds_pinned_and_actual_analysis_environment(tmp_path):
    output = tmp_path / "analysis"
    receipt = analyze_human_eval.write_bundle(_payload(), output)
    manifest = json.loads(
        (output / analyze_human_eval.ANALYSIS_MANIFEST).read_text(encoding="utf-8")
    )

    assert manifest["analysis_environment"] == _expected_analysis_environment()
    assert receipt["analysis_environment_bound"] is True


def test_rejects_missing_analysis_environment_contract(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("analysis_environment", None)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="analysis environment"):
        verify.verify_bundle(output)


@pytest.mark.parametrize(
    ("entry", "error_match"),
    [
        ("requirements", "analysis requirements fingerprint"),
        ("ci_requirements", "analysis CI requirements fingerprint"),
    ],
)
def test_rejects_tampered_analysis_environment_contract(
    tmp_path, entry, error_match
):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["analysis_environment"] = _expected_analysis_environment()
    manifest["analysis_environment"][entry]["sha256"] = "0" * 64
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=error_match):
        verify.verify_bundle(output)


def test_rejects_analysis_runtime_drift(tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    expected = _expected_analysis_environment()["runtime"]
    monkeypatch.setattr(
        analyze_human_eval,
        "analysis_runtime_contract",
        lambda: {**expected, "python_version": "0.0.0-drifted"},
        raising=False,
    )

    with pytest.raises(ValueError, match="analysis runtime contract"):
        verify.verify_bundle(output)


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("schema_version", True),
        ("random_state_version", float(core.random.Random.VERSION)),
    ],
)
def test_rejects_non_exact_analysis_runtime_types(tmp_path, field, malformed):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["analysis_environment"]["runtime"][field] = malformed
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="analysis runtime contract"):
        verify.verify_bundle(output)


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("bytes", "matching_float"),
        ("unexpected", "undeclared"),
    ],
)
def test_rejects_non_exact_analysis_pin_entry_schema(
    tmp_path, field, malformed
):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if malformed == "matching_float":
        malformed = float(
            manifest["analysis_environment"]["requirements"]["bytes"]
        )
    manifest["analysis_environment"]["requirements"][field] = malformed
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="analysis requirements manifest entry"):
        verify.verify_bundle(output)


def test_invalid_payload_does_not_reserve_publication_path(tmp_path):
    output = tmp_path / "analysis"
    payload = _payload()
    payload["human_ratings_generated"] = True

    with pytest.raises(ValueError, match="analysis human_ratings_generated mismatch"):
        analyze_human_eval.write_bundle(payload, output)

    assert not output.exists()


def test_provenance_preflight_failure_does_not_reserve_publication_path(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    missing_verifier = tmp_path / "missing_verifier.py"
    monkeypatch.setattr(
        analyze_human_eval,
        "ANALYSIS_VERIFIER_SOURCE",
        missing_verifier,
    )

    with pytest.raises(ValueError, match="must be a regular file"):
        analyze_human_eval.write_bundle(_payload(), output)

    assert not output.exists()


def test_failed_candidate_verification_never_publishes_final_directory(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"

    def fail_verification(*args, **kwargs):
        raise ValueError("synthetic candidate verification failure")

    monkeypatch.setattr(verify, "verify_bundle", fail_verification)
    with pytest.raises(ValueError, match="synthetic candidate verification failure"):
        analyze_human_eval.write_bundle(_payload(), output)

    assert not output.exists()
    staging = list(tmp_path.glob(".analysis.staging-*"))
    assert len(staging) == 1
    assert {
        analyze_human_eval.ANALYSIS_JSON,
        analyze_human_eval.ANALYSIS_MARKDOWN,
        analyze_human_eval.ANALYSIS_MANIFEST,
    } == {path.name for path in (staging[0] / "candidate").iterdir()}


def test_failed_independent_recomputation_never_publishes_final_directory(tmp_path):
    output = tmp_path / "analysis"
    observed = {}

    def fail_recomputation(candidate_root):
        observed["candidate_root"] = candidate_root
        assert candidate_root != output
        assert (candidate_root / analyze_human_eval.ANALYSIS_MANIFEST).is_file()
        raise ValueError("synthetic independent recomputation failure")

    with pytest.raises(ValueError, match="synthetic independent recomputation failure"):
        analyze_human_eval.write_bundle(
            _payload(),
            output,
            verify_candidate=fail_recomputation,
        )

    assert "candidate_root" in observed
    assert not output.exists()


def test_open_bound_directory_closes_descriptor_when_fstat_fails(
    tmp_path, monkeypatch
):
    real_open = analyze_human_eval.os.open
    real_fstat = analyze_human_eval.os.fstat
    opened = []

    def tracked_open(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def fail_fstat(_descriptor):
        raise OSError("synthetic fstat failure")

    monkeypatch.setattr(analyze_human_eval.os, "open", tracked_open)
    monkeypatch.setattr(analyze_human_eval.os, "fstat", fail_fstat)
    with pytest.raises(OSError, match="synthetic fstat failure"):
        analyze_human_eval._open_bound_directory(tmp_path)

    assert len(opened) == 1
    with pytest.raises(OSError):
        real_fstat(opened[0])


def test_concurrent_destination_is_never_replaced(tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    real_publish = analyze_human_eval._publish_directory

    def publish_after_competitor(*args, output_root, **kwargs):
        output_root.mkdir()
        return real_publish(*args, output_root=output_root, **kwargs)

    monkeypatch.setattr(
        analyze_human_eval,
        "_publish_directory",
        publish_after_competitor,
    )
    with pytest.raises(ValueError, match="refusing to overwrite human-analysis output"):
        analyze_human_eval.write_bundle(_payload(), output)

    assert output.is_dir()
    assert list(output.iterdir()) == []
    staging = list(tmp_path.glob(".analysis.staging-*"))
    assert len(staging) == 1


def test_staging_path_replacement_cannot_publish_replacement_directory(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    real_publish = analyze_human_eval._publish_directory
    detached = []

    def replace_before_publish(*args, output_root, **kwargs):
        staging_root = Path(f"/proc/self/fd/{args[0]}").resolve()
        moved = staging_root.with_name(f"{staging_root.name}-detached")
        staging_root.rename(moved)
        staging_root.mkdir()
        detached.append(moved)
        return real_publish(*args, output_root=output_root, **kwargs)

    monkeypatch.setattr(
        analyze_human_eval,
        "_publish_directory",
        replace_before_publish,
    )
    receipt = analyze_human_eval.write_bundle(_payload(), output)

    assert receipt["status"] == "human_validation_analysis_bundle_verified"
    assert (output / analyze_human_eval.ANALYSIS_MANIFEST).is_file()
    assert len(detached) == 1
    assert list(detached[0].iterdir()) == []


def test_destination_parent_replacement_is_detected_without_touching_replacement(
    tmp_path, monkeypatch
):
    output = tmp_path / "published-parent" / "analysis"
    real_publish = analyze_human_eval._publish_directory
    detached = []

    def replace_parent_before_publish(*args, output_root, **kwargs):
        parent = output_root.parent
        moved = parent.with_name(f"{parent.name}-detached")
        parent.rename(moved)
        parent.mkdir()
        detached.append(moved)
        return real_publish(*args, output_root=output_root, **kwargs)

    monkeypatch.setattr(
        analyze_human_eval,
        "_publish_directory",
        replace_parent_before_publish,
    )
    with pytest.raises(ValueError, match="output parent changed"):
        analyze_human_eval.write_bundle(_payload(), output)

    assert not output.exists()
    assert list(output.parent.iterdir()) == []
    assert len(detached) == 1
    assert (detached[0] / output.name / analyze_human_eval.ANALYSIS_MANIFEST).is_file()


def test_destination_parent_replacement_during_staging_setup_is_detected(
    tmp_path, monkeypatch
):
    output = tmp_path / "published-parent" / "analysis"
    real_mkdtemp = analyze_human_eval.tempfile.mkdtemp
    detached = []

    def create_staging_then_replace_parent(*args, **kwargs):
        staging = real_mkdtemp(*args, **kwargs)
        parent = output.parent
        moved = parent.with_name(f"{parent.name}-detached")
        parent.rename(moved)
        parent.mkdir()
        (parent / Path(staging).name).mkdir()
        detached.append(moved)
        return staging

    monkeypatch.setattr(
        analyze_human_eval.tempfile,
        "mkdtemp",
        create_staging_then_replace_parent,
    )
    with pytest.raises(ValueError, match="output parent changed"):
        analyze_human_eval.write_bundle(_payload(), output)

    assert not output.exists()
    assert [path.name for path in output.parent.iterdir()] == [
        next(detached[0].glob(".analysis.staging-*")).name
    ]
    assert len(detached) == 1


def test_independent_verifier_recomputes_from_retained_ratings(tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    freeze_root = tmp_path / "freeze"
    raw_root = freeze_root / "raw_rating_inputs"
    raw_root.mkdir(parents=True)
    second = raw_root / "0002.csv"
    first = raw_root / "0001.csv"
    second.write_text("second\n", encoding="utf-8")
    first.write_text("first\n", encoding="utf-8")
    observed = {}

    def fake_analyze(rating_paths, **kwargs):
        observed["rating_paths"] = list(rating_paths)
        observed.update(kwargs)
        return expected

    monkeypatch.setattr(core, "analyze", fake_analyze)

    receipt = verify.verify_bundle_against_inputs(output, freeze_root=freeze_root)

    assert receipt["independent_recomputation_verified"] is True
    assert receipt["recomputed_from_retained_ratings"] is True
    assert receipt["outputs_stable_during_independent_recomputation"] is True
    assert observed["rating_paths"] == []
    assert observed["freeze_root"] == freeze_root


@pytest.mark.parametrize(
    ("filename", "label"),
    [
        (analyze_human_eval.ANALYSIS_JSON, "canonical human-analysis JSON"),
        (analyze_human_eval.ANALYSIS_MARKDOWN, "human-analysis Markdown"),
        (analyze_human_eval.ANALYSIS_MANIFEST, "human-analysis output manifest"),
    ],
)
def test_independent_verifier_rejects_output_drift_during_recomputation(
    tmp_path, monkeypatch, filename, label
):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    artifact = output / filename

    def mutate_output_during_recomputation(*_args, **_kwargs):
        artifact.write_bytes(artifact.read_bytes() + b"\n")
        return expected

    monkeypatch.setattr(core, "analyze", mutate_output_during_recomputation)

    with pytest.raises(
        ValueError,
        match=f"{label} changed during independent recomputation",
    ):
        verify.verify_bundle_against_inputs(
            output,
            rating_paths=[tmp_path / "retained.csv"],
        )


def test_independent_verifier_rejects_identical_output_inode_replacement(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    artifact = output / analyze_human_eval.ANALYSIS_JSON
    detached = tmp_path / "detached-analysis.json"

    def replace_output_inode(*_args, **_kwargs):
        original = artifact.read_bytes()
        artifact.rename(detached)
        artifact.write_bytes(original)
        return expected

    monkeypatch.setattr(core, "analyze", replace_output_inode)

    with pytest.raises(ValueError, match="changed during independent recomputation"):
        verify.verify_bundle_against_inputs(
            output,
            rating_paths=[tmp_path / "retained.csv"],
        )


def test_independent_verifier_rejects_identical_output_directory_replacement(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    detached = tmp_path / "detached-analysis"

    def replace_output_directory(*_args, **_kwargs):
        output.rename(detached)
        shutil.copytree(detached, output)
        return expected

    monkeypatch.setattr(core, "analyze", replace_output_directory)

    with pytest.raises(ValueError, match="output root changed"):
        verify.verify_bundle_against_inputs(
            output,
            rating_paths=[tmp_path / "retained.csv"],
        )


def test_independent_verifier_rejects_change_after_output_content_recheck(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    artifact = output / analyze_human_eval.ANALYSIS_JSON
    real_snapshot = verify._regular_snapshot_from_descriptor
    calls = 0

    def change_after_json_final_read(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 5:
            artifact.write_bytes(artifact.read_bytes() + b"\n")
        return real_snapshot(*args, **kwargs)

    monkeypatch.setattr(core, "analyze", lambda *_args, **_kwargs: expected)
    monkeypatch.setattr(
        verify,
        "_regular_snapshot_from_descriptor",
        change_after_json_final_read,
    )

    with pytest.raises(ValueError, match="changed during independent recomputation"):
        verify.verify_bundle_against_inputs(
            output,
            rating_paths=[tmp_path / "retained.csv"],
        )


def test_independent_verifier_rejects_directory_replacement_during_final_observation(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    detached = tmp_path / "detached-analysis"
    real_snapshot = verify._regular_snapshot_from_descriptor
    calls = 0

    def replace_after_first_final_read(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 5:
            output.rename(detached)
            shutil.copytree(detached, output)
        return real_snapshot(*args, **kwargs)

    monkeypatch.setattr(core, "analyze", lambda *_args, **_kwargs: expected)
    monkeypatch.setattr(
        verify,
        "_regular_snapshot_from_descriptor",
        replace_after_first_final_read,
    )

    with pytest.raises(ValueError, match="output root changed"):
        verify.verify_bundle_against_inputs(
            output,
            rating_paths=[tmp_path / "retained.csv"],
        )


def test_independent_verifier_closes_output_descriptors_on_analysis_failure(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    descriptor_root = Path("/proc/self/fd")
    before = len(list(descriptor_root.iterdir()))

    def fail_analysis(*_args, **_kwargs):
        raise ValueError("synthetic analysis failure")

    monkeypatch.setattr(core, "analyze", fail_analysis)
    with pytest.raises(ValueError, match="synthetic analysis failure"):
        verify.verify_bundle_against_inputs(
            output,
            rating_paths=[tmp_path / "retained.csv"],
        )

    assert len(list(descriptor_root.iterdir())) == before


def test_verifier_rejects_fifo_output_without_blocking(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    artifact = output / analyze_human_eval.ANALYSIS_JSON
    artifact.unlink()
    os.mkfifo(artifact)

    with pytest.raises(ValueError, match="must be a regular file"):
        verify.verify_bundle(output)


def test_independent_verifier_rejects_rehashed_outcome_tampering(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    changed = json.loads(json.dumps(expected))
    changed["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = 4.0
    _rewrite_and_rehash(output, changed)
    monkeypatch.setattr(core, "analyze", lambda *_args, **_kwargs: expected)

    with pytest.raises(ValueError, match="independently recomputed human analysis"):
        verify.verify_bundle_against_inputs(
            output,
            rating_paths=[tmp_path / "retained.csv"],
        )


def test_independent_verifier_uses_type_strict_payload_comparison(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    changed = json.loads(json.dumps(expected))
    changed["n_tasks"] = 2.0
    _rewrite_and_rehash(output, changed)
    monkeypatch.setattr(core, "analyze", lambda *_args, **_kwargs: expected)

    with pytest.raises(ValueError, match="independently recomputed human analysis"):
        verify.verify_bundle_against_inputs(
            output,
            rating_paths=[tmp_path / "retained.csv"],
        )


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


def test_rejects_analysis_verifier_implementation_drift(tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)

    changed_verifier = tmp_path / "verify_human_eval_analysis_outputs.py"
    changed_verifier.write_text("# changed verification gate\n", encoding="utf-8")
    monkeypatch.setattr(verify, "__file__", str(changed_verifier))

    with pytest.raises(ValueError, match="analysis verifier implementation fingerprint"):
        verify.verify_bundle(output)


def test_rejects_ratings_freezer_implementation_drift(tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)

    changed_freezer = tmp_path / "freeze_human_eval_ratings.py"
    changed_freezer.write_text("# changed governing-input anchors\n", encoding="utf-8")
    monkeypatch.setattr(freeze, "__file__", str(changed_freezer))
    monkeypatch.setattr(
        freeze,
        "DEFAULT_PROTOCOL",
        tmp_path / "must-not-read-drifted-protocol.md",
    )

    with pytest.raises(ValueError, match="ratings freezer implementation fingerprint"):
        verify.verify_bundle(output)


@pytest.mark.parametrize(
    "module,filename,label",
    [
        (
            core.blind_verify,
            "verify_human_eval_freeze.py",
            "blinded freeze verifier implementation fingerprint",
        ),
        (
            core.packet,
            "build_human_eval_packet.py",
            "packet builder implementation fingerprint",
        ),
        (
            core.map_verify,
            "verify_human_eval_packet.py",
            "packet verifier implementation fingerprint",
        ),
    ],
)
def test_rejects_upstream_validation_implementation_drift(
    tmp_path, monkeypatch, module, filename, label
):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)

    changed_verifier = tmp_path / filename
    changed_verifier.write_text("# changed upstream verification gate\n", encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(changed_verifier))

    with pytest.raises(ValueError, match=label):
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


@pytest.mark.parametrize(
    "entry",
    ["protocol", "assignment_plan", "annotator_guide"],
)
def test_rejects_governing_document_provenance_drift_after_rehash(tmp_path, entry):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = json.loads(
        (output / analyze_human_eval.ANALYSIS_JSON).read_text(encoding="utf-8")
    )
    payload["provenance"][entry]["sha256"] = "0" * 64
    _rewrite_and_rehash(output, payload)

    with pytest.raises(ValueError, match=f"{entry.replace('_', '-')} provenance"):
        verify.verify_bundle(output)


def test_rejects_missing_manifest(tmp_path):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    (output / analyze_human_eval.ANALYSIS_MANIFEST).unlink()

    with pytest.raises(ValueError, match="output manifest must be a regular file"):
        verify.verify_bundle(output)
