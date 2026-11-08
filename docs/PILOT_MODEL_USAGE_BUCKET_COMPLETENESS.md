# Diagnostic-pilot provider-usage bucket completeness

## Research-integrity gap

The standalone offline pilot summarizer reconciles per-model token usage and
uses dated frozen prices for **descriptive diagnostic** cost accounting. It
previously used an implicit zero when a *present* model bucket omitted
`prompt_tokens` or `completion_tokens`. With correspondingly incomplete
trace totals, this could understate cost and still pass model-to-trace
reconciliation. A *present* non-mapping `provider_usage_by_model` could
also be treated as missing rather than corrupt source evidence.

## Fail-closed contract

Model buckets must explicitly contain both prompt and completion token
counters as exact nonnegative integers. A **recorded zero** remains valid;
an **absent field** is not interpreted as zero. The reconciliation and cost
calculator enforce the same rule, including for unknown-priced models when
full trace loading performs the ledger audit. A supplied model map must be
a mapping; malformed values reject source publication. A genuinely absent
legacy map or an empty valid map retains the existing visibly **uncosted**
classification. Missing usage or prices are not imputed.

This protects standalone summary validity without changing any historical
token count, frozen price, treatment assignment or estimated cost on valid
records.

## Offline regression tests

```sh
python -m pytest -q tests/test_pilot_model_usage_bucket_completeness.py
python -m pytest -q tests/test_pilot_cost_ledger_integrity.py
python -m pytest -q tests/test_pilot_summarizer_source_integrity.py
```

All test evidence is synthetic. The pilot remains **diagnostic**; frozen
automated main-study results retain their evaluator comparability and
analysis-chronology qualifications; retrospective robustness remains
**exploratory**; authentic original reports and traces remain unavailable
for the source-verified blinded handoff; and **human validation is pending**.
No treatment, automated evaluation, or human annotation is rerun or invented.
