# Frozen automated–human reconciliation contract

Status: **frozen before collection and unblinding of human ratings**.

Study ID: `budget-main-v1`  
Frozen: **2026-10-04**

## Purpose

VERA already has a frozen automated confirmatory analysis and a separately frozen complementary human-evaluation analysis plan. The remaining research gate requires reconciling those two measurement systems after real blinded ratings exist. This contract fixes that reconciliation rule before any treatment-level human result can be inspected, so the method cannot be selected because it produces a favorable narrative.

The automated analysis under `paper/ANALYSIS_PLAN.md` remains the preregistered confirmatory analysis. Human ratings under `paper/HUMAN_EVAL_ANALYSIS_PLAN.md` remain complementary validation. Reconciliation is descriptive only and cannot replace either analysis, create a new primary outcome, or promote human validation into the automated confirmatory family.

## Verification gate

Reconciliation may occur only after the canonical automated analysis passes `scripts/verify_analysis_provenance.py` and `scripts/verify_main_study_outputs.py`, and the human-analysis bundle passes `scripts/verify_human_eval_analysis_outputs.py`. Both analyses must identify `budget-main-v1`, the same ordered frozen task IDs, and the same three treatment contrasts.

No treatment generation, common-evaluator run, rating generation, rating imputation, or post-unblinding rubric change is part of reconciliation.

## Fixed measures and contrasts

The automated measure is fixed to the preregistered primary outcome `strict_support_rate`. All five human dimensions are retained without post-hoc selection: correctness, completeness, source quality, synthesis/reasoning, and clarity. There is no combined automated–human quality score.

The only contrasts are `D6 - D3` for retrieval depth, `P6 - D6` for explicit planning, and `P6V - P6` for treatment verification. Each comparison is task-paired.

## Missingness

A task is comparable for a contrast/dimension only when the frozen human analysis contains an observed paired difference for that task. Missing human pairs remain missing and must be listed explicitly. Automated values for those tasks cannot be used to manufacture a human comparison, and no neutral or favorable human value may be imputed.

## Directional reconciliation

For each comparable task, compare the signs of the automated and human paired differences and use exactly one category: `concordant_positive`, `concordant_negative`, `discordant`, `automated_tie`, `human_tie`, or `both_tie`.

Report all six counts. Also report non-tie directional concordance as `(concordant_positive + concordant_negative) / (concordant_positive + concordant_negative + discordant)`. If that denominator is zero, report the value as missing/NA rather than forcing zero or one.

For context, report the mean automated and mean human paired difference over the comparable task subset and classify the relation between those two mean directions with the same rule. These summaries remain descriptive.

## Deliberately excluded analyses

This reconciliation adds no human-validation null-hypothesis p-values, no new multiplicity family, no confidence interval chosen after inspecting human results, no post-hoc correlation coefficient, no weighted/composite score, and no threshold for declaring a treatment validated. Any such analysis introduced after unblinding is exploratory and must be labelled accordingly.

## Interpretation

Automated strict support and human report quality measure different constructs. Concordance can strengthen qualitative confidence that the measurement systems tell a similar directional story for a dimension. Discordance is itself a result and must be retained rather than resolved by choosing whichever metric favours a treatment.

Human results cannot retroactively change the preregistered status of the automated confirmatory analysis, and automated results cannot override human quality judgments. Pilot, automated-confirmatory, exploratory, and human-validation claims remain distinct.

## Implementation requirement

Any future reconciliation implementation must follow this contract exactly, run offline, independently verify both published analysis bundles before comparison, require exact task/contrast identity, preserve missingness, and bind its output to verified input fingerprints plus this frozen contract. Execution is deliberately deferred until real blinded human-validation results exist.
