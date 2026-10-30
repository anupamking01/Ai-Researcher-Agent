"""Synthetic recovered-original-to-evaluator ZIP checks; no live research data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

import pytest

from scripts import audit_recovered_artifact_treatment_matrix as matrix
from scripts import compare_recovered_artifact_treatment_sources as concordance
from scripts import preflight_recovered_artifact_zip as preflight
from scripts import verify_human_eval_automated_run_lineage as lineage


def _pair(
    tmp_path, monkeypatch, *, mutate=None, drop=None,
    mutate_evaluator=None, drop_recovery_evaluator=None,
    omit_original_evaluator=None, extra_original_evaluator=None,
    extra_recovery_evaluator=None, bad_original_cache=None,
    bad_recovery_cache=None, tamper_original_measurements=None,
    tamper_recovery_measurements=None,
):
    csv_path = matrix.REPO_ROOT / lineage.SUPPORT_REL
    csv_bytes, _ = matrix._capture_evaluator(csv_path)
    traces, reports = matrix._expected_paths(csv_bytes, csv_path=csv_path)
    frozen_rows = lineage._matrix(
        lineage._read_study_csv(csv_bytes, path=csv_path),
        label="synthetic test's frozen CSV reference",
        expected_cells=matrix.EXPECTED_CELLS, run_identity=True,
    )
    frozen_run_ids = {
        cell: row["run_id"] for cell, row in frozen_rows.items()
    }

    def synthetic_cache(variant, task, overrides=None):
        # Fake archive fixtures copy numbers from the pinned CSV. They are
        # never original evaluator outputs or new experimental measurements.
        row = frozen_rows[(variant, task)]
        record = {
            "schema_version": 1,
            "study_id": "budget-main-v1",
            "variant_id": variant,
            "task_id": task,
            "run_id": frozen_run_ids[(variant, task)],
            "synthetic_fixture_only": True,
            **{field: int(row[field]) for field in
               concordance.PUBLISHED_EVALUATOR_COUNT_FIELDS},
            **{field: float(row[field]) for field in
               concordance.PUBLISHED_EVALUATOR_DECIMAL_FIELDS},
        }
        if overrides:
            record.update(overrides)
        return json.dumps(record, sort_keys=True).encode("utf-8")

    files = {
        **{name: b'{"synthetic_fixture_only":true}' for name in sorted(traces)},
        **{name: b"# Synthetic markdown; not a research result\n" for name in sorted(reports)},
    }
    # Reproduce only the frozen historical recovery *shape*, not real scores:
    # original archive contains 37 cached JSONs; recovery adds three.
    evaluator_path = lambda variant, task: f"posthoc_evaluations/{variant}/{task}.json"
    evaluator_cells = [
        (variant, task) for variant in lineage.VARIANTS for task in lineage.TASKS
    ]
    for variant, task in evaluator_cells:
        if (variant, task) not in concordance.RECOVERY_ONLY_EVALUATOR_CELLS:
            files[evaluator_path(variant, task)] = synthetic_cache(variant, task)
    if bad_original_cache:
        variant, task, payload = bad_original_cache
        files[evaluator_path(variant, task)] = payload
    if tamper_original_measurements:
        variant, task, fields = tamper_original_measurements
        files[evaluator_path(variant, task)] = synthetic_cache(variant, task, fields)
    if omit_original_evaluator:
        files.pop(evaluator_path(*omit_original_evaluator))
    if extra_original_evaluator:
        files[extra_original_evaluator] = b'{"synthetic_only":true}'
    original_path = tmp_path / "original.zip"
    recovered_path = tmp_path / "evaluator-recovery.zip"
    with zipfile.ZipFile(original_path, "w", compression=zipfile.ZIP_STORED) as out:
        for name, data in sorted(files.items()):
            out.writestr(name, data)
    recovered = dict(files)
    for variant, task in sorted(concordance.RECOVERY_ONLY_EVALUATOR_CELLS):
        recovered[evaluator_path(variant, task)] = synthetic_cache(variant, task)
    if bad_recovery_cache:
        variant, task, payload = bad_recovery_cache
        recovered[evaluator_path(variant, task)] = payload
    if tamper_recovery_measurements:
        variant, task, fields = tamper_recovery_measurements
        recovered[evaluator_path(variant, task)] = synthetic_cache(variant, task, fields)
    if mutate_evaluator:
        recovered[evaluator_path(*mutate_evaluator)] += b"\nsynthetic cache modification"
    if drop_recovery_evaluator:
        recovered.pop(evaluator_path(*drop_recovery_evaluator))
    if extra_recovery_evaluator:
        recovered[extra_recovery_evaluator] = b'{"synthetic_only":true}'
    if drop:
        del recovered[drop]
    if mutate:
        recovered[mutate] += b"\nSynthetic modification to research source\n"
    recovered = {"outputs/" + name: data for name, data in recovered.items()}
    recovered["recovery_note.txt"] = b"synthetic evaluator-only bookkeeping"
    with zipfile.ZipFile(recovered_path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name, data in sorted(recovered.items()):
            out.writestr(name, data)
    anchors = {}
    for role, path in (
        ("original_treatment", original_path),
        ("evaluator_recovery", recovered_path),
    ):
        anchors[role] = {
            **preflight.GITHUB_JOB_LOG_ARCHIVES[role],
            "zip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }
    monkeypatch.setattr(preflight, "GITHUB_JOB_LOG_ARCHIVES", anchors)
    return original_path, recovered_path, traces, reports


def test_matching_40_sources_survive_repackaging_and_extra_recovery_metadata(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    receipt = concordance.compare_recovered_treatment_sources(original, recovered)
    assert receipt["trace_sources_unchanged"] == 40
    assert receipt["report_sources_unchanged"] == 40
    assert receipt["preserved_evaluator_cache_members_byte_identical"] == 37
    assert receipt["recovery_only_evaluator_cache_members_present"] == 3
    assert receipt["evaluator_cache_payload_semantics_verified"] is False
    assert receipt["original_evaluator_cache_json_identities_checked"] == 37
    assert receipt["recovery_evaluator_cache_json_identities_checked"] == 40
    assert receipt["original_evaluator_cache_published_measurements_matched"] == 37
    assert receipt["recovery_evaluator_cache_published_measurements_matched"] == 40
    assert receipt["original_zip_sha256_observed_now"] != receipt[
        "recovery_zip_sha256_observed_now"
    ]
    assert receipt["status"].endswith("_not_authenticated")
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_evaluation_ready"] is False
    assert receipt["independent_archive_custody_verified"] is False
    assert set(tmp_path.iterdir()) == {original, recovered}


@pytest.mark.parametrize("source", ("trace", "report"))
def test_one_changed_original_source_blocks_evaluator_only_lineage(
    tmp_path, monkeypatch, source
):
    csv_path = matrix.REPO_ROOT / lineage.SUPPORT_REL
    raw, _ = matrix._capture_evaluator(csv_path)
    traces, reports = matrix._expected_paths(raw, csv_path=csv_path)
    changed = sorted(traces if source == "trace" else reports)[0]
    original, recovered, _, _ = _pair(tmp_path, monkeypatch, mutate=changed)
    with pytest.raises(
        concordance.RecoveryConcordanceError, match=f"{source}"
    ):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_recovery_zip_missing_source_fails_before_concordance(tmp_path, monkeypatch):
    raw, _ = matrix._capture_evaluator(matrix.REPO_ROOT / lineage.SUPPORT_REL)
    _, reports = matrix._expected_paths(
        raw, csv_path=matrix.REPO_ROOT / lineage.SUPPORT_REL
    )
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, drop=sorted(reports)[0]
    )
    with pytest.raises(matrix.RecoveryMatrixError, match="complete published"):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_role_pin_cannot_be_bypassed_by_a_plausible_source_matrix(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    with zipfile.ZipFile(recovered, "a") as out:
        out.writestr("extra.txt", b"synthetic alteration after pinning")
    with pytest.raises(preflight.RecoveredArchiveError, match="historical GitHub"):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_same_file_cannot_claim_independent_original_and_recovery_roles(
    tmp_path, monkeypatch
):
    original, _, _, _ = _pair(tmp_path, monkeypatch)
    with pytest.raises(concordance.RecoveryConcordanceError, match="distinct"):
        concordance.compare_recovered_treatment_sources(original, original)


def test_independent_pin_argument_is_checked_not_inferred(tmp_path, monkeypatch):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    with pytest.raises(preflight.RecoveredArchiveError, match="independent pin"):
        concordance.compare_recovered_treatment_sources(
            original, recovered, original_expected_archive_sha256="0" * 64,
        )


def test_cli_emits_explicitly_non_authenticating_comparison_receipt(
    tmp_path, monkeypatch, capsys
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", [
        "compare_recovered_artifact_treatment_sources",
        "--original-zip", str(original),
        "--recovery-zip", str(recovered),
    ])
    assert concordance.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source_cells_compared"] == 40
    assert receipt["historical_evidence_authenticated"] is False
    assert receipt["human_ratings_generated"] is False


def test_original_zip_same_byte_replacement_between_audits_is_rejected(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    actual_audit = matrix.audit_recovered_treatment_matrix

    def replace_original_after_first_audit(*args, **kwargs):
        result = actual_audit(*args, **kwargs)
        if kwargs["artifact_role"] == "original_treatment":
            replacement = tmp_path / "fresh-original.zip"
            replacement.write_bytes(original.read_bytes())
            os.replace(replacement, original)
        return result

    monkeypatch.setattr(matrix, "audit_recovered_treatment_matrix", replace_original_after_first_audit)
    with pytest.raises(concordance.RecoveryConcordanceError, match="changed during comparison"):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_recovery_zip_same_byte_replacement_after_its_audit_is_rejected(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    actual_audit = matrix.audit_recovered_treatment_matrix

    def replace_recovery_after_second_audit(*args, **kwargs):
        result = actual_audit(*args, **kwargs)
        if kwargs["artifact_role"] == "evaluator_recovery":
            replacement = tmp_path / "fresh-recovery.zip"
            replacement.write_bytes(recovered.read_bytes())
            os.replace(replacement, recovered)
        return result

    monkeypatch.setattr(matrix, "audit_recovered_treatment_matrix", replace_recovery_after_second_audit)
    with pytest.raises(concordance.RecoveryConcordanceError, match="changed during comparison"):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_evaluator_same_byte_replacement_between_archive_audits_is_rejected(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    root = tmp_path / "checkout"
    frozen_csv = root / lineage.SUPPORT_REL
    frozen_csv.parent.mkdir(parents=True)
    frozen_csv.write_bytes((matrix.REPO_ROOT / lineage.SUPPORT_REL).read_bytes())
    actual_audit = matrix.audit_recovered_treatment_matrix

    def replace_evaluator_after_first_audit(*args, **kwargs):
        result = actual_audit(*args, **kwargs)
        if kwargs["artifact_role"] == "original_treatment":
            replacement = frozen_csv.with_suffix(".replacement")
            replacement.write_bytes(frozen_csv.read_bytes())
            os.replace(replacement, frozen_csv)
        return result

    monkeypatch.setattr(matrix, "audit_recovered_treatment_matrix", replace_evaluator_after_first_audit)
    with pytest.raises(concordance.RecoveryConcordanceError, match="changed during comparison"):
        concordance.compare_recovered_treatment_sources(
            original, recovered, repo_root=root,
        )


def test_archive_symlink_is_not_accepted_as_comparison_input(tmp_path, monkeypatch):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    alias = tmp_path / "aliased-original.zip"
    try:
        alias.symlink_to(original)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(concordance.RecoveryConcordanceError, match="archive source"):
        concordance.compare_recovered_treatment_sources(alias, recovered)


def test_recovery_preserves_all_37_existing_evaluator_cache_bytes(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, mutate_evaluator=("D3", "main-01"),
    )
    with pytest.raises(
        concordance.RecoveryConcordanceError,
        match="preserved evaluator cache bytes changed",
    ):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_recovery_requires_all_three_missing_evaluator_cache_members(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, drop_recovery_evaluator=("P6V", "main-08"),
    )
    with pytest.raises(
        concordance.RecoveryConcordanceError, match="complete 40-cell state"
    ):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_original_evaluator_cannot_claim_one_of_the_three_recovery_only_cells(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        extra_original_evaluator="posthoc_evaluations/P6V/main-02.json",
    )
    with pytest.raises(
        concordance.RecoveryConcordanceError, match="historical 37-cell"
    ):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_missing_preserved_original_evaluator_cell_fails(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, omit_original_evaluator=("D3", "main-01"),
    )
    with pytest.raises(
        concordance.RecoveryConcordanceError, match="historical 37-cell"
    ):
        concordance.compare_recovered_treatment_sources(original, recovered)


@pytest.mark.parametrize("unexpected_path", [
    "posthoc_evaluations/P6V/main-99.json",
    "unselected/posthoc_evaluations/D3/main-01.json",
])
def test_extra_or_mixed_layout_evaluator_cache_is_not_silently_ignored(
    tmp_path, monkeypatch, unexpected_path,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, extra_recovery_evaluator=unexpected_path,
    )
    with pytest.raises(
        concordance.RecoveryConcordanceError, match="unselected or mixed-layout"
    ):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_recovered_evaluator_wrong_execution_id_rejected_even_with_correct_zip_pin(
    tmp_path, monkeypatch,
):
    payload = json.dumps({
        "schema_version": 1, "study_id": "budget-main-v1",
        "variant_id": "P6V", "task_id": "main-02",
        "run_id": "fabricated-execution-id",
    }).encode("utf-8")
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, bad_recovery_cache=("P6V", "main-02", payload),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match="run_id differs"):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_preserved_evaluator_wrong_identity_blocked_even_when_byte_identical(
    tmp_path, monkeypatch,
):
    payload = json.dumps({
        "schema_version": 1, "study_id": "budget-main-v1",
        "variant_id": "P6V", "task_id": "main-01", "run_id": "incorrect",
    }).encode("utf-8")
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, bad_original_cache=("D3", "main-01", payload),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match="variant_id differs"):
        concordance.compare_recovered_treatment_sources(original, recovered)


@pytest.mark.parametrize(("payload", "expected_error"), [
    (b'{"schema_version":1,"study_id":"budget-main-v1","study_id":"fake"}',
     "duplicate key"),
    (b'{"schema_version":1,"study_id":"budget-main-v1","x":NaN}',
     "nonfinite numeric token"),
    (b'{"schema_version":1,', "invalid evaluator cache JSON"),
    (b'{"study_id":"budget-main-v1"}', "schema_version"),
    (b'["not","a","cache"]', "must be an object"),
])
def test_recovery_only_evaluator_malformed_or_ambiguous_json_rejected(
    tmp_path, monkeypatch, payload, expected_error,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, bad_recovery_cache=("P6V", "main-02", payload),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=expected_error):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_evaluator_json_member_size_bound_is_checked(tmp_path, monkeypatch):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    monkeypatch.setattr(concordance, "MAX_EVALUATOR_CACHE_JSON_BYTES", 10)
    with pytest.raises(concordance.RecoveryConcordanceError, match="size outside"):
        concordance.compare_recovered_treatment_sources(original, recovered)


@pytest.mark.parametrize(("field", "replacement"), [
    ("claims_checked", 0),
    ("supported", 99),
    ("partially_supported", -1),
    ("unsupported", True),
    ("contradicted", 1),
    ("strict_support_rate", 0.123456789),
    ("total_tokens", 0),
    ("estimated_cost_usd", -1.0),
    ("estimated_cost_usd", "0.01"),
])
def test_recovery_only_cache_numeric_disagreement_with_frozen_csv_is_rejected(
    tmp_path, monkeypatch, field, replacement,
):
    # P6V/main-02 is one of the three *historically missing* cache cells.
    # Its synthetic fixture is deliberately altered after its other metadata
    # is copied from the published CSV; no real evaluator scores are created.
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        tamper_recovery_measurements=("P6V", "main-02", {field: replacement}),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=field):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_preserved_original_and_recovery_identical_wrong_numeric_cache_blocked(
    tmp_path, monkeypatch,
):
    # Byte continuity alone must not bless a preexisting incorrect measurement.
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        tamper_original_measurements=("D3", "main-01", {"supported": 99}),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match="supported"):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_recovery_only_cache_matching_published_counts_but_wrong_rate_rejected(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        tamper_recovery_measurements=(
            "P6V", "main-08", {"strict_support_rate": 1.0e-10},
        ),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match="strict_support_rate"):
        concordance.compare_recovered_treatment_sources(original, recovered)
