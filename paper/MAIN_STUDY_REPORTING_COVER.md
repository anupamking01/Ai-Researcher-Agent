# VERA main-study reporting cover — analysis-plan timing qualification

**Status (7 November 2026):** This is a noncanonical, source-linked reporting
qualification for the unchanged [September 24 main-study results](MAIN_STUDY_INFERENCE.md).
It adds no experiment, outcome, p-value, human rating, or replacement analysis.

## Required qualification when citing the frozen main-study report

The historical report uses the phrase **"three preregistered strict-support
contrasts"**. That wording is preserved as part of the original published
artifact, **not** endorsed as proof of prospective statistical preregistration.

The broad research protocol preceded treatment execution on September 11, 2026.
The exact paired statistical-analysis plan entered Git on September 14, **after**
treatment execution and the September 13 common-evaluator recovery, but before
canonical results were published on September 24. Consequently, **prospective
precollection statistical preregistration is not established**, and **outcome
blinding at the September 14 freeze is not established**. These facts do not
prove that the researcher inspected outcomes before writing the plan. See the
[source-linked chronology and full-history audit](../docs/MAIN_STUDY_ANALYSIS_FREEZE_CHRONOLOGY.md).

The three comparisons are **designated primary contrasts** of a frozen
**post-collection, pre-canonical-publication analysis**. The paired estimates,
confidence intervals, exact sign-flip arithmetic, and Holm-adjusted p-values
remain unchanged. They are not evidence of randomized treatment assignment:
**fixed-order temporal confounding** remains unresolved.

The **five-task pilot remains diagnostic**; the **ten-task automated analysis
is frozen but methodologically qualified**; **post-hoc exploratory diagnostics
remain exploratory**; **human validation remains pending**. The original
40 treatment reports and traces are not independently authenticated; original
source custody remains unverified. No human ratings or inter-annotator
agreement have been collected. This cover does not close evidence-recovery or
blinded-distribution gates.

## Separate human-evaluation analysis-plan chronology

The [human-evaluation analysis plan](HUMAN_EVAL_ANALYSIS_PLAN.md) was committed
on **25 September 2026**, after the automated canonical publication. It was
frozen before collection of human ratings, which remain pending. Its historical
description of the automated strict-support analysis as **"preregistered
confirmatory"** is preserved as written, but this later human-evaluation plan
**does not retroactively establish prospective** precollection statistical
preregistration for the earlier automated experiment. The September 14 exact
automated plan still postdates the September 11 treatments and September 13
evaluator recovery; neither plan proves outcome blinding. This qualification
is required when citing the human-evaluation plan beside automated results.

**Citation practice:** Accompany the historical
[main-study inference report](MAIN_STUDY_INFERENCE.md) with this cover and
[the chronology audit](../docs/MAIN_STUDY_ANALYSIS_FREEZE_CHRONOLOGY.md).
Do not edit the immutable historical report to silently replace its wording.

## Interpretation of the paired inferential reference distribution

The frozen exact sign-flip p-values enumerate signs of the ten paired task
differences. Within every historical task the treatment order was fixed:
D3, D6, P6, then P6V. No randomized allocation of treatment to execution
position occurred. Accordingly, the sign-flip reference distribution is
**not justified by the design as a randomization test of causal treatment
effects**. Its inferential calibration instead depends on assumptions such as
sign exchangeability/symmetry of the paired differences, which the historical
data and fixed order do not establish. Holm adjustment addresses multiplicity;
it cannot establish exchangeability, remove temporal confounding, or repair
the post-collection analysis-plan chronology.

The paired-bootstrap confidence intervals resample the ten selected tasks.
They do not establish representative sampling from a wider task population,
stable live-web conditions, or coverage for a causal treatment effect.
Neither these qualifications nor the source-recovery gap changes any saved
estimate, exact sign-flip calculation, confidence interval, or adjusted
p-value. Cite them as methodologically qualified calculations, not as
randomized causal evidence or independently preregistered confirmation. See
the [exact design-rank audit](../docs/MAIN_STUDY_DESIGN_IDENTIFIABILITY.md).

## Measurement comparability and scope (27 November 2026)

The common support measurement was intended to be separate from treatment
verification, but the historical evaluator-only recovery changed the
empty-evidence input policy. The historical workflow specifies three recovered
cells, all in P6V (main-02, main-08, main-10). The frozen summary records
`retrieved_evidence` for the first two and `zero_successful_sources` for
main-10; the other 37 evidence-status fields are unspecified. This
**arm-concentrated evaluator-policy difference** limits comparability,
particularly P6V versus P6; neither actual provider input nor bias direction
or magnitude is established. Do not exclude, replace or re-score these cells.
See the [source-to-summary partition audit](../docs/HISTORICAL_EVALUATOR_MEASUREMENT_PARTITION.md).
The [replacement-envelope frontier analysis](../docs/EVALUATOR_RECOVERY_FRONTIER_BOUNDS.md)
is exploratory, not a correction to the observed frozen descriptive frontier.

Strict support measures the historical model's judgments against retrieved
evidence, not independently established factual accuracy. The
[historical evaluator source audit](../docs/HISTORICAL_COMMON_EVALUATOR_SOURCE_POLICY.md)
documents permissive raw-response normalization and requested-versus-returned
model identity limitations; valid normalized counts do not establish
raw-response schema compliance, resolved model identity or claim-label accuracy.
The [task-freeze audit](../docs/MAIN_STUDY_TASK_FREEZE_CHRONOLOGY.md) also
establishes that the historical live-web pipeline did not independently
enforce main-09's September 1 information cutoff; actual cutoff compliance
is unknown. The ten selected questions have one question per category.

The [original protocol scope crosswalk](../docs/MAIN_STUDY_PROTOCOL_SCOPE.md)
distinguishes four realized configurations from the eight originally proposed.
The scheduled browse caps are not equal total compute; missing factorial cells
preclude estimating planning-by-verification interactions, retrieval curvature
or an optimal allocation policy. The descriptive cost-quality frontier is
limited to the included configurations and measured endpoints; estimated costs
are not authenticated provider bills.

The planned five-dimension human ratings address report-level quality.
Even if genuinely collected, they would not by themselves establish
**claim-level classification accuracy** of the automated support evaluator.
The independent claim-level reference study remains unperformed. These
qualifications apply to the historical automated results without changing
the frozen analysis or authorizing any new treatment or rating collection.
