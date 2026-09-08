# Pilot Implementation Notes

## Status

This document records the operational choices used by the first executable pilot and takes precedence over any earlier planning-language in `RESEARCH_PROTOCOL.md` where the two differ. The protocol should be revised to match these choices before the main experiment is frozen.

The pilot infrastructure is implemented and offline-validated. The remaining experimental step is the live 15-run execution (5 tasks × D6/P6/P6V) with explicit current model IDs and an authenticated OpenAI API key.

## Source-budget operationalization

For pilot v1, `source_budget` means the **maximum number of unique URLs scheduled for browsing** in one run, not the number of successful page fetches.

Reason: a successful-source target would allow a variant experiencing browse failures to make extra external calls until it reached the target. That would silently grant unreliable variants more tool usage. Counting scheduled browse calls makes the cap controllable before results are known.

The trace separately records attempted, successful, and failed browse URLs. Failed scrapes raise into the experiment gather path and are no longer represented as non-empty success strings.

For planner variants, the total browsing-call budget is distributed as evenly as possible across planned queries. With P6 and four planner queries the allocation is `[2, 2, 1, 1]`. Direct D6 receives a single query with a six-call maximum. Search returns may be over-fetched as candidates so duplicate URLs across planner queries do not unnecessarily leave the fixed browse-call budget unused; only scheduled browse calls consume the browse budget.

## Initial pilot variants

| ID | Planning | Browse-call cap | Verification |
|---|---|---:|---|
| D6 | direct question | 6 | none |
| P6 | exactly four planner queries | 6 total | none |
| P6V | exactly four planner queries | 6 total | bounded verifier |

The verifier examines up to 20 important atomic factual claims using only evidence already retrieved by the run. It labels claims `supported`, `partially_supported`, `unsupported`, or `contradicted`. Pilot v1 does **not** repair the report after verification, which keeps verification measurement separate from generation/retrieval.

## Usage accounting

The project still pins `openai==0.27.10`, but pilot report generation is deliberately non-streaming so the Chat Completions response exposes provider-reported usage. A thread-safe usage ledger aggregates:

- model-call count;
- prompt tokens;
- completion tokens;
- total tokens;
- per-model token totals;
- calls for which provider usage was unavailable.

Per-source summarization calls, planner calls, report-generation calls, and verifier calls share the same run-level usage ledger. If any call lacks provider usage, the trace marks usage as partial/unavailable rather than estimating missing tokens.

## Frozen cost accounting

`experiments/openai_pricing_2026-09-08.json` freezes a dated text-token pricing snapshot for the model IDs intended for this pilot. The default live workflow uses:

- smart/planning/report/verifier model: `gpt-5.6-terra`;
- fast/source-summarization model: `gpt-5.6-luna`;
- temperature: `0`.

`scripts/summarize_pilot.py` uses the trace's **per-model provider-reported prompt and completion token totals** and the frozen pricing file to calculate an estimated USD cost for each run, variant averages, and paired cost deltas.

The cost estimator deliberately:

- applies the frozen uncached input rate because cached-input tokens are not separately captured by the current ledger;
- refuses to cost an unknown model ID rather than substituting another model's price;
- labels the estimate and pricing effective date in the summary output;
- leaves long-context pricing multipliers for explicit review if any live request crosses the provider threshold.

The pricing file is a frozen research artifact and should not be silently edited after live pilot execution.

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
- latency and run errors.

## Reproducibility guards

`scripts/run_pilot.py` refuses to run unless the following are explicitly set:

- `OPENAI_API_KEY`
- `SMART_LLM_MODEL`
- `FAST_LLM_MODEL`
- `TEMPERATURE`

Explicit process environment variables take precedence over `.env`, preventing stale local settings from replacing pinned experiment values.

The runner writes `outputs/pilot_manifest.json` with the task set, selected variants, model IDs, temperature, and Git commit before execution. `scripts/summarize_pilot.py` subsequently produces `pilot_summary.json` and `pilot_runs.csv` from persisted traces.

## GitHub Actions execution

`.github/workflows/live-pilot.yml` provides a manual `workflow_dispatch` path. It requires an `OPENAI_API_KEY` repository secret, defaults to Terra/Luna at temperature 0, runs offline tests first, executes the frozen pilot, summarizes traces, and uploads reports/traces/CSV/JSON as a workflow artifact.

No API key is committed to the repository.

## Pilot gate

The five frozen tasks in `experiments/pilot_tasks.json` are diagnostic only. Do not turn their outputs into publication claims. Use them to check:

1. that all 15 intended runs are represented by traces;
2. that all variants complete reliably;
3. that browsing budgets are actually respected;
4. that failed scraping is correctly distinguished from successful evidence;
5. that provider usage accounting is complete for the live configuration;
6. that frozen-price cost accounting covers every used model;
7. that verifier output is parseable often enough to be useful;
8. that D6/P6/P6V show enough operational and support-metric variation to justify a larger study;
9. that reports are suitable for a later blinded human-quality evaluation.

Only after this pilot should the main task set, human-rubric protocol, and expanded variant matrix be frozen for the full study.
