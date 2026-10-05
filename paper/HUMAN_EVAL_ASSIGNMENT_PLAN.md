# Human-evaluation assignment plan

Status: **frozen before collecting human ratings**.

Study: `budget-main-v1`

This document operationalizes the independent-rating requirement in Section 5 of `paper/HUMAN_EVAL_PROTOCOL.md`. It does not change the rubric, reveal treatment identity, or define treatment-level conclusions.

## Coverage rule

The full blinded packet is the reliability subset. Every blinded report in the 40-report main-study packet must be scored independently by at least **two distinct human annotators** before ratings are frozen or joined to treatment identities. Missing rubric dimensions remain governed by the frozen protocol and require a recorded reason. Duplicate rows from the same annotator do not count as independent ratings.

## Annotator eligibility and independence

Eligibility must be decided **before an annotator sees any study report or rating from another annotator**. An eligible annotator must:

- be a human evaluator able to read the English research questions and reports and apply the frozen 1–5 rubric;
- have no access to the coordinator-only blinding key, treatment labels, treatment-specific metadata, treatment-level human summaries, or other annotators' scores while producing independent ratings;
- not have generated, edited, or selected the treatment reports being rated;
- not use an LLM, automated evaluator, or another person to supply the human rubric scores;
- complete ratings independently, without discussing report scores with another annotator before the blinded freeze.

Prior familiarity with the project, repository, or research question is not by itself an exclusion if treatment identity remains concealed. Any material conflict or role that could reasonably reveal treatment identity must be recorded before assignment and resolved before ratings are accepted.

## Submission provenance and correction rule

Each annotator must submit ratings under a single stable `annotator_id`, and each submitted CSV must represent exactly one annotator. The coordinator must preserve every submitted file unchanged rather than combining rows from different annotators into a convenience file before the blinded freeze.

If an annotator discovers a clerical mistake **before** seeing another annotator's ratings, treatment identity, or treatment-level human summaries, a corrected submission may replace that annotator's prior submission only if the superseded file is retained and the replacement is documented while still blinded. Do not cherry-pick favorable rows across versions: replacement is whole-submission, not row-by-row. Once an annotator has seen another annotator's ratings or any treatment identity, their prior scores must not be revised for the frozen human-validation analysis.

This rule is about human-rating provenance, not statistical direction. It must be applied without inspecting whether a correction helps or hurts any treatment.

## Pre-unblinding exclusion rule

Annotator or row exclusions are permitted only for **objective protocol-validity failures documented while treatment identity is still blinded**. Examples include confirmed treatment-identity exposure before scoring, non-independent/copied ratings, automated or non-human score generation, duplicate submissions, or ratings that fail the frozen input-validity rules.

The following are **not** valid exclusion reasons:

- low inter-annotator agreement;
- unusually high, low, or extreme scores;
- disagreement with the automated support evaluator;
- scores that favor or disfavor a particular treatment after unblinding;
- failure to produce a desired statistical direction or narrative.

If a rating or annotator must be excluded for an allowed reason, preserve the original submitted file unchanged, record the reason and scope before unblinding, and obtain any replacement rating from a fresh eligible blinded annotator so that the coverage rule is still satisfied. Do not ask an excluded annotator to revise scores after seeing other ratings or treatment identity. Any deviation from these rules must be labeled as a protocol deviation and must not be silently incorporated into confirmatory or human-validation claims.

## Freeze gate

`scripts/freeze_human_eval_ratings.py` must fail closed if any packet item has fewer than two distinct annotators. A successful freeze records the SHA-256 fingerprint of this plan plus the required and observed rater coverage. Because the plan fingerprint is part of the blinded freeze manifest, later changes to eligibility or exclusion rules require a new versioned plan/freeze and must not be retroactively substituted for the rules governing an existing frozen dataset.

## Rationale and deviations

Full double-rating avoids post-hoc selection of an agreement subset and makes human-validation coverage auditable before unblinding. Predeclaring eligibility and exclusion rules prevents outcome-dependent removal of inconvenient raters or scores. If full double-rating cannot be completed, preserve the incomplete blinded data and document a versioned deviation before any treatment-level human analysis. This plan does not alter the frozen automated main-study analysis or its results.
