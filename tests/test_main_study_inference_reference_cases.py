"""Independent synthetic reference cases for the frozen 10-task inference.

These are mathematical oracles, not empirical VERA findings. In particular,
they exercise the published two-sided sign-flip convention including ties and
the exactly-three-contrast Holm family without modifying the pinned historical
analysis implementation or rerunning any experiment.
"""
import pytest

from scripts import analyze_main_study as analysis


@pytest.mark.parametrize(
    ("differences", "expected_p"),
    [
        ([1.0] * 10, 2 / 1024),
        ([0.0] * 10, 1.0),
        ([3.0] + [0.0] * 9, 1.0),
        ([1.0, 2.0] + [0.0] * 8, 0.5),
    ],
)
def test_exact_ten_task_two_sided_signflip_reference_cases(differences, expected_p):
    # There are always 2^10 assignments under the preregistered complete
    # matrix, including zero-difference tasks; no nonzero-only subsetting.
    assert len(differences) == analysis.EXPECTED_TASKS == 10
    assert analysis._exact_signflip_pvalue(differences) == pytest.approx(expected_p)
    # Exact sign flips are invariant to task ordering and reversing the arm
    # orientation. These checks do not impose an invalid analogous claim on
    # seeded Monte Carlo bootstrap draws, which depend on index order.
    assert analysis._exact_signflip_pvalue(list(reversed(differences))) == pytest.approx(expected_p)
    assert analysis._exact_signflip_pvalue([-value for value in differences]) == pytest.approx(expected_p)


def test_frozen_inference_parameters_and_primary_family():
    assert analysis.EXPECTED_TASKS == 10
    assert analysis.BOOTSTRAP_SEED == 20260914
    assert analysis.BOOTSTRAP_DRAWS == 20_000
    assert analysis.PRIMARY_CONTRASTS == (
        ("D3", "D6", "D6_minus_D3_retrieval_depth"),
        ("D6", "P6", "P6_minus_D6_planning"),
        ("P6", "P6V", "P6V_minus_P6_verification"),
    )


def test_holm_three_contrast_reference_and_order_invariance():
    smallest = 2 / 1024
    values = [
        ("retrieval", smallest),
        ("planning", 0.5),
        ("verification", 1.0),
    ]
    expected = {
        "retrieval": 3 * smallest,
        "planning": 1.0,
        "verification": 1.0,
    }
    assert analysis._holm_adjust(values) == pytest.approx(expected)
    assert analysis._holm_adjust(list(reversed(values))) == pytest.approx(expected)


def test_constant_ten_task_paired_effect_is_directional_and_deterministic():
    left = [0.25] * 10
    right = [0.5] * 10
    forward = analysis._paired_summary(
        left, right, seed=analysis.BOOTSTRAP_SEED, exact_p=True
    )
    reverse = analysis._paired_summary(
        right, left, seed=analysis.BOOTSTRAP_SEED, exact_p=True
    )
    assert forward["mean_difference"] == pytest.approx(0.25)
    assert reverse["mean_difference"] == pytest.approx(-0.25)
    assert forward["bootstrap_95pct_ci_mean_difference"] == pytest.approx([0.25, 0.25])
    assert reverse["bootstrap_95pct_ci_mean_difference"] == pytest.approx([-0.25, -0.25])
    assert forward["exact_two_sided_signflip_p"] == pytest.approx(2 / 1024)
    assert reverse["exact_two_sided_signflip_p"] == pytest.approx(2 / 1024)
    assert forward["positive_tasks"] == 10
    assert reverse["negative_tasks"] == 10
    assert forward["paired_dz"] is None
    assert reverse["paired_dz"] is None


def test_all_tied_ten_task_summary_retains_ties_and_no_standardized_effect(monkeypatch):
    monkeypatch.setattr(analysis, "BOOTSTRAP_DRAWS", 250)
    tied = analysis._paired_summary(
        [0.75] * 10, [0.75] * 10,
        seed=analysis.BOOTSTRAP_SEED, exact_p=True
    )
    assert tied["n_pairs"] == 10
    assert tied["tied_tasks"] == 10
    assert tied["positive_tasks"] == tied["negative_tasks"] == 0
    assert tied["mean_difference"] == 0.0
    assert tied["paired_dz"] is None
    assert tied["bootstrap_95pct_ci_mean_difference"] == [0.0, 0.0]
    assert tied["exact_two_sided_signflip_p"] == 1.0
