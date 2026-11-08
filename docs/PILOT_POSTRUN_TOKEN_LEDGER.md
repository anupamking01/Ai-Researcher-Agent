# Diagnostic-pilot postrun provider token conservation

## Methodological gap

The independent postrun artifact validator previously accepted a positive
`trace.total_tokens` and `provider_usage_complete` label without comparing
the total to observed prompt/completion token counts or to the recorded
`provider_usage_by_model` accounting. A self-consistent treatment/task matrix
could therefore pass with an inflated or understated usage denominator.
The standalone summarizer already performs its own provider-ledger check;
this adds the missing **independent CI validity gate**.

## Fail-closed validation

For the producer's schema-v2 JSON traces, the validator requires exact
nonnegative integer prompt, completion, and total tokens; checks
`total_tokens = prompt_tokens + completion_tokens`; requires a present
mapping of per-model usage with explicit integer token categories; and
reconciles the sums across models to both run-level categories.
Malformed model buckets, boolean/fractional/missing counts, empty ledgers
claiming complete usage, and malformed schema markers are rejected.

For historical unversioned minimal fixture/checkpoint records that never
supplied detailed token fields, the older compatibility behavior is
retained **without claiming independent ledger verification**. Whenever
an unversioned record supplies token-accounting fields, incomplete or
contradictory observations are still rejected. No token counts are inferred
and no external provider prices are consulted.

Reproduce offline:

```sh
python -m pytest -q tests/test_pilot_postrun_token_ledger.py
```

These are entirely synthetic regression cases. No pilot treatment, automated
support evaluator, frozen result, exploratory analysis, or human rating is
rerun or altered. The five-task pilot remains diagnostic. The frozen automated
main study remains qualified by unavailable independently authenticated
original source artifacts, fixed treatment ordering, and post-collection
analysis-plan timing; retrospective sensitivity analyses remain exploratory,
and real blinded human validation remains pending. This audit establishes
internal accounting consistency only, not independent provider-billing
authenticity or recovery of historical evidence.
