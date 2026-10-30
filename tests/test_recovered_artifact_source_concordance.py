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
from scripts import verify_frozen_main_study_tasks as frozen_tasks


def _pair(
    tmp_path, monkeypatch, *, mutate=None, drop=None,
    mutate_evaluator=None, drop_recovery_evaluator=None,
    omit_original_evaluator=None, extra_original_evaluator=None,
    extra_recovery_evaluator=None, bad_original_cache=None,
    bad_recovery_cache=None, tamper_original_measurements=None,
    tamper_trace=None, invalid_trace_bytes=None,
    tamper_recovery_measurements=None, schema2_recovery_cache=None,
    invalid_report_bytes=None,
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
    treatment_csv = matrix.REPO_ROOT / lineage.MAIN_REL
    published_treatments = lineage._matrix(
        lineage._read_study_csv(treatment_csv.read_bytes(), path=treatment_csv),
        label="synthetic test's frozen treatment CSV reference",
        expected_cells=matrix.EXPECTED_CELLS, run_identity=False,
    )

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

    task_manifest = json.loads(
        (matrix.REPO_ROOT / frozen_tasks.TASK_MANIFEST_REL).read_text(encoding="utf-8")
    )
    original_questions = {task["id"]: task["question"] for task in task_manifest["tasks"]}
    by_run_id = {run_id: cell for cell, run_id in frozen_run_ids.items()}

    def synthetic_trace(name):
        run_id = Path(name).stem
        variant, task = by_run_id[run_id]
        mode, budget, verification = concordance.FROZEN_TREATMENT_ASSIGNMENTS[variant]
        published = published_treatments[(variant, task)]
        success, failure = int(published["successful_sources"]), int(published["failed_sources"])
        record = {
            "schema_version": 2,
            "synthetic_fixture_only": True,
            "experiment": {
                "variant_id": variant, "task_id": task,
                "task_set_id": "main-budget-v1-2026-09-11",
                "planning_mode": mode, "source_budget": budget,
                "verification_mode": verification,
            },
            "trace": {
                "variant_id": variant, "task_id": task,
                "task_set_id": "main-budget-v1-2026-09-11",
                "run_id": run_id, "question": original_questions[task],
                "completed": True, "usage_accounting_status": "provider_usage_complete",
                "source_budget": budget, "source_count": success + failure,
                "successful_source_count": success, "failed_source_count": failure,
                "search_call_count": int(published["search_calls"]),
                "model_call_count": int(published["model_calls"]),
                "total_tokens": int(published["total_tokens"]),
                "report_words": int(published["report_words"]),
                "report_path": f"./outputs/{run_id}/research_report.pdf",
            },
        }
        # Strictly synthetic query/result URL ledgers. The counts are copied
        # from the frozen CSV only to exercise its already-published shape;
        # these URLs do not represent actual retrieved web sources.
        scheduled_urls = [
            f"https://fixture.invalid/{variant}/{task}/source-{index:02d}"
            for index in range(success + failure)
        ]
        search_queries = (
            [original_questions[task]] if variant in ("D3", "D6") else
            [f"synthetic planner query {index + 1} for {task}" for index in range(4)]
        )
        base, remainder = divmod(budget, len(search_queries))
        records = []
        offset = 0
        for index, query in enumerate(search_queries):
            allocation = base + (1 if index < remainder else 0)
            selected = scheduled_urls[offset:offset + allocation]
            records.append({
                "query": query,
                "candidate_urls": list(selected),
                "scheduled_urls": list(selected),
            })
            offset += len(selected)
        assert offset == len(scheduled_urls)
        assert len(records) == int(published["search_calls"])
        record["trace"].update({
            "query_count": len(search_queries),
            "search_queries": search_queries,
            "search_records": records,
            "scheduled_urls": scheduled_urls,
            "successful_urls": scheduled_urls[:success],
            "failed_urls": scheduled_urls[success:],
        })
        return json.dumps(record, sort_keys=True).encode("utf-8")

    def synthetic_report(name):
        # Match only the *recorded* frozen word-count shape. No genuine report,
        # experimental output, or claimed human observation is reconstructed.
        run_id = Path(name).parent.name
        cell = by_run_id[run_id]
        words = int(published_treatments[cell]["report_words"])
        return ("synthetic " * words).encode("utf-8")

    files = {
        **{name: synthetic_trace(name) for name in sorted(traces)},
        **{name: synthetic_report(name) for name in sorted(reports)},
    }
    if invalid_report_bytes:
        variant, task, replacement = invalid_report_bytes
        files[f"{frozen_run_ids[(variant, task)]}/research_report.md"] = replacement
    if tamper_trace or invalid_trace_bytes:
        variant, task = (tamper_trace or invalid_trace_bytes)[:2]
        trace_path = f"experiment_traces/{variant}/{frozen_run_ids[(variant, task)]}.json"
        if tamper_trace:
            _variant, _task, section, field, replacement = tamper_trace
            record = json.loads(files[trace_path])
            target = record if section == "top" else record[section]
            if type(field) is tuple:
                for key, value in zip(field, replacement, strict=True):
                    target[key] = value
            else:
                target[field] = (
                    replacement(target[field]) if callable(replacement) else replacement
                )
            files[trace_path] = json.dumps(record, sort_keys=True).encode("utf-8")
        else:
            files[trace_path] = invalid_trace_bytes[2]
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
    if schema2_recovery_cache:
        variant, task, mutation = schema2_recovery_cache
        cache_path = evaluator_path(variant, task)
        record = json.loads(recovered[cache_path])
        report_bytes = recovered[f"{frozen_run_ids[(variant, task)]}/research_report.md"]
        task_manifest = json.loads(
            (matrix.REPO_ROOT / frozen_tasks.TASK_MANIFEST_REL).read_text(encoding="utf-8")
        )
        question_bytes = next(
            cell["question"] for cell in task_manifest["tasks"] if cell["id"] == task
        ).encode("utf-8")
        empty_sha = hashlib.sha256(b"").hexdigest()
        fingerprints = {
            "algorithm": "sha256",
            "encoding": "utf-8",
            "question": {
                "byte_size": len(question_bytes),
                "sha256": hashlib.sha256(question_bytes).hexdigest(),
            },
            **{
                field: {"byte_size": 0, "sha256": empty_sha}
                for field in ("evidence", "prompt")
            },
            "report": {
                "byte_size": len(report_bytes),
                "sha256": hashlib.sha256(report_bytes).hexdigest(),
            },
        }
        record["schema_version"] = 2
        record["input_fingerprints"] = fingerprints
        if mutation == "wrong_digest":
            fingerprints["report"]["sha256"] = empty_sha
        elif mutation == "wrong_question_digest":
            fingerprints["question"]["sha256"] = empty_sha
        elif mutation == "wrong_question_size":
            fingerprints["question"]["byte_size"] += 1
        elif mutation == "wrong_size":
            fingerprints["report"]["byte_size"] += 1
        elif mutation == "missing_report":
            del fingerprints["report"]
        elif mutation == "bool_size":
            fingerprints["report"]["byte_size"] = True
        elif mutation == "missing_question":
            del fingerprints["question"]
        elif mutation == "wrong_algorithm":
            fingerprints["algorithm"] = "md5"
        elif mutation == "v1_claims_fingerprints":
            record["schema_version"] = 1
        recovered[cache_path] = json.dumps(record, sort_keys=True).encode("utf-8")
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
    assert receipt["original_completed_treatment_trace_identities_checked"] == 40
    assert receipt["recovery_completed_treatment_trace_identities_checked"] == 40
    assert receipt["original_treatment_published_resource_ledgers_matched"] == 40
    assert receipt["recovery_treatment_published_resource_ledgers_matched"] == 40
    assert receipt["published_treatment_csv_sha256"] == concordance.PUBLISHED_TREATMENT_CSV_SHA256
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
    (root / lineage.MAIN_REL).write_bytes(
        (matrix.REPO_ROOT / lineage.MAIN_REL).read_bytes()
    )
    task_source = root / frozen_tasks.TASK_MANIFEST_REL
    task_source.parent.mkdir(parents=True)
    task_source.write_bytes((matrix.REPO_ROOT / frozen_tasks.TASK_MANIFEST_REL).read_bytes())
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


def test_schema_v2_recovery_cache_report_fingerprint_matches_verified_archive(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        schema2_recovery_cache=("P6V", "main-02", "valid"),
    )
    receipt = concordance.compare_recovered_treatment_sources(original, recovered)
    assert receipt["original_schema_v2_evaluator_report_input_fingerprints_matched"] == 0
    assert receipt["recovery_schema_v2_evaluator_report_input_fingerprints_matched"] == 1
    assert receipt["recovery_schema_v2_evaluator_question_input_fingerprints_matched"] == 1
    assert receipt["original_treatment_task_manifest_sha256"] == frozen_tasks.ORIGINAL_TASK_MANIFEST_SHA256
    assert receipt["schema_v1_evaluator_report_input_binding_unavailable"] is True
    assert receipt["schema_v1_evaluator_question_input_binding_unavailable"] is True
    assert receipt["historical_evidence_authenticated"] is False


@pytest.mark.parametrize(("mutation", "error"), [
    ("wrong_digest", "report fingerprint does not match"),
    ("wrong_size", "report fingerprint does not match"),
    ("wrong_question_digest", "question fingerprint does not match"),
    ("wrong_question_size", "question fingerprint does not match"),
    ("missing_report", "invalid schema-version-2"),
    ("bool_size", "invalid schema-version-2"),
    ("missing_question", "invalid schema-version-2"),
    ("wrong_algorithm", "invalid schema-version-2"),
    ("v1_claims_fingerprints", "schema-version-1 evaluator cache"),
])
def test_schema_v2_recovery_cache_cannot_misbind_report_or_fake_fingerprint_shape(
    tmp_path, monkeypatch, mutation, error,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        schema2_recovery_cache=("P6V", "main-02", mutation),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=error):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_modified_original_task_manifest_blocks_question_lineage_before_archive_audit(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch, schema2_recovery_cache=("P6V", "main-02", "valid")
    )
    root = tmp_path / "modified-task-source"
    evaluator = root / lineage.SUPPORT_REL
    evaluator.parent.mkdir(parents=True)
    evaluator.write_bytes((matrix.REPO_ROOT / lineage.SUPPORT_REL).read_bytes())
    (root / lineage.MAIN_REL).write_bytes(
        (matrix.REPO_ROOT / lineage.MAIN_REL).read_bytes()
    )
    task_path = root / frozen_tasks.TASK_MANIFEST_REL
    task_path.parent.mkdir(parents=True)
    manifest = json.loads(
        (matrix.REPO_ROOT / frozen_tasks.TASK_MANIFEST_REL).read_text(encoding="utf-8")
    )
    manifest["tasks"][1]["question"] = "Synthetic altered main-02 question?"
    task_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        concordance.RecoveryConcordanceError, match="original treatment-run source"
    ):
        concordance.compare_recovered_treatment_sources(
            original, recovered, repo_root=root
        )


def test_original_task_manifest_same_byte_replacement_during_audit_is_rejected(
    tmp_path, monkeypatch
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    root = tmp_path / "task-source-checkout"
    evaluator = root / lineage.SUPPORT_REL
    evaluator.parent.mkdir(parents=True)
    evaluator.write_bytes((matrix.REPO_ROOT / lineage.SUPPORT_REL).read_bytes())
    (root / lineage.MAIN_REL).write_bytes(
        (matrix.REPO_ROOT / lineage.MAIN_REL).read_bytes()
    )
    task_path = root / frozen_tasks.TASK_MANIFEST_REL
    task_path.parent.mkdir(parents=True)
    task_path.write_bytes((matrix.REPO_ROOT / frozen_tasks.TASK_MANIFEST_REL).read_bytes())
    actual_audit = matrix.audit_recovered_treatment_matrix

    def replace_task_source_after_first_audit(*args, **kwargs):
        result = actual_audit(*args, **kwargs)
        if kwargs["artifact_role"] == "original_treatment":
            replacement = task_path.with_suffix(".replacement")
            replacement.write_bytes(task_path.read_bytes())
            os.replace(replacement, task_path)
        return result

    monkeypatch.setattr(
        matrix, "audit_recovered_treatment_matrix", replace_task_source_after_first_audit
    )
    with pytest.raises(
        concordance.RecoveryConcordanceError, match="changed during comparison"
    ):
        concordance.compare_recovered_treatment_sources(
            original, recovered, repo_root=root
        )


@pytest.mark.parametrize(("field", "replacement", "error"), [
    ("search_call_count", 0, "search_call_count differs"),
    ("model_call_count", 0, "model_call_count differs"),
    ("total_tokens", 0, "total_tokens differs"),
    ("report_words", 0, "report_words differs"),
    (("successful_source_count", "failed_source_count"), (2, 1),
     "successful_source_count differs"),
])
def test_byte_identical_archived_trace_cannot_disagree_with_published_resource_ledger(
    tmp_path, monkeypatch, field, replacement, error,
):
    # Frozen D3/main-07 reports one successful and two failed sources.
    # Paired mutation keeps source_count and completion ledger consistent.
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        tamper_trace=("D3", "main-07", "trace", field, replacement),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=error):
        concordance.compare_recovered_treatment_sources(original, recovered)


def _isolated_pinned_research_checkout(root):
    for relative in (
        lineage.MAIN_REL, lineage.SUPPORT_REL, frozen_tasks.TASK_MANIFEST_REL,
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((matrix.REPO_ROOT / relative).read_bytes())


def test_modified_frozen_treatment_csv_blocks_archive_audit(tmp_path, monkeypatch):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    root = tmp_path / "changed-treatment-source"
    _isolated_pinned_research_checkout(root)
    source = root / lineage.MAIN_REL
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(concordance.RecoveryConcordanceError,
                       match="published treatment CSV differs"):
        concordance.compare_recovered_treatment_sources(
            original, recovered, repo_root=root,
        )


def test_same_byte_replacement_of_treatment_csv_during_audit_is_rejected(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    root = tmp_path / "replacement-treatment-source"
    _isolated_pinned_research_checkout(root)
    source = root / lineage.MAIN_REL
    audit = matrix.audit_recovered_treatment_matrix

    def swap_after_original(*args, **kwargs):
        result = audit(*args, **kwargs)
        if kwargs["artifact_role"] == "original_treatment":
            replacement = source.with_suffix(".replacement")
            replacement.write_bytes(source.read_bytes())
            os.replace(replacement, source)
        return result

    monkeypatch.setattr(matrix, "audit_recovered_treatment_matrix", swap_after_original)
    with pytest.raises(concordance.RecoveryConcordanceError,
                       match="changed during comparison"):
        concordance.compare_recovered_treatment_sources(
            original, recovered, repo_root=root,
        )


@pytest.mark.parametrize(("section", "field", "replacement", "error"), [
    ("trace", "run_id", "synthetic-false-run", "run_id disagrees"),
    ("trace", "question", "Synthetic altered question", "question disagrees"),
    ("trace", "completed", False, "not explicitly completed"),
    ("trace", "task_set_id", "substituted-task-list", "trace.task_set_id"),
    ("experiment", "variant_id", "P6", "experiment.variant_id"),
    ("experiment", "planning_mode", "planner", "experiment.planning_mode"),
    ("experiment", "verification_mode", "verify", "experiment.verification_mode"),
    ("experiment", "source_budget", 6, "experiment.source_budget"),
    ("trace", "source_count", 7, "source ledger"),
    ("trace", "successful_source_count", True, "successful_source_count"),
    ("top", "schema_version", 1, "schema/metadata"),
])
def test_historical_trace_identity_completion_assignment_are_not_inferred_from_zip_paths(
    tmp_path, monkeypatch, section, field, replacement, error,
):
    # Apply the same synthetic corruption to BOTH role-pinned ZIPs: byte
    # concordance succeeds, but the newly required trace semantics must not.
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        tamper_trace=("D3", "main-01", section, field, replacement),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=error):
        concordance.compare_recovered_treatment_sources(original, recovered)


@pytest.mark.parametrize(("raw", "error"), [
    (b'{"schema_version":2,"experiment":{},"trace":{},"trace":{}}', "duplicate key"),
    (b'{"schema_version":2,"experiment":{},"trace":{"value":NaN}}', "nonfinite"),
    (b'{"schema_version":2,"experiment":{}', "invalid historical treatment trace JSON"),
    (b'["synthetic-invalid-trace"]', "schema/metadata"),
])
def test_historical_trace_malformed_or_ambiguous_json_rejected_even_if_archives_agree(
    tmp_path, monkeypatch, raw, error,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        invalid_trace_bytes=("D3", "main-01", raw),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=error):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_historical_trace_semantic_read_has_independent_member_size_bound(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    monkeypatch.setattr(concordance, "MAX_TREATMENT_TRACE_JSON_BYTES", 10)
    with pytest.raises(concordance.RecoveryConcordanceError, match="semantic size bound"):
        concordance.compare_recovered_treatment_sources(original, recovered)


@pytest.mark.parametrize(("report_path", "message"), [
    ("", "report_path is missing or invalid"),
    ("../main-01/research_report.pdf", "report_path does not identify its run"),
    ("./outputs/different-run/research_report.pdf", "report_path does not identify its run"),
    ("./outputs/%2e%2e/research_report.pdf", "report_path does not identify its run"),
    ("./outputs/other\\run/research_report.pdf", "report_path does not identify its run"),
])
def test_historical_trace_report_pointer_must_select_its_own_frozen_run(
    tmp_path, monkeypatch, report_path, message,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        tamper_trace=("D3", "main-01", "trace", "report_path", report_path),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=message):
        concordance.compare_recovered_treatment_sources(original, recovered)


@pytest.mark.parametrize(("replacement", "message"), [
    (b"synthetic mismatch with frozen report count\n", "Markdown report word count"),
    (b"\xff\xfeinvalid utf8", "Markdown report must be UTF-8"),
    (b"   \n\t", "Markdown report word count"),
])
def test_identical_archives_cannot_hide_report_content_disagreement_with_trace(
    tmp_path, monkeypatch, replacement, message,
):
    # Change both archives: source-concordance and the published trace count
    # still match, but the actual archived report no longer corresponds.
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        invalid_report_bytes=("D3", "main-01", replacement),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=message):
        concordance.compare_recovered_treatment_sources(original, recovered)


def test_historical_report_semantic_reread_has_independent_size_guard(
    tmp_path, monkeypatch,
):
    original, recovered, _, _ = _pair(tmp_path, monkeypatch)
    monkeypatch.setattr(concordance, "MAX_TREATMENT_REPORT_BYTES", 1)
    with pytest.raises(concordance.RecoveryConcordanceError, match="semantic size bound"):
        concordance.compare_recovered_treatment_sources(original, recovered)


@pytest.mark.parametrize(("field", "replacement", "error"), [
    ("query_count", 0, "query_count"),
    ("search_queries", ["substituted query"], "query order"),
    ("search_records", [], "search_records/search_call_count"),
    ("scheduled_urls", ["https://fixture.invalid/fake"], "scheduled_urls"),
    ("successful_urls", [], "successful_urls"),
])
def test_historical_source_query_ledgers_are_not_inferred_from_aggregate_counts(
    tmp_path, monkeypatch, field, replacement, error,
):
    # Both synthetic ZIPs carry the SAME tampered trace: byte concordance
    # and the frozen published counters still agree, but the nested source
    # provenance contradicts the original research-agent execution contract.
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        tamper_trace=("D3", "main-07", "trace", field, replacement),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=error):
        concordance.compare_recovered_treatment_sources(original, recovered)


def _synthetic_overallocated_first_planner_query(records):
    rows = [
        {**record,
         "candidate_urls": list(record["candidate_urls"]),
         "scheduled_urls": list(record["scheduled_urls"])}
        for record in records
    ]
    # P6/main-01 has 6 scheduled URLs across four planned searches with
    # per-query allocation [2,2,1,1]. Move one scheduled URL from the
    # second query to the first: all global counts and URL order still match.
    transferred = rows[1]["scheduled_urls"].pop(0)
    assert transferred == rows[1]["candidate_urls"].pop(0)
    rows[0]["candidate_urls"].append(transferred)
    rows[0]["scheduled_urls"].append(transferred)
    return rows


def _synthetic_skipped_earliest_candidate(records):
    rows = [
        {**record,
         "candidate_urls": list(record["candidate_urls"]),
         "scheduled_urls": list(record["scheduled_urls"])}
        for record in records
    ]
    # Scheduled URLs remain a valid subsequence and all global counts agree,
    # yet an earlier unseen candidate was silently skipped.
    rows[0]["candidate_urls"].insert(
        0, "https://fixture.invalid/P6/main-01/skipped-earliest"
    )
    return rows


@pytest.mark.parametrize(("mutation", "error"), [
    (_synthetic_overallocated_first_planner_query, "per-query browse budget"),
    (_synthetic_skipped_earliest_candidate, "greedy candidate URL scheduling"),
])
def test_historical_planner_query_allocation_and_greedy_url_scheduling(
    tmp_path, monkeypatch, mutation, error,
):
    original, recovered, _, _ = _pair(
        tmp_path, monkeypatch,
        tamper_trace=("P6", "main-01", "trace", "search_records", mutation),
    )
    with pytest.raises(concordance.RecoveryConcordanceError, match=error):
        concordance.compare_recovered_treatment_sources(original, recovered)
