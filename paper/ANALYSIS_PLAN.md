# Main-study analysis plan

Status: **frozen before inspecting main-study outcome summaries**.

Study ID: `budget-main-v1`

## Purpose

The main study asks where a web-research agent should spend a limited computation budget: retrieval depth, explicit planning, or verification. The design is paired by task: the same 10 frozen live-web tasks are evaluated under D3, D6, P6, and P6V.

This document fixes the inferential analysis before outcome summaries are inspected. It is intentionally conservative because the task set is small (`n = 10` paired tasks) and is not an established public benchmark.

## Dataset-selection rule

1. The primary dataset is the **first treatment execution** that contains all 40 predeclared treatment cells (10 tasks x 4 variants), passes the repository's cardinality/provenance/budget validation, and has no treatment failures or timeouts.
2. If treatment execution is complete but the common evaluator is interrupted, evaluator-only recovery may fill missing evaluation records **without rerunning or replacing treatment outputs**. Recovery must use the same frozen evaluator model, prompt, claim cap, evidence restriction, temperature, and pricing policy.
3. A treatment run with zero successful retrieved sources is a valid experimental outcome, not missing data. It remains in the primary analysis and is scored under the common evaluator's no-evidence rule.
4. Later duplicate treatment executions are not substituted because their results look better. They may be reported only as accidental/confirmatory replications or sensitivity analyses.
5. No task or treatment cell may be excluded after outcomes are known unless a pre-existing validation/provenance rule marks it invalid. Any exclusion must be reported with its reason.

## Variants and predeclared contrasts

The three primary paired contrasts are:

1. **Retrieval depth:** D6 - D3.
2. **Planning:** P6 - D6.
3. **Verification:** P6V - P6.

Other pairwise contrasts are exploratory.

## Primary outcome

The primary outcome is each report's **strict support rate** from the common post-hoc evaluator:

`supported claims / claims checked`

The evaluator is measurement-only, uses the same rubric for all four variants, checks at most 12 claims per report, and is restricted to evidence retrieved by that treatment.

## Secondary outcomes

Secondary outcomes are:

- broad support rate: `(supported + partially_supported) / claims_checked`;
- unsupported-or-contradicted rate;
- successful retrieved sources;
- total model tokens;
- treatment-model cost in USD under frozen pricing;
- latency in seconds;
- model-call count;
- report word count.

Evaluator cost is reported as research measurement overhead and is not mixed into the deployment/treatment cost comparison.

## Statistical procedure

For each primary contrast and outcome, analysis is paired by task and the effect is `right - left`.

For the **primary outcome** the report will include:

- paired mean difference;
- paired median difference;
- deterministic paired bootstrap 95% percentile confidence interval for the mean difference;
- an exact two-sided sign-flip/randomization p-value over all `2^10` sign assignments when all 10 pairs are present;
- paired standardized mean difference (`d_z`) when the difference standard deviation is nonzero;
- number of positive, negative, and tied task-level effects.

The three primary p-values are adjusted together using the Holm step-down procedure. Both raw and adjusted values are reported. With only 10 tasks, confidence intervals and task-level consistency are emphasized over binary significance labels.

The same paired summaries may be produced for secondary outcomes, but their p-values, if shown, are exploratory and are **not** promoted to confirmatory claims.

## Cost-quality analysis

For each variant, report mean strict support and mean treatment cost. A variant is Pareto-dominated when another variant has at least as high mean strict support and no greater mean treatment cost, with one inequality strict. This analysis is descriptive and does not replace the paired primary contrasts.

## Missingness and failures

- Zero retrieved evidence is retained as an outcome.
- Missing saved evidence despite a trace claiming successful retrieval is a provenance failure and invalidates that evaluation cell until the provenance problem is resolved; it is not silently scored as zero evidence.
- Provider-usage accounting must be complete for included treatment and evaluator calls.
- Failed/timeout treatment cells prevent the dataset from being declared a complete primary dataset under the current workflow validation.

## Multiplicity and interpretation

Only the three strict-support contrasts listed above are confirmatory. Holm adjustment controls family-wise error across those three tests. All additional metrics, pairwise comparisons, subgroup patterns, and cost-quality observations are descriptive/exploratory unless a future independent replication predeclares them.

No claim of general superiority will be made from this 10-task original live-web set alone. Results will be framed as evidence within this task set and execution environment.

## Reproducibility

The inference script uses a fixed bootstrap seed (`20260914`) and requires the full balanced 10-task x 4-variant matrix. It emits machine-readable JSON plus a Markdown report. Raw traces, reports, evaluator outputs, frozen pricing, task manifest, and workflow provenance remain the source of truth.

## Human evaluation

Blinded human quality scoring remains a separate planned validation step. Automated support scoring must not be described as a substitute for human judgments of usefulness, completeness, readability, or overall report quality.
