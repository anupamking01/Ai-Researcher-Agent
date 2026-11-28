"""Adversarial offline checks for the archived two-objective Pareto claim.

The tests use only retained CSV/JSON evidence and synthetic objective vectors.
They do not call providers, rerun treatments, or change frozen results.
"""
import copy
from fractions import Fraction
from functools import lru_cache
import json

import pytest

import scripts.audit_primary_inference_independently as audit
from scripts.validate_main_study_inputs import read_csv_rows


# Keep input-tampering tests affordable: the separate primary-bootstrap tests
# already exercise the original 20,000-draw estimator. All altered payloads
# below preserve the identical primary task vectors.
_original_bootstrap = audit._bootstrap_percentile_interval


@lru_cache(maxsize=3)
def _cached_primary_bootstrap(values, seed, draws):
    return _original_bootstrap(list(values), seed=seed, draws=draws)


@pytest.fixture(autouse=True)
def reuse_primary_bootstrap_for_pareto_tests(monkeypatch):
    monkeypatch.setattr(
        audit, "_bootstrap_percentile_interval",
        lambda differences, *, seed, draws: _cached_primary_bootstrap(
            tuple(differences), seed, draws
        ),
    )


@pytest.fixture(scope="module")
def frozen_evidence():
    return (
        read_csv_rows(audit.ROOT / "outputs/main_study_runs.csv"),
        read_csv_rows(audit.ROOT / "outputs/posthoc_support_runs.csv"),
        json.loads((audit.ROOT / "outputs/main_study_inference.json").read_text()),
    )


def test_archived_pareto_matches_raw_cost_and_strict_support(frozen_evidence):
    assert audit.audit_primary(*frozen_evidence)["cost_quality_pareto_checked"] is True


def test_rejects_false_frontier_even_if_all_means_remain_correct(frozen_evidence):
    main, evaluator, recorded = frozen_evidence
    changed = copy.deepcopy(recorded)
    changed["cost_quality_pareto"]["frontier"] = ["D6"]
    with pytest.raises(ValueError, match="Pareto mismatch: frontier"):
        audit.audit_primary(main, evaluator, changed)


def test_rejects_wrong_dominance_relation_without_changing_means(frozen_evidence):
    main, evaluator, recorded = frozen_evidence
    changed = copy.deepcopy(recorded)
    changed["cost_quality_pareto"]["dominated_by"]["P6"] = ["D6"]
    with pytest.raises(ValueError, match="dominated_by\\[P6\\]"):
        audit.audit_primary(main, evaluator, changed)


def test_rejects_misleading_scope_note_claiming_evaluator_cost(frozen_evidence):
    main, evaluator, recorded = frozen_evidence
    changed = copy.deepcopy(recorded)
    changed["cost_quality_pareto"]["note"] = "Evaluator cost included"
    with pytest.raises(ValueError, match="cost scope note"):
        audit.audit_primary(main, evaluator, changed)


def test_rejects_missing_or_extra_pareto_variant_mapping():
    strict = {variant: Fraction(1) for variant in audit.VARIANTS}
    cost = {variant: Fraction(1) for variant in audit.VARIANTS}
    malformed = {
        "frontier": list(audit.VARIANTS),
        "dominated_by": {"D3": []},
        "note": audit.PARETO_NOTE,
    }
    with pytest.raises(ValueError, match="dominated_by schema"):
        audit._audit_cost_quality_pareto(malformed, strict, cost)


def test_equal_objectives_are_not_mistaken_for_dominance():
    strict = {variant: Fraction(1, 2) for variant in audit.VARIANTS}
    cost = {variant: Fraction(1, 5) for variant in audit.VARIANTS}
    audit._audit_cost_quality_pareto(
        {
            "frontier": list(audit.VARIANTS),
            "dominated_by": {variant: [] for variant in audit.VARIANTS},
            "note": audit.PARETO_NOTE,
        },
        strict, cost,
    )


def test_pareto_tradeoff_and_strict_cost_improvement_both_preserved():
    strict = {
        "D3": Fraction(1, 2), "D6": Fraction(1, 2),
        "P6": Fraction(3, 4), "P6V": Fraction(1, 2),
    }
    cost = {
        "D3": Fraction(1), "D6": Fraction(1),
        "P6": Fraction(2), "P6V": Fraction(1, 2),
    }
    audit._audit_cost_quality_pareto(
        {
            "frontier": ["P6", "P6V"],
            "dominated_by": {
                "D3": ["P6V"], "D6": ["P6V"], "P6": [], "P6V": [],
            },
            "note": audit.PARETO_NOTE,
        },
        strict, cost,
    )
