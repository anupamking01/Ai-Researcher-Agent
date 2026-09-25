"""Synthetic regression tests for snapshot-bound human-validation analysis.

These tests mutate on-disk artifacts at deterministic verifier boundaries.
All scores and mappings are synthetic fixtures, not collected human ratings or
experimental results.
"""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as core


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
                    "report_markdown": f"Synthetic report {variant}",
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
    protocol.write_text("# Synthetic protocol\n", encoding="utf-8")
    assignment = tmp_path / "assignment.md"
    assignment.write_text("# Synthetic assignment\n", encoding="utf-8")
    plan = tmp_path / "analysis_plan.md"
    plan.write_text("# Synthetic human-analysis plan\n", encoding="utf-8")
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
        analysis_plan_path=case["plan"],
        task_manifest_path=case["task_manifest"],
        repo_root=case["repo_root"],
    )


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
