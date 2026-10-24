"""Tests for the provenance-gated main-study analysis entry point."""
import json
import hashlib
import os
import stat
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts import analyze_main_study
from scripts.fingerprint_research_artifacts import build_manifest
from scripts import run_verified_main_study_analysis as verified
from scripts.run_verified_main_study_analysis import verify_and_run, verify_run_and_record


MAIN_HEADER = "successful_sources,total_tokens,treatment_cost_usd,latency_seconds,model_calls,report_words\n"
MAIN_ROW = "2,100,0.05,1.2,3,250\n"
SUPPORT_HEADER = "claims_checked,supported,partially_supported,unsupported,contradicted\n"
SUPPORT_ROW = "4,2,1,1,0\n"


def _study(tmp_path: Path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    main = outputs / "main_study_runs.csv"
    support = outputs / "posthoc_support_runs.csv"
    main.write_text(MAIN_HEADER + MAIN_ROW, encoding="utf-8")
    support.write_text(SUPPORT_HEADER + SUPPORT_ROW, encoding="utf-8")
    return main, support


def _analysis_outputs(strict_support: float) -> tuple[bytes, bytes]:
    means = {
        "strict_support_rate": strict_support,
        "broad_support_rate": strict_support,
        "successful_sources": 2.0,
        "total_tokens": 100.0,
        "treatment_cost_usd": 0.05,
        "latency_seconds": 1.2,
    }
    payload = {
        "variant_summary": {
            variant: {"means": dict(means), "zero_evidence_runs": 0}
            for variant in analyze_main_study.VARIANTS
        },
        "primary_contrasts": {
            name: {
                "mean_difference": 0.0,
                "median_difference": 0.0,
                "bootstrap_95pct_ci_mean_difference": [0.0, 0.0],
                "exact_two_sided_signflip_p": 1.0,
                "holm_adjusted_p": 1.0,
                "paired_dz": None,
                "positive_tasks": 0,
                "negative_tasks": 0,
                "tied_tasks": 10,
            }
            for _, _, name in analyze_main_study.PRIMARY_CONTRASTS
        },
        "cost_quality_pareto": {"frontier": ["D3"]},
    }
    return (
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
        analyze_main_study._markdown(payload).encode("utf-8"),
    )


def _stage_analysis(monkeypatch, json_bytes: bytes, markdown_bytes: bytes):
    observed = {}

    def stage(
        manifest,
        *,
        root,
        analyze=None,
        output_json=None,
        output_markdown=None,
    ):
        assert analyze is None
        assert output_json is not None
        assert output_markdown is not None
        observed["json"] = Path(output_json)
        observed["markdown"] = Path(output_markdown)
        observed["json"].parent.mkdir(parents=True, exist_ok=True)
        observed["markdown"].parent.mkdir(parents=True, exist_ok=True)
        observed["json"].write_bytes(json_bytes)
        observed["markdown"].write_bytes(markdown_bytes)
        return 0

    monkeypatch.setattr(verified, "verify_and_run", stage)
    return observed


def test_verified_gate_runs_analysis_only_after_checks(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    result = verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 7)
    assert result == 7
    assert calls == ["ran"]


def test_verified_gate_blocks_mutated_input_before_analysis(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    main.write_text(MAIN_HEADER + "9,100,0.05,1.2,3,250\n", encoding="utf-8")
    calls = []
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 0)
    assert calls == []


def test_verified_gate_rejects_manifest_for_wrong_artifacts(tmp_path):
    main, _ = _study(tmp_path)
    manifest = build_manifest([main], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="exactly the canonical analysis inputs"):
        verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 0)
    assert calls == []


def test_verified_gate_blocks_invalid_scientific_counts(tmp_path):
    main, support = _study(tmp_path)
    support.write_text(SUPPORT_HEADER + "4,2.5,0.5,1,0\n", encoding="utf-8")
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="non-integer value"):
        verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 0)
    assert calls == []


def test_verified_gate_blocks_duplicate_csv_headers_before_analysis(tmp_path):
    main, support = _study(tmp_path)
    main.write_text(
        "successful_sources,total_tokens,treatment_cost_usd,latency_seconds,"
        "model_calls,report_words,successful_sources\n"
        "2,100,0.05,1.2,3,250,2\n",
        encoding="utf-8",
    )
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []

    with pytest.raises(ValueError, match="duplicate CSV header"):
        verify_and_run(manifest, root=tmp_path, analyze=lambda: calls.append("ran") or 0)

    assert calls == []


def test_input_validator_binding_detects_drift_after_capture(tmp_path):
    validator = tmp_path / verified.INPUT_VALIDATOR
    validator.parent.mkdir(parents=True)
    validator.write_text("# validator revision one\n", encoding="utf-8")

    binding = verified._capture_input_validator_binding(root=tmp_path)
    validator.write_text("# validator revision two\n", encoding="utf-8")

    with pytest.raises(ValueError, match="changed during verified analysis"):
        verified._require_input_validator_unchanged(binding)


def test_input_validator_binding_executes_the_exact_captured_source(tmp_path):
    validator = tmp_path / verified.INPUT_VALIDATOR
    validator.parent.mkdir(parents=True)
    validator.write_text("REVISION = 'captured'\n", encoding="utf-8")

    binding = verified._capture_input_validator_binding(root=tmp_path)
    validator.write_text("REVISION = 'replacement'\n", encoding="utf-8")

    assert binding.module.REVISION == "captured"


def test_input_validator_binding_rejects_missing_source(tmp_path):
    with pytest.raises(ValueError, match="stable regular file"):
        verified._capture_input_validator_binding(root=tmp_path)


def test_execution_receipt_uses_prevalidated_input_validator_digest(tmp_path):
    runner = tmp_path / verified.VERIFIED_RUNNER
    verifier = tmp_path / verified.EXECUTION_VERIFIER
    validator = tmp_path / verified.INPUT_VALIDATOR
    runner.parent.mkdir(parents=True)
    runner.write_text("# runner\n", encoding="utf-8")
    verifier.write_text("# verifier\n", encoding="utf-8")
    validator.write_text("# validator used\n", encoding="utf-8")
    captured = hashlib.sha256(validator.read_bytes()).hexdigest()
    validator.write_text("# later replacement\n", encoding="utf-8")

    receipt = verified._bind_verified_execution(
        {"schema_version": 1},
        root=tmp_path,
        input_validator_sha256=captured,
    )

    assert receipt["verified_execution"]["input_validator"]["sha256"] == captured


def test_verified_run_refuses_receipt_when_validator_changes_during_analysis(
    tmp_path, monkeypatch
):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    validator = tmp_path / verified.INPUT_VALIDATOR
    validator.parent.mkdir(parents=True, exist_ok=True)
    validator.write_text(
        "import csv\n"
        "def read_csv_rows(path):\n"
        "    with path.open(newline='') as handle:\n"
        "        return list(csv.DictReader(handle))\n"
        "def validate_rows(main_rows, support_rows, *, require_canonical_matrix=False):\n"
        "    return None\n",
        encoding="utf-8",
    )
    verifier_calls = []

    def fake_builder(payload, *, root):
        return {"schema_version": 1}

    def fake_verifier(*, root):
        verifier_calls.append(root)

    monkeypatch.setattr(verified, "build_receipt", fake_builder)
    monkeypatch.setattr(verified, "verify_outputs", fake_verifier)

    def mutate_validator():
        validator.write_text("# validator revision two\n", encoding="utf-8")
        return 0

    receipt = tmp_path / "outputs" / "main_study_analysis_provenance.json"
    with pytest.raises(ValueError, match="changed during verified analysis"):
        verify_run_and_record(
            manifest,
            root=tmp_path,
            analyze=mutate_validator,
            receipt_builder=fake_builder,
            output_verifier=fake_verifier,
            output=receipt,
        )

    assert verifier_calls == []
    assert not receipt.exists()


def test_default_analysis_consumes_manifest_bound_input_snapshots(tmp_path, monkeypatch):
    main, support = _study(tmp_path)
    original_main = main.read_bytes()
    original_support = support.read_bytes()
    manifest = build_manifest([main, support], root=tmp_path)
    observed = {}

    def analyze_snapshots(command, *, cwd, check, timeout):
        # Simulate a live-input edit after the verified runner has captured its
        # analysis inputs but before the analyzer opens them.
        main.write_text(MAIN_HEADER + "9,999,0.99,9.9,9,999\n", encoding="utf-8")
        support.write_text(SUPPORT_HEADER + "4,4,0,0,0\n", encoding="utf-8")
        observed["main_path"] = Path(command[3])
        observed["support_path"] = Path(command[4])
        observed["main_bytes"] = observed["main_path"].read_bytes()
        observed["support_bytes"] = observed["support_path"].read_bytes()
        observed["out_json"] = Path(command[5])
        observed["out_md"] = Path(command[6])
        observed["cwd"] = Path(cwd)
        assert check is False
        assert timeout == 300
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(verified.subprocess, "run", analyze_snapshots)

    assert verified.verify_and_run(manifest, root=tmp_path) == 0
    assert observed["main_path"] != main
    assert observed["support_path"] != support
    assert observed["main_bytes"] == original_main
    assert observed["support_bytes"] == original_support
    assert observed["out_json"] == tmp_path / "outputs/main_study_inference.json"
    assert observed["out_md"] == tmp_path / "paper/MAIN_STUDY_INFERENCE.md"
    assert observed["cwd"] == tmp_path


def test_verified_gate_rejects_drift_between_manifest_check_and_snapshot(
    tmp_path, monkeypatch
):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    real_verify_manifest = verified.verify_manifest

    def mutate_after_manifest_check(payload, *, root):
        entries = real_verify_manifest(payload, root=root)
        main.write_text(MAIN_HEADER + "9,100,0.05,1.2,3,250\n", encoding="utf-8")
        return entries

    monkeypatch.setattr(verified, "verify_manifest", mutate_after_manifest_check)
    calls = []

    with pytest.raises(ValueError, match="changed while capturing verified analysis input"):
        verified.verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
        )
    assert calls == []


def test_snapshot_analysis_driver_runs_in_an_isolated_process(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    (scripts / "analyze_main_study.py").write_text(
        """from pathlib import Path
MAIN_CSV = Path('live-main.csv')
SUPPORT_CSV = Path('live-support.csv')
OUT_JSON = Path('wrong.json')
OUT_MD = Path('wrong.md')
def main():
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_bytes(MAIN_CSV.read_bytes() + b'|' + SUPPORT_CSV.read_bytes())
    OUT_MD.write_text('isolated snapshot analysis\\n', encoding='utf-8')
    return 0
""",
        encoding="utf-8",
    )
    main_snapshot = tmp_path / "snapshots" / "main.csv"
    support_snapshot = tmp_path / "snapshots" / "support.csv"
    main_snapshot.parent.mkdir()
    main_snapshot.write_bytes(b"manifest-bound-main")
    support_snapshot.write_bytes(b"manifest-bound-support")

    result = verified._run_analysis_from_snapshots(
        {
            verified.CANONICAL_MAIN: main_snapshot,
            verified.CANONICAL_SUPPORT: support_snapshot,
        },
        root=tmp_path,
    )

    assert result == 0
    assert (tmp_path / "outputs/main_study_inference.json").read_bytes() == (
        b"manifest-bound-main|manifest-bound-support"
    )
    assert (tmp_path / "paper/MAIN_STUDY_INFERENCE.md").read_text(
        encoding="utf-8"
    ) == "isolated snapshot analysis\n"


def test_successful_verified_run_records_receipt_only_after_output_verification(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    output = tmp_path / "receipt.json"
    expected = {"schema_version": 1, "bound": manifest["aggregate_sha256"]}
    events = []

    result = verify_run_and_record(
        manifest,
        root=tmp_path,
        analyze=lambda: events.append("analysis") or 0,
        receipt_builder=lambda payload, root: expected,
        output_verifier=lambda root: events.append("outputs-verified"),
        output=output,
    )

    assert result == 0
    assert events == ["analysis", "outputs-verified"]
    assert json.loads(output.read_text(encoding="utf-8")) == expected


def test_failed_analysis_does_not_verify_outputs_or_emit_receipt(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    output = tmp_path / "receipt.json"
    verifier_calls = []
    result = verify_run_and_record(
        manifest,
        root=tmp_path,
        analyze=lambda: 3,
        receipt_builder=lambda payload, root: {"prepared": True},
        output_verifier=lambda root: verifier_calls.append("verified"),
        output=output,
    )
    assert result == 3
    assert verifier_calls == []
    assert not output.exists()


def test_output_verification_failure_does_not_emit_success_receipt(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    output = tmp_path / "receipt.json"

    def fail_outputs(*, root):
        raise ValueError("manuscript inference Markdown does not match canonical JSON")

    with pytest.raises(ValueError, match="does not match canonical JSON"):
        verify_run_and_record(
            manifest,
            root=tmp_path,
            analyze=lambda: 0,
            receipt_builder=lambda payload, root: {"prepared": True},
            output_verifier=fail_outputs,
            output=output,
        )
    assert not output.exists()


def test_output_verification_failure_invalidates_stale_success_receipt(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    output = tmp_path / "receipt.json"
    output.write_text('{"status":"old-success"}\n', encoding="utf-8")

    def fail_outputs(*, root):
        raise ValueError("malformed canonical output")

    with pytest.raises(ValueError, match="malformed canonical output"):
        verify_run_and_record(
            manifest,
            root=tmp_path,
            analyze=lambda: 0,
            receipt_builder=lambda payload, root: {"prepared": True},
            output_verifier=fail_outputs,
            output=output,
        )
    assert not output.exists()


def test_failed_rerun_invalidates_stale_success_receipt(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    output = tmp_path / "receipt.json"
    output.write_text('{"status":"old-success"}\n', encoding="utf-8")
    result = verify_run_and_record(
        manifest,
        root=tmp_path,
        analyze=lambda: 3,
        receipt_builder=lambda payload, root: {"prepared": True},
        output_verifier=lambda root: None,
        output=output,
    )
    assert result == 3
    assert not output.exists()


def test_preflight_failure_invalidates_stale_success_receipt(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    output = tmp_path / "receipt.json"
    output.write_text('{"status":"old-success"}\n', encoding="utf-8")
    calls = []
    def fail_receipt(payload, root):
        raise ValueError("analysis plan drift")
    with pytest.raises(ValueError, match="analysis plan drift"):
        verify_run_and_record(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            receipt_builder=fail_receipt,
            output_verifier=lambda root: None,
            output=output,
        )
    assert calls == []
    assert not output.exists()


def test_receipt_preflight_failure_blocks_analysis(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    def fail_receipt(payload, root):
        raise ValueError("analysis plan drift")
    with pytest.raises(ValueError, match="analysis plan drift"):
        verify_run_and_record(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            receipt_builder=fail_receipt,
            output_verifier=lambda root: None,
        )
    assert calls == []


def test_failed_candidate_verification_preserves_published_outputs(
    tmp_path, monkeypatch
):
    outputs = tmp_path / "outputs"
    paper = tmp_path / "paper"
    outputs.mkdir()
    paper.mkdir()
    canonical_json, canonical_markdown = _analysis_outputs(0.5)
    json_path = outputs / "main_study_inference.json"
    markdown_path = paper / "MAIN_STUDY_INFERENCE.md"
    json_path.write_bytes(canonical_json)
    markdown_path.write_bytes(canonical_markdown)
    receipt = outputs / "main_study_analysis_provenance.json"
    receipt.write_text('{"status":"previous-success"}\n', encoding="utf-8")
    observed = _stage_analysis(monkeypatch, b"{not-json", b"invalid markdown")

    with pytest.raises(ValueError, match="canonical inference JSON is malformed"):
        verify_run_and_record(
            {"aggregate_sha256": "synthetic"},
            root=tmp_path,
            receipt_builder=lambda manifest, root: {"schema_version": 1},
            output=receipt,
        )

    assert observed["json"] != json_path
    assert observed["markdown"] != markdown_path
    assert json_path.read_bytes() == canonical_json
    assert markdown_path.read_bytes() == canonical_markdown
    assert not receipt.exists()


def test_divergent_verified_candidate_cannot_replace_published_outputs(
    tmp_path, monkeypatch
):
    outputs = tmp_path / "outputs"
    paper = tmp_path / "paper"
    outputs.mkdir()
    paper.mkdir()
    canonical_json, canonical_markdown = _analysis_outputs(0.5)
    candidate_json, candidate_markdown = _analysis_outputs(0.9)
    json_path = outputs / "main_study_inference.json"
    markdown_path = paper / "MAIN_STUDY_INFERENCE.md"
    json_path.write_bytes(canonical_json)
    markdown_path.write_bytes(canonical_markdown)
    _stage_analysis(monkeypatch, candidate_json, candidate_markdown)

    with pytest.raises(ValueError, match="differs from published canonical outputs"):
        verify_run_and_record(
            {"aggregate_sha256": "synthetic"},
            root=tmp_path,
            receipt_builder=lambda manifest, root: {"schema_version": 1},
        )

    assert json_path.read_bytes() == canonical_json
    assert markdown_path.read_bytes() == canonical_markdown


def test_identical_verified_candidate_reuses_published_outputs_and_records_receipt(
    tmp_path, monkeypatch
):
    outputs = tmp_path / "outputs"
    paper = tmp_path / "paper"
    outputs.mkdir()
    paper.mkdir()
    canonical_json, canonical_markdown = _analysis_outputs(0.5)
    json_path = outputs / "main_study_inference.json"
    markdown_path = paper / "MAIN_STUDY_INFERENCE.md"
    json_path.write_bytes(canonical_json)
    markdown_path.write_bytes(canonical_markdown)
    _stage_analysis(monkeypatch, canonical_json, canonical_markdown)
    receipt = outputs / "main_study_analysis_provenance.json"

    assert verify_run_and_record(
        {"aggregate_sha256": "synthetic"},
        root=tmp_path,
        receipt_builder=lambda manifest, root: {"schema_version": 1},
        output=receipt,
    ) == 0

    assert json_path.read_bytes() == canonical_json
    assert markdown_path.read_bytes() == canonical_markdown
    recorded = json.loads(receipt.read_text(encoding="utf-8"))
    assert set(recorded["verified_outputs"]) == {
        "canonical_inference",
        "manuscript_rendering",
    }


def test_receipt_publication_stages_complete_bytes_before_atomic_link(
    tmp_path, monkeypatch
):
    destination = tmp_path / "outputs" / "receipt.json"
    content = b'{"status":"verified"}\n'
    real_link = os.link
    observed = []

    def inspect_link(
        source,
        target,
        *,
        src_dir_fd=None,
        dst_dir_fd=None,
        follow_symlinks=True,
    ):
        assert src_dir_fd == dst_dir_fd
        metadata = os.stat(source, dir_fd=src_dir_fd, follow_symlinks=False)
        assert stat.S_ISREG(metadata.st_mode)
        source_fd = os.open(source, os.O_RDONLY, dir_fd=src_dir_fd)
        try:
            observed.append(os.read(source_fd, len(content) + 1))
        finally:
            os.close(source_fd)
        with pytest.raises(FileNotFoundError):
            os.stat(target, dir_fd=dst_dir_fd, follow_symlinks=False)
        return real_link(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(verified.os, "link", inspect_link)

    verified._publish_receipt(destination, content)

    assert observed == [content]
    assert destination.read_bytes() == content
    assert list(destination.parent.glob(".receipt.json.*.tmp")) == []


def test_receipt_publication_refuses_concurrent_destination(tmp_path):
    destination = tmp_path / "outputs" / "receipt.json"
    destination.parent.mkdir()
    destination.write_bytes(b'{"publisher":"concurrent"}\n')

    with pytest.raises(ValueError, match="concurrent provenance receipt publication"):
        verified._publish_receipt(destination, b'{"status":"verified"}\n')

    assert destination.read_bytes() == b'{"publisher":"concurrent"}\n'
    assert list(destination.parent.glob(".receipt.json.*.tmp")) == []


def test_receipt_publication_rejects_symlink_parent(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    parent = tmp_path / "outputs"
    parent.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="provenance receipt parent must be a regular directory"):
        verified._publish_receipt(
            parent / "receipt.json",
            b'{"status":"verified"}\n',
        )

    assert list(external.iterdir()) == []


def test_verified_run_does_not_invalidate_receipt_through_symlink_parent(tmp_path):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    external_receipt = external / "receipt.json"
    original = b'{"publisher":"external"}\n'
    external_receipt.write_bytes(original)
    redirected_parent = tmp_path / "redirected"
    redirected_parent.symlink_to(external, target_is_directory=True)

    with pytest.raises(
        ValueError,
        match="provenance receipt parent must be a regular directory",
    ):
        verify_run_and_record(
            manifest,
            root=tmp_path,
            analyze=lambda: 0,
            receipt_builder=lambda payload, root: {"schema_version": 1},
            output_verifier=lambda root: None,
            output=redirected_parent / "receipt.json",
        )

    assert external_receipt.read_bytes() == original


def test_first_publication_rollback_never_deletes_a_concurrent_replacement(
    tmp_path, monkeypatch
):
    candidate_json, candidate_markdown = _analysis_outputs(0.5)
    candidate_root = tmp_path / "candidate"
    candidate_json_path = candidate_root / "analysis.json"
    candidate_markdown_path = candidate_root / "analysis.md"
    candidate_root.mkdir()
    candidate_json_path.write_bytes(candidate_json)
    candidate_markdown_path.write_bytes(candidate_markdown)
    published_json = tmp_path / "outputs" / "main_study_inference.json"
    replacement = b'{"publisher":"concurrent"}\n'
    real_create = verified._create_output_at

    def replace_json_then_collide_on_markdown(directory_fd, name, content):
        if name == verified.DEFAULT_JSON.name:
            real_create(directory_fd, name, content)
            published_json.unlink()
            published_json.write_bytes(replacement)
            return
        raise FileExistsError(name)

    monkeypatch.setattr(
        verified,
        "_create_output_at",
        replace_json_then_collide_on_markdown,
    )

    with pytest.raises(ValueError, match="concurrent canonical analysis publication"):
        verified._publish_verified_outputs(
            candidate_json_path,
            candidate_markdown_path,
            root=tmp_path,
        )

    assert published_json.read_bytes() == replacement


def test_parent_swap_cannot_redirect_or_launder_verified_candidate(
    tmp_path, monkeypatch
):
    candidate_json, candidate_markdown = _analysis_outputs(0.5)
    _stage_analysis(monkeypatch, candidate_json, candidate_markdown)
    external = tmp_path / "external"
    external.mkdir()
    # Semantically equivalent JSON would pass the renderer check, but these
    # bytes were never the verified candidate and must not be receipt-bound.
    external_json = external / "main_study_inference.json"
    external_json.write_bytes(candidate_json + b"\n")
    detached = tmp_path / "detached-outputs"
    real_open = verified._open_output_directory
    swapped = []

    def open_then_swap(path):
        directory_fd = real_open(path)
        if Path(path) == tmp_path / "outputs" and not swapped:
            Path(path).rename(detached)
            Path(path).symlink_to(external, target_is_directory=True)
            swapped.append(True)
        return directory_fd

    monkeypatch.setattr(verified, "_open_output_directory", open_then_swap)
    receipt = external / "main_study_analysis_provenance.json"

    with pytest.raises(ValueError, match="canonical analysis parent changed"):
        verify_run_and_record(
            {"aggregate_sha256": "synthetic"},
            root=tmp_path,
            receipt_builder=lambda manifest, root: {"schema_version": 1},
        )

    assert swapped == [True]
    assert (detached / "main_study_inference.json").read_bytes() == candidate_json
    assert external_json.read_bytes() == candidate_json + b"\n"
    assert not receipt.exists()


def test_receipt_rejects_semantically_equivalent_post_publication_byte_drift(
    tmp_path, monkeypatch
):
    candidate_json, candidate_markdown = _analysis_outputs(0.5)
    _stage_analysis(monkeypatch, candidate_json, candidate_markdown)
    real_publish = verified._publish_verified_outputs

    def publish_then_drift(candidate_json_path, candidate_markdown_path, *, root):
        real_publish(candidate_json_path, candidate_markdown_path, root=root)
        canonical = root / verified.DEFAULT_JSON
        canonical.write_bytes(canonical.read_bytes() + b"\n")

    monkeypatch.setattr(
        verified,
        "_publish_verified_outputs",
        publish_then_drift,
    )
    receipt = tmp_path / "outputs" / "main_study_analysis_provenance.json"

    with pytest.raises(ValueError, match="changed after candidate verification"):
        verify_run_and_record(
            {"aggregate_sha256": "synthetic"},
            root=tmp_path,
            receipt_builder=lambda manifest, root: {"schema_version": 1},
            output=receipt,
        )

    assert not receipt.exists()


def test_verified_analysis_cli_rejects_duplicate_manifest_fields(
    tmp_path, monkeypatch
):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"schema_version": 2, "schema_version": 1}\n',
        encoding="utf-8",
    )
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(verified, "verify_run_and_record", lambda payload, output: 0)
    monkeypatch.setattr(
        verified.sys,
        "argv",
        [
            "run_verified_main_study_analysis.py",
            str(manifest),
            "--provenance-output",
            str(receipt),
        ],
    )

    with pytest.raises(SystemExit, match="duplicate JSON field"):
        verified.main()

    assert not receipt.exists()

# These regression tests use synthetic CSV cells, never frozen research outputs.
def _frozen_matrix_study(tmp_path: Path):
    main, support = _study(tmp_path)
    main_records = [
        "variant_id,task_id,completed,source_budget,successful_sources,"
        "failed_sources,total_tokens,treatment_cost_usd,latency_seconds,"
        "model_calls,report_words,posthoc_claims_checked,posthoc_strict_support_rate,"
        "search_calls,posthoc_evaluator_cost_usd,cost_status,"
        "pricing_file,pricing_file_size_bytes,pricing_file_sha256,pricing_unit"
    ]
    support_records = [
        "variant_id,task_id,claims_checked,supported,partially_supported,"
        "unsupported,contradicted,strict_support_rate,evidence_status,"
        "total_tokens,estimated_cost_usd,run_id"
    ]
    for variant in ("D3", "D6", "P6", "P6V"):
        budget = 3 if variant == "D3" else 6
        for task_index in range(1, 11):
            cell = f"{variant},main-{task_index:02d}"
            main_records.append(
                f"{cell},True,{budget},2,0,100,0.05,1.2,3,250,4,0.5,1,0.0125,estimated_from_frozen_uncached_rates,"
                "experiments/openai_pricing_2026-09-08.json,1090,"
                "35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace,per_1m_text_tokens"
            )
            support_records.append(
                f"{cell},4,2,1,1,0,0.5,retrieved_evidence,200,0.0125,synthetic-run-{variant}-{task_index:02d}"
            )
    main.write_text("\n".join(main_records) + "\n", encoding="utf-8")
    support.write_text("\n".join(support_records) + "\n", encoding="utf-8")
    return main, support


def test_verified_gate_accepts_exact_frozen_matrix_before_analyzer(tmp_path):
    main, support = _frozen_matrix_study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    assert verify_and_run(
        manifest,
        root=tmp_path,
        analyze=lambda: calls.append("ran") or 0,
        require_canonical_matrix=True,
    ) == 0
    assert calls == ["ran"]


def test_verified_gate_blocks_pinned_budget_drift_before_analyzer(tmp_path):
    main, support = _frozen_matrix_study(tmp_path)
    old = "D3,main-01,True,3,2,0"
    assert old in main.read_text(encoding="utf-8")
    main.write_text(
        main.read_text(encoding="utf-8").replace(old, "D3,main-01,True,6,2,0", 1),
        encoding="utf-8",
    )
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="frozen source_budget mismatch"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert calls == []


def test_verified_gate_blocks_mirrored_evaluator_drift_before_analyzer(tmp_path):
    main, support = _frozen_matrix_study(tmp_path)
    old = "D3,main-01,True,3,2,0,100,0.05,1.2,3,250,4,0.5"
    assert old in main.read_text(encoding="utf-8")
    main.write_text(
        main.read_text(encoding="utf-8").replace(old, old[:-3] + "0.75", 1),
        encoding="utf-8",
    )
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="post-hoc strict support rate differs"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert calls == []




def test_verified_gate_blocks_evaluator_cost_mirror_drift_before_analyzer(tmp_path):
    # Even if both CSVs and their new manifest are internally SHA-consistent,
    # contradicting evaluator-overhead measurements must block inference.
    main, support = _frozen_matrix_study(tmp_path)
    old = "D3,main-01,4,2,1,1,0,0.5,retrieved_evidence,200,0.0125"
    assert old in support.read_text(encoding="utf-8")
    support.write_text(
        support.read_text(encoding="utf-8").replace(
            old, old[:-6] + "0.013", 1
        ),
        encoding="utf-8",
    )
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="post-hoc evaluator cost differs"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert calls == []

def test_verified_gate_blocks_incomplete_matrix_before_analyzer(tmp_path):
    main, support = _frozen_matrix_study(tmp_path)
    for path in (main, support):
        rows = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="frozen 4x10 main-study matrix"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert calls == []


def test_production_receipt_passes_strict_validation_to_snapshot_gate(
    tmp_path, monkeypatch
):
    main, support = _study(tmp_path)
    manifest = build_manifest([main, support], root=tmp_path)
    marker = SimpleNamespace(module=object(), sha256="0" * 64)
    monkeypatch.setattr(verified, "_capture_input_validator_binding", lambda **_: marker)

    def fake_builder(payload, *, root):
        return {"schema_version": 1}

    monkeypatch.setattr(verified, "build_receipt", fake_builder)
    seen = {}

    def intercept_gate(payload, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("synthetic stop before analysis")

    monkeypatch.setattr(verified, "verify_and_run", intercept_gate)
    with pytest.raises(RuntimeError, match="synthetic stop"):
        verify_run_and_record(
            manifest,
            root=tmp_path,
            analyze=lambda: 0,
            receipt_builder=fake_builder,
        )
    assert seen["require_canonical_matrix"] is True
    assert seen["input_validator"] is marker.module



def test_verified_gate_blocks_mirrored_overcap_measurement_before_inference(tmp_path):
    # Both independently hash-pinned synthetic CSVs can agree with each other
    # while violating the preregistered 12-claim post-hoc measurement cap.
    main, support = _frozen_matrix_study(tmp_path)
    old_main = "D3,main-01,True,3,2,0,100,0.05,1.2,3,250,4,0.5,1,0.0125"
    old_support = "D3,main-01,4,2,1,1,0,0.5,retrieved_evidence,200,0.0125"
    assert old_main in main.read_text(encoding="utf-8")
    assert old_support in support.read_text(encoding="utf-8")
    main.write_text(
        main.read_text(encoding="utf-8").replace(
            old_main,
            "D3,main-01,True,3,2,0,100,0.05,1.2,3,250,13,1.0,1,0.0125",
            1,
        ),
        encoding="utf-8",
    )
    support.write_text(
        support.read_text(encoding="utf-8").replace(
            old_support,
            "D3,main-01,13,13,0,0,0,1.0,retrieved_evidence,200,0.0125",
            1,
        ),
        encoding="utf-8",
    )
    manifest = build_manifest([main, support], root=tmp_path)
    analyzer_calls = []
    with pytest.raises(ValueError, match="frozen claim cap"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: analyzer_calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert analyzer_calls == []



def test_verified_gate_blocks_repinned_unknown_treatment_cost_method(tmp_path):
    # Re-fingerprinting both CSVs is insufficient if treatment costs lose the
    # frozen estimation provenance needed for descriptive Pareto comparisons.
    main, support = _frozen_matrix_study(tmp_path)
    original = main.read_text(encoding="utf-8")
    assert original.count("estimated_from_frozen_uncached_rates") == 40
    main.write_text(
        original.replace(
            ",estimated_from_frozen_uncached_rates,experiments/",
            ",provider_billed,experiments/",
            1,
        ),
        encoding="utf-8",
    )
    manifest = build_manifest([main, support], root=tmp_path)
    analyzer_calls = []
    with pytest.raises(ValueError, match="treatment cost_status diverges"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: analyzer_calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert analyzer_calls == []


def test_verified_gate_blocks_repinned_zero_cost_for_completed_treatment(tmp_path):
    # Both CSVs remain well-formed and the changed data is re-fingerprinted.
    # A zero-cost completed live run with positive model usage would otherwise
    # distort the frozen study's descriptive cost-quality comparison.
    main, support = _frozen_matrix_study(tmp_path)
    original = main.read_text(encoding="utf-8")
    before = "D3,main-01,True,3,2,0,100,0.05,1.2,3,250"
    after = "D3,main-01,True,3,2,0,100,0,1.2,3,250"
    assert before in original
    main.write_text(original.replace(before, after, 1), encoding="utf-8")
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="canonical completed treatment treatment_cost_usd must be positive"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert calls == []



def test_verified_gate_blocks_repinned_reused_evaluator_run_id(tmp_path):
    # Even a new manifest of two internally valid-looking CSVs must not make
    # different reports alias the same evaluation/trace reference.
    main, support = _frozen_matrix_study(tmp_path)
    original = support.read_text(encoding="utf-8")
    assert ",synthetic-run-D3-02" in original
    support.write_text(
        original.replace(",synthetic-run-D3-02", ",synthetic-run-D3-01", 1),
        encoding="utf-8",
    )
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="duplicate evaluator run_id"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert calls == []


def test_verified_gate_blocks_repinned_uniform_pricing_source_drift(tmp_path):
    # Regenerating the CSV manifest cannot establish which pricing schedule
    # supplied completed-run cost estimates. Reject coherent, rehashed drift
    # of the frozen pricing digest before calling any analyzer.
    main, support = _frozen_matrix_study(tmp_path)
    original = main.read_text(encoding="utf-8")
    assert original.count("35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace") == 40
    main.write_text(
        original.replace("35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace", "f" * 64),
        encoding="utf-8",
    )
    manifest = build_manifest([main, support], root=tmp_path)
    calls = []
    with pytest.raises(ValueError, match="frozen pricing_file_sha256 mismatch"):
        verify_and_run(
            manifest,
            root=tmp_path,
            analyze=lambda: calls.append("ran") or 0,
            require_canonical_matrix=True,
        )
    assert calls == []


