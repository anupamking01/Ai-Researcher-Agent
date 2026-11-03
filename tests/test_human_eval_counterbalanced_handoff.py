"""Synthetic, offline coverage for paired pre-distribution source binding."""

import hashlib
import json

import pytest

from scripts import build_human_eval_packet as build
from scripts import export_human_eval_annotator_bundle as exporter
from scripts import verify_human_eval_counterbalanced_handoff as handoff


@pytest.fixture
def case(tmp_path):
    manifest = tmp_path / "experiments" / "main_budget_tasks.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "task_set_id": "main-budget-v1-test",
        "frozen_before_execution": True,
        "tasks": [
            {"id": "main-01", "question": "Synthetic question one?"},
            {"id": "main-02", "question": "Synthetic question two?"},
        ],
    }))
    for task_id, question in [("main-01", "Synthetic question one?"),
                              ("main-02", "Synthetic question two?")]:
        for variant in build.EXPECTED_VARIANTS:
            run_id = f"{variant.lower()}-{task_id}"
            report = tmp_path / "outputs" / run_id / "research_report.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("# Synthetic neutral report\n\nText to assess.\n")
            trace = tmp_path / "outputs" / "experiment_traces" / variant / f"{run_id}.json"
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(json.dumps({
                "schema_version": 2,
                "experiment": {"variant_id": variant, "task_id": task_id,
                               "task_set_id": "main-budget-v1-test"},
                "trace": {"run_id": run_id, "variant_id": variant,
                          "task_id": task_id, "question": question,
                          "completed": True,
                          "report_path": f"./outputs/{run_id}/research_report.pdf"},
            }))
    packet = tmp_path / "outputs" / "human_eval"
    build.build_packet(
        tmp_path / "outputs" / "experiment_traces", packet,
        seed=20260925, task_manifest_path=manifest,
    )
    canonical, reverse = tmp_path / "canonical", tmp_path / "reverse"
    for root, order in ((canonical, "canonical"), (reverse, "reverse")):
        exporter.export_annotator_bundle(
            packet_root=packet, output_root=root, task_manifest_path=manifest,
            repo_root=tmp_path, presentation_order=order,
        )
    return {
        "packet_root": packet,
        "canonical_root": canonical,
        "reverse_root": reverse,
        "expected_coordinator_manifest_sha256": hashlib.sha256(
            (packet / "manifest.json").read_bytes()
        ).hexdigest(),
        "expected_n_reports": 8,
        "task_manifest_path": manifest,
        "repo_root": tmp_path,
    }


def test_valid_pair_emits_only_source_bound_distribution_receipt(case):
    receipt = handoff.verify_counterbalanced_handoff(**case)
    assert receipt["status"] == "human_eval_counterbalanced_handoff_verified"
    assert receipt["n_reports"] == 8
    assert receipt["presentation_orders"] == ["canonical", "reverse"]
    assert receipt["bundles"]["canonical"]["packet_sha256"] != receipt["bundles"]["reverse"]["packet_sha256"]
    assert receipt["bundles"]["canonical"]["annotator_guide_sha256"] == receipt["bundles"]["reverse"]["annotator_guide_sha256"]
    assert not any(secret in json.dumps(receipt) for secret in ("blinding_key", "variant_id", "run_id", "annotator_id", "correctness_1_5"))


def test_same_directory_cannot_supply_two_independent_handoffs(case):
    case["reverse_root"] = case["canonical_root"]
    with pytest.raises(ValueError, match="two distinct bundle directories"):
        handoff.verify_counterbalanced_handoff(**case)


def test_reversed_bundle_assignment_fails(case):
    case["canonical_root"], case["reverse_root"] = case["reverse_root"], case["canonical_root"]
    with pytest.raises(ValueError, match="expected presentation order"):
        handoff.verify_counterbalanced_handoff(**case)


def test_two_canonical_bundles_cannot_pass(case):
    alternative = case["reverse_root"].parent / "canonical-copy"
    exporter.export_annotator_bundle(
        packet_root=case["packet_root"], output_root=alternative,
        task_manifest_path=case["task_manifest_path"],
        repo_root=case["repo_root"], presentation_order="canonical",
    )
    case["reverse_root"] = alternative
    with pytest.raises(ValueError, match="expected presentation order"):
        handoff.verify_counterbalanced_handoff(**case)


def test_unpinned_or_wrong_source_digest_fails(case):
    case["expected_coordinator_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="independently pinned"):
        handoff.verify_counterbalanced_handoff(**case)


@pytest.mark.parametrize("bad_digest", ["", "A" * 64, "0" * 63, 9, None])
def test_malformed_pin_fails_before_reading_bundles(case, bad_digest):
    case["expected_coordinator_manifest_sha256"] = bad_digest
    with pytest.raises(ValueError, match="64 lowercase hex"):
        handoff.verify_counterbalanced_handoff(**case)


def test_tampered_reverse_packet_fails_even_if_canonical_valid(case):
    packet = case["reverse_root"] / "packet.jsonl"
    packet.write_bytes(packet.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        handoff.verify_counterbalanced_handoff(**case)


def test_wrong_report_count_fails_closed(case):
    case["expected_n_reports"] = 40
    with pytest.raises(ValueError, match="expected report count"):
        handoff.verify_counterbalanced_handoff(**case)


def test_missing_reverse_bundle_fails(case):
    case["reverse_root"] = case["canonical_root"].parent / "missing"
    with pytest.raises(ValueError):
        handoff.verify_counterbalanced_handoff(**case)


def test_verifier_does_not_change_source_bytes(case):
    files = [case["packet_root"] / "manifest.json",
             case["canonical_root"] / "packet.jsonl",
             case["reverse_root"] / "packet.jsonl"]
    before = [path.read_bytes() for path in files]
    handoff.verify_counterbalanced_handoff(**case)
    assert [path.read_bytes() for path in files] == before


def test_first_bundle_content_mutation_during_reverse_verification_fails(case, monkeypatch):
    """A source-bound receipt for one bundle cannot outlive the pair audit."""
    original = exporter.verify_annotator_bundle_against_source

    def mutate_canonical(*, expected_presentation_order, **kwargs):
        if expected_presentation_order == "reverse":
            first = case["canonical_root"] / "packet.jsonl"
            first.write_bytes(first.read_bytes() + b"\\n")
        return original(expected_presentation_order=expected_presentation_order, **kwargs)

    monkeypatch.setattr(exporter, "verify_annotator_bundle_against_source", mutate_canonical)
    with pytest.raises(ValueError, match="canonical packet.jsonl changed during combined"):
        handoff.verify_counterbalanced_handoff(**case)


def test_first_bundle_same_byte_inode_replacement_during_reverse_fails(case, monkeypatch):
    """Even a byte-identical pathname replacement invalidates pair custody."""
    original = exporter.verify_annotator_bundle_against_source

    def replace_canonical(*, expected_presentation_order, **kwargs):
        if expected_presentation_order == "reverse":
            first = case["canonical_root"] / "packet.jsonl"
            original_bytes = first.read_bytes()
            first.unlink()
            first.write_bytes(original_bytes)
        return original(expected_presentation_order=expected_presentation_order, **kwargs)

    monkeypatch.setattr(exporter, "verify_annotator_bundle_against_source", replace_canonical)
    with pytest.raises(ValueError, match="canonical packet.jsonl changed during combined"):
        handoff.verify_counterbalanced_handoff(**case)


def test_first_bundle_receives_extra_file_during_reverse_fails(case, monkeypatch):
    """Do not issue pair success after a coordinator-only file was injected."""
    original = exporter.verify_annotator_bundle_against_source

    def inject_extra(*, expected_presentation_order, **kwargs):
        if expected_presentation_order == "reverse":
            (case["canonical_root"] / "blinding_key.csv").write_text("synthetic key")
        return original(expected_presentation_order=expected_presentation_order, **kwargs)

    monkeypatch.setattr(exporter, "verify_annotator_bundle_against_source", inject_extra)
    with pytest.raises(ValueError, match="artifact set mismatch"):
        handoff.verify_counterbalanced_handoff(**case)


def test_pair_verification_never_reads_coordinator_blinding_key(case, monkeypatch):
    """The pair-window hash pass must inspect only treatment-blind files."""
    original = exporter._regular_bytes

    def forbid_private(path, *, label):
        if "blinding_key" in str(path):
            raise AssertionError("pair gate must not open the blinding key")
        return original(path, label=label)

    # Underlying one-bundle source verification legitimately reads coordinator
    # private files, so exercise only the new pair-window capture and closing check.
    monkeypatch.setattr(exporter, "_regular_bytes", forbid_private)
    observed = handoff._snapshot_bundle_pair_sources(
        case["canonical_root"], case["reverse_root"]
    )
    handoff._require_bundle_pair_sources_unchanged(observed)
