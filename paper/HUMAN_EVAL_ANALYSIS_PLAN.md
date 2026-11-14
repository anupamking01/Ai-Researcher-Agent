# Human-evaluation analysis plan

Status: **frozen before collection and unblinding of human ratings**.

Study ID: `budget-main-v1`  
Frozen: **2026-09-25**

## Scope

This plan governs treatment-level analysis of the blinded ratings defined by
`paper/HUMAN_EVAL_PROTOCOL.md`. Real human annotations are still pending when
this plan is frozen.

The automated strict-support analysis remains the study's preregistered
confirmatory analysis under `paper/ANALYSIS_PLAN.md`. Human ratings are a
**complementary validation layer**: they do not enter the automated Holm family,
replace automated outcomes, or justify selecting/rerunning treatment outputs.

## Unblinding gate

Treatment-level human analysis may begin only after:

1. the exact packet/key set passes `scripts/verify_human_eval_packet.py`;
2. every blinded report has at least two independent human annotators under
   `paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md`;
3. completed ratings are frozen while still blinded;
4. the freeze and archived raw rating inputs pass
   `scripts/verify_human_eval_freeze.py`.

The implementation must verify the blinded freeze **before** invoking any helper
that reads `blinding_key.csv`. The current plan supports exactly two annotators.
If more than two contribute, treatment-level analysis stops until a multi-rater
ordinal reliability statistic is predeclared while treatment identities remain
unopened.

## Analysis unit and aggregation

The analysis unit is one report for one frozen task/treatment cell, not one
annotator row. For each rubric dimension and report:

- retain original independent scores for agreement and raw distributions;
- report-level score = arithmetic mean of the **observed** independent 1–5
  ratings for that dimension;
- if every rating for that dimension is blank with a documented reason, the
  report-level score is missing;
- never impute a neutral, favorable, or treatment-derived value.

Means are accompanied by medians and raw 1–5 counts; interpretation must retain
the ordinal nature of the rubric.

All five frozen dimensions are analyzed without post-hoc selection: correctness,
completeness, source quality, synthesis/reasoning, and clarity. No dimension is
promoted post hoc to a new confirmatory primary outcome.

## Variant summaries

For each variant/dimension report total reports, reports with an observed score,
number of nonmissing original ratings, mean and median report-level score, and
raw independent-score counts for 1 through 5.

## Paired contrasts

Use the same task-paired contrasts as the automated study:

1. `D6 - D3` — retrieval depth;
2. `P6 - D6` — explicit planning;
3. `P6V - P6` — treatment verification.

For each dimension compute `right - left` on report-level scores within the same
frozen task. Include a task only when both report scores are observed. Report
included/missing task IDs, left/right means, paired mean and median difference,
positive/negative/tied task counts, task-level differences, and a deterministic
paired-bootstrap 95% percentile CI for the mean difference.

Use **20,000 paired bootstrap draws**, base seed `20260925`, with deterministic
offsets by contrast and dimension.

## Inference and agreement

No null-hypothesis p-values are predeclared for this human-validation layer.
Therefore no human p-value belongs to the automated main-study confirmatory
family and no multiplicity adjustment is reinterpreted. Emphasize effect sizes,
uncertainty, missingness, raw distributions, and task-level consistency.

Agreement is reported from `agreement.json`, generated **before unblinding** from
the original independent ratings. For exactly two annotators retain the frozen
raw exact agreement, mean absolute difference, and quadratic-weighted Cohen's
kappa. Do not recompute agreement after opening treatment identity; adjudicated
scores, if any, remain separate.

## Missingness, reconciliation, and deviations

Dimension blanks remain missing and pair counts may differ by dimension. Never
drop a task because its score is inconvenient. Post-unblinding departures from
this plan are exploratory and must be labeled as such.

Automated support and human ratings measure different constructs. Later
reconciliation must show all five predeclared human dimensions beside the frozen
automated results and report agreement or disagreement without choosing whichever
metric favors a treatment. Pilot, automated confirmatory, exploratory, and
human-validation claims remain distinct.

## Reproducibility

`scripts/analyze_human_eval.py` implements this plan offline. It fingerprints the
analysis plan, task manifest, packet manifest, coordinator key, freeze manifest,
frozen ratings, and pre-unblinding agreement artifact. It writes a new
create-only analysis directory containing `analysis.json` and `analysis.md`.
It makes no model/API calls, generates no ratings, and reruns no treatment or
automated evaluator.
