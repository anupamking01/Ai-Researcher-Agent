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

## Local message preparation versus provider attempts (21 November 2026)

Both streaming and non-streaming adapters first materialize the supplied
one-pass `messages` iterable **before** entering the
`ChatCompletion.create` invocation boundary. Previously, an exception from
the local iterable while evaluating `messages=list(messages)` was caught as
if the provider call had raised, inflating the unavailable model-call count
even though `ChatCompletion.create` was never entered.

Local message preparation failures now propagate without changing usage
counters. A subsequent failure **inside the invoked provider method** still
counts one usage-unavailable attempted call, as separately regression-tested.
Synthetic tests cover both paths and producer failures before and after a
partial input yield; they never access a real provider. This prospective
measurement-accounting correction does not change frozen treatment outputs,
paired estimates, exploratory analyses, or pending human-evaluation claims.

## Unreadable provider usage metadata must not discard completed outputs (21 November 2026)

The provider call can complete successfully while a response or token-usage
object exposes a malformed accessor (for example, a `get` method or attribute
that raises during reading). Previously, that metadata-only exception escaped
`UsageTracker.record_response`, so the non-streaming adapter could lose a
completed report and mark its run failed *because usage extraction failed*.

Capture now treats exceptions raised while reading the response's `usage`,
either category token count, or the optional reported total as **one model
call with usage unavailable**. It does not impute any tokens. An unreadable
total is **not** equivalent to a legitimately absent legacy `total_tokens`
field; it must not be silently reconstructed. Successful output text remains
available to the experiment. The tracker still rejects invalid model labels
before accessing provider metadata, and any actual exception from the
provider invocation itself continues to propagate under the existing
attempt-accounting policy.

Synthetic offline regressions exercise mapping and attribute getters,
each usage field, ledger recovery after malformed metadata, and the actual
non-streaming adapter's returned text. These tests do not contact a provider
or modify historical records. This is a prospective measurement-integrity
guard only; it does not establish true provider billing, original-artifact
custody, automated confirmatory validity, or human-validation results.


## Early tracked-model validation before provider invocation (21 November 2026)

The tracker already rejects malformed model labels before mutating its ledger.
That validation occurred *after* the live adapter obtained a successful response,
however, so a non-string or noncanonical model identity could be rejected only
after attempting an external completion and discarding its output. A completed
call would then have no trustworthy per-model accounting.

For calls with a usage tracker, the public chat adapter now validates the
exact model-label type **before** consuming one-pass messages or invoking
`ChatCompletion.create`, for both streaming and non-streaming paths. Rejected
local inputs do not change preexisting usage counters or trigger a provider
attempt. Untracked legacy calls retain their prior behavior. Existing
in-tracker validation remains the boundary for direct tracker callers.

Synthetic offline regressions cover invalid labels on both paths and assert
that neither the provider stub nor message producer is accessed. This is a
prospective accounting and budget-integrity safeguard, not evidence of actual
provider billing or recovery of historical usage. Frozen automated results,
post-hoc exploratory findings, and pending human validation remain unchanged.


## Finite preflight for provider request settings (21 November 2026)

The chat adapter previously used only a positive-sign comparison to validate
`request_timeout_seconds`. IEEE-754 NaN bypasses that comparison, and
infinity can also pass through. An explicitly Boolean timeout could become
`1.0`. Likewise, a nonfinite or out-of-range temperature could reach the
provider without a local validity check. These malformed settings risk
undocumented execution behavior, invalid experiment configurations and
misleading call-attempt accounting.

The public adapter now validates a finite, strictly positive timeout and a
finite numeric temperature in the pinned OpenAI chat range [0, 2] **before**
materializing one-pass messages or attempting an external model invocation.
Finite numeric timeout strings remain accepted for existing callers, and
valid numeric temperatures retain their original transmitted type/value.
Invalid settings fail locally without adding a model-call ledger entry.
This holds for streaming and non-streaming invocations.

The synthetic offline tests verify NaN/infinity, bounds, Boolean/invalid
types, conversion overflow, no message consumption or provider invocation,
unchanged preexisting usage accounting, and successful valid requests. This
is a *prospective* safety and provenance check, not a change to frozen
pilot/main-study records or exploratory estimates; independent original
evidence custody and genuine blinded human validation remain outstanding.

## Malformed completion output is not a recorded empty report (21 November 2026)

The non-streaming OpenAI 0.x adapter previously returned an empty string when
the completed provider response lacked the expected first choice, assistant
message or content field, or when non-text content was falsy. In a prospective
research trace that can make malformed output indistinguishable from a genuine,
explicit empty-string response. It is an output-validity issue, separate from
whether the provider reported token consumption.

The adapter now raises a deterministic local validation error for missing or
non-text assistant content, while continuing to accept a genuine string
(including an explicitly empty string). Usage is recorded **once before**
response-text validation: known provider token counts remain known even when
the output is invalid; unknown counts remain unavailable. No synthetic fallback
report is created. Offline synthetic regression cases exercise the malformed
and valid envelopes without contacting a provider.

This prospective safeguard does not alter frozen experiment outputs or imply
that a missing historical report/trace has been recovered. The pilot remains
diagnostic, the designated-primary historical automated findings retain their
post-collection chronology and evaluator-comparability qualifications,
retrospective sensitivity analyses remain exploratory, and authentic blinded
human validation has not been completed.

## Streaming response-frame validity (21 November 2026)

The pinned OpenAI 0.x streaming adapter previously swallowed missing or
malformed frame envelopes and silently ignored falsey **present** content
values. A truncated or corrupted stream could therefore be returned as a
plausibly complete partial report. Truthy non-text deltas could also reach the
websocket before failing during string assembly.

For prospective calls, a chunk must provide a first-choice `delta` mapping;
a present `content` must be text. Role-only frames, terminal frames with an
empty `delta`, and explicit empty-string content remain valid. Invalid frames
raise a deterministic output-validation error rather than being silently
skipped. The stream continues to count **exactly one usage-unavailable
provider attempt**, without inventing billed tokens; any already-sent
websocket bytes are not retractable, and the adapter does not return the
partial report as a successfully completed result.

Eleven offline synthetic regressions cover corrupt frames, normal
role/terminal frames, websocket delivery and single-call ledger continuity.
This is an adapter robustness/provenance guard, **not** recovery of historical
traces or proof of provider billing. Pilot findings remain diagnostic;
historical automated comparisons retain post-collection chronology and
evaluator-policy comparability qualifications; retrospective sensitivity
findings remain exploratory; blinded human validation remains pending.
