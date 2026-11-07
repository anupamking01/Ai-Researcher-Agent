# Diagnostic pilot: provider-usage and frozen-price reconciliation

**Scope:** Only the diagnostic five-task pilot's *future local offline summaries* from `scripts/summarize_pilot.py`. Original pilot CSVs/reports, frozen ten-task automated measurements, retrospective exploratory analyses, and human-evaluation data are not modified.

## Failure mode and correction

The pilot estimator formerly converted model-level token counters using `int(value or 0)`, skipped malformed model buckets, and multiplied values by unchecked frozen pricing. Fractional, boolean, negative, or nonfinite values could therefore be coerced into plausible-looking costs or propagate as invalid numbers. A complete-looking run could also report one total-token denominator while its per-model provider ledger represented another.

The summarizer now requires exact **nonnegative integer** prompt/completion counters in every available model bucket, **finite nonnegative numeric** frozen input/output rates for every priced model with usage, and a **finite** resulting cost. Where a nonempty model usage map exists, it independently requires the trace's prompt, completion and combined totals to equal the per-model sums before constructing rows or publishing summaries. The cross-model accounting explicitly uses prompt plus completion; it does not substitute independently provider-reported total-token fields, which can differ in some APIs.

Malformed data raise an error **before either pilot summary output is published**, rather than silently truncating counts, dropping buckets, or producing impossible prices. Unknown model pricing still returns an explicit `unknown_model_price:<model>` uncosted status; missing/empty model ledgers remain uncosted rather than fabricated. The frozen rate table is never rewritten or updated. This does not verify external billing, cached-token discounts, long-context multipliers, or provider-reported usage authenticity.

## Reproduction

```bash
python -m pytest -q tests/test_pilot_cost_ledger_integrity.py tests/test_experiment.py
```

The ordinary offline/firewalled `tests` CI executes the tests without calling model providers or modifying past observations. Negative cases are synthetic, including fractional/negative/bool token counts, nonfinite rates, malformed model buckets, and inconsistent trace-vs-model totals. This integrity gate is not a new experiment, pilot outcome, confirmatory inference, exploratory treatment sensitivity result, or human validation.

**Remaining scientific gates are unchanged:** independently authenticated original ten-task reports/traces, source-verified blinded human handoff, actual independent annotations and agreement, and the previously disclosed treatment-order and automated-analysis-plan timing limitations.
