"""Synthetic-only tests for the automated-human reconciliation readiness gate."""

import copy
import hashlib
import json
import os
import statistics

import pytest

from scripts import verify_human_reconciliation_readiness as readiness


def test_repository_reconciliation_contract_matches_frozen_anchor():
    content = (readiness.ROOT / readiness.CONTRACT).read_bytes()
    assert hashlib.sha256(content).hexdigest() == getattr(
        readiness,
        "FROZEN_RECONCILIATION_CONTRACT_SHA256",
        None,
    )


def test_repository_automated_receipt_uses_execution_bound_verification():
    content = (readiness.ROOT / readiness.AUTO_PROV).read_bytes()
    assert hashlib.sha256(content).hexdigest() != getattr(
        readiness,
        "FROZEN_LEGACY_AUTOMATED_PROVENANCE_SHA256",
        None,
    )
    payload = readiness._load(content, "automated provenance")
    assert set(payload["verified_execution"]) == {
        "runner",
        "execution_verifier",
        "input_validator",
    }


@pytest.mark.parametrize(
    "raw",
    [
        b'{"nested":{"status":"ambiguous","status":"valid"}}',
        b'{"nested":{"st\\u0061tus":"ambiguous","status":"valid"}}',
    ],
)
def test_readiness_loader_rejects_recursive_duplicate_json_members(raw):
    with pytest.raises(
        ValueError, match="synthetic analysis.*duplicate JSON key.*status"
    ):
        readiness._load(raw, "synthetic analysis")


def test_changed_contract_is_rejected_before_human_analysis_is_read(tmp_path):
    contract = tmp_path / "changed-contract.md"
    contract.write_bytes(b"post-freeze contract substitution\n")
    # The human root intentionally does not exist. Reaching it before the
    # contract anchor would therefore produce a regular-file error instead.
    with pytest.raises(ValueError, match="frozen reconciliation contract fingerprint"):
        readiness.verify_readiness(
            root=tmp_path,
            human_root=tmp_path / "human",
            contract=contract,
        )


def test_human_recomputation_uses_requested_checkout_paths(tmp_path, monkeypatch):
    root = tmp_path / "alternate-checkout"
    human_root = root / "outputs" / "human_eval" / "analysis-v1"
    observed = {}

    def fake_verify(output_root, **kwargs):
        observed["output_root"] = output_root
        observed.update(kwargs)

    monkeypatch.setattr(
        readiness.verify_human_eval_analysis_outputs,
        "verify_bundle_against_inputs",
        fake_verify,
    )

    readiness._verify_human_analysis_bundle(human_root, root=root)

    assert observed == {
        "output_root": human_root,
        "freeze_root": root / "outputs" / "human_eval" / "frozen-v1",
        "packet_root": root / "outputs" / "human_eval",
        "packet_path": root / "outputs" / "human_eval" / "packet.jsonl",
        "protocol_path": root / "paper" / "HUMAN_EVAL_PROTOCOL.md",
        "assignment_plan_path": root / "paper" / "HUMAN_EVAL_ASSIGNMENT_PLAN.md",
        "annotator_guide_path": root / "paper" / "HUMAN_EVAL_ANNOTATOR_GUIDE.md",
        "analysis_plan_path": root / "paper" / "HUMAN_EVAL_ANALYSIS_PLAN.md",
        "task_manifest_path": root / "experiments" / "main_budget_tasks.json",
        "repo_root": root,
    }


def test_selected_checkout_guide_bytes_are_forwarded_for_independent_recomputation(
    tmp_path, monkeypatch
):
    # This guide is a synthetic sentinel, not a collected annotation or a
    # replacement for the frozen research protocol.
    root = tmp_path / "selected-checkout"
    guide = root / "paper" / "HUMAN_EVAL_ANNOTATOR_GUIDE.md"
    guide.parent.mkdir(parents=True)
    guide.write_bytes(b"synthetic selected-checkout guide\\n")
    observed = []

    def fake_verify(output_root, **kwargs):
        selected = kwargs["annotator_guide_path"]
        assert selected == guide
        observed.append(selected.read_bytes())
        return {"independent_recomputation_verified": True}

    monkeypatch.setattr(
        readiness.verify_human_eval_analysis_outputs,
        "verify_bundle_against_inputs",
        fake_verify,
    )
    readiness._verify_human_analysis_bundle(
        root / "outputs" / "human_eval" / "analysis-v1", root=root
    )
    assert observed == [b"synthetic selected-checkout guide\\n"]


def test_missing_selected_checkout_guide_cannot_fall_back_to_ambient_checkout(
    tmp_path, monkeypatch
):
    root = tmp_path / "checkout-with-missing-guide"
    expected = root / "paper" / "HUMAN_EVAL_ANNOTATOR_GUIDE.md"

    def fake_verify(output_root, **kwargs):
        assert kwargs["annotator_guide_path"] == expected
        if not expected.is_file():
            raise ValueError("selected checkout guide missing")
        return {"independent_recomputation_verified": True}

    monkeypatch.setattr(
        readiness.verify_human_eval_analysis_outputs,
        "verify_bundle_against_inputs",
        fake_verify,
    )
    with pytest.raises(ValueError, match="selected checkout guide missing"):
        readiness._verify_human_analysis_bundle(
            root / "outputs" / "human_eval" / "analysis-v1", root=root
        )


def test_future_automated_receipt_requires_execution_layer_verification(
    tmp_path, monkeypatch
):
    payload = {"schema_version": 1, "verified_execution": {"runner": {}}}
    calls = {"execution": [], "recomputation": []}
    monkeypatch.setattr(
        readiness.verify_analysis_provenance,
        "verify_receipt",
        lambda receipt, root: pytest.fail("legacy-only verification was used"),
    )
    monkeypatch.setattr(
        readiness.verify_main_study_execution,
        "verify_execution_receipt",
        lambda receipt, root: calls["execution"].append((receipt, root)),
    )
    monkeypatch.setattr(
        readiness.verify_analysis_provenance,
        "verify_recomputed_outputs",
        lambda receipt, root: calls["recomputation"].append((receipt, root)),
    )

    readiness._verify_automated_provenance(
        json.dumps(payload).encode("utf-8"), root=tmp_path
    )

    assert calls == {
        "execution": [(payload, tmp_path)],
        "recomputation": [(payload, tmp_path)],
    }


def test_preserved_legacy_receipt_keeps_legacy_verification_path(tmp_path, monkeypatch):
    payload = {"schema_version": 1}
    content = json.dumps(payload).encode("utf-8")
    calls = []
    monkeypatch.setattr(
        readiness,
        "FROZEN_LEGACY_AUTOMATED_PROVENANCE_SHA256",
        hashlib.sha256(content).hexdigest(),
    )
    monkeypatch.setattr(
        readiness.verify_analysis_provenance,
        "verify_receipt",
        lambda receipt, root: pytest.fail("legacy receipt bypass helper was not used"),
    )
    monkeypatch.setattr(
        readiness,
        "_verify_preserved_legacy_receipt",
        lambda receipt, root: calls.append((receipt, root)),
    )
    monkeypatch.setattr(
        readiness.verify_main_study_execution,
        "verify_execution_receipt",
        lambda receipt, root: pytest.fail("legacy receipt required new execution field"),
    )

    readiness._verify_automated_provenance(content, root=tmp_path)

    assert calls == [(payload, tmp_path)]


def test_exact_pinned_legacy_receipt_remains_verifiable_after_verifier_evolution():
    root = readiness.ROOT
    receipt = readiness._load(
        (root / readiness.AUTO_PROV).read_bytes(),
        "automated provenance",
    )
    receipt.pop("verified_execution")
    receipt["schema_version"] = 1
    receipt["provenance_builder"]["sha256"] = (
        "19e012858767073dad0e9e2ae36f6dc659bcd85983d1e31f14f8099df224b28f"
    )
    receipt["verification_implementations"].pop("artifact_manifest")
    receipt["verification_implementations"].pop("artifact_fingerprinter")
    receipt["verification_implementations"]["provenance"]["sha256"] = (
        "100383c008923e4a4a4f9d433cfb556198b9bb4d6d381793283b84c8bcc6be4e"
    )
    receipt["verification_implementations"]["output_consistency"]["sha256"] = (
        "126a86eeb88a99d22f6e6689eeff387d75a4027534acd01fb75332aca1b77d87"
    )
    content = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    assert hashlib.sha256(content).hexdigest() == (
        readiness.FROZEN_LEGACY_AUTOMATED_PROVENANCE_SHA256
    )

    readiness._verify_automated_provenance(content, root=root)


def test_stripped_future_execution_binding_cannot_downgrade_to_legacy(
    tmp_path, monkeypatch
):
    payload = {"schema_version": 1, "verified_execution": {"runner": {}}}
    payload.pop("verified_execution")
    monkeypatch.setattr(
        readiness.verify_analysis_provenance,
        "verify_receipt",
        lambda receipt, root: pytest.fail("stripped receipt reached legacy verifier"),
    )

    with pytest.raises(ValueError, match="missing verified_execution"):
        readiness._verify_automated_provenance(
            json.dumps(payload).encode("utf-8"), root=tmp_path
        )


def _summary(diffs):
    return {
        "n_pairs": len(diffs),
        "mean_difference": statistics.mean(diffs) if diffs else None,
        "positive_tasks": sum(x > 0 for x in diffs),
        "negative_tasks": sum(x < 0 for x in diffs),
        "tied_tasks": sum(x == 0 for x in diffs),
    }


def _payloads():
    tasks = [f"main-{index:02d}" for index in range(1, 11)]
    base_diffs = [0.25, -0.5, 0.0, 0.25, -0.25, 0.5, 0.0, 0.25, -0.25, 0.0]
    automated = {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "n_tasks": len(tasks),
        "task_ids": tasks,
        "primary_outcome": "strict_support_rate",
        "primary_contrasts": {},
    }
    for name in readiness.CONTRASTS:
        automated["primary_contrasts"][name] = {
            **_summary(base_diffs),
            "task_differences": list(base_diffs),
        }

    human = {
        "schema_version": 1,
        "study_id": readiness.STUDY,
        "status": "human_validation_analysis",
        "analysis_scope": "complementary_not_main_confirmatory",
        "human_ratings_generated": False,
        "treatment_outputs_rerun": False,
        "hypothesis_tests": "none_predeclared_for_human_validation",
        "n_tasks": len(tasks),
        "task_ids": tasks,
        "dimensions": list(readiness.DIMS),
        "paired_contrasts": {},
    }
    for name in readiness.CONTRASTS:
        human["paired_contrasts"][name] = {}
        for dimension in readiness.DIMS:
            diffs = {task: base_diffs[index] for index, task in enumerate(tasks)}
            human["paired_contrasts"][name][dimension] = {
                **_summary(list(diffs.values())),
                "task_ids_included": list(tasks),
                "missing_pair_tasks": [],
                "task_differences": diffs,
            }
    return automated, human


def _readiness_case(tmp_path, monkeypatch, *, redirected_human_root=False):
    root = tmp_path / "checkout"
    contract = root / readiness.CONTRACT
    contract.parent.mkdir(parents=True)
    contract.write_bytes(b"frozen reconciliation contract\n")

    automated, human = _payloads()
    automated_path = root / readiness.AUTO_JSON
    provenance_path = root / readiness.AUTO_PROV
    automated_path.parent.mkdir(parents=True)
    automated_path.write_text(json.dumps(automated), encoding="utf-8")
    provenance_path.write_text("{}", encoding="utf-8")

    human_root = root / readiness.HUMAN_ROOT
    actual_human_root = tmp_path / "external-human" if redirected_human_root else human_root
    actual_human_root.mkdir(parents=True)
    (actual_human_root / "analysis.json").write_text(
        json.dumps(human), encoding="utf-8"
    )
    (actual_human_root / "analysis_manifest.json").write_text(
        "{}", encoding="utf-8"
    )
    if redirected_human_root:
        human_root.parent.mkdir(parents=True)
        human_root.symlink_to(actual_human_root, target_is_directory=True)

    monkeypatch.setattr(
        readiness,
        "FROZEN_RECONCILIATION_CONTRACT_SHA256",
        hashlib.sha256(contract.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(readiness, "_verify_automated_provenance", lambda *a, **k: None)
    monkeypatch.setattr(
        readiness.verify_main_study_outputs,
        "verify_outputs",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        readiness,
        "_verify_human_analysis_bundle",
        lambda *a, **k: {"independent_recomputation_verified": True},
    )
    return root, human_root, actual_human_root, contract


def test_readiness_rejects_same_byte_input_replacement_during_verification(
    tmp_path, monkeypatch
):
    root, human_root, actual_human_root, contract = _readiness_case(
        tmp_path, monkeypatch
    )
    analysis = actual_human_root / "analysis.json"
    original = analysis.read_bytes()

    def replace_after_capture(*args, **kwargs):
        replacement = actual_human_root / "replacement.json"
        replacement.write_bytes(original)
        os.replace(replacement, analysis)
        return {"independent_recomputation_verified": True}

    monkeypatch.setattr(
        readiness,
        "_verify_human_analysis_bundle",
        replace_after_capture,
    )

    with pytest.raises(ValueError, match="human_analysis changed during verification"):
        readiness.verify_readiness(
            root=root,
            human_root=human_root,
            contract=contract,
        )


def test_readiness_rejects_redirected_human_analysis_parent(tmp_path, monkeypatch):
    root, human_root, _, contract = _readiness_case(
        tmp_path,
        monkeypatch,
        redirected_human_root=True,
    )

    with pytest.raises(
        ValueError,
        match="human_analysis parent must be a regular directory",
    ):
        readiness.verify_readiness(
            root=root,
            human_root=human_root,
            contract=contract,
        )


def test_valid_synthetic_inputs_pass_without_computing_reconciliation_results():
    automated, human = _payloads()
    receipt = readiness.validate_payloads(automated, human)
    assert receipt["status"] == "automated_human_reconciliation_identity_valid"
    assert receipt["analysis_scope"] == "descriptive_reconciliation_only"
    assert receipt["human_ratings_generated"] is False
    assert receipt["treatment_outputs_rerun"] is False
    assert receipt["hypothesis_tests_added"] is False
    assert "results" not in receipt


def test_missing_human_pair_remains_explicit_and_is_not_imputed():
    automated, human = _payloads()
    name = readiness.CONTRASTS[0]
    dimension = readiness.DIMS[0]
    block = human["paired_contrasts"][name][dimension]
    missing_task = human["task_ids"][-1]
    block["task_ids_included"] = human["task_ids"][:-1]
    block["missing_pair_tasks"] = [missing_task]
    block["task_differences"].pop(missing_task)
    diffs = list(block["task_differences"].values())
    block.update(_summary(diffs))

    receipt = readiness.validate_payloads(automated, human)
    assert receipt["status"] == "automated_human_reconciliation_identity_valid"


def test_ordered_task_identity_mismatch_is_rejected():
    automated, human = _payloads()
    human["task_ids"] = list(reversed(human["task_ids"]))
    with pytest.raises(ValueError, match="ordered task identity mismatch"):
        readiness.validate_payloads(automated, human)


def test_human_missingness_must_partition_the_frozen_task_set():
    automated, human = _payloads()
    name = readiness.CONTRASTS[0]
    dimension = readiness.DIMS[0]
    human["paired_contrasts"][name][dimension]["missing_pair_tasks"] = [
        human["task_ids"][0]
    ]
    with pytest.raises(ValueError, match="partition frozen tasks"):
        readiness.validate_payloads(automated, human)


def test_human_task_difference_summary_drift_is_rejected():
    automated, human = _payloads()
    name = readiness.CONTRASTS[0]
    dimension = readiness.DIMS[0]
    human["paired_contrasts"][name][dimension]["mean_difference"] = 99.0
    with pytest.raises(ValueError, match="mean_difference inconsistent"):
        readiness.validate_payloads(automated, human)


def test_automated_difference_outside_strict_support_domain_is_rejected():
    automated, human = _payloads()
    result = automated["primary_contrasts"][readiness.CONTRASTS[0]]
    result["task_differences"][0] = 1.01
    result.update(_summary(result["task_differences"]))

    with pytest.raises(ValueError, match=r"outside \[-1\.0, 1\.0\]"):
        readiness.validate_payloads(automated, human)


def test_human_difference_outside_five_point_rubric_domain_is_rejected():
    automated, human = _payloads()
    result = human["paired_contrasts"][readiness.CONTRASTS[0]][readiness.DIMS[0]]
    task = human["task_ids"][0]
    result["task_differences"][task] = 4.01
    result.update(_summary(list(result["task_differences"].values())))

    with pytest.raises(ValueError, match=r"outside \[-4\.0, 4\.0\]"):
        readiness.validate_payloads(automated, human)


def test_boolean_summary_count_is_rejected_even_when_numerically_equal():
    automated, human = _payloads()
    result = human["paired_contrasts"][readiness.CONTRASTS[0]][readiness.DIMS[0]]
    included = human["task_ids"][:1]
    result["task_ids_included"] = included
    result["missing_pair_tasks"] = human["task_ids"][1:]
    result["task_differences"] = {
        task: result["task_differences"][task] for task in included
    }
    result.update(_summary(list(result["task_differences"].values())))
    result["n_pairs"] = True

    with pytest.raises(ValueError, match="n_pairs must be a non-negative integer"):
        readiness.validate_payloads(automated, human)


def test_posthoc_dimension_or_contrast_selection_is_rejected():
    automated, human = _payloads()
    name = readiness.CONTRASTS[0]
    human["paired_contrasts"][name].pop(readiness.DIMS[-1])
    with pytest.raises(ValueError, match="dimensions mismatch"):
        readiness.validate_payloads(automated, human)

    automated, human = _payloads()
    human["paired_contrasts"].pop(readiness.CONTRASTS[-1])
    with pytest.raises(ValueError, match="human contrast set mismatch"):
        readiness.validate_payloads(automated, human)
