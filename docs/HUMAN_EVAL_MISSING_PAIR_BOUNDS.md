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

These bounds vary **missing paired tasks only**. A pair with one observed
rater score per side stays included with its frozen observed-rater report means;
the unobserved second rater is **not** varied. Consequently the envelope is
not a full missing-rater sensitivity interval. When one of two reports on an
omitted pair was observed, using [-4,+4] is intentionally conservative rather
than the tightest possible interval.

The five-task historical pilot is diagnostic. The frozen automated September
2026 designated-primary analysis remains post-collection rather than
prospectively precollection preregistered, retains its fixed treatment-order
and evaluator-recovery comparability limitations, and is **not** modified.
Historical retrospective analyses remain exploratory. No human ratings,
agreement or automated–human reconciliation results currently exist; these
synthetic regression tests are **not** human-validation results.
