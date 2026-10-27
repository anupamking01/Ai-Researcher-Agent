"""Synthetic-only tests for diagnostic exact input custody and byte receipt."""
import csv
import hashlib
import json

import pytest

from scripts import analyze_main_study as frozen
from scripts import analyze_main_study_with_preflight as diagnostic
from scripts import verify_main_study_diagnostic as verifier
from scripts.validate_main_study_inputs import EXPECTED_CELLS, FROZEN_SOURCE_BUDGETS


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    treatment, evaluator = [], []
    for variant, task in sorted(EXPECTED_CELLS):
        treatment.append({
            "variant_id": variant, "task_id": task, "completed": "True",
            "source_budget": str(FROZEN_SOURCE_BUDGETS[variant]),
            "successful_sources": "3", "failed_sources": "0", "search_calls": "1",
            "total_tokens": "1200", "model_calls": "2", "report_words": "500",
            "treatment_cost_usd": "0.04", "latency_seconds": "12.5",
            "posthoc_claims_checked": "4", "posthoc_strict_support_rate": "0.5",
            "posthoc_evaluator_cost_usd": "0.0125",
            "cost_status": "estimated_from_frozen_uncached_rates",
            "pricing_file": "experiments/openai_pricing_2026-09-08.json",
            "pricing_file_size_bytes": "1090",
            "pricing_file_sha256":
                "35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace",
            "pricing_unit": "per_1m_text_tokens",
        })
        evaluator.append({
            "variant_id": variant, "task_id": task,
            "run_id": f"synthetic-{variant}-{task}",
            "claims_checked": "4", "supported": "2", "partially_supported": "1",
            "unsupported": "1", "contradicted": "0", "strict_support_rate": "0.5",
            "evidence_status": "", "total_tokens": "200",
            "estimated_cost_usd": "0.0125",
        })
    source_main = tmp_path / "treat.csv"
    source_support = tmp_path / "eval.csv"
    for path, rows in ((source_main, treatment), (source_support, evaluator)):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    monkeypatch.setattr(frozen, "MAIN_CSV", source_main)
    monkeypatch.setattr(frozen, "SUPPORT_CSV", source_support)
    monkeypatch.setattr(frozen, "BOOTSTRAP_DRAWS", 8)
    return source_main, source_support, tmp_path / "local-diagnostic"


def _build(inputs):
    main, support, destination = inputs
    initial = (main.read_bytes(), support.read_bytes())
    assert diagnostic.main(output_dir=destination) == 0
    return destination, initial


def test_diagnostic_retains_precise_analyzed_csv_and_fingerprints(inputs):
    destination, (main, support) = _build(inputs)
    assert (destination / diagnostic.DIAGNOSTIC_MAIN_INPUT).read_bytes() == main
    assert (destination / diagnostic.DIAGNOSTIC_SUPPORT_INPUT).read_bytes() == support
    manifest = json.loads((destination / diagnostic.DIAGNOSTIC_MANIFEST).read_text())
    assert manifest["scope"] == "local_diagnostic_not_canonical"
    assert manifest["analysis_config"]["bootstrap_draws"] == 8
    assert set(manifest["sources"]) == {
        "scripts/analyze_main_study.py",
        "scripts/analyze_main_study_with_preflight.py",
        "scripts/validate_main_study_inputs.py",
        "scripts/validate_numeric_inputs.py",
    }
    for name, fingerprint in manifest["artifacts"].items():
        data = (destination / name).read_bytes()
        assert fingerprint == {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    receipt = verifier.verify_diagnostic_bundle(destination)
    assert receipt["retained_input_cells"] == 40
    assert receipt["files_verified"] == 4


def test_source_mutation_after_capture_does_not_retarget_analyzer(inputs, monkeypatch):
    main, _, destination = inputs
    original = main.read_bytes()
    original_builder = frozen._build_dataset

    def change_source_after_capture():
        main.write_bytes(b"changed after capture but before inference\n")
        return original_builder()

    monkeypatch.setattr(frozen, "_build_dataset", change_source_after_capture)
    assert diagnostic.main(output_dir=destination) == 0
    assert (destination / diagnostic.DIAGNOSTIC_MAIN_INPUT).read_bytes() == original
    assert verifier.verify_diagnostic_bundle(destination)["retained_input_cells"] == 40
    assert main.read_bytes() != original


@pytest.mark.parametrize("side", ["input", "output"])
def test_changed_retained_artifact_fails_verification(inputs, side):
    destination, _ = _build(inputs)
    name = diagnostic.DIAGNOSTIC_MAIN_INPUT if side == "input" else diagnostic.DIAGNOSTIC_JSON
    file_path = destination / name
    file_path.write_bytes(file_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="byte mismatch"):
        verifier.verify_diagnostic_bundle(destination)


def test_manifest_cannot_relabel_local_diagnostic_as_canonical(inputs):
    destination, _ = _build(inputs)
    path = destination / diagnostic.DIAGNOSTIC_MANIFEST
    manifest = json.loads(path.read_text())
    manifest["scope"] = "canonical"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="study/scope mismatch"):
        verifier.verify_diagnostic_bundle(destination)


def test_undeclared_file_fails_verification(inputs):
    destination, _ = _build(inputs)
    (destination / "unexpected.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="file set mismatch"):
        verifier.verify_diagnostic_bundle(destination)


def test_symlinked_retained_file_fails_closed(inputs):
    destination, _ = _build(inputs)
    original = destination / diagnostic.DIAGNOSTIC_SUPPORT_INPUT
    outside = destination.parent / "unrelated"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        verifier.verify_diagnostic_bundle(destination)
    assert outside.is_file()


def test_symlinked_source_input_refused_before_analysis(inputs):
    main, _, destination = inputs
    outside = main.parent / "outside.csv"
    main.rename(outside)
    main.symlink_to(outside)
    with pytest.raises(ValueError, match="regular file"):
        diagnostic.main(output_dir=destination)
    assert not destination.exists()


def test_oversized_source_input_refused_before_analysis(inputs, monkeypatch):
    _, _, destination = inputs
    monkeypatch.setattr(diagnostic, "MAX_DIAGNOSTIC_INPUT_BYTES", 16)
    with pytest.raises(ValueError, match="size limit"):
        diagnostic.main(output_dir=destination)
    assert not destination.exists()


def test_observed_mid_capture_mutation_refused(inputs, monkeypatch):
    main, _, destination = inputs
    original_read = diagnostic.os.read
    changed = False

    def mutate_first_read(fd, nbytes):
        nonlocal changed
        raw = original_read(fd, nbytes)
        if raw and not changed:
            changed = True
            with main.open("ab") as handle:
                handle.write(b"mutation\n")
        return raw

    monkeypatch.setattr(diagnostic.os, "read", mutate_first_read)
    with pytest.raises(ValueError, match="changed during capture"):
        diagnostic.main(output_dir=destination)
    assert not destination.exists()


def test_duplicate_manifest_key_fails_closed(inputs):
    destination, _ = _build(inputs)
    path = destination / diagnostic.DIAGNOSTIC_MANIFEST
    raw = path.read_text()
    path.write_text(raw.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
    with pytest.raises(ValueError, match="duplicate diagnostic manifest key"):
        verifier.verify_diagnostic_bundle(destination)


def _rehash_claimed_artifact(destination, name):
    """Simulate a locally rewritten result accompanied by its forged receipt."""
    content = (destination / name).read_bytes()
    path = destination / diagnostic.DIAGNOSTIC_MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["artifacts"][name] = {
        "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()
    }
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def test_opt_in_recomputation_matches_both_synthetic_outputs(inputs):
    destination, _ = _build(inputs)
    verified = verifier.verify_diagnostic_bundle(destination, recompute=True)
    assert verified["offline_inference_recomputed"] is True
    assert verified["files_verified"] == 4


def test_recomputation_detects_forged_json_with_repaired_local_receipt(inputs):
    destination, _ = _build(inputs)
    path = destination / diagnostic.DIAGNOSTIC_JSON
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["variant_summary"]["D3"]["means"]["strict_support_rate"] = 0.99
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    _rehash_claimed_artifact(destination, diagnostic.DIAGNOSTIC_JSON)
    # Self-consistent byte hashes alone do not show the numbers were computed
    # from the retained rows; recomputation must reject this altered result.
    assert verifier.verify_diagnostic_bundle(destination)["files_verified"] == 4
    with pytest.raises(ValueError, match="recomputed inference byte mismatch"):
        verifier.verify_diagnostic_bundle(destination, recompute=True)


def test_recomputation_detects_forged_markdown_with_repaired_receipt(inputs):
    destination, _ = _build(inputs)
    name = diagnostic.DIAGNOSTIC_MD
    with (destination / name).open("a", encoding="utf-8") as handle:
        handle.write("\nSynthetic changed interpretation.\n")
    _rehash_claimed_artifact(destination, name)
    assert verifier.verify_diagnostic_bundle(destination)["files_verified"] == 4
    with pytest.raises(ValueError, match="recomputed inference byte mismatch"):
        verifier.verify_diagnostic_bundle(destination, recompute=True)


def test_recomputation_restores_historical_analyzer_globals_on_failure(inputs, monkeypatch):
    destination, _ = _build(inputs)
    original_reader = frozen._read_csv
    original_json, original_md = frozen.OUT_JSON, frozen.OUT_MD

    def failed_render(_payload):
        raise RuntimeError("synthetic recomputation renderer failure")

    monkeypatch.setattr(frozen, "_markdown", failed_render)
    with pytest.raises(RuntimeError, match="synthetic recomputation"):
        verifier.verify_diagnostic_bundle(destination, recompute=True)
    assert frozen._read_csv is original_reader
    assert frozen.OUT_JSON == original_json
    assert frozen.OUT_MD == original_md
