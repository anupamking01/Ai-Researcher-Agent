"""Synthetic-only tests for diagnostic exact input custody and byte receipt."""
import csv
import hashlib
import json
from types import SimpleNamespace

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


def test_bundle_inventory_scan_stops_at_first_undeclared_name(monkeypatch):
    """An untrusted directory cannot force unbounded enumeration or allocation."""
    required = set(verifier.ARTIFACTS) | {diagnostic.DIAGNOSTIC_MANIFEST}
    visited = []

    class SyntheticListing:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            for name in sorted(required):
                visited.append(name)
                yield SimpleNamespace(name=name)
            visited.append("undeclared-synthetic")
            yield SimpleNamespace(name="undeclared-synthetic")
            raise AssertionError("directory scan continued after unexpected entry")

    monkeypatch.setattr(verifier.os, "scandir", lambda _fd: SyntheticListing())
    with pytest.raises(ValueError, match="file set mismatch"):
        verifier._require_exact_bundle_inventory(
            -1, required, "diagnostic bundle file set mismatch"
        )
    assert len(visited) == len(required) + 1


def test_undeclared_file_added_after_verification_fails_at_final_inventory(
    inputs, monkeypatch,
):
    destination, _ = _build(inputs)
    original = verifier._verify_bound_diagnostic_bundle

    def add_extra_after_read(*args, **kwargs):
        result = original(*args, **kwargs)
        (destination / "late-undeclared-synthetic.txt").write_text(
            "not research evidence", encoding="utf-8"
        )
        return result

    monkeypatch.setattr(verifier, "_verify_bound_diagnostic_bundle", add_extra_after_read)
    with pytest.raises(ValueError, match="file set changed during verification"):
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



@pytest.mark.parametrize(
    "section,field",
    [
        ("analysis_config", "bootstrap_draws"),
        ("analysis_config", "bootstrap_seed"),
        ("analysis_config", "expected_tasks"),
        ("sources", "bytes"),
        ("artifacts", "bytes"),
    ],
)
def test_manifest_rejects_numerically_equal_float_as_integer(
    inputs, section, field,
):
    destination, _ = _build(inputs)
    path = destination / diagnostic.DIAGNOSTIC_MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    # These preserve Python's equality comparison with the expected integer.
    # A verifier relying on dict == would incorrectly accept them.
    if section == "analysis_config":
        original = manifest[section][field]
        manifest[section][field] = float(original)
        assert manifest[section][field] == original
    else:
        name = sorted(manifest[section])[0]
        original = manifest[section][name][field]
        manifest[section][name][field] = float(original)
        assert manifest[section][name][field] == original
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(
        ValueError, match="configuration differs|fingerprint schema mismatch"
    ):
        verifier.verify_diagnostic_bundle(destination)


@pytest.mark.parametrize("section", ["sources", "artifacts"])
def test_manifest_rejects_undeclared_fingerprint_metadata(inputs, section):
    destination, _ = _build(inputs)
    path = destination / diagnostic.DIAGNOSTIC_MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    name = sorted(manifest[section])[0]
    manifest[section][name]["undeclared"] = "not a frozen fingerprint field"
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint schema mismatch"):
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


@pytest.mark.parametrize(
    "bad_pin", ["", "0" * 63, "A" * 64, "g" * 64, 123, True],
)
def test_diagnostic_manifest_external_pin_requires_exact_sha256_format(
    inputs, bad_pin,
):
    destination, _ = _build(inputs)
    with pytest.raises(ValueError, match="64 lowercase hex digits"):
        verifier.verify_diagnostic_bundle(
            destination, expected_manifest_sha256=bad_pin
        )


def test_diagnostic_external_manifest_pin_accepts_exact_archived_bytes(inputs):
    destination, _ = _build(inputs)
    raw = (destination / diagnostic.DIAGNOSTIC_MANIFEST).read_bytes()
    archived_sha256 = hashlib.sha256(raw).hexdigest()
    result = verifier.verify_diagnostic_bundle(
        destination, expected_manifest_sha256=archived_sha256
    )
    assert result["supplied_manifest_pin_matched"] is True
    assert result["status"] == "verified_local_diagnostic_bytes_not_canonical_provenance"
    assert verifier.verify_diagnostic_bundle(
        destination
    )["supplied_manifest_pin_matched"] is False


def test_diagnostic_external_pin_rejects_self_consistent_result_rewrite(inputs):
    destination, _ = _build(inputs)
    manifest_path = destination / diagnostic.DIAGNOSTIC_MANIFEST
    archived_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    # Rewriting output and its *local* receipt can fool an unpinned byte check.
    # A separately preserved fingerprint of the original manifest must reject
    # that self-consistent rewrite before the altered metadata is interpreted.
    output = destination / diagnostic.DIAGNOSTIC_JSON
    output.write_bytes(output.read_bytes() + b"\n")
    _rehash_claimed_artifact(destination, diagnostic.DIAGNOSTIC_JSON)
    assert verifier.verify_diagnostic_bundle(
        destination
    )["supplied_manifest_pin_matched"] is False
    with pytest.raises(ValueError, match="differs from supplied external SHA-256 pin"):
        verifier.verify_diagnostic_bundle(
            destination, expected_manifest_sha256=archived_sha256
        )


def test_diagnostic_external_pin_binds_raw_bytes_not_equivalent_json(inputs):
    destination, _ = _build(inputs)
    manifest_path = destination / diagnostic.DIAGNOSTIC_MANIFEST
    original = manifest_path.read_bytes()
    archived_sha256 = hashlib.sha256(original).hexdigest()
    payload = json.loads(original)
    # Same semantic receipt and source fingerprints; different published bytes.
    rewritten = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert rewritten != original
    manifest_path.write_bytes(rewritten)
    assert verifier.verify_diagnostic_bundle(
        destination
    )["retained_input_cells"] == 40
    with pytest.raises(ValueError, match="differs from supplied external SHA-256 pin"):
        verifier.verify_diagnostic_bundle(
            destination, expected_manifest_sha256=archived_sha256
        )


def test_diagnostic_cli_forwards_external_pin(inputs, monkeypatch, capsys):
    destination, _ = _build(inputs)
    # The diagnostic producer prints its own JSON; capture only the verifier CLI.
    capsys.readouterr()
    manifest = destination / diagnostic.DIAGNOSTIC_MANIFEST
    archived_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "sys.argv",
        ["verify_main_study_diagnostic", str(destination),
         "--expected-manifest-sha256", archived_sha256],
    )
    assert verifier._cli() == 0
    assert json.loads(capsys.readouterr().out)[
        "supplied_manifest_pin_matched"
    ] is True


def test_verifier_refuses_symlinked_analysis_source_ancestor(inputs, monkeypatch):
    destination, _ = _build(inputs)
    name = "scripts/analyze_main_study.py"
    original = verifier.SOURCES[name]
    alias = destination.parent / "source-code-alias"
    alias.symlink_to(original.parent, target_is_directory=True)
    monkeypatch.setattr(
        verifier, "SOURCES",
        {**verifier.SOURCES, name: alias / original.name},
    )
    # Byte-identical target: hashing the redirected pathname alone used to pass.
    with pytest.raises(ValueError, match="diagnostic source cannot be opened safely"):
        verifier.verify_diagnostic_bundle(destination)


def test_verifier_detects_identical_byte_source_replacement_after_capture(
    inputs, monkeypatch,
):
    destination, _ = _build(inputs)
    name = "scripts/analyze_main_study.py"
    original = verifier.SOURCES[name]
    copy = destination.parent / "retained-analyzer-copy.py"
    copy.write_bytes(original.read_bytes())
    monkeypatch.setattr(verifier, "SOURCES", {**verifier.SOURCES, name: copy})
    read = verifier._read_regular
    swapped = False

    def replace_after_manifest(path, *, limit, directory_fd=None,
                               expected_generation=None):
        nonlocal swapped
        raw = read(
            path, limit=limit, directory_fd=directory_fd,
            expected_generation=expected_generation,
        )
        if directory_fd is not None and path.name == diagnostic.DIAGNOSTIC_MANIFEST:
            replacement = destination.parent / "replacement-analyzer.py"
            replacement.write_bytes(copy.read_bytes())
            replacement.replace(copy)
            swapped = True
        return raw

    monkeypatch.setattr(verifier, "_read_regular", replace_after_manifest)
    with pytest.raises(ValueError, match="diagnostic source changed during verification"):
        verifier.verify_diagnostic_bundle(destination)
    assert swapped


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


def test_symlinked_source_ancestor_refused_before_analysis(inputs, monkeypatch):
    main, _, destination = inputs
    source_dir = main.parent / "original-source"
    source_dir.mkdir()
    moved = source_dir / main.name
    main.rename(moved)
    alias = main.parent / "source-alias"
    alias.symlink_to(source_dir, target_is_directory=True)
    monkeypatch.setattr(frozen, "MAIN_CSV", alias / main.name)
    with pytest.raises(ValueError, match="cannot be opened safely"):
        diagnostic.main(output_dir=destination)
    assert moved.is_file()
    assert not destination.exists()


def test_parent_traversal_refused_before_analysis(inputs, monkeypatch):
    main, _, destination = inputs
    source_dir = main.parent / "source-folder"
    source_dir.mkdir()
    moved = source_dir / main.name
    main.rename(moved)
    monkeypatch.setattr(
        frozen, "MAIN_CSV",
        source_dir / ".." / source_dir.name / moved.name,
    )
    with pytest.raises(ValueError, match="parent components"):
        diagnostic.main(output_dir=destination)
    assert moved.is_file()
    assert not destination.exists()


def test_source_ancestor_swapped_after_descriptor_read_fails_closed(
    inputs, monkeypatch,
):
    main, _, destination = inputs
    source_dir = main.parent / "source-folder"
    source_dir.mkdir()
    moved = source_dir / main.name
    main.rename(moved)
    monkeypatch.setattr(frozen, "MAIN_CSV", moved)
    original_read = diagnostic.os.read
    replaced = False

    def substitute_parent(fd, size):
        nonlocal replaced
        raw = original_read(fd, size)
        if raw and not replaced:
            replaced = True
            relocated = main.parent / "relocated-source"
            source_dir.rename(relocated)
            source_dir.symlink_to(relocated, target_is_directory=True)
        return raw

    monkeypatch.setattr(diagnostic.os, "read", substitute_parent)
    with pytest.raises(ValueError, match="parent directory changed"):
        diagnostic.main(output_dir=destination)
    assert replaced
    assert not destination.exists()


def test_verifier_refuses_symlinked_bundle_ancestor(inputs):
    destination, _ = _build(inputs)
    container = destination.parent / "source-bundles"
    container.mkdir()
    destination.rename(container / destination.name)
    alias = destination.parent / "redirected-bundles"
    alias.symlink_to(container, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be opened safely"):
        verifier.verify_diagnostic_bundle(alias / destination.name)


def test_verifier_refuses_explicit_bundle_parent_traversal(inputs):
    destination, _ = _build(inputs)
    folder = destination.parent / "subfolder"
    folder.mkdir()
    via_parent = folder / ".." / destination.name
    with pytest.raises(ValueError, match="parent traversal"):
        verifier.verify_diagnostic_bundle(via_parent)


def test_verifier_detects_bundle_directory_substitution_during_verification(
    inputs, monkeypatch,
):
    destination, _ = _build(inputs)
    reader = verifier._read_regular
    swapped = False

    def swap_after_manifest(path, *, limit, directory_fd=None, expected_generation=None):
        nonlocal swapped
        raw = reader(path, limit=limit, directory_fd=directory_fd,
                     expected_generation=expected_generation)
        if directory_fd is not None and path.name == diagnostic.DIAGNOSTIC_MANIFEST:
            relocated = destination.parent / "relocated-diagnostic"
            destination.rename(relocated)
            destination.symlink_to(relocated, target_is_directory=True)
            swapped = True
        return raw

    monkeypatch.setattr(verifier, "_read_regular", swap_after_manifest)
    with pytest.raises(ValueError, match="ancestor changed during verification"):
        verifier.verify_diagnostic_bundle(destination)
    assert swapped


def test_verifier_detects_identical_byte_member_swap_after_its_read(
    inputs, monkeypatch,
):
    destination, _ = _build(inputs)
    reader = verifier._read_regular
    swapped = False

    def swap_after_last_artifact(path, *, limit, directory_fd=None,
                                 expected_generation=None):
        nonlocal swapped
        raw = reader(path, limit=limit, directory_fd=directory_fd,
                     expected_generation=expected_generation)
        if directory_fd is not None and path.name == diagnostic.DIAGNOSTIC_MD:
            first = destination / diagnostic.DIAGNOSTIC_MAIN_INPUT
            replacement = destination.parent / "same-content-replacement.csv"
            replacement.write_bytes(first.read_bytes())
            replacement.replace(first)
            swapped = True
        return raw

    monkeypatch.setattr(verifier, "_read_regular", swap_after_last_artifact)
    with pytest.raises(ValueError, match="member changed during verification"):
        verifier.verify_diagnostic_bundle(destination)
    assert swapped
