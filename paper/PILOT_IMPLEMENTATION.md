# Pilot Implementation Notes

## Status

Pilot v1 has completed end-to-end validation. The canonical diagnostic dataset contains 15 successful runs (5 tasks × D6/P6/P6V) and is documented in `paper/PILOT_RESULTS.md` and `experiments/results/pilot_v1_canonical_runs.csv`.

The first full live run (`34377707838`) completed 13/15 experiments before the API account exhausted prepaid credit. The two missing runs, `P6V/pilot-04` and `P6V/pilot-05`, were executed later in the targeted run `34388324051` after credit was restored. The canonical dataset retains the original 13 successful traces and substitutes only those two successful targeted reruns. The failed credit-exhaustion traces remain preserved in the original workflow artifact as infrastructure-failure records.

This document records the operational choices actually used by pilot v1. The pilot is a **fixed browse-call-budget** diagnostic ablation; it is not yet an equal-total-token or equal-total-dollar comparison. The main study must either impose an explicit total compute/cost cap or analyze quality-cost Pareto trade-offs as specified in `RESEARCH_PROTOCOL.md`.

## Source-budget operationalization

For pilot v1, `source_budget` means the **maximum number of unique URLs scheduled for browsing** in one run, not the number of successful page fetches.

Reason: a successful-source target would allow a variant experiencing browse failures to make extra external calls until it reached the target. That would silently grant unreliable variants more tool usage. Counting scheduled browse calls makes the cap controllable before results are known.

The trace separately records attempted, successful, and failed browse URLs. Failed scrapes raise into the experiment gather path and are not represented as non-empty success strings.

For planner variants, the total browsing-call budget is distributed as evenly as possible across planned queries. With P6 and four planner queries the allocation is `[2, 2, 1, 1]`. Direct D6 receives a single query with a six-call maximum. Search returns may be over-fetched as candidates so duplicate URLs across planner queries do not unnecessarily leave the fixed browse-call budget unused; only scheduled browse calls consume the browse budget.

## Pilot variants

| ID | Planning | Browse-call cap | Verification |
|---|---|---:|---|
| D6 | direct question | 6 | none |
| P6 | exactly four planner queries | 6 total | none |
| P6V | exactly four planner queries | 6 total | bounded verifier |

The verifier examines up to 20 important atomic factual claims using only evidence already retrieved by the run. It labels claims `supported`, `partially_supported`, `unsupported`, or `contradicted`. Pilot v1 does **not** repair the report after verification, which keeps verification measurement separate from generation/retrieval.

## Frozen live configuration

The successful pilot used:

- smart/planning/report/verifier model: `gpt-5.6-terra`;
- fast/source-summarization model: `gpt-5.6-luna`;
- temperature: `1` (the provider-supported value for these models);
- source/browse-call budget: `6`;
- maximum concurrent browser extractions: `2`;
- per-source browse timeout: `60 s`;
- per-run timeout: `480 s`.

Earlier planning text specified temperature 0. The provider rejected temperature 0 before any successful live experimental run, so the value was changed to the provider-supported default of 1 as an infrastructure compatibility correction, not after observing valid research outcomes.

## Usage accounting

The project pins an older OpenAI Python client, but pilot report generation is deliberately non-streaming so the Chat Completions response exposes provider-reported usage. A thread-safe usage ledger aggregates:

- model-call count;
- prompt tokens;
- completion tokens;
- total tokens;
- per-model token totals;
- calls for which provider usage was unavailable.

Per-source summarization calls, planner calls, report-generation calls, and verifier calls share the same run-level usage ledger. If any call lacks provider usage, the trace marks usage as partial/unavailable rather than estimating missing tokens.

Source summarization was hardened before the valid pilot to use one bounded fast-model call per successfully extracted source. Input evidence is sampled deterministically from the source text rather than allowing document length to create an unbounded number of model calls.

## Frozen cost accounting

`experiments/openai_pricing_2026-09-08.json` freezes the dated text-token pricing snapshot used for the pilot.

`scripts/summarize_pilot.py` uses each trace's **per-model provider-reported prompt and completion token totals** and the frozen pricing file to calculate estimated USD cost per run, variant averages, and paired operational deltas.

The estimator deliberately:

- applies the frozen uncached input rate because cached-input tokens are not separately captured by the current ledger;
- refuses to cost an unknown model ID rather than substituting another model's price;
- labels the estimate and pricing effective date in the summary output;
- leaves long-context pricing multipliers for explicit review if a request crosses a provider threshold.

The pricing file is a frozen research artifact and should not be silently edited after pilot execution.

## Retrieval audit trail

Every run trace records:

- task-set ID and task ID;
- planning/verification variant;
- exact generated search queries;
- search-call count;
- candidate URLs returned per query;
- URLs scheduled for browsing;
- successful URLs;
- failed URLs;
- source-attempt count;
- research-context word count;
- report word count;
- exact smart/fast model IDs and temperature;
- provider token usage by model;
- verifier counts/status where applicable;
- latency and run errors;
- browse/run timeout configuration.

## Reliability safeguards introduced before valid pilot results

Infrastructure diagnostics exposed browser and provider failure modes before the canonical pilot was completed. The final pilot therefore used the following uniform safeguards:

- optional legacy overlay injection so a missing `js/overlay.js` cannot crash extraction;
- isolated Chrome debugging ports and bounded concurrent browser instances;
- Selenium page/script/close limits;
- explicit per-source browse timeout and per-run experiment timeout;
- bounded provider request timeouts;
- atomic `pilot_progress.json` checkpoints;
- a live preflight that checks metasearch plus concurrent browser extraction before spending experiment API budget;
- offline regression tests before every live workflow run;
- strict post-run artifact validation that fails the workflow when expected traces, accounting, source evidence, or verifier outputs are missing.

These safeguards were introduced in response to infrastructure hangs/failures **before a complete valid result set existed**. They were applied uniformly and should be disclosed as reproducibility controls rather than result-driven treatment tuning.

## Reproducibility guards

`scripts/run_pilot.py` refuses to run unless the following are explicitly set:

- `OPENAI_API_KEY`
- `SMART_LLM_MODEL`
- `FAST_LLM_MODEL`
- `TEMPERATURE`

Explicit process environment variables take precedence over `.env`, preventing stale local settings from replacing pinned experiment values.

The runner writes `outputs/pilot_manifest.json` before execution. `scripts/summarize_pilot.py` then produces `pilot_summary.json` and `pilot_runs.csv` from persisted traces, and `scripts/validate_pilot_artifacts.py` enforces the expected run/usage/source/verifier invariants.

## GitHub Actions execution

`.github/workflows/live-pilot.yml` is now **manual-dispatch only**. The temporary research-branch push trigger used to launch the validated pilot has been removed after successful completion to prevent accidental API spending.

The workflow requires the repository `OPENAI_API_KEY` secret, runs compile/offline tests and live browser/search preflight first, executes the selected frozen configuration, summarizes and validates artifacts, then uploads reports/traces/CSV/JSON.

No API key is committed to the repository.

## Canonical pilot gate outcome

The 15-run canonical pilot verifies that:

1. all intended D6/P6/P6V `(variant, task)` pairs can complete under the final runtime safeguards;
2. the six-call browsing budget is respected;
3. failed scraping is distinguished from successful evidence;
4. provider usage accounting is complete for all selected runs;
5. frozen-price cost accounting covers every selected run;
6. the bounded verifier produces parseable structured outputs for all five P6V reports;
7. operational metrics vary enough to justify a larger study;
8. the workflow correctly fails on incomplete datasets and succeeds on the targeted valid rerun.

The pilot does **not** establish a publication-level answer to the research question. A larger task set, common support evaluation across variants, and blinded human report-quality assessment remain necessary before strong empirical claims are made.
