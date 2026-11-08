# Diagnostic pilot: independent arm-level operational summary audit

Newly produced pilot summaries use **schema version 3**. The independent
postrun validator now rebuilds the per-treatment descriptive means and
denominators from every manifest-selected, validated trace. The existing
schema-v1 paired operational audit and schema-v2 frozen-price/cost-coverage
audit still apply. No treatment rerun or result revision is involved.

This closes a distinct residual gap: a summary could previously preserve
correct trace counts, paired differences, frozen USD cost accounting and
cost-coverage denominators while publishing a false **single-arm mean**
(e.g., latency, prompt tokens, model calls, source attempts or report length),
or a false verified-only support mean/denominator.

## Contract and evidence boundary

For D6, P6 and P6V, the validator independently checks:

- Runs, completions, completion rates, verified-run counts and recorded
  provider-usage-complete counts.
- Means of source attempts, successful/failed sources, search/model calls,
  prompt/completion/total tokens, latency and report words.
- The **verified-only** mean of recorded support rates, using only source
  traces with a positive `verified_claim_count`. Unverified runs must not
  enter this denominator. No human scores are generated or inferred.
- Absent arms: zero observed runs and **null** means, not measured zeros.

A supplied invalid numeric value is rejected, including booleans, fractional
counters, negative or nonfinite measurements, and nonfinite means. Values are
not repaired or selected to improve results. This audit cross-checks the
*internal* source-to-summary relationship; it does not independently
authenticate original source custody, actual provider billing, retrieval
truth, or causal validity.

Schema versions 1 and 2 remain accepted with their original verified scope;
they are **not** retrospectively described as independently arm-audited.
The producer emits schema 3 so freshly created summaries cannot bypass the
stronger audit. All regression inputs are synthetic and offline.

Reproduce the focused tests:

```bash
python -m pytest -q tests/test_pilot_paired_summary_reconciliation.py -k "version3 or arm_metric"
```

The five-task pilot remains diagnostic. The 10-task automated main-study
findings remain frozen and historically qualified by unavailable
independently authenticated original treatment artifacts, fixed execution
order, evaluator-recovery measurement-policy comparability, and the
post-collection statistical plan. Retrospective sensitivities remain
exploratory. Two independent blinded human annotators and genuine human
ratings/agreement/reconciliation remain outstanding; this change supplies
none of those missing scientific results.
