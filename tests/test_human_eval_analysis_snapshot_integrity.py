"""Synthetic regression tests for snapshot-bound human-validation analysis.

These tests mutate on-disk artifacts at deterministic verifier boundaries.
All scores and mappings are synthetic fixtures, not collected human ratings or
experimental results.
"""
import csv
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import analyze_human_eval
from scripts import human_eval_analysis_core as core
from scripts import verify_human_eval_analysis_outputs as output_verify


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_snapshot_rejects_redirected_source_parent(tmp_path: Path):
    actual_parent = tmp_path / "actual-inputs"
    actual_parent.mkdir()
    (actual_parent / "analysis.json").write_text(
        '{"synthetic": true}\n', encoding="utf-8"
    )
    redirected_parent = tmp_path / "redirected-inputs"
    redirected_parent.symlink_to(actual_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="parent must be a regular directory"):
        core._snapshot_file(
            redirected_parent / "analysis.json",
            tmp_path / "snapshot" / "analysis.json",
            label="synthetic human-analysis input",
        )


def test_snapshot_rejects_same_byte_source_replacement(
    tmp_path: Path, monkeypatch
):
    source_parent = tmp_path / "inputs"
    source_parent.mkdir()
    source = source_parent / "analysis.json"
    original = b'{"synthetic": true}\n'
    source.write_bytes(original)
    real_pread = core.os.pread
    replaced = False

    def replace_after_read(descriptor, length, offset):
        nonlocal replaced
        chunk = real_pread(descriptor, length, offset)
        if not chunk and not replaced:
            replacement = source_parent / "replacement.json"
            replacement.write_bytes(original)
            os.replace(replacement, source)
            replaced = True
        return chunk

    monkeypatch.setattr(core.os, "pread", replace_after_read)
    with pytest.raises(ValueError, match="changed while it was being"):
        core._snapshot_file(
            source,
            tmp_path / "snapshot" / "analysis.json",
            label="synthetic human-analysis input",
        )


def test_freeze_snapshot_rejects_root_replacement_across_all_artifacts(
    tmp_path: Path, monkeypatch
):
    freeze_root = tmp_path / "frozen-v1"
    freeze_root.mkdir()
    expected = {
        "freeze_manifest.json": b'{"generation":"original"}\n',
        "frozen_ratings.csv": b"generation\noriginal\n",
        "agreement.json": b'{"generation":"original"}\n',
        "raw_rating_inputs/0001.csv": b"generation\noriginal\n",
        "provenance/freeze_human_eval_ratings.py": b"# original freezer\n",
        "provenance/build_human_eval_packet.py": b"# original packet builder\n",
        "governing_inputs/protocol.md": b"# original protocol\n",
        "submission_preflights/0001/receipt/preflight_receipt.json": (
            b'{"generation":"original"}\n'
        ),
    }
    for relative_path, content in expected.items():
        path = freeze_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    replacement_root = tmp_path / "frozen-v1-replacement"
    for relative_path in expected:
        path = replacement_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"replacement generation\n")
    held_root = tmp_path / "frozen-v1-held"

    original_identity = (freeze_root.stat().st_dev, freeze_root.stat().st_ino)
    real_listdir = core.os.listdir
    root_reads = 0

    def swap_path_between_bound_root_inventory_reads(path_or_descriptor):
        nonlocal root_reads
        if isinstance(path_or_descriptor, int):
            current = os.fstat(path_or_descriptor)
            if (current.st_dev, current.st_ino) == original_identity:
                root_reads += 1
                if root_reads == 1:
                    names = real_listdir(path_or_descriptor)
                    freeze_root.rename(held_root)
                    replacement_root.rename(freeze_root)
                    return names
                if root_reads == 2:
                    freeze_root.rename(replacement_root)
                    held_root.rename(freeze_root)
        return real_listdir(path_or_descriptor)

    monkeypatch.setattr(
        core.os,
        "listdir",
        swap_path_between_bound_root_inventory_reads,
    )

    with pytest.raises(ValueError, match="freeze root changed while it was being"):
        core._snapshot_freeze_tree(freeze_root, tmp_path / "captured-freeze")

    assert root_reads >= 2


def test_freeze_snapshot_rejects_entry_replacement_before_tree_copy(
    tmp_path: Path, monkeypatch
):
    freeze_root = tmp_path / "frozen-v1"
    freeze_root.mkdir()
    for filename in ("freeze_manifest.json", "frozen_ratings.csv", "agreement.json"):
        (freeze_root / filename).write_text(
            f"original {filename}\n",
            encoding="utf-8",
        )
    replacement = tmp_path / "replacement.csv"
    replacement.write_text("replacement ratings\n", encoding="utf-8")

    snapshot_directory = core._snapshot_directory_descriptor
    replaced = []

    def replace_before_tree_copy(*args, label, **kwargs):
        if label == "freeze root" and not replaced:
            os.replace(replacement, freeze_root / "frozen_ratings.csv")
            replaced.append(True)
        return snapshot_directory(*args, label=label, **kwargs)

    monkeypatch.setattr(
        core,
        "_snapshot_directory_descriptor",
        replace_before_tree_copy,
    )

    with pytest.raises(ValueError, match="freeze root changed while it was being"):
        core._snapshot_freeze_tree(freeze_root, tmp_path / "captured-freeze")

    assert replaced == [True]


def test_freeze_snapshot_rejects_deep_same_byte_replacement_before_tree_copy(
    tmp_path: Path, monkeypatch
):
    freeze_root = tmp_path / "frozen-v1"
    receipt = (
        freeze_root
        / "submission_preflights"
        / "0001"
        / "receipt"
        / "preflight_receipt.json"
    )
    receipt.parent.mkdir(parents=True)
    original = b'{"synthetic":"same bytes"}\n'
    receipt.write_bytes(original)
    for filename in ("freeze_manifest.json", "frozen_ratings.csv", "agreement.json"):
        (freeze_root / filename).write_text(
            f"original {filename}\n",
            encoding="utf-8",
        )
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(original)

    snapshot_directory = core._snapshot_directory_descriptor
    replaced = []

    def replace_deep_entry_before_tree_copy(*args, label, **kwargs):
        if label == "freeze root" and not replaced:
            os.replace(replacement, receipt)
            replaced.append(True)
        return snapshot_directory(*args, label=label, **kwargs)

    monkeypatch.setattr(
        core,
        "_snapshot_directory_descriptor",
        replace_deep_entry_before_tree_copy,
    )

    with pytest.raises(ValueError, match="freeze root changed while it was being"):
        core._snapshot_freeze_tree(freeze_root, tmp_path / "captured-freeze")

    assert replaced == [True]


def test_freeze_snapshot_reports_root_sidecar_before_malformed_provenance(tmp_path: Path):
    freeze_root = tmp_path / "frozen-v1"
    freeze_root.mkdir()
    for filename in ("freeze_manifest.json", "frozen_ratings.csv", "agreement.json"):
        (freeze_root / filename).write_text(
            f"original {filename}\n",
            encoding="utf-8",
        )
    (freeze_root / "provenance").write_text("not a directory\n", encoding="utf-8")
    (freeze_root / "undeclared.txt").write_text("sidecar\n", encoding="utf-8")

    with pytest.raises(ValueError, match="freeze root contents mismatch"):
        core._snapshot_freeze_tree(freeze_root, tmp_path / "captured-freeze")


def _write_csv(path: Path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(rows)


def _key_rows():
    variants = ("D3", "D6", "P6", "P6V")
    return [
        {
            "blind_id": f"H{index:03d}",
            "variant_id": variant,
            "task_id": "main-01",
            "run_id": f"synthetic-{variant.lower()}",
            "trace_path": f"outputs/experiment_traces/{variant}/synthetic.json",
            "report_path": f"outputs/{variant}/research_report.md",
        }
        for index, variant in enumerate(variants, start=1)
    ]


def _rating_rows(d3_score="2"):
    score_by_blind = {"H001": d3_score, "H002": "4", "H003": "3", "H004": "4"}
    rows = []
    for annotator in ("synthetic-a", "synthetic-b"):
        for blind_id, score in score_by_blind.items():
            rows.append(
                {
                    "annotator_id": annotator,
                    "blind_id": blind_id,
                    "correctness_1_5": score,
                    "completeness_1_5": score,
                    "source_quality_1_5": score,
                    "synthesis_reasoning_1_5": score,
                    "clarity_1_5": score,
                    "notes": "",
                }
            )
    return rows


@pytest.fixture
def analysis_case(tmp_path: Path, monkeypatch):
    packet_root = tmp_path / "human_eval"
    freeze_root = packet_root / "frozen-v1"
    freeze_root.mkdir(parents=True)

    task_manifest = tmp_path / "main_budget_tasks.json"
    task_manifest.write_text(
        json.dumps(
            {
                "task_set_id": "main-budget-v1-test",
                "frozen_before_execution": True,
                "tasks": [{"id": "main-01", "question": "Synthetic question?"}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    packet_path = packet_root / "packet.jsonl"
    packet_path.write_text(
        "".join(
            json.dumps(
                {
                    "blind_id": f"H{index:03d}",
                    "task_id": "main-01",
                    "question": "Synthetic question?",
                    "report_markdown": f"Synthetic report for main item {index}",
                },
                sort_keys=True,
            )
            + "\n"
            for index, variant in enumerate(("D3", "D6", "P6", "P6V"), start=1)
        ),
        encoding="utf-8",
    )

    key_path = packet_root / "blinding_key.csv"
    _write_csv(key_path, core.map_verify.KEY_FIELDS, _key_rows())

    template_path = packet_root / "ratings_template.csv"
    _write_csv(
        template_path,
        freeze.RATING_FIELDS,
        [
            {**{field: "" for field in freeze.RATING_FIELDS}, "blind_id": f"H{index:03d}"}
            for index in range(1, 5)
        ],
    )

    packet_manifest = packet_root / "manifest.json"
    packet_manifest.write_text('{"synthetic":"packet manifest"}\n', encoding="utf-8")

    frozen_path = freeze_root / "frozen_ratings.csv"
    _write_csv(frozen_path, freeze.RATING_FIELDS, _rating_rows())
    agreement_path = freeze_root / "agreement.json"
    agreement_path.write_text(
        json.dumps({"schema_version": 1, "status": "synthetic_agreement"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    freeze_manifest = freeze_root / "freeze_manifest.json"
    freeze_manifest.write_text('{"synthetic":"freeze manifest"}\n', encoding="utf-8")

    protocol = tmp_path / "protocol.md"
    protocol.write_bytes(freeze.DEFAULT_PROTOCOL.read_bytes())
    assignment = tmp_path / "assignment.md"
    assignment.write_bytes(freeze.DEFAULT_ASSIGNMENT_PLAN.read_bytes())
    guide = tmp_path / "annotator-guide.md"
    guide.write_bytes(freeze.DEFAULT_ANNOTATOR_GUIDE.read_bytes())
    plan = tmp_path / "analysis_plan.md"
    plan.write_text("# Synthetic human-analysis plan\n", encoding="utf-8")
    monkeypatch.setattr(
        core,
        "FROZEN_ANALYSIS_PLAN_SHA256",
        _sha(plan.read_bytes()),
        raising=False,
    )
    raw_a = tmp_path / "raw-a.csv"
    raw_b = tmp_path / "raw-b.csv"
    raw_a.write_text("synthetic\n", encoding="utf-8")
    raw_b.write_text("synthetic\n", encoding="utf-8")

    def blind_ok(*args, **kwargs):
        return {
            "n_annotators": 2,
            "requires_predeclared_multi_rater_statistic": False,
        }

    def map_ok(*args, **kwargs):
        return {"status": "human_eval_packet_verified"}

    monkeypatch.setattr(core.blind_verify, "verify_frozen_snapshot", blind_ok)
    monkeypatch.setattr(core.map_verify, "verify_packet", map_ok)

    return {
        "packet_root": packet_root,
        "freeze_root": freeze_root,
        "packet_path": packet_path,
        "task_manifest": task_manifest,
        "key_path": key_path,
        "template_path": template_path,
        "packet_manifest": packet_manifest,
        "frozen_path": frozen_path,
        "agreement_path": agreement_path,
        "freeze_manifest": freeze_manifest,
        "protocol": protocol,
        "assignment": assignment,
        "guide": guide,
        "plan": plan,
        "ratings": [raw_a, raw_b],
        "repo_root": tmp_path,
    }


def _analyze(case):
    return core.analyze(
        case["ratings"],
        freeze_root=case["freeze_root"],
        packet_root=case["packet_root"],
        packet_path=case["packet_path"],
        protocol_path=case["protocol"],
        assignment_plan_path=case["assignment"],
        annotator_guide_path=case["guide"],
        analysis_plan_path=case["plan"],
        task_manifest_path=case["task_manifest"],
        repo_root=case["repo_root"],
    )


def test_analysis_carries_submission_preflight_evidence_into_blinded_gate(
    analysis_case, monkeypatch
):
    case = analysis_case
    evidence_root = case["freeze_root"] / "submission_preflights" / "0001"
    receipt_root = evidence_root / "receipt"
    bundle_root = evidence_root / "bundle"
    receipt_root.mkdir(parents=True)
    bundle_root.mkdir()
    expected = {
        "receipt/preflight_receipt.json": b'{"synthetic":"receipt"}\n',
        "bundle/packet.jsonl": b'{"synthetic":"packet"}\n',
        "bundle/ratings_template.csv": b"blind_id\nH001\n",
        "bundle/annotator_instructions.md": b"# Synthetic instructions\n",
        "bundle/annotator_manifest.json": b'{"synthetic":"manifest"}\n',
    }
    for relative_path, content in expected.items():
        (evidence_root / relative_path).write_bytes(content)

    observed = []

    def verify_blinded_snapshot(*args, **kwargs):
        retained_root = Path(kwargs["freeze_root"]) / "submission_preflights" / "0001"
        observed.append(
            {
                relative_path: (retained_root / relative_path).read_bytes()
                for relative_path in expected
            }
        )
        return {
            "n_annotators": 2,
            "requires_predeclared_multi_rater_statistic": False,
        }

    monkeypatch.setattr(
        core.blind_verify,
        "verify_frozen_snapshot",
        verify_blinded_snapshot,
    )

    _analyze(case)

    assert observed == [expected]


def test_analysis_rejects_preflight_entry_added_during_snapshot(
    analysis_case, monkeypatch
):
    case = analysis_case
    receipt_root = (
        case["freeze_root"] / "submission_preflights" / "0001" / "receipt"
    )
    receipt_root.mkdir(parents=True)
    (receipt_root / "preflight_receipt.json").write_text(
        '{"synthetic":"receipt"}\n', encoding="utf-8"
    )

    real_pread = core.os.pread
    added = []

    def add_entry_after_archive_read(descriptor, length, offset):
        chunk = real_pread(descriptor, length, offset)
        descriptor_path = os.readlink(f"/proc/self/fd/{descriptor}")
        if (
            not chunk
            and descriptor_path.endswith("/preflight_receipt.json")
            and not added
        ):
            (receipt_root / "late-added.json").write_text(
                '{"synthetic":"late"}\n', encoding="utf-8"
            )
            added.append(True)
        return chunk

    snapshot_file = core._snapshot_file

    def forbid_mapping_snapshot(source, destination, *, label):
        if label in {"human-evaluation packet manifest", "coordinator blinding key"}:
            raise AssertionError("treatment mapping opened after an unstable snapshot")
        return snapshot_file(source, destination, label=label)

    monkeypatch.setattr(core.os, "pread", add_entry_after_archive_read)
    monkeypatch.setattr(core, "_snapshot_file", forbid_mapping_snapshot)

    with pytest.raises(ValueError, match="changed while it was being snapshotted"):
        _analyze(case)
    assert added == [True]


def test_analysis_rejects_preflight_archive_appearing_at_snapshot_boundary(
    analysis_case, monkeypatch
):
    case = analysis_case
    reject_sidecars = core._reject_undeclared_freeze_sidecars
    injected = []

    def inject_archive_then_reject(freeze_root, *args, **kwargs):
        archive = Path(freeze_root) / "submission_preflights" / "0001" / "receipt"
        archive.mkdir(parents=True)
        (archive / "preflight_receipt.json").write_text(
            '{"synthetic":"appeared-late"}\n', encoding="utf-8"
        )
        injected.append(True)
        return reject_sidecars(freeze_root, *args, **kwargs)

    snapshot_file = core._snapshot_file

    def forbid_mapping_snapshot(source, destination, *, label):
        if label in {"human-evaluation packet manifest", "coordinator blinding key"}:
            raise AssertionError("treatment mapping opened after an unstable snapshot")
        return snapshot_file(source, destination, label=label)

    monkeypatch.setattr(
        core,
        "_reject_undeclared_freeze_sidecars",
        inject_archive_then_reject,
    )
    monkeypatch.setattr(core, "_snapshot_file", forbid_mapping_snapshot)

    with pytest.raises(ValueError, match="changed while it was being snapshotted"):
        _analyze(case)
    assert injected == [True]


def test_analysis_rejects_same_name_preflight_replacement_after_copy(
    analysis_case, monkeypatch
):
    case = analysis_case
    receipt_root = (
        case["freeze_root"] / "submission_preflights" / "0001" / "receipt"
    )
    receipt_root.mkdir(parents=True)
    first = receipt_root / "a.json"
    first.write_text('{"synthetic":"original"}\n', encoding="utf-8")
    (receipt_root / "z.json").write_text(
        '{"synthetic":"last"}\n', encoding="utf-8"
    )

    real_pread = core.os.pread
    replaced = []

    def replace_first_after_last_read(descriptor, length, offset):
        chunk = real_pread(descriptor, length, offset)
        descriptor_path = os.readlink(f"/proc/self/fd/{descriptor}")
        if not chunk and descriptor_path.endswith("/z.json") and not replaced:
            replacement = receipt_root / "replacement.json"
            replacement.write_text(
                '{"synthetic":"replacement"}\n', encoding="utf-8"
            )
            os.replace(replacement, first)
            replaced.append(True)
        return chunk

    snapshot_file = core._snapshot_file

    def forbid_mapping_snapshot(source, destination, *, label):
        if label in {"human-evaluation packet manifest", "coordinator blinding key"}:
            raise AssertionError("treatment mapping opened after an unstable snapshot")
        return snapshot_file(source, destination, label=label)

    monkeypatch.setattr(core.os, "pread", replace_first_after_last_read)
    monkeypatch.setattr(core, "_snapshot_file", forbid_mapping_snapshot)

    with pytest.raises(ValueError, match="changed while it was being snapshotted"):
        _analyze(case)
    assert replaced == [True]


def test_analysis_rejects_freeze_root_path_aba(
    analysis_case, monkeypatch
):
    case = analysis_case
    freeze_root = case["freeze_root"]
    original_archive = freeze_root / "submission_preflights" / "0001" / "receipt"
    original_archive.mkdir(parents=True)
    original_bytes = b'{"synthetic":"original"}\n'
    replacement_bytes = b'{"synthetic":"replacement"}\n'
    (original_archive / "preflight_receipt.json").write_bytes(original_bytes)

    held_root = freeze_root.with_name("frozen-v1-held")
    replacement_root = freeze_root.with_name("frozen-v1-replacement")
    replacement_archive = replacement_root / "submission_preflights" / "0001" / "receipt"
    replacement_archive.mkdir(parents=True)
    (replacement_archive / "preflight_receipt.json").write_bytes(replacement_bytes)

    original_identity = (freeze_root.stat().st_dev, freeze_root.stat().st_ino)
    real_listdir = core.os.listdir
    swapped = []
    restored = []

    def swap_root_between_inventory_reads(path_or_descriptor):
        if isinstance(path_or_descriptor, int):
            current = os.fstat(path_or_descriptor)
            if (current.st_dev, current.st_ino) == original_identity:
                if not swapped:
                    names = real_listdir(path_or_descriptor)
                    freeze_root.rename(held_root)
                    replacement_root.rename(freeze_root)
                    swapped.append(True)
                    return names
                if not restored:
                    freeze_root.rename(replacement_root)
                    held_root.rename(freeze_root)
                    restored.append(True)
        return real_listdir(path_or_descriptor)

    monkeypatch.setattr(core.os, "listdir", swap_root_between_inventory_reads)

    with pytest.raises(
        ValueError,
        match="freeze root changed while it was being snapshotted",
    ):
        _analyze(case)

    assert swapped == [True]
    assert restored == [True]


def test_analysis_checks_provenance_sidecars_from_bound_root_during_path_aba(
    analysis_case, monkeypatch
):
    case = analysis_case
    freeze_root = case["freeze_root"]
    provenance = freeze_root / "provenance"
    provenance.mkdir()
    for filename in ("freeze_human_eval_ratings.py", "build_human_eval_packet.py"):
        (provenance / filename).write_text("# synthetic\n", encoding="utf-8")
    (provenance / "notes.txt").write_text(
        "undeclared synthetic sidecar\n", encoding="utf-8"
    )

    held_root = freeze_root.with_name("frozen-v1-held")
    replacement_root = freeze_root.with_name("frozen-v1-replacement")
    clean_provenance = replacement_root / "provenance"
    clean_provenance.mkdir(parents=True)
    for filename in ("freeze_human_eval_ratings.py", "build_human_eval_packet.py"):
        (clean_provenance / filename).write_text("# synthetic\n", encoding="utf-8")

    original_identity = (freeze_root.stat().st_dev, freeze_root.stat().st_ino)
    real_listdir = core.os.listdir
    swapped = []
    restored = []

    def swap_root_between_inventory_reads(path_or_descriptor):
        if isinstance(path_or_descriptor, int):
            current = os.fstat(path_or_descriptor)
            if (current.st_dev, current.st_ino) == original_identity:
                if not swapped:
                    names = real_listdir(path_or_descriptor)
                    freeze_root.rename(held_root)
                    replacement_root.rename(freeze_root)
                    swapped.append(True)
                    return names
                if not restored:
                    freeze_root.rename(replacement_root)
                    held_root.rename(freeze_root)
                    restored.append(True)
        return real_listdir(path_or_descriptor)

    snapshot_file = core._snapshot_file

    def forbid_mapping_snapshot(source, destination, *, label):
        if label in {"human-evaluation packet manifest", "coordinator blinding key"}:
            raise AssertionError("treatment mapping opened with an undeclared sidecar")
        return snapshot_file(source, destination, label=label)

    monkeypatch.setattr(core.os, "listdir", swap_root_between_inventory_reads)
    monkeypatch.setattr(core, "_snapshot_file", forbid_mapping_snapshot)

    with pytest.raises(ValueError, match="provenance archive contents mismatch"):
        _analyze(case)
    assert swapped == [True]


def test_analysis_rejects_same_name_preflight_archive_aba(
    analysis_case, monkeypatch
):
    case = analysis_case
    freeze_root = case["freeze_root"]
    archive = freeze_root / "submission_preflights"
    receipt = archive / "0001" / "receipt"
    receipt.mkdir(parents=True)
    (receipt / "preflight_receipt.json").write_text(
        '{"synthetic":"original"}\n', encoding="utf-8"
    )

    held_archive = freeze_root.parent / "submission-preflights-held"
    replacement_archive = freeze_root.parent / "submission-preflights-replacement"
    replacement_receipt = replacement_archive / "0001" / "receipt"
    replacement_receipt.mkdir(parents=True)
    (replacement_receipt / "preflight_receipt.json").write_text(
        '{"synthetic":"replacement"}\n', encoding="utf-8"
    )

    root_identity = (freeze_root.stat().st_dev, freeze_root.stat().st_ino)
    real_listdir = core.os.listdir
    swapped = []
    restored = []

    def swap_archive_between_root_inventory_reads(path_or_descriptor):
        if isinstance(path_or_descriptor, int):
            current = os.fstat(path_or_descriptor)
            if (current.st_dev, current.st_ino) == root_identity:
                if not swapped:
                    names = real_listdir(path_or_descriptor)
                    archive.rename(held_archive)
                    replacement_archive.rename(archive)
                    swapped.append(True)
                    return names
                if not restored:
                    archive.rename(replacement_archive)
                    held_archive.rename(archive)
                    restored.append(True)
        return real_listdir(path_or_descriptor)

    snapshot_file = core._snapshot_file

    def forbid_mapping_snapshot(source, destination, *, label):
        if label in {"human-evaluation packet manifest", "coordinator blinding key"}:
            raise AssertionError("treatment mapping opened after archive ABA")
        return snapshot_file(source, destination, label=label)

    monkeypatch.setattr(
        core.os,
        "listdir",
        swap_archive_between_root_inventory_reads,
    )
    monkeypatch.setattr(core, "_snapshot_file", forbid_mapping_snapshot)

    with pytest.raises(ValueError, match="freeze root changed while it was being snapshotted"):
        _analyze(case)
    assert swapped == [True]
    assert restored == [True]


def test_analysis_rejects_observed_provenance_disappearance(
    analysis_case, monkeypatch
):
    case = analysis_case
    freeze_root = case["freeze_root"]
    provenance = freeze_root / "provenance"
    provenance.mkdir()
    for filename in ("freeze_human_eval_ratings.py", "build_human_eval_packet.py"):
        (provenance / filename).write_text("# synthetic\n", encoding="utf-8")
    held_provenance = freeze_root.parent / "provenance-held"

    real_stat = core.os.stat
    removed = []

    def remove_provenance_before_bound_stat(path, *args, **kwargs):
        if path == "provenance" and kwargs.get("dir_fd") is not None and not removed:
            provenance.rename(held_provenance)
            removed.append(True)
        return real_stat(path, *args, **kwargs)

    root_identity = (freeze_root.stat().st_dev, freeze_root.stat().st_ino)
    real_listdir = core.os.listdir
    root_reads = []

    def restore_before_final_root_inventory(path_or_descriptor):
        if isinstance(path_or_descriptor, int):
            current = os.fstat(path_or_descriptor)
            if (current.st_dev, current.st_ino) == root_identity:
                root_reads.append(True)
                if len(root_reads) == 2 and removed:
                    held_provenance.rename(provenance)
        return real_listdir(path_or_descriptor)

    snapshot_file = core._snapshot_file

    def forbid_mapping_snapshot(source, destination, *, label):
        if label in {"human-evaluation packet manifest", "coordinator blinding key"}:
            raise AssertionError("treatment mapping opened after provenance disappeared")
        return snapshot_file(source, destination, label=label)

    monkeypatch.setattr(core.os, "stat", remove_provenance_before_bound_stat)
    monkeypatch.setattr(core.os, "listdir", restore_before_final_root_inventory)
    monkeypatch.setattr(core, "_snapshot_file", forbid_mapping_snapshot)

    with pytest.raises(
        ValueError,
        match="freeze (?:root )?provenance changed",
    ):
        _analyze(case)
    assert removed == [True]


def test_published_payload_recomputes_from_retained_rating_archive(
    analysis_case, monkeypatch
):
    case = analysis_case
    raw_archive = case["freeze_root"] / "raw_rating_inputs"
    raw_archive.mkdir()
    for index, source in enumerate(case["ratings"], start=1):
        (raw_archive / f"{index:04d}.csv").write_bytes(source.read_bytes())
    case["agreement_path"].write_text(
        json.dumps(freeze.build_agreement(_rating_rows()), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    payload = _analyze(case)
    output_root = case["packet_root"] / "analysis-v1"
    monkeypatch.setattr(core, "PLAN", case["plan"])
    analyze_human_eval.write_bundle(payload, output_root)

    receipt = output_verify.verify_bundle_against_inputs(
        output_root,
        freeze_root=case["freeze_root"],
        packet_root=case["packet_root"],
        packet_path=case["packet_path"],
        protocol_path=case["protocol"],
        assignment_plan_path=case["assignment"],
        analysis_plan_path=case["plan"],
        task_manifest_path=case["task_manifest"],
        repo_root=case["repo_root"],
    )

    assert receipt["independent_recomputation_verified"] is True
    assert receipt["recomputed_from_retained_ratings"] is True


def test_analysis_payload_binds_frozen_governing_documents(analysis_case):
    payload = _analyze(analysis_case)

    expected = {
        "protocol": (analysis_case["protocol"], "paper/HUMAN_EVAL_PROTOCOL.md"),
        "assignment_plan": (
            analysis_case["assignment"],
            "paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md",
        ),
        "annotator_guide": (
            analysis_case["guide"],
            "paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md",
        ),
    }
    for key, (path, logical_path) in expected.items():
        content = path.read_bytes()
        assert payload["provenance"][key] == {
            "path": logical_path,
            "bytes": len(content),
            "sha256": _sha(content),
        }


def test_modified_analysis_plan_is_rejected_before_unblinding(analysis_case, monkeypatch):
    case = analysis_case
    case["plan"].write_text(
        "# Modified after ratings were frozen\n\nUse a different analysis.\n",
        encoding="utf-8",
    )
    snapshot_file = core._snapshot_file

    def forbid_mapping_snapshot(source, destination, *, label):
        if label in {"human-evaluation packet manifest", "coordinator blinding key"}:
            raise AssertionError("treatment mapping opened before plan verification")
        return snapshot_file(source, destination, label=label)

    monkeypatch.setattr(core, "_snapshot_file", forbid_mapping_snapshot)

    with pytest.raises(ValueError, match="frozen analysis plan fingerprint"):
        _analyze(case)


def test_repository_analysis_plan_matches_production_anchor():
    assert _sha(core.PLAN.read_bytes()) == core.FROZEN_ANALYSIS_PLAN_SHA256


@pytest.mark.parametrize(
    ("case_key", "label"),
    [("protocol", "protocol"), ("assignment", "assignment plan")],
)
def test_analysis_rejects_governing_document_drift_before_rating_snapshots(
    analysis_case, monkeypatch, case_key, label
):
    case = analysis_case
    case[case_key].write_text("# Replaced after preregistration\n", encoding="utf-8")
    snapshot_file = core._snapshot_file

    def forbid_rating_snapshot(source, destination, *, label):
        if "rating" in label or label.startswith("blinded freeze"):
            raise AssertionError("rating artifact opened before governing-document verification")
        return snapshot_file(source, destination, label=label)

    monkeypatch.setattr(core, "_snapshot_file", forbid_rating_snapshot)
    with pytest.raises(ValueError, match=f"frozen human-evaluation {label} fingerprint"):
        _analyze(case)


def test_analysis_uses_key_bytes_captured_before_mapping_verification(analysis_case, monkeypatch):
    case = analysis_case
    original = case["key_path"].read_bytes()
    original_verify = core.map_verify.verify_packet

    def verify_then_edit(*args, **kwargs):
        receipt = original_verify(*args, **kwargs)
        rows = _key_rows()
        rows[0]["variant_id"], rows[1]["variant_id"] = rows[1]["variant_id"], rows[0]["variant_id"]
        _write_csv(case["key_path"], core.map_verify.KEY_FIELDS, rows)
        return receipt

    monkeypatch.setattr(core.map_verify, "verify_packet", verify_then_edit)
    payload = _analyze(case)
    assert payload["variant_summary"]["D3"]["correctness_1_5"]["mean_report_score"] == 2.0
    assert payload["variant_summary"]["D6"]["correctness_1_5"]["mean_report_score"] == 4.0
    assert payload["provenance"]["treatment_mapping"]["sha256"] == _sha(original)


def test_analysis_uses_ratings_bytes_captured_before_blinded_verification(analysis_case, monkeypatch):
    case = analysis_case
    original = case["frozen_path"].read_bytes()
    original_verify = core.blind_verify.verify_frozen_snapshot

    def verify_then_edit(*args, **kwargs):
        receipt = original_verify(*args, **kwargs)
        _write_csv(case["frozen_path"], freeze.RATING_FIELDS, _rating_rows(d3_score="4"))
        return receipt

    monkeypatch.setattr(core.blind_verify, "verify_frozen_snapshot", verify_then_edit)
    payload = _analyze(case)
    assert payload["variant_summary"]["D3"]["correctness_1_5"]["mean_report_score"] == 2.0
    assert payload["provenance"]["frozen_ratings"]["sha256"] == _sha(original)


def test_analysis_uses_agreement_bytes_captured_before_blinded_verification(analysis_case, monkeypatch):
    case = analysis_case
    original = case["agreement_path"].read_bytes()
    original_payload = json.loads(original)
    original_verify = core.blind_verify.verify_frozen_snapshot

    def verify_then_edit(*args, **kwargs):
        receipt = original_verify(*args, **kwargs)
        case["agreement_path"].write_text('{"tampered":true}\n', encoding="utf-8")
        return receipt

    monkeypatch.setattr(core.blind_verify, "verify_frozen_snapshot", verify_then_edit)
    payload = _analyze(case)
    assert payload["pre_unblinding_agreement"] == original_payload
    assert payload["provenance"]["pre_unblinding_agreement"]["sha256"] == _sha(original)


def test_analysis_uses_task_manifest_captured_before_mapping_verification(analysis_case, monkeypatch):
    case = analysis_case
    original = case["task_manifest"].read_bytes()
    original_verify = core.map_verify.verify_packet

    def verify_then_edit(*args, **kwargs):
        receipt = original_verify(*args, **kwargs)
        payload = json.loads(case["task_manifest"].read_text(encoding="utf-8"))
        payload["task_set_id"] = "tampered-after-verification"
        case["task_manifest"].write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return receipt

    monkeypatch.setattr(core.map_verify, "verify_packet", verify_then_edit)
    payload = _analyze(case)
    assert payload["task_set_id"] == "main-budget-v1-test"
    assert payload["provenance"]["task_manifest"]["sha256"] == _sha(original)


@pytest.mark.parametrize(
    "name,verifier",
    [
        ("packet_manifest", "map"),
        ("freeze_manifest", "blind"),
    ],
)
def test_analysis_provenance_uses_manifest_snapshot_from_verification_boundary(
    analysis_case, monkeypatch, name, verifier
):
    case = analysis_case
    path = case[name]
    original = path.read_bytes()
    module = core.map_verify if verifier == "map" else core.blind_verify
    attr = "verify_packet" if verifier == "map" else "verify_frozen_snapshot"
    original_verify = getattr(module, attr)

    def verify_then_edit(*args, **kwargs):
        receipt = original_verify(*args, **kwargs)
        path.write_text('{"tampered":"after verification"}\n', encoding="utf-8")
        return receipt

    monkeypatch.setattr(module, attr, verify_then_edit)
    payload = _analyze(case)
    provenance_key = "packet_manifest" if name == "packet_manifest" else "freeze_manifest"
    assert payload["provenance"][provenance_key]["sha256"] == _sha(original)
