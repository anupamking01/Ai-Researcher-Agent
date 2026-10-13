"""Tests for the provenance-gated main-study analysis entry point."""
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

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
