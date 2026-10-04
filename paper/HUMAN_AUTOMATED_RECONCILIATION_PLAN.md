# Automated–human reconciliation plan

Status: **frozen before collection and unblinding of human ratings**.

Study ID: `budget-main-v1`  
Frozen: **2026-10-04**

## Purpose and scope

This plan predeclares how VERA will reconcile its frozen automated support
analysis with the complementary blinded human evaluation. It exists so the
reconciliation method is not chosen after seeing which treatment or metric
looks favorable.

The automated analysis under `paper/ANALYSIS_PLAN.md` remains the study's
preregistered confirmatory analysis. Human ratings remain a separate
complementary validation layer under `paper/HUMAN_EVAL_ANALYSIS_PLAN.md`.
Reconciliation is descriptive only: it does not replace either analysis,
create a new primary outcome, or promote human validation into the automated
confirmatory family.

## Required verified inputs

Reconciliation may run only after both sides are independently verified:

1. `outputs/main_study_analysis_provenance.json` must pass
   `scripts/verify_analysis_provenance.py`, and the canonical automated JSON and
   Markdown must pass `scripts/verify_main_study_outputs.py`.
2. The human-analysis directory must pass
   `scripts/verify_human_eval_analysis_outputs.py`.
3. Both analyses must identify the same `budget-main-v1` study and the exact
   same ordered frozen task IDs.

No treatment or evaluator is rerun for reconciliation. Human ratings are never
generated, filled, or modified by this step.

## Measures retained

The automated measure is fixed to the preregistered primary outcome:

- `strict_support_rate`.

All five predeclared human dimensions are retained; none may be selected after
unblinding:

- correctness;
- completeness;
- source quality;
- synthesis/reasoning;
- clarity.

There is no combined automated–human quality score.

## Contrasts

Reconciliation uses only the three treatment contrasts already shared by the
automated and human plans:

1. `D6 - D3` — retrieval depth;
2. `P6 - D6` — explicit planning;
3. `P6V - P6` — treatment verification.

For every contrast and human dimension, compare the automated and human
task-level paired differences on the same frozen tasks.

## Missing human ratings

A task is comparable for a contrast/dimension only when the human analysis has
an observed paired difference for that task. Missing human pairs remain missing
and are reported explicitly. Automated values for non-comparable tasks are not
used to manufacture a human comparison, and no neutral or favorable human value
is imputed.

## Directional reconciliation

For every comparable task, classify the signs of the automated and human paired
differences using these exhaustive categories:

- `concordant_positive` — both favor the right-hand treatment;
- `concordant_negative` — both favor the left-hand treatment;
- `discordant` — nonzero effects point in opposite directions;
- `automated_tie` — automated difference is zero and human difference is nonzero;
- `human_tie` — human difference is zero and automated difference is nonzero;
- `both_tie` — both differences are zero.

Also report the six category counts and the **non-tie directional concordance**:

`(concordant_positive + concordant_negative) / (concordant_positive + concordant_negative + discordant)`

This quantity is undefined when there are no tasks with two nonzero directions
and must then be reported as missing/NA, not as zero or one.

For context, report the mean automated and mean human paired difference across
the comparable task subset and classify the relation between those two mean
directions with the same rule.

## What is deliberately not computed

This reconciliation adds:

- no human-validation null-hypothesis p-values;
- no new multiplicity family;
- no new confidence interval chosen after viewing human results;
- no correlation coefficient selected post hoc;
- no composite or weighted score combining automated and human outcomes;
- no threshold for declaring a treatment "validated".

The small ten-task design and ordinal human rubric make descriptive
task-paired agreement/disagreement more defensible than selecting a new
inferential target after unblinding.

## Interpretation rule

Automated strict support and human report quality measure different constructs.
Concordance strengthens qualitative confidence that the two measurement systems
tell a similar directional story for that dimension. Discordance is itself a
result and must be shown rather than resolved by choosing whichever metric
favours a treatment.

Human results cannot retroactively change the preregistered status of the
automated confirmatory analysis. Automated results cannot override human
quality judgments. Any analysis beyond this frozen reconciliation plan is
exploratory and must be labelled accordingly.

## Reproducibility

`scripts/reconcile_human_automated.py` implements this plan offline. It first
verifies both published analyses, requires exact task/contrast identity, then
writes a new create-only reconciliation bundle. The output fingerprints its
verified inputs, this plan, and the reconciliation implementation.

The script does not make network/model calls, regenerate treatments, rerun the
common evaluator, create human ratings, or alter any pilot, automated
confirmatory, exploratory, or human-validation result.
