"""Synthetic checks for human-analysis output attestation.

These fixtures are not collected human ratings or study findings.
"""
import hashlib
import json
import os
import platform
import shutil
import stat
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
                "paired_dz": 2 ** -0.5,
                "positive_tasks": 1,
                "negative_tasks": 0,
                "tied_tasks": 1,
                "task_differences": {"task-a": 1.0, "task-b": 0.0},
                "task_ids_included": ["task-a", "task-b"],
                "missing_pair_tasks": [],
                "rater_coverage": {
                    "count_by_rater_pair": {
                        cell: 2 if cell == "2/2" else 0
                        for cell in core.RATER_COVERAGE_CELLS
                    },
                    "task_ids_by_rater_pair": {
                        cell: ["task-a", "task-b"] if cell == "2/2" else []
                        for cell in core.RATER_COVERAGE_CELLS
                    },
                },
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
                        "n_annotator_a_only_rated": 0,
                        "n_annotator_b_only_rated": 0,
                        "n_neither_rated": 0,
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
    assert "A-only rated | B-only rated | Neither rated" in markdown
    assert "annotator-a / annotator-b | correctness_1_5 | 8 | 0.750 | 0.250 | 0.800 | 0 | 0 | 0 |" in markdown
    assert "No human-validation null-hypothesis p-values are computed" in markdown


def test_markdown_renders_asymmetric_nonresponse_without_imputation():
    payload = _payload()
    dimension = payload["pre_unblinding_agreement"]["pairwise"][0]["dimensions"][core.DIMS[0]]
    dimension.update(
        n_double_rated=2,
        n_annotator_a_only_rated=2,
        n_annotator_b_only_rated=1,
        n_neither_rated=3,
    )
    markdown = analyze_human_eval.render_markdown(payload)
    assert "annotator-a / annotator-b | correctness_1_5 | 2 | 0.750 | 0.250 | 0.800 | 2 | 1 | 3 |" in markdown
    assert "Agreement metrics use double-rated items only" in markdown


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



@pytest.mark.parametrize(
    "injected_label",
    [
        "[external](https://example.invalid/coordinator)",
        "![pixel](https://example.invalid/track)",
        '<img src="https://example.invalid/track">',
        "<script>alert(1)</script>",
        "`code` **bold**",
        "plain multilingual label – 日本語",
    ],
)
def test_markdown_keeps_untrusted_rater_and_task_labels_inert(injected_label):
    """Pseudonyms and task IDs must never become links or HTML in analysis.md."""
    from html import unescape

    from markdown_it import MarkdownIt

    payload = _payload()
    contrast = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    contrast["task_ids_included"] = [injected_label]
    contrast["task_differences"] = {injected_label: 1.0}
    payload["pre_unblinding_agreement"]["pairwise"][0]["annotator_a"] = injected_label

    markdown = analyze_human_eval.render_markdown(payload)
    rendered = MarkdownIt("default", {"html": True}).render(markdown)

    assert injected_label in unescape(rendered)
    assert "<a href=" not in rendered
    assert "<img " not in rendered
    assert "<script" not in rendered
    assert "<code>code</code>" not in rendered
    assert "<strong>bold</strong>" not in rendered


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
    "mutation",
    [
        "root_claim",
        "artifact_metadata",
        "implementation_metadata",
        "integrity_note",
    ],
)
def test_rejects_undeclared_or_misleading_manifest_metadata(tmp_path, mutation):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    manifest_path = output / analyze_human_eval.ANALYSIS_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if mutation == "root_claim":
        manifest["human_validation_confirmed"] = True
    elif mutation == "artifact_metadata":
        manifest["artifacts"]["canonical_analysis"]["claim"] = "confirmatory"
    elif mutation == "implementation_metadata":
        manifest["implementation"]["analysis_core"]["source"] = "reviewed"
    else:
        manifest["integrity_note"] = "Human validation is confirmed."
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="manifest schema|manifest entry|integrity note"
    ):
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


def test_analysis_publication_syncs_files_and_rename_before_success(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    events = []
    real_fsync = os.fsync
    real_publish = analyze_human_eval._publish_directory
    real_verify_bundle = verify.verify_bundle

    def observe_fsync(descriptor):
        mode = os.fstat(descriptor).st_mode
        resolved = Path(f"/proc/self/fd/{descriptor}").resolve()
        if stat.S_ISREG(mode):
            label = resolved.name
        elif resolved == tmp_path.resolve():
            label = "output-parent"
        elif resolved.name == "candidate":
            label = "candidate"
        elif resolved.name.startswith(".analysis.staging-"):
            label = "staging"
        else:
            label = f"unexpected-directory:{resolved}"
        events.append(("sync", label))
        return real_fsync(descriptor)

    def observe_publish(*args, **kwargs):
        events.append(("publish",))
        return real_publish(*args, **kwargs)

    def observe_verify_bundle(candidate):
        events.append(("verify-bundle",))
        return real_verify_bundle(candidate)

    def observe_recomputation(_candidate):
        events.append(("verify-recomputation",))
        return {"status": "human_validation_analysis_bundle_verified"}

    monkeypatch.setattr(analyze_human_eval.os, "fsync", observe_fsync)
    monkeypatch.setattr(analyze_human_eval, "_publish_directory", observe_publish)
    monkeypatch.setattr(verify, "verify_bundle", observe_verify_bundle)

    receipt = analyze_human_eval.write_bundle(
        _payload(), output, verify_candidate=observe_recomputation
    )

    assert receipt["status"] == "human_validation_analysis_bundle_verified"
    assert events == [
        ("sync", analyze_human_eval.ANALYSIS_JSON),
        ("sync", analyze_human_eval.ANALYSIS_MARKDOWN),
        ("sync", analyze_human_eval.ANALYSIS_MANIFEST),
        ("sync", "candidate"),
        ("sync", "staging"),
        ("verify-bundle",),
        ("verify-recomputation",),
        ("publish",),
        ("sync", "staging"),
        ("sync", "output-parent"),
    ]


def test_analysis_publication_syncs_new_output_parent_hierarchy(
    tmp_path, monkeypatch
):
    first_parent = tmp_path / "new-parent"
    output_parent = first_parent / "nested"
    output = output_parent / "analysis"
    synced_directories = []
    real_fsync = os.fsync

    def observe_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            synced_directories.append(Path(f"/proc/self/fd/{descriptor}").resolve())
        return real_fsync(descriptor)

    monkeypatch.setattr(analyze_human_eval.os, "fsync", observe_fsync)

    analyze_human_eval.write_bundle(_payload(), output)

    assert tmp_path.resolve() in synced_directories
    assert first_parent.resolve() in synced_directories
    assert output_parent.resolve() in synced_directories


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


def test_independent_verifier_rejects_identical_source_replacement_during_recomputation(
    tmp_path, monkeypatch
):
    source = tmp_path / "verify_human_eval_analysis_outputs.py"
    source.write_bytes(Path(verify.__file__).read_bytes())
    monkeypatch.setattr(verify, "__file__", str(source))
    monkeypatch.setattr(analyze_human_eval, "ANALYSIS_VERIFIER_SOURCE", source)

    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    detached = tmp_path / "detached-verifier.py"

    def replace_verifier_during_recomputation(*_args, **_kwargs):
        original = source.read_bytes()
        source.rename(detached)
        source.write_bytes(original)
        return expected

    monkeypatch.setattr(core, "analyze", replace_verifier_during_recomputation)

    with pytest.raises(
        ValueError,
        match="analysis verifier implementation changed during independent recomputation",
    ):
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


def test_verifier_opens_provenance_fifo_nonblocking(tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    plan = tmp_path / "analysis-plan.fifo"
    os.mkfifo(plan)
    monkeypatch.setattr(core, "PLAN", plan)
    real_open = verify.os.open

    def require_nonblocking_open(path, flags, *args, **kwargs):
        if Path(path) == plan and not flags & os.O_NONBLOCK:
            raise AssertionError("provenance source must be opened nonblocking")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(verify.os, "open", require_nonblocking_open)

    with pytest.raises(ValueError, match="must be a regular file"):
        verify.verify_bundle(output)


def test_independent_verifier_rejects_rehashed_outcome_tampering(
    tmp_path, monkeypatch
):
    output = tmp_path / "analysis"
    expected = _payload()
    analyze_human_eval.write_bundle(expected, output)
    changed = json.loads(json.dumps(expected))
    changed["pre_unblinding_agreement"]["pairwise"][0]["dimensions"][core.DIMS[0]]["raw_exact_agreement"] = 0.875
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
    # Preserve the numeric value but change its JSON type. New denominator
    # checks correctly reject n_tasks=2.0 before recomputation.
    changed["variant_summary"]["D3"][core.DIMS[0]]["mean_report_score"] = 3
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


def test_implementation_drift_precedes_nonregular_owned_path(tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)

    changed_freezer = tmp_path / "freeze_human_eval_ratings.py"
    changed_freezer.write_text("# changed governing-input anchors\n", encoding="utf-8")
    monkeypatch.setattr(freeze, "__file__", str(changed_freezer))
    monkeypatch.setattr(freeze, "DEFAULT_PROTOCOL", tmp_path)

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


@pytest.mark.parametrize(
    "artifact",
    [
        analyze_human_eval.ANALYSIS_JSON,
        analyze_human_eval.ANALYSIS_MARKDOWN,
        analyze_human_eval.ANALYSIS_MANIFEST,
    ],
)
def test_candidate_post_verification_mutation_cannot_be_published(
    tmp_path, artifact
):
    """Synthetic post-verifier byte changes must not inherit a PASS receipt."""
    output = tmp_path / "analysis"

    def modify_candidate_after_verification(candidate):
        source = candidate / artifact
        source.write_bytes(source.read_bytes() + b"synthetic post-verify drift")
        return {"status": "synthetic_verifier_pass"}

    with pytest.raises(ValueError, match="changed during independent recomputation"):
        analyze_human_eval.write_bundle(
            _payload(), output, verify_candidate=modify_candidate_after_verification
        )
    assert not output.exists()


def test_same_byte_inode_replacement_after_candidate_verification_is_rejected(
    tmp_path,
):
    """Hash equality does not excuse a swapped staged-file identity."""
    output = tmp_path / "analysis"

    def replace_candidate(candidate):
        original = candidate / analyze_human_eval.ANALYSIS_MARKDOWN
        replacement = tmp_path / "synthetic-replacement.md"
        replacement.write_bytes(original.read_bytes())
        os.replace(replacement, original)
        return {"status": "synthetic_verifier_pass"}

    with pytest.raises(ValueError, match="changed during independent recomputation"):
        analyze_human_eval.write_bundle(
            _payload(), output, verify_candidate=replace_candidate
        )
    assert not output.exists()


def test_candidate_inventory_mutation_after_verification_is_rejected(tmp_path):
    """Unannounced additions to a verified candidate invalidate its directory."""
    output = tmp_path / "analysis"

    def add_candidate_sidecar(candidate):
        (candidate / "synthetic-unverified-sidecar").write_text(
            "not part of the verified bundle", encoding="utf-8"
        )
        return {"status": "synthetic_verifier_pass"}

    with pytest.raises(ValueError, match="output root changed"):
        analyze_human_eval.write_bundle(
            _payload(), output, verify_candidate=add_candidate_sidecar
        )
    assert not output.exists()


def test_candidate_changes_inside_semantic_verifier_are_rejected(
    tmp_path, monkeypatch
):
    """A successful semantic check cannot be reused after its candidate drifts."""
    output = tmp_path / "analysis"
    original_verify = verify.verify_bundle

    def verify_then_mutate(candidate):
        receipt = original_verify(candidate)
        path = candidate / analyze_human_eval.ANALYSIS_JSON
        path.write_bytes(path.read_bytes() + b"synthetic post-check mutation")
        return receipt

    monkeypatch.setattr(verify, "verify_bundle", verify_then_mutate)
    with pytest.raises(ValueError, match="changed during independent recomputation"):
        analyze_human_eval.write_bundle(_payload(), output)
    assert not output.exists()


def test_unchanged_candidate_remains_publishable_with_second_verifier(tmp_path):
    """The custody gate does not require real ratings or alter valid results."""
    output = tmp_path / "analysis"

    def synthetic_second_verifier(candidate):
        assert (candidate / analyze_human_eval.ANALYSIS_JSON).is_file()
        return verify.verify_bundle(candidate)

    receipt = analyze_human_eval.write_bundle(
        _payload(), output, verify_candidate=synthetic_second_verifier
    )
    assert receipt["status"] == "human_validation_analysis_bundle_verified"
    assert verify.verify_bundle(output)["status"] == receipt["status"]


@pytest.mark.parametrize(
    "mutation",
    [
        "changed_task_effect",
        "extra_task_effect",
        "off_lattice_effect",
        "false_mean",
        "false_median",
        "false_direction_count",
        "false_arm_mean",
    ],
)
def test_standalone_verifier_rejects_rehashed_paired_arithmetic_drift(
    tmp_path, mutation
):
    # Synthetic publication bundle; this does not create human ratings.
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    if mutation == "changed_task_effect":
        block["task_differences"]["task-a"] = -1.0
    elif mutation == "extra_task_effect":
        block["task_differences"]["unknown-task"] = 0.0
    elif mutation == "off_lattice_effect":
        block["task_differences"]["task-a"] = 1.25
    elif mutation == "false_mean":
        block["mean_difference"] = 0.25
    elif mutation == "false_median":
        block["median_difference"] = 1.0
    elif mutation == "false_direction_count":
        block["positive_tasks"] = 0
    elif mutation == "false_arm_mean":
        block["right_mean"] = 4.0
    _rewrite_and_rehash(output, payload)
    with pytest.raises(ValueError, match="analysis paired effect arithmetic"):
        verify.verify_bundle(output)


def test_empty_paired_effects_require_null_statistics_without_imputing_scores():
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    block.update(
        task_ids_included=[],
        missing_pair_tasks=payload["task_ids"],
        task_differences={},
        positive_tasks=0,
        negative_tasks=0,
        tied_tasks=0,
        left_mean=None,
        right_mean=None,
        mean_difference=None,
        median_difference=None,
        paired_dz=None,
        bootstrap_95pct_ci_mean_difference=None,
    )
    verify._validate_paired_effect_arithmetic(payload)
    block["mean_difference"] = 0.0
    with pytest.raises(ValueError, match="empty paired sample"):
        verify._validate_paired_effect_arithmetic(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "false_paired_dz",
        "missing_paired_dz",

        "outside_bootstrap_support",
        "reversed_bootstrap_interval",
        "missing_bootstrap_interval",
        "non_finite_bootstrap_endpoint",

    ],
)
def test_standalone_verifier_rejects_rehashed_effect_size_and_bootstrap_bounds(
    tmp_path, mutation
):
    """A rehashed result cannot invent standardized effects or impossible CIs."""
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    if mutation == "false_paired_dz":
        block["paired_dz"] = -0.7071067811865476
    elif mutation == "missing_paired_dz":
        block["paired_dz"] = None
    elif mutation == "outside_bootstrap_support":
        block["bootstrap_95pct_ci_mean_difference"] = [-0.1, 1.0]
    elif mutation == "reversed_bootstrap_interval":
        block["bootstrap_95pct_ci_mean_difference"] = [1.0, 0.0]
    elif mutation == "missing_bootstrap_interval":
        block["bootstrap_95pct_ci_mean_difference"] = None
    elif mutation == "non_finite_bootstrap_endpoint":
        # Exponent overflow is valid JSON syntax; the verifier must reject it.
        block["bootstrap_95pct_ci_mean_difference"] = [0.0, float("inf")]
    _rewrite_and_rehash(output, payload)
    with pytest.raises(ValueError, match="non-finite numeric|analysis paired effect arithmetic"):
        verify.verify_bundle(output)


@pytest.mark.parametrize(
    ("differences", "left_mean", "attainable"),
    [
        ([1.0, 0.0], 2.5, True),
        ([4.0, -2.0], 2.0, True),   # minimum feasible left sum
        ([4.0, -2.0], 3.0, True),   # maximum feasible left sum
        ([4.0, -2.0], 2.5, True),   # interior half-point allocation
        ([4.0, -2.0], 3.5, False),  # right mean still in [1, 5], but impossible
        ([4.0, -2.0], 1.5, False),  # below attainable left-score support
        ([1.0, 0.0], 2.1, False),   # impossible aggregate half-point lattice
        ([1.0], 2.25, False),       # single report cannot have quarter score
    ],
)
def test_paired_arm_means_are_jointly_feasible_for_task_effects(
    differences, left_mean, attainable
):
    """Only synthetic score pairs; no human rater observations are inferred."""
    if attainable:
        verify._validate_paired_arm_mean_feasibility(
            differences, left_mean, label="synthetic paired arm"
        )
    else:
        with pytest.raises(ValueError, match="paired arm means cannot arise"):
            verify._validate_paired_arm_mean_feasibility(
                differences, left_mean, label="synthetic paired arm"
            )


@pytest.mark.parametrize(
    ("differences", "left_mean", "coverage", "attainable"),
    [
        ([0.5], 3.0, [(1, 1)], False),  # two single ratings differ by an integer
        ([0.5], 3.0, [(1, 2)], True),
        ([0.5], 3.5, [(2, 1)], True),
        ([0.0], 3.5, [(1, 1)], False),
        ([0.0], 3.5, [(2, 2)], True),
        ([1.0, 0.0], 2.25, [(1, 1), (1, 1)], False),
        ([1.0, 0.0], 2.25, [(2, 2), (2, 2)], True),
        ([0.5, -0.5], 2.25, [(1, 2), (2, 1)], True),
        ([0.5, -0.5], 2.25, [(1, 2), (1, 2)], False),
    ],
)
def test_paired_arm_feasibility_respects_each_original_rater_count(
    differences, left_mean, coverage, attainable
):
    """Synthetic score lattices, not reconstructed or collected human ratings."""
    if attainable:
        verify._validate_paired_arm_mean_feasibility(
            differences, left_mean, label="synthetic pair", rating_counts=coverage
        )
    else:
        with pytest.raises(ValueError, match="paired arm means cannot arise"):
            verify._validate_paired_arm_mean_feasibility(
                differences, left_mean, label="synthetic pair", rating_counts=coverage
            )


def test_paired_effect_arithmetic_checks_published_task_rater_coverage():
    """A half-point-compatible arm mean can still violate singleton ratings."""
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    block["left_mean"] = 2.25
    block["right_mean"] = 2.75
    # Two double-rated reports can attain these means with effects [1, 0].
    verify._validate_paired_effect_arithmetic(payload)
    coverage = block["rater_coverage"]
    coverage["task_ids_by_rater_pair"]["1/1"] = ["task-a", "task-b"]
    coverage["task_ids_by_rater_pair"]["2/2"] = []
    coverage["count_by_rater_pair"]["1/1"] = 2
    coverage["count_by_rater_pair"]["2/2"] = 0
    with pytest.raises(ValueError, match="paired arm means cannot arise"):
        verify._validate_paired_effect_arithmetic(payload)


def test_rehashed_human_bundle_rejects_singleton_incompatible_arm_means(tmp_path):
    """Hash-consistent publications must honor recorded per-report denominators."""
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = _payload()
    # Keep shared-arm counts, raw histograms and blinded missingness coherent.
    # Only the published paired arm means are impossible for singleton reports.
    for _, _, contrast in core.CONTRASTS:
        for field in core.DIMS:
            coverage = payload["paired_contrasts"][contrast][field]["rater_coverage"]
            coverage["task_ids_by_rater_pair"]["1/1"] = ["task-a", "task-b"]
            coverage["task_ids_by_rater_pair"]["2/2"] = []
            coverage["count_by_rater_pair"]["1/1"] = 2
            coverage["count_by_rater_pair"]["2/2"] = 0
    for variant in core.VARIANTS:
        for field in core.DIMS:
            summary = payload["variant_summary"][variant][field]
            summary["n_raw_scores"] = 2
            summary["raw_score_distribution"]["3"] = 2
    for field in core.DIMS:
        agreement = payload["pre_unblinding_agreement"]["pairwise"][0]["dimensions"][field]
        agreement.update(
            n_double_rated=0,
            n_annotator_a_only_rated=8,
            n_annotator_b_only_rated=0,
            n_neither_rated=0,
            raw_exact_agreement=None,
            mean_absolute_difference=None,
            quadratic_weighted_cohen_kappa=None,
        )
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    block["left_mean"] = 2.25
    block["right_mean"] = 2.75
    assert block["right_mean"] - block["left_mean"] == block["mean_difference"]
    _rewrite_and_rehash(output, payload)
    with pytest.raises(ValueError, match="paired arm means cannot arise"):
        verify.verify_bundle(output)


def test_rehashed_paired_arm_means_fail_when_no_half_point_pairs_can_yield_them(
    tmp_path,
):
    """Consistent hashes and the correct paired difference cannot bless impossible arm means."""
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    block["left_mean"] = 2.1
    block["right_mean"] = 2.6
    assert block["right_mean"] - block["left_mean"] == pytest.approx(
        block["mean_difference"]
    )
    _rewrite_and_rehash(output, payload)
    with pytest.raises(ValueError, match="paired arm means cannot arise"):
        verify.verify_bundle(output)


@pytest.mark.parametrize("differences", [[1.0], [1.0, 1.0], [0.0, 0.0]])
def test_paired_arithmetic_accepts_null_effect_size_and_degenerate_bootstrap(differences):
    """Single-pair and zero-variance cases have no finite standardized effect."""
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    tasks = ["task-a", "task-b"][: len(differences)]
    effect = differences[0]
    block.update(
        n_pairs=len(differences),
        task_ids_included=tasks,
        task_differences=dict(zip(tasks, differences)),
        positive_tasks=sum(v > 0 for v in differences),
        negative_tasks=sum(v < 0 for v in differences),
        tied_tasks=sum(v == 0 for v in differences),
        left_mean=2.5,
        right_mean=2.5 + effect,
        mean_difference=effect,
        median_difference=effect,
        paired_dz=None,
        bootstrap_95pct_ci_mean_difference=[effect, effect],
    )
    verify._validate_paired_effect_arithmetic(payload)
    block["paired_dz"] = 0.0
    with pytest.raises(ValueError, match="paired_dz must be null"):
        verify._validate_paired_effect_arithmetic(payload)


def test_paired_arithmetic_rejects_non_degenerate_single_pair_interval():
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    block.update(
        n_pairs=1,
        task_ids_included=["task-a"],
        task_differences={"task-a": 1.0},
        positive_tasks=1,
        negative_tasks=0,
        tied_tasks=0,
        left_mean=2.5,
        right_mean=3.5,
        mean_difference=1.0,
        median_difference=1.0,
        paired_dz=None,
        bootstrap_95pct_ci_mean_difference=[0.0, 1.0],
    )
    with pytest.raises(ValueError, match="bootstrap CI violates paired task support"):
        verify._validate_paired_effect_arithmetic(payload)


@pytest.mark.parametrize(
    ("field", "invalid", "error"),
    [
        ("paired_dz", "0.7071067811865476", "paired_dz disagrees"),
        ("bootstrap_95pct_ci_mean_difference", [0.0], "bootstrap CI violates"),
    ],
)
def test_paired_arithmetic_rejects_unrenderable_invalid_values(field, invalid, error):
    """Exercise verifier arithmetic directly when the Markdown renderer cannot format bad types."""
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    block[field] = invalid
    with pytest.raises(ValueError, match=error):
        verify._validate_paired_effect_arithmetic(payload)

@pytest.mark.parametrize(
    "fabricated_bounds",
    [[0.0, 0.5], [0.5, 1.0], [0.25, 0.75]],
)
def test_rehashed_plausible_but_incorrect_bootstrap_interval_fails(
    tmp_path, fabricated_bounds
):
    """An in-support rehashed CI must match frozen seeded resampling exactly."""
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = _payload()
    block = payload["paired_contrasts"][core.CONTRASTS[0][2]][core.DIMS[0]]
    block["bootstrap_95pct_ci_mean_difference"] = fabricated_bounds
    _rewrite_and_rehash(output, payload)
    with pytest.raises(ValueError, match="bootstrap CI disagrees with seeded task-level replay"):
        verify.verify_bundle(output)


@pytest.mark.parametrize("seed_offset", [0, 1, 100, 201])
def test_seeded_replay_matches_frozen_producer_for_heterogeneous_effects(seed_offset):
    """Synthetic effects exercise actual percentile interpolation and seed mapping."""
    differences = (0.0, 0.5, 1.0, 2.0, 3.5)
    seed = core.SEED + seed_offset
    expected = core._bootstrap_mean_ci(differences, seed=seed)
    replayed = verify._replay_paired_bootstrap_ci(
        differences, seed=seed, draws=core.BOOTSTRAP_DRAWS
    )
    assert replayed == pytest.approx(expected, rel=0, abs=1e-12)


def test_seeded_replay_is_bound_to_canonical_task_identity_order():
    """Presentation order cannot silently change the accepted resampling order."""
    differences = {"task-z": 2.0, "task-a": 0.0, "task-m": 0.5}
    expected = core._bootstrap_mean_ci([0.0, 0.5, 2.0], seed=core.SEED)
    for displayed in (
        ["task-z", "task-a", "task-m"],
        ["task-m", "task-z", "task-a"],
    ):
        ordered = tuple(differences[task] for task in sorted(displayed))
        assert verify._replay_paired_bootstrap_ci(
            ordered, seed=core.SEED, draws=core.BOOTSTRAP_DRAWS
        ) == pytest.approx(expected, rel=0, abs=1e-12)


@pytest.mark.parametrize(
    "mutation",
    [
        "fractional_exact_count",
        "fractional_total_gap",
        "impossible_small_gap",
        "impossible_large_gap",
        "exact_beyond_rubric",
        "negative_absolute_gap",
        "missing_exact",
        "missing_gap",
        "undefined_kappa_with_disagreement",
        "kappa_above_one",
        "kappa_below_minus_one",
        "perfect_kappa_with_disagreement",
        "perfect_agreement_with_nonperfect_kappa",
    ],
)
def test_rehashed_publication_rejects_impossible_ordinal_agreement(tmp_path, mutation):
    """No participant ratings: only deliberately corrupted synthetic JSON."""
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = _payload()
    block = payload["pre_unblinding_agreement"]["pairwise"][0]["dimensions"][core.DIMS[0]]
    if mutation == "fractional_exact_count":
        block["raw_exact_agreement"] = 0.7       # 8 * .7 is not an integer
    elif mutation == "fractional_total_gap":
        block["mean_absolute_difference"] = 0.3  # 8 * .3 is not an integer
    elif mutation == "impossible_small_gap":
        block["mean_absolute_difference"] = 0.125  # 1 unit cannot cover 2 disagreements
    elif mutation == "impossible_large_gap":
        block["mean_absolute_difference"] = 1.125  # 9 units exceed 2 * 4
    elif mutation == "exact_beyond_rubric":
        block["raw_exact_agreement"] = 1.25
    elif mutation == "negative_absolute_gap":
        block["mean_absolute_difference"] = -0.25
    elif mutation == "missing_exact":
        block["raw_exact_agreement"] = None
    elif mutation == "missing_gap":
        block["mean_absolute_difference"] = None
    elif mutation == "undefined_kappa_with_disagreement":
        block["quadratic_weighted_cohen_kappa"] = None
    elif mutation == "kappa_above_one":
        block["quadratic_weighted_cohen_kappa"] = 1.2
    elif mutation == "kappa_below_minus_one":
        block["quadratic_weighted_cohen_kappa"] = -1.2
    elif mutation == "perfect_kappa_with_disagreement":
        block["quadratic_weighted_cohen_kappa"] = 1.0
    elif mutation == "perfect_agreement_with_nonperfect_kappa":
        block["raw_exact_agreement"] = 1.0
        block["mean_absolute_difference"] = 0.0
        block["quadratic_weighted_cohen_kappa"] = 0.8
    _rewrite_and_rehash(output, payload)
    with pytest.raises(ValueError, match="analysis blinded ordinal agreement arithmetic"):
        verify.verify_bundle(output)


def test_ordinal_agreement_allows_unrated_and_perfect_rater_cases():
    """Undefined reliability for zero overlap or a constant shared category is legitimate."""
    payload = _payload()
    block = payload["pre_unblinding_agreement"]["pairwise"][0]["dimensions"][core.DIMS[0]]
    block.update(
        n_double_rated=0, raw_exact_agreement=None,
        mean_absolute_difference=None, quadratic_weighted_cohen_kappa=None,
    )
    verify._validate_blinded_agreement_arithmetic(payload)
    block.update(
        n_double_rated=8, raw_exact_agreement=1.0,
        mean_absolute_difference=0.0, quadratic_weighted_cohen_kappa=None,
    )
    verify._validate_blinded_agreement_arithmetic(payload)
    block["quadratic_weighted_cohen_kappa"] = 1.0
    verify._validate_blinded_agreement_arithmetic(payload)


def test_ordinal_agreement_rejects_defined_reliability_with_zero_overlap():
    payload = _payload()
    block = payload["pre_unblinding_agreement"]["pairwise"][0]["dimensions"][core.DIMS[0]]
    block.update(
        n_double_rated=0, raw_exact_agreement=None,
        mean_absolute_difference=None, quadratic_weighted_cohen_kappa=0.0,
    )
    with pytest.raises(ValueError, match="no double-rated items require null"):
        verify._validate_blinded_agreement_arithmetic(payload)


@pytest.mark.parametrize(
    ("counts", "distribution", "mean", "median", "valid"),
    [
        # One-and-two rater mix: [1, 5, 5] can yield mean 3 or 4.
        ([1, 2], {"1": 1, "5": 2}, 3.0, 3.0, True),
        ([1, 2], {"1": 1, "5": 2}, 4.0, 4.0, True),
        # This sits *inside* the coarse possible range but is unattainable.
        ([1, 2], {"1": 1, "5": 2}, 3.5, 3.5, False),
        ([2, 2], {"2": 2, "4": 2}, 3.0, 3.0, True),
        ([2, 2], {"2": 2, "4": 2}, 2.5, 2.5, False),
        ([1, 1], {"1": 1, "2": 1}, 1.5, 1.5, True),
        # Feasible mean, but impossible median despite valid bounds and lattice.
        ([1, 1], {"1": 1, "5": 1}, 3.0, 2.5, False),
        ([1, 1], {"1": 1, "5": 1}, 3.0, 3.0, True),
        # Each marginal can occur, but not this mean/median *together*.
        ([1, 2], {"1": 2, "5": 1}, 2.0, 3.0, False),
        ([1, 2], {"1": 2, "5": 1}, 2.0, 2.0, True),
        ([1, 2], {"1": 2, "5": 1}, 3.0, 3.0, True),
        ([2, 2, 2], {"1": 3, "5": 3}, 3.0, 2.5, False),
        ([2, 2, 2], {"1": 3, "5": 3}, 3.0, 3.0, True),
        ([1, 2], {"1": 2, "2": 1}, 1.25, 1.25, True),
        ([1, 1], {"1": 1, "2": 1}, 1.5, 1.125, False),
        ([2], {"2": 1, "4": 1}, 3.0, 3.0, True),
        ([2], {"2": 1, "4": 1}, 3.0, 3.5, False),
        ([0, 0], {}, None, None, True),
        ([0, 0], {}, 3.0, None, False),
        ([1], {"3": 1}, True, 3.0, False),
        ([1], {"3": 1}, 3.0, float("inf"), False),
    ],
)
def test_report_summary_arithmetic_constrains_observed_rating_counts(
    counts, distribution, mean, median, valid
):
    """Synthetic ordinal histograms only; no original human ratings are inferred."""
    histogram = {str(rating): distribution.get(str(rating), 0) for rating in range(1, 6)}
    summary = {
        "raw_score_distribution": histogram,
        "mean_report_score": mean,
        "median_report_score": median,
    }
    if valid:
        verify._validate_report_score_summary(
            summary, counts, label="synthetic report arithmetic"
        )
    else:
        with pytest.raises(ValueError, match="synthetic report arithmetic"):
            verify._validate_report_score_summary(
                summary, counts, label="synthetic report arithmetic"
            )


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("mean_report_score", 3.5),
        ("median_report_score", 3.125),
        ("median_report_score", 2.5),
        ("mean_report_score", None),
    ],
)
def test_standalone_verifier_rejects_rehashed_variant_score_inconsistency(
    tmp_path, field, invalid
):
    """A rewritten JSON/Markdown/manifest must not override the raw histogram."""
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = _payload()
    payload["variant_summary"][core.VARIANTS[0]][core.DIMS[0]][field] = invalid
    _rewrite_and_rehash(output, payload)
    with pytest.raises(ValueError, match="analysis variant score arithmetic"):
        verify.verify_bundle(output)


def test_standalone_verifier_rejects_rehashed_unattainable_report_median(tmp_path):
    """A plausible median cannot be asserted by a rehashed publication."""
    output = tmp_path / "analysis"
    analyze_human_eval.write_bundle(_payload(), output)
    payload = _payload()
    summary = payload["variant_summary"][core.VARIANTS[0]][core.DIMS[0]]
    summary["raw_score_distribution"] = {
        "1": 2, "2": 0, "3": 0, "4": 0, "5": 2
    }
    summary["median_report_score"] = 2.5
    # Two double-rated reports have mean 3, whatever the pairing.
    # For exactly two reports, the median must also be 3.
    _rewrite_and_rehash(output, payload)
    with pytest.raises(ValueError, match="report median cannot arise jointly"):
        verify.verify_bundle(output)
