# Human-evaluation assignment plan

Status: **frozen before collecting human ratings**.

Study: `budget-main-v1`

This document operationalizes the independent-rating requirement in Section 5 of `paper/HUMAN_EVAL_PROTOCOL.md`. It does not change the rubric, reveal treatment identity, or define treatment-level conclusions.

## Coverage rule

The full blinded packet is the reliability subset. Every blinded report in the 40-report main-study packet must be scored independently by at least **two distinct human annotators** before ratings are frozen or joined to treatment identities. Missing rubric dimensions remain governed by the frozen protocol and require a recorded reason. Duplicate rows from the same annotator do not count as independent ratings.

## Freeze gate

`scripts/freeze_human_eval_ratings.py` must fail closed if any packet item has fewer than two distinct annotators. A successful freeze records the SHA-256 fingerprint of this plan plus the required and observed rater coverage.

## Rationale and deviations

Full double-rating avoids post-hoc selection of an agreement subset and makes human-validation coverage auditable before unblinding. If full double-rating cannot be completed, preserve the incomplete blinded data and document a versioned deviation before any treatment-level human analysis. This plan does not alter the frozen automated main-study analysis or its results.
