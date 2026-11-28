# Original research protocol versus realized study scope

**26 November 2026 — retrospective protocol-to-design crosswalk, not a new
analysis plan, experiment, or result.** The broad [research protocol](../paper/RESEARCH_PROTOCOL.md)
describes a larger intended experiment than the source-linked four-arm main
study. Preserve both the original protocol and the exact
[automated analysis plan](../paper/ANALYSIS_PLAN.md); this crosswalk records
which questions the realized design can address and which remain untested.

## Factor coverage and estimability

The [historical variant-factor audit](HISTORICAL_VARIANT_FACTOR_SOURCE_AUDIT.md)
establishes the planned factor settings below, not the authenticity of the
missing realized reports and traces. The eight rows are the minimum viable
matrix originally proposed in the broad protocol.

| Arm | Planning | Scheduled browse cap | Treatment verification | Historical main-study design |
| --- | --- | ---: | --- | --- |
| D3 | direct | 3 | none | included |
| D6 | direct | 6 | none | included |
| D12 | direct | 12 | none | not included |
| P3 | planner | 3 | none | not included |
| P6 | planner | 6 | none | included |
| P12 | planner | 12 | none | not included |
| D6V | direct | 6 | verify | not included |
| P6V | planner | 6 | verify | included |

The three designated primary contrasts describe D6 minus D3, P6 minus D6,
and P6V minus P6 on the selected tasks. They are conditional comparisons
at specific factor settings, not general marginal effects. In particular,
even if all four observed arm means were known without measurement error:

- A planning-by-verification interaction at browse cap 6 would require
  (P6V - P6) - (D6V - D6). D6V is absent. In a model with planning indicator
  P, verification indicator V, and their product P*V, the V and P*V
  columns are identical across the observed arms. An additive-only model
  cannot test the interaction it assumes away.
- A planning-by-retrieval interaction between caps 3 and 6 without
  verification would require (P6 - D6) - (P3 - D3). P3 is absent.
- A direct-mode diminishing-return comparison between caps 3, 6 and 12
  would require both (D6 - D3)/3 and (D12 - D6)/6. D12 is absent.
  A comparison of only two caps cannot establish curvature or saturation.
  These denominators are increments of the scheduled cap, not realized
  successful sources, tokens or cost.
- Neither a repair treatment nor a shared total-inference-budget
  allocation policy was tested. The observed descriptive Pareto frontier
  concerns only the four included configurations and the chosen endpoints.

These are outcome-independent missing-factor limitations, additional to the
[fixed-order treatment/position alias](MAIN_STUDY_DESIGN_IDENTIFIABILITY.md).
Pairing, regression, more ratings on the same reports, or narrower
confidence intervals cannot supply the absent factorial cells.

## Crosswalk of the original research questions and hypotheses

| Original item | Evidence available or planned | Unresolved claim boundary |
| --- | --- | --- |
| RQ1 / H1: planning, source diversity and completeness at low-to-medium budgets | P6 vs D6 at cap 6; retained retrieval/resource summaries; planned human completeness | No low-cap planner comparison; cannot identify where planning helps most. |
| RQ2 / H2: retrieval depth and diminishing returns | D6 vs D3 at direct/no verification; support and recorded resource summaries; planned human completeness | No cap-12 observations; cannot establish diminishing returns, an optimum, or causal returns per retrieved source. |
| RQ3 / H3: verification, support, coverage and overhead | P6V vs P6 at planner/cap 6; automated support and resource summaries; planned human completeness | No shared total-compute cap or repair condition; three recovered evaluator cells are concentrated in P6V. |
| RQ4: complementarity of planning and verification | Conditional verification contrast within planner mode | No D6V cell; interaction not identified. |
| RQ5: movement of failure modes | Retained operational counts and later exploratory diagnostics | Claim-level and qualitative failure attribution require original evidence; no general causal failure-transfer conclusion. |
| H4: moderate planning/retrieval and selective verification is optimal | Descriptive mean strict-support versus treatment-cost frontier among four arms | No selective/adaptive verification intervention, equal-cost allocation, or evidence of a globally optimal policy. |

The [historical measurement partition](HISTORICAL_EVALUATOR_MEASUREMENT_PARTITION.md)
and [retrieval exposure audit](MAIN_STUDY_RETRIEVAL_EXPOSURE.md) provide
additional qualifications. This crosswalk does not designate new primary
outcomes or classify any hypothesis as confirmed or rejected from its
coverage alone.

## Human measurement scope

The broad protocol also proposes independent human claim segmentation and
four-level claim-to-retrieved-evidence labels. The separately frozen
[human protocol](../paper/HUMAN_EVAL_PROTOCOL.md),
[annotator guide](../paper/HUMAN_EVAL_ANNOTATOR_GUIDE.md) and
[human analysis plan](../paper/HUMAN_EVAL_ANALYSIS_PLAN.md) instead specify
report-level ordinal ratings on five dimensions. The distribution contains
blinded question/report text, a ratings template and instructions; it does
not supply a separate matched set of historical evidence passages and
automated claim labels for human claim-by-claim verification.

Consequently, even successful genuine human ratings and the planned
[directional reconciliation](../paper/HUMAN_RECONCILIATION_FREEZE.md)
would provide complementary report-quality judgments and descriptive
directional concordance, not an estimate of the common evaluator's
claim-level classification accuracy, sensitivity, specificity, or
calibration. A high human correctness score is not an exhaustive
external factual audit, and report-level inter-rater agreement is not
agreement on individual automated support labels. The claim-label reference
study proposed in the broad protocol remains unperformed; any future
claim-level validation needs separately authorized and independently
specified sampling, evidence access and matching rules. Do not add it to
the frozen rubric, change the blinded instructions, or reuse its results
to select the original outcomes.

## Reporting and remaining gates

This coordinator/reviewer-facing crosswalk must not accompany annotator
packets. The five-task pilot remains diagnostic; the ten-task automated
analysis is frozen with designated primary contrasts, post-collection
analysis-plan timing and unverified outcome blinding at freeze (see
[required reporting cover](../paper/MAIN_STUDY_REPORTING_COVER.md)).
Retrospective diagnostics remain exploratory. Original report/trace
authentication, eligible independent human annotators, real blinded
ratings, agreement and reconciliation remain outstanding. No treatment,
evaluator or human rating was generated, no original result was replaced,
and no new treatment is authorized by this document.
