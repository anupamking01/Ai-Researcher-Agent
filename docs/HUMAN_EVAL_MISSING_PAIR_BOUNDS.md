# Exploratory bounds for missing human-evaluation task pairs

**Status: post-freeze ancillary sensitivity tool, not a change to the frozen human
analysis plan, statistical estimand, treatment outcomes, or human ratings.**

## Purpose

The frozen human analysis averages **observed** original rater scores within
each report and includes a paired task if each treatment report has at least
one observed score. A complete-case paired mean may therefore be sensitive to
which tasks are missing. The existing nine-cell rater-coverage table identifies
that missingness; it does not quantify how much the omitted task *pairs* could
change the all-ten-task mean contrast.

`scripts/audit_human_eval_missing_pair_bounds.py` computes conservative
**worst-case mathematical bounds**, separately for all three frozen contrasts
and all five rubric dimensions, using the established 1–5 range:

- Hold each observed paired task difference `right - left` exactly as reported.
- For each task absent from the paired analysis, let the unknown difference be
  anywhere in **[-4, +4]**, regardless of which side is missing.
- Add the observed differences to the worst-case endpoints and divide by **10**,
  the fixed frozen task count. No task is preferentially selected or rerun.

If `S` is the sum of differences for `k` included pairs, the reported envelope
is **[(S − 4(10−k))/10, (S + 4(10−k))/10]**. It is an identified
range under the score bounds alone, **not** a confidence interval, bootstrap
result, effect estimate for actually missing observations, p-value, or
recommendation to impute scores. It can include both signs even when the
observed-pair mean has one sign. When all ten pairs are observed the envelope
collapses to the originally reported paired mean.

The calculation uses exact integer half-point units internally. It fails
closed on an altered ten-task inventory, incomplete contrast/dimension
coverage, missing/duplicate task IDs, an inconsistent paired denominator,
a non-rubric score difference, or disagreement with the reported observed mean.

## Additional exploratory sensitivity: missing original second-rater scores

The same verified human-analysis record supplies a **nine-cell original-rater
coverage partition** for every contrast and dimension. The auditor now checks
that the counts and task IDs partition all ten tasks without duplicates and
that the presence or absence of report scores agrees with paired inclusion.
Missing coverage is rejected rather than treated as complete.

Besides the original fixed-observed-pair envelope above, the independent
`hypothetical_two_rater_completion_bounds` asks a **different counterfactual
question**: how much could the all-ten-task mean contrast change if every
report on an *already included* task had both planned human ratings, rather
than only its observed rating(s)? For an observed task difference `d` with
`q` unobserved second-rater slots across the two reports (0, 1, or 2),
each missing second rating could change its report's two-rater mean by at
most 2 points. Thus the hypothetical paired difference is conservatively
bounded by **[max(-4, d - 2q), min(4, d + 2q)]**. Every excluded task pair
still contributes [-4, +4]. The ten task-level lower/upper endpoints are
summed and divided by ten with exact half-point-unit arithmetic. Original
paired differences, missing-pair counts and the frozen paired bootstrap are
never changed.

This is a deliberately **conservative** envelope because the verified paired
summary exposes differences and original-rater counts, not the individual
observed report means needed for tighter endpoints. It requires no assumption
that absent scores are missing at random. It is **not a confidence interval,
a new planned estimand, evidence that another annotator would have provided a
score, a human finding, or a reason to discard partial observations**. The
completion envelope equals the original missing-pair envelope when all
included tasks are already 2/2 rated; with all ten tasks included and 2/2
rated, both collapse to the observed mean.

## Source-bound use, only after genuine ratings exist

Run the existing blinded-rating freeze, human analysis and independent analysis
verification procedures before requesting sensitivity output. With the
retained frozen raw rating inputs and canonical output layout in place:

```bash
python -m scripts.audit_human_eval_missing_pair_bounds \
  --output-root outputs/human_eval/analysis-v1 \
  --freeze-root outputs/human_eval/frozen-v1 \
  --packet-root outputs/human_eval
```

The exact analysis output directory should be taken from the actual analysis
publication; do not infer its name from this example. The CLI calls
`verify_bundle_against_inputs`, which independently recomputes the human
analysis from frozen original inputs. It then captures canonical
`analysis.json` and requires its SHA-256 to equal the verification receipt
**before** deriving bounds. The CLI only emits JSON on stdout; it never creates
or overwrites an analysis archive. Independent custody of the underlying
reports/annotator distribution is a separate, still-unmet research gate.

For unit tests only, `audit_missing_pair_bounds` accepts an in-memory synthetic
payload without a verification receipt. Such calls cannot establish provenance
or certify any real human observations.

## Scope limits

The original `worst_case_all_task_mean_difference` bound varies **missing
paired tasks only**; it holds all observed pairs fixed, even if a report has
only one original human rating. The separate *hypothetical* two-rater
completion bound additionally varies the unobserved second rating on
included pairs without changing any actually observed data. It remains
conservative rather than sharp. When one of the two reports on an excluded
pair was observed, both envelopes retain [-4,+4] rather than inferring an
unrecorded score. Neither envelope can replace independent human ratings,
pre-unblinding agreement, or validated report custody.

The five-task historical pilot is diagnostic. The frozen automated September
2026 designated-primary analysis remains post-collection rather than
prospectively precollection preregistered, retains its fixed treatment-order
and evaluator-recovery comparability limitations, and is **not** modified.
Historical retrospective analyses remain exploratory. No human ratings,
agreement or automated–human reconciliation results currently exist; these
synthetic regression tests are **not** human-validation results.

## Coverage-conditioned attainable completion envelope (ancillary)

The auditor additionally reports
`coverage_conditioned_two_rater_completion_bounds`. Unlike the prior
conservative `hypothetical_two_rater_completion_bounds`, this separate
envelope enumerates every **possible integer 1–5 observed score sum** on each
included task that agrees with its independently verified paired difference
and its original-rater counts (1/1, 1/2, 2/1, or 2/2). It then optimizes the
remaining one or two hypothetical second-rater scores over 1–5. All arithmetic
uses exact integer doubled differences; an impossible half-point difference
for two singly rated reports now fails closed.

This yields **attainable extrema conditional only on the published paired
difference and original-rater counts**, rather than allowing changes that
cannot arise from any combination of integer scores. It is generally narrower
than, or equal to, the original conservative envelope. In particular, it
preserves exact equality for fully double-rated pairs. Excluded pairs still
receive the deliberately broad [-4,+4] range, even if one report had a score.

The attainable extrema are **not necessarily sharp conditional on the
underlying raw annotations**, because the summary omits each report's observed
mean; those means could further constrain possible missing ratings. The tool
does not reconstruct real rating records, fill in missing ratings, replace the
frozen observed-pair estimand, compute a confidence interval, or establish
human validation. The established conservative envelope is retained unchanged
for audit continuity. Synthetic tests independently enumerate all four
planned integer ratings for each possible original-rater count pattern to
check the score-sum optimization, including infeasible combinations.

The five-task pilot remains diagnostic, historical automated designated-primary
inference is post-collection-planned and treatment-order/evaluator-qualified,
and retrospective sensitivities (including both completion envelopes) are
exploratory, not prospective confirmatory or human-validation findings.
