"""Synthetic-only regressions for saved exploratory joint-bound source replay."""
from __future__ import annotations

import copy
import json

import pytest

from scripts import audit_human_eval_joint_missingness_bounds as joint
from scripts import verify_human_eval_joint_missingness_artifact as check
from test_human_eval_joint_missingness_bounds import _fixture


def _expected():
    # Entirely synthetic analysis. Never a human-evaluation result.
    result = joint.audit_joint_shared_arm_bounds(_fixture())
    result["verified_source"] = {
        "canonical_analysis_sha256": "a" * 64,
        "independent_recomputation_verified": True,
    }
    return result


def _raw(expected):
    return (json.dumps(expected, indent=2, sort_keys=True, allow_nan=False)
            + "\n").encode("utf-8")


def test_source_bound_replay_accepts_exact_synthetic_report():
    expected = _expected()
    receipt = check.verify_saved_bytes(_raw(expected), expected)
    assert receipt["same_implementation_replay_verified"] is True
    assert receipt["independent_human_analysis_recomputation_verified"] is True
    assert receipt["independent_sensitivity_arithmetic_verified"] is False
    assert receipt["source_canonical_human_analysis_sha256"] == "a" * 64
    assert len(receipt["saved_report_sha256"]) == 64


def test_json_whitespace_and_member_order_do_not_invalidate_report():
    expected = _expected()
    compact = json.dumps(expected, separators=(",", ":"), sort_keys=False).encode()
    assert check.verify_saved_bytes(compact, expected)["same_implementation_replay_verified"]


def test_altered_exploratory_bound_fails_even_when_source_hash_retained():
    expected = _expected()
    modified = copy.deepcopy(expected)
    name = next(iter(modified["bounds_by_contrast_and_dimension"]))
    dim = next(iter(modified["bounds_by_contrast_and_dimension"][name]))
    modified["bounds_by_contrast_and_dimension"][name][dim][
        "shared_arm_conditioned_all_task_bounds"
    ][0] = -0.25
    with pytest.raises(ValueError, match="disagree with verified-source replay"):
        check.verify_saved_bytes(_raw(modified), expected)


@pytest.mark.parametrize("edit", [
    lambda r: r.update(no_imputation_or_new_ratings=False),
    lambda r: r.update(classification="human_validation_confirmed"),
    lambda r: r.update(schema_version=True),
    lambda r: r.pop("verified_source"),
    lambda r: r["verified_source"].update(independent_recomputation_verified=False),
    lambda r: r.update(human_ratings_observed=True),
])
def test_tampered_claims_missing_binding_or_extra_claims_fail(edit):
    expected = _expected()
    modified = copy.deepcopy(expected)
    edit(modified)
    with pytest.raises(ValueError, match="disagree with verified-source replay"):
        check.verify_saved_bytes(_raw(modified), expected)


def test_bool_replacing_numeric_one_is_not_accepted_as_python_equal():
    expected = _expected()
    modified = copy.deepcopy(expected)
    modified["schema_version"] = True
    assert modified == expected  # Demonstrate Python dict equality's hazard.
    with pytest.raises(ValueError, match="disagree with verified-source replay"):
        check.verify_saved_bytes(_raw(modified), expected)


def test_duplicate_json_members_and_nonfinite_values_rejected():
    expected = _expected()
    for content, diagnostic in [
        (b'{"schema_version":1,"schema_version":1}', "duplicate JSON key"),
        (b'{"schema_version":NaN}', "non-finite numeric"),
        (b'{"schema_version":1e999}', "non-finite numeric"),
    ]:
        with pytest.raises(ValueError, match=diagnostic):
            check.verify_saved_bytes(content, expected)


def test_unverified_source_claim_fails_even_with_identical_saved_bytes():
    expected = _expected()
    bad = copy.deepcopy(expected)
    bad["verified_source"]["independent_recomputation_verified"] = False
    with pytest.raises(ValueError, match="source lacks verified"):
        check.verify_saved_bytes(_raw(bad), bad)


def test_spoofed_boolean_upstream_schema_is_not_accepted():
    expected = _expected()
    spoofed = copy.deepcopy(expected)
    spoofed["schema_version"] = True
    with pytest.raises(ValueError, match="classification/claim contract"):
        check.verify_saved_bytes(_raw(spoofed), spoofed)


def test_oversized_report_refused_before_json_decoding():
    expected = _expected()
    with pytest.raises(ValueError, match="bounded byte contract"):
        check.verify_saved_bytes(b"x" * (check.MAX_SAVED_REPORT_BYTES + 1), expected)


def test_verified_upstream_gate_runs_before_saved_file_capture(monkeypatch, tmp_path):
    calls = []

    def refuse(*args, **kwargs):
        calls.append("upstream")
        raise ValueError("no authentic human analysis")

    def capture(*args, **kwargs):
        calls.append("saved-report")
        return b"{}"

    monkeypatch.setattr(check.joint, "audit_verified_bundle", refuse)
    monkeypatch.setattr(check.freeze, "_capture_regular_input", capture)
    with pytest.raises(ValueError, match="no authentic human analysis"):
        check.verify_saved_report(tmp_path / "untrusted.json")
    assert calls == ["upstream"]


def test_capture_rejects_symlinked_saved_report_after_upstream_replay(
    monkeypatch, tmp_path,
):
    expected = _expected()
    target = tmp_path / "source.json"
    target.write_bytes(_raw(expected))
    alias = tmp_path / "alias.json"
    alias.symlink_to(target.name)
    monkeypatch.setattr(
        check.joint, "audit_verified_bundle", lambda *a, **k: expected
    )
    with pytest.raises(ValueError, match="regular file"):
        check.verify_saved_report(alias)


def test_real_saved_file_replayed_after_synthetic_upstream_stub(
    monkeypatch, tmp_path,
):
    expected = _expected()
    report = tmp_path / "saved.json"
    report.write_bytes(_raw(expected))
    monkeypatch.setattr(
        check.joint, "audit_verified_bundle", lambda *a, **k: expected
    )
    assert check.verify_saved_report(report)[
        "status"
    ] == "verified_exploratory_joint_missingness_replay"
