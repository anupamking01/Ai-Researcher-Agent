# Human-validation shared-arm original-rating consistency

## Problem and research scope

VERA's complementary, treatment-aware human-validation output reports nine
original-rater coverage categories (0/0 through 2/2) for every frozen paired
contrast, task, and rubric dimension. A contrast-local partition and its
reported number of complete pairs can be internally valid even when two
contrasts contradict each other about the **same original report rating**.

In the frozen design, D6 is the right arm of D6–D3 and the left arm of P6–D6;
P6 is the right arm of P6–D6 and the left arm of P6V–P6. Each shared arm has
one actual blinded report per task and dimension. It cannot legitimately
have two observed independent scores in one contrast and one (or zero) in
the other. This previously escaped the lightweight standalone bundle
identity check even though full verification against retained ratings could
recompute and detect a changed result.

## New fail-closed identity check

For every declared `(variant, task_id, rubric_dimension)`, the verifier now
collects its original-rater count from all contrast category memberships. If
any later occurrence disagrees, verification fails with a
`cross-contrast shared-arm mismatch` error. Category membership and
paired-denominator checks run first, so this catches specifically the
cross-contrast contradiction rather than rejecting valid missingness.

- 0, 1 and 2 remain the only admitted observed-rating counts.
- A report with at least one observed score on each side remains in a pair;
  a zero-score side remains excluded. No imputation or post-hoc filtering.
- A count may differ by rubric dimension, but not by contrast for the same
  treatment, report, and dimension.
- D3 and P6V occur in only one predeclared contrast; the gate does not
  manufacture additional pairings for them.
- All input evidence and statistical estimands remain frozen. The addition
  verifies reporting consistency; it does not calculate new results.

## Synthetic regression coverage

Tests exercise inconsistent D6 and P6 denominators (both partial and absent
ratings), consistent partial and zero-rating cases, dimension-specific
missingness, independent endpoints, and the analysis identity preflight.
These are synthetic control fixtures, **not** collected human annotations or
experimental outcomes.

## Limits

This check does not prove that reported ratings are authentic, that annotators
were independent, or that provenance hashes match original submissions.
Full `verify_bundle_against_inputs` remains necessary to recompute against
retained, verified human-evaluation inputs. Genuine blinded independent
ratings, measured agreement, reconciliation with automated support, and
appropriately limited conclusions remain pending. Automated confirmatory
results, diagnostic pilot evidence and exploratory analysis are distinct from
human validation.
