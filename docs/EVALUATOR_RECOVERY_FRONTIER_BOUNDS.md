# Evaluator-recovery policy: exploratory cost–quality frontier envelope

**Status:** Retrospective, read-only measurement-robustness analysis. **Not** prospective preregistration, a confidence interval, corrected automated inference, or human validation.

## Why this is distinct

The September 2026 recovery workflow supplied three post-hoc evaluator measurements **only** in P6V, and introduced a zero-successful-source input sentinel absent from the original evaluator revision. The previously published strict-support comparison bound shows how those three recorded scores could move the P6V–P6 macro difference if replaced arbitrarily between 0 and 1. That scalar contrast alone does not show whether the reported **descriptive quality–treatment-cost Pareto frontier** is insensitive to this measurement-policy split.

This audit uses the *same* three externally identified recovered cells (P6V/main-02, main-08, main-10), not a subset selected to affect conclusions. It preserves every frozen score, cost, estimate, p-value, and canonical manuscript artifact.

## Method

Require the historical evaluator-source/37+3 partition audit and both published CSV byte pins. Calculate per-treatment mean strict support by averaging each report's exact supported/checked fraction over **ten equal-weight tasks**, and average recorded **treatment-only** USD cost over the same ten tasks (exclude common-evaluator research overhead). Hold all 40 treatment costs and all 37 other support scores fixed. Independently allow each of the three recovered P6V scores to range over [0,1].

P6V quality therefore lies between the sum of its seven unchanged rates divided by ten and that quantity plus 3/10. No other treatment quality or cost can change under this defined stress test. At each endpoint, use the original Pareto rule: an arm is dominated when another costs no more and scores no worse, with at least one strict inequality.

With only **one** treatment's quality varying monotonically, that treatment may enter the frontier as its score increases, and other treatments may leave, but none can change in the reverse direction. Thus the union/intersection of **both** endpoint frontiers exactly identifies possible/guaranteed membership throughout this particular envelope; inspecting favorable individual replacements is unnecessary. Exact rational arithmetic avoids boundary mistakes.

## Retained-input result and reproduction

For the byte-pinned 40-cell **automated** summary, fixed treatment-cost means are D3 $0.04755828, D6 $0.05330990, P6 $0.05550018, P6V $0.08449294. The frozen automated mean strict-support scores are D3 67/80, D6 49/60, P6 63/80, P6V 173/240. The policy replacement envelope for P6V mean support is **7/12 to 53/60**. Consequently the observed and lower-endpoint Pareto frontiers contain **D3 alone**, while the upper endpoint contains **D3 and P6V**. D3 is guaranteed to remain on this descriptive frontier under the stated assumptions; P6V's membership is *possible*, not guaranteed.

To verify from a full-history checkout, without running models or treatments:

    python -m scripts.analyze_evaluator_recovery_frontier_bounds
    python -m pytest -q tests/test_evaluator_recovery_frontier_bounds.py

The historical-design-source audit workflow runs the verified entrypoint and retains a separate machine-readable receipt. Both CSVs must still match their published SHA-256, and the historical source-policy audit must pass before issuing a production receipt. The synthetic tests do not constitute new experimental observations.

## Exact frontier-entry threshold and minimum-replacement certificate

The endpoint envelope identifies *whether* P6V could appear on the descriptive
frontier, but not *how much* policy-sensitive measurement replacement would be
required. The same source-pinned audit now computes the exact boundary set by
non-more-expensive unchanged treatments. If the competing treatment is
**strictly cheaper**, P6V must have **strictly greater** quality; a quality
tie does not suffice. For an equal-cost competitor, equal quality is sufficient
when no cheaper arm has that quality. The audit checks this boundary using
exact fractions rather than rounded published rates.

For the retained inputs D3 is cheaper than P6V and has quality **67/80**.
P6V's seven held-fixed scores contribute **7/12** to its ten-task mean.
Therefore P6V could join the frontier only if the **sum** of its three
replacement scores were **strictly greater than 61/24** (approximately
2.5417 out of 3). Their published sum is **11/8**. The required total
increase is therefore **strictly greater than 7/6** across those three
scores (or **strictly greater than 7/60** in P6V's mean quality).

With at most **one** arbitrary replacement, the largest possible quality is
**197/240**, still below 67/80. With at most **two** replacements, the
largest possible quality is **103/120**, above 67/80; with all three, it is
**53/60**. Thus **at least two of the three historically recovered scores
would have to change** to make P6V enter the frontier within this unrestricted
[0,1] replacement model. This certificate follows by selecting the largest
gains `1 - observed_score` for each permitted replacement count; it does
not choose replacement outcomes or conduct new experiments.

These are purely algebraic stress-test thresholds, **not** evidence that two
real measurements were wrong, that such shifts are plausible, or that the
recovery policy caused any shift. The frozen descriptive frontier and all
primary inference remain unchanged.

## Claim limits

These are mathematically possible replacements, **not** observed policy-induced changes or credible distributions of unknown scores. No evidence establishes that any of the three published measurements is wrong, or that the sentinel changed an actual provider call. The envelope cannot diagnose the direction of any bias and excludes potential errors in the 37 held-fixed measurements or in treatment costs. It does not establish causal effects, independently authenticate missing original traces/reports, resolve fixed-order timing confounding, or retrospectively preregister the September analysis. Its "possible" frontier does **not** overturn the unchanged frozen descriptive result or justify changing a treatment's reported score.

The five-task pilot remains diagnostic, the ten-task frozen automated primary analysis remains historically qualified, this sensitivity is **exploratory**, and independent blinded human ratings/agreement/reconciliation remain outstanding.
