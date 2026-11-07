# Diagnostic pilot postrun numeric telemetry integrity

**Scope:** Forward-looking, offline validation of diagnostic D6/P6/P6V pilot manifests, checkpoints, traces and summaries. Original five-task pilot records, the frozen ten-task automated data, retrospective exploratory analyses, and human-evaluation artifacts are unchanged.

## Failure mode

The prior validator converted reported counts via `int(value or 0)`, so strings, booleans, and fractional measurements could silently become plausible browse, query, word, token, verifier and summary numbers (e.g., `int(6.9) == 6`). Equality also treated boolean `True` as count 1, and `float(...)` accepted numeric-looking strings for the experimental temperature. Some malformed data instead crashed with an unhelpful exception.

The postrun validator now requires exact native **nonnegative integers**, including for explicitly zero failed/timeout counts, across all inspected progress, trace and summary counters. Missing mandatory producer counters are rejected; bad values are accumulated as structured validation errors rather than truncated or imputed. P6V verification counts must be positive exact integers; nonverification arms allow an absent historical verified-claim field but reject invalid supplied values. Trace/manifest temperatures must be finite numbers (never boolean or string) and must agree. Existing cardinality, budget, provenance and successful-evidence checks remain in place.

## Offline verification

```bash
python -m pytest -q tests/test_pilot_numeric_counter_integrity.py tests/test_pilot_plan_identity.py tests/test_pilot_source_url_accounting.py tests/test_pilot_treatment_factor_identity.py tests/test_runtime_guardrails.py
```

Synthetic regression inputs exercise lossy coercions, missing counters, nonfinite measurements, and treatment-specific verification; no live work is performed. This is a prospective artifact-validity guard, not new experimental evidence. The five-task pilot remains diagnostic, the frozen automated main study remains methodologically qualified, sensitivity checks are retrospective/exploratory, and human ratings remain pending. Missing original reports/traces, fixed-order confounding and automated-analysis-plan timing remain unresolved.
