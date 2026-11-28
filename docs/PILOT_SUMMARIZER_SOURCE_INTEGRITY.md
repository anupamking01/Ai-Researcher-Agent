# Diagnostic pilot summarizer: independent source-integrity gate

The pilot operational summarizer (`scripts/summarize_pilot.py`) may be run
standalone, without first invoking `scripts/validate_pilot_artifacts.py`.
Before this change it independently parsed raw JSON with permissive
last-duplicate-key-wins semantics, accepted nonstandard `NaN`/`Infinity`
values, and cast certain observed telemetry with `int(...)`,
`float(...)`, or `bool(...)`. A fractional source count or numeric-looking
string could therefore be silently rounded, and nonfinite latency or support
rates could enter the descriptive output.

## Safeguard

The summarizer now uses the postrun validator's strict JSON-object loader for
both experimental traces and the frozen pricing JSON. It rejects duplicate
object keys at any nesting depth, nonstandard constants, nonfinite parsed
floating literals, and non-object documents before row selection. It separately
checks *observed* pilot counters as exact, nonnegative Python integers,
completion flags as booleans, latency as finite nonnegative numeric data,
and strict claim-support rate as a finite value in [0, 1]. An invalid source
fails the summary run before either the JSON or CSV output is published.

Absent optional legacy telemetry fields retain their historical zero/false
fallbacks, and absent provider-by-model usage remains uncosted as before.
These are **not** newly authenticated observations: missingness and completeness
still require the existing postrun pilot validator. Frozen prices, treatment
records, estimands, and the historical diagnostic-pilot data are unchanged.

## Offline reproduction

```sh
python -m pytest -q tests/test_pilot_summarizer_source_integrity.py
python -m pytest -q tests/test_pilot_cost_ledger_integrity.py tests/test_pilot_cost_coverage.py tests/test_pilot_source_selection_integrity.py
```

All new tests use synthetic local JSON and temporary paths. They require no
API keys, browsing, treatment execution, evaluator recovery, or human ratings.
The five-task D6/P6/P6V pilot is **diagnostic only**. This source guard does
not validate the separate frozen ten-task automated analysis, alter any
post-collection exploratory result, cure historical treatment-order confounding,
authenticate missing original reports/traces, establish prospective
precollection preregistration, or supply genuine human validation. The
source-verified human-evaluation handoff remains blocked until original
evidence custody is independently recovered.
