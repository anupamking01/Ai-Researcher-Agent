"""Synthetic, offline verification of prospective design handoff custody."""
from __future__ import annotations

import hashlib
import json
import sys

import pytest

from scripts import plan_counterbalanced_replication as design
from scripts import verify_counterbalanced_replication_plan as verify


def manifest_bytes():
    return json.dumps({
        "schema_version": 1,
        "task_set_id": "prospective-unseen-task-set-v2",
        "frozen_before_execution": True,
        "tasks": [
            {"id": f"new-{i:02d}", "category": "research",
             "question": f"New study question number {i}?"}
            for i in range(10)
        ],
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def plan_bytes(source):
    return (json.dumps(design.build_plan(source), indent=2,
                       sort_keys=True) + "\n").encode("utf-8")


def test_roundtrip_recomputes_every_field_without_model_calls():
    source = manifest_bytes()
    receipt = plan_bytes(source)
    result = verify.verify_plan(source, receipt)
    assert result["status"] == "pass"
    assert result["classification"] == (
        "prospective_design_verification_only_no_executions"
    )
    assert result["source_manifest_sha256"] == hashlib.sha256(source).hexdigest()
    assert result["design_receipt_sha256"] == design.build_plan(source)[
        "design_receipt_sha256"
    ]
    assert result["plan_file_sha256"] == hashlib.sha256(receipt).hexdigest()
    assert result["supplied_plan_file_pin_matched"] is False
    assert result["supplied_task_manifest_pin_matched"] is False
    assert result["historical_study_validated"] is False
    assert result["replication_or_human_validation_performed"] is False


def test_independently_supplied_file_digest_can_bind_exact_archived_bytes():
    source = manifest_bytes()
    receipt = plan_bytes(source)
    digest = hashlib.sha256(receipt).hexdigest()
    assert verify.verify_plan(
        source, receipt, expected_plan_file_sha256=digest
    )["supplied_plan_file_pin_matched"] is True
    with pytest.raises(design.DesignError, match="differs from supplied external pin"):
        verify.verify_plan(
            source, receipt, expected_plan_file_sha256="0" * 64
        )
    # A semantically identical but byte-different printing cannot pass the
    # independently supplied exact-file digest.
    compact = json.dumps(design.build_plan(source), sort_keys=True).encode()
    assert verify.verify_plan(source, compact)["status"] == "pass"
    with pytest.raises(design.DesignError, match="differs from supplied external pin"):
        verify.verify_plan(
            source, compact, expected_plan_file_sha256=digest
        )


def test_balanced_schedule_swap_with_recomputed_internal_hash_is_rejected():
    source = manifest_bytes()
    forged = design.build_plan(source)
    rows = forged["schedule"]
    left, right = next(
        (a, b) for a in range(10) for b in range(a + 1, 10)
        if rows[a]["arm_order"] != rows[b]["arm_order"]
    )
    rows[left]["arm_order"], rows[right]["arm_order"] = (
        rows[right]["arm_order"], rows[left]["arm_order"]
    )
    # Aggregate position, pairwise-precedence, and 40-cell checks still pass.
    # Recompute the receipt's self-hash as an adversarial coordinator might.
    forged.pop("design_receipt_sha256")
    forged["design_receipt_sha256"] = hashlib.sha256(
        verify._canonical_json(forged).encode("utf-8")
    ).hexdigest()
    with pytest.raises(design.DesignError, match="recomputed manifest-bound design"):
        verify.verify_plan(source, json.dumps(forged).encode())


def test_verifier_rejects_prospective_pseudoreplication_before_handoff():
    original = manifest_bytes()
    changed = json.loads(original)
    changed["tasks"][1]["question"] = changed["tasks"][0]["question"].upper()
    with pytest.raises(design.DesignError, match="normalized-equivalent questions"):
        verify.verify_plan(json.dumps(changed).encode(), plan_bytes(original))


def test_new_manifest_revision_does_not_verify_against_old_receipt():
    original = manifest_bytes()
    revised = json.loads(original)
    revised["tasks"][0]["question"] = "A different independent question?"
    with pytest.raises(design.DesignError, match="recomputed manifest-bound design"):
        verify.verify_plan(json.dumps(revised).encode(), plan_bytes(original))


@pytest.mark.parametrize("change", [
    lambda r: r.update(extra_field="surprise"),
    lambda r: r.update(task_count=True),  # True == 1 must NOT be accepted
    lambda r: r.update(task_count=10.0),  # 10.0 == 10 must NOT be accepted
    lambda r: r.update(historical_2026_study_replaced=0),
    lambda r: r["schedule"][0].update(task_id="different-new-task"),
    lambda r: r.update(pairwise_precedence_counts={}),
    lambda r: r.update(classification="historical_confirmatory_evidence"),
])
def test_tampered_receipt_fields_fail_closed(change):
    source = manifest_bytes()
    changed = design.build_plan(source)
    change(changed)
    with pytest.raises(design.DesignError, match="recomputed manifest-bound design"):
        verify.verify_plan(source, json.dumps(changed).encode())


@pytest.mark.parametrize("raw,pattern", [
    (b"", "outside supported range"),
    (b"x" * (verify.MAX_RECEIPT_BYTES + 1), "outside supported range"),
    (b"not json", "unambiguous UTF-8 JSON"),
    (b"[]", "recomputed manifest-bound design"),
    (b'{"status":"x","status":"x"}', "duplicate"),
    (b'{"value":NaN}', "nonstandard"),
    (b'{"value":1e999}', "not finite"),
    (b'{"value":' + b"9" * 129 + b"}", "unbounded"),
])
def test_invalid_receipt_json_and_input_bounds_fail_closed(raw, pattern):
    with pytest.raises(design.DesignError, match=pattern):
        verify.verify_plan(manifest_bytes(), raw)


@pytest.mark.parametrize("pin", ["", "A" * 64, "z" * 64, "0" * 63, 0, True])
def test_malformed_external_digest_pin_rejected(pin):
    source = manifest_bytes()
    with pytest.raises(design.DesignError, match="64 lowercase hex"):
        verify.verify_plan(
            source, plan_bytes(source), expected_plan_file_sha256=pin
        )


def test_cli_emits_only_digests_and_rejects_bad_file_or_symlink(
    tmp_path, monkeypatch, capsys
):
    source = manifest_bytes()
    receipt = plan_bytes(source)
    manifest_path = tmp_path / "tasks.json"
    receipt_path = tmp_path / "receipt.json"
    manifest_path.write_bytes(source)
    receipt_path.write_bytes(receipt)
    digest = hashlib.sha256(receipt).hexdigest()
    monkeypatch.setattr(sys, "argv", [
        "verify_counterbalanced_replication_plan.py",
        "--task-manifest", str(manifest_path),
        "--plan-file", str(receipt_path),
        "--expected-plan-file-sha256", digest,
    ])
    assert verify.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["supplied_plan_file_pin_matched"] is True
    assert "schedule" not in output
    assert list(tmp_path.iterdir()) == [manifest_path, receipt_path]

    symlink = tmp_path / "alias.json"
    symlink.symlink_to(receipt_path)
    monkeypatch.setattr(sys, "argv", [
        "verify_counterbalanced_replication_plan.py",
        "--task-manifest", str(manifest_path),
        "--plan-file", str(symlink),
    ])
    with pytest.raises(SystemExit) as exc:
        verify.main()
    assert exc.value.code == 2
    assert "bounded regular non-symlink" in capsys.readouterr().err

    receipt_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "verify_counterbalanced_replication_plan.py",
        "--task-manifest", str(manifest_path),
        "--plan-file", str(receipt_path),
    ])
    with pytest.raises(SystemExit) as exc:
        verify.main()
    assert exc.value.code == 2
    assert "recomputed manifest-bound" in capsys.readouterr().err


def test_external_source_pin_rejects_self_consistent_manifest_and_plan_replacement():
    original = manifest_bytes()
    original_pin = hashlib.sha256(original).hexdigest()
    revised = json.loads(original)
    revised["tasks"][0]["question"] = "A newly substituted future question?"
    altered = json.dumps(revised, sort_keys=True, separators=(",", ":")).encode()
    # Without separately preserved source custody, both candidate inputs
    # can be replaced together and still form a valid new schedule.
    assert verify.verify_plan(altered, plan_bytes(altered))["status"] == "pass"
    with pytest.raises(design.DesignError, match="task manifest SHA-256 differs"):
        verify.verify_plan(
            altered, plan_bytes(altered),
            expected_task_manifest_sha256=original_pin,
        )
    assert verify.verify_plan(
        original, plan_bytes(original),
        expected_task_manifest_sha256=original_pin,
    )["supplied_task_manifest_pin_matched"] is True


@pytest.mark.parametrize("pin", ["", "A" * 64, "z" * 64, "0" * 63, 0, True])
def test_invalid_external_task_source_pin_is_rejected(pin):
    source = manifest_bytes()
    with pytest.raises(design.DesignError, match="64 lowercase hex"):
        verify.verify_plan(
            source, plan_bytes(source), expected_task_manifest_sha256=pin,
        )


def test_source_pin_is_byte_exact_even_if_schedule_is_unchanged():
    source = manifest_bytes()
    formatted = (json.dumps(json.loads(source), indent=2, sort_keys=True) + "\n").encode()
    assert design.build_plan(source)["schedule"] == design.build_plan(formatted)["schedule"]
    with pytest.raises(design.DesignError, match="task manifest SHA-256 differs"):
        verify.verify_plan(
            formatted, plan_bytes(formatted),
            expected_task_manifest_sha256=hashlib.sha256(source).hexdigest(),
        )


def test_plan_cli_verifies_independently_preserved_source_pin(tmp_path, monkeypatch, capsys):
    source = manifest_bytes()
    manifest = tmp_path / "tasks.json"
    plan = tmp_path / "plan.json"
    manifest.write_bytes(source)
    plan.write_bytes(plan_bytes(source))
    monkeypatch.setattr(sys, "argv", [
        "verify_counterbalanced_replication_plan.py",
        "--task-manifest", str(manifest), "--plan-file", str(plan),
        "--expected-task-manifest-sha256", hashlib.sha256(source).hexdigest(),
    ])
    assert verify.main() == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["supplied_task_manifest_pin_matched"] is True
    assert "schedule" not in verified
