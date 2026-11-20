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

## Prospective capture-time usage integrity (21 November 2026)

The live, non-streaming provider adapter uses `logic.usage.UsageTracker` to
capture token use before a trace reaches the standalone summarizer. The capture
boundary now treats a missing, partial, non-integer, Boolean, negative, or
internally contradictory provider usage record as **usage unavailable**, rather
than coercing missing/malformed counters to recorded zeros or silently replacing
an inconsistent reported `total_tokens`. Each such call still increments both
the global and per-model call/unavailable counters. A valid **reported zero**
remains valid, and a legacy usage object lacking only `total_tokens` can
still use the exact sum of its present, valid prompt/completion counts.

This makes prospective missingness visible at capture rather than falsely
reporting a complete model-consumption ledger. It does **not** recover unknown
usage, authenticate provider billing, or change historical/frozen study outputs.
The standalone summarizer continues to reject incomplete *present* model
buckets under its separate fail-closed provenance contract. Synthetic
capture-boundary regressions run in `tests/test_evaluation.py` under the
offline diagnostic-evaluation fast CI lane.

## Capture-time model identity and atomic ledger updates

Per-model usage buckets are keyed by the literal model label. If a caller passes a
non-string or a string subclass with nonstandard hashing, an insertion could
previously raise *after* advancing global model-call/token counts, leaving a
partially committed measurement ledger that cannot reconcile by model.

The capture boundary now requires an **exact string** label before inspecting a
provider response or mutating any counters, for both recorded responses and
explicit usage-unavailable calls. Valid string labels (including legacy empty
labels) are not modified. Invalid identities raise a clear validation error
without changing the prior snapshot. Synthetic regressions test both ingress
paths, failed inputs followed by valid calls, and a provider object that must
not be read after an invalid model label.

This is an in-memory prospective diagnostic consistency guard. It does not
authenticate provider identities, infer missing tokens or prices, alter frozen
analysis artifacts, rerun experimental treatments or produce human ratings.


## Unsuccessful model invocation accounting (21 November 2026)

The pinned OpenAI 0.x adapter previously recorded token usage only when a
non-streaming request returned a response, and marked a streaming request
unavailable only *after* its iterator was created. A provider invocation that
raised before returning a response therefore disappeared from the model-call
denominator, even when the containing research run was persisted as failed.

Both adapter paths now record exactly **one attempted model call with
unavailable usage** when `ChatCompletion.create` raises, and re-raise the
original error. Streaming calls that successfully return an iterator remain
usage-unavailable exactly once, even if iteration later fails; successful
non-streaming calls still use the provider-reported counters. Local input
validation before the attempted invocation is not counted.

An exception does **not** prove that a request reached the provider, consumed
tokens, or incurred a charge; this is conservative *invocation-attempt*
coverage, not provider billing attestation. Missing tokens are never imputed.
Synthetic offline adapter tests use a stubbed provider and no live requests.
Existing historical/frozen treatments and analysis are left unchanged.
