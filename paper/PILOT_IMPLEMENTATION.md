# Pilot Implementation Notes

## Status

This document records the operational choices used by the first executable pilot and takes precedence over any earlier planning-language in `RESEARCH_PROTOCOL.md` where the two differ. The protocol should be revised to match these choices before the main experiment is frozen.

## Source-budget operationalization

For pilot v1, `source_budget` means the **maximum number of unique URLs scheduled for browsing** in one run, not the number of successful page fetches.

Reason: a successful-source target would allow a variant experiencing browse failures to make extra external calls until it reached the target. That would silently grant unreliable variants more tool usage. Counting scheduled browse calls makes the cap controllable before results are known.

The trace separately records browse failures and successful-source count, so reliability remains measurable.

For planner variants, the total browsing-call budget is distributed as evenly as possible across planned queries. With P6 and four planner queries the allocation is `[2, 2, 1, 1]`. Direct D6 receives a single query with a six-call maximum.

## Initial pilot variants

| ID | Planning | Browse-call cap | Verification |
|---|---|---:|---|
| D6 | direct question | 6 | none |
| P6 | four-query planner | 6 total | none |
| P6V | four-query planner | 6 total | bounded verifier |

The verifier examines up to 20 important atomic factual claims using only evidence already retrieved by the run. It labels claims `supported`, `partially_supported`, `unsupported`, or `contradicted`. Pilot v1 does **not** repair the report after verification, which keeps verification measurement separate from generation/retrieval.

## Usage accounting limitation

The legacy project pins `openai==0.27.10` and its streaming path does not currently expose a reliable token-usage object through the existing adapter. Pilot traces therefore set token/cost fields to zero and mark `usage_accounting_status` as unavailable. These values must not be interpreted as zero actual usage.

Before any paper makes a token- or USD-cost claim, provider usage metadata must be implemented and validated or an independently verified token counter must be added.

## Reproducibility guard

`scripts/run_pilot.py` refuses to run unless the following are explicitly set:

- `OPENAI_API_KEY`
- `SMART_LLM_MODEL`
- `FAST_LLM_MODEL`
- `TEMPERATURE`

This prevents the paper run from silently using the application's historical default model names.

## Pilot gate

The five frozen tasks in `experiments/pilot_tasks.json` are diagnostic only. Do not turn their outputs into publication claims. Use them to check:

1. that all variants complete reliably;
2. that trace files contain expected metadata;
3. that browsing budgets are actually respected;
4. that verifier output is parseable often enough to be useful;
5. that D6/P6/P6V show enough metric variation to justify a larger study.

Only after this pilot should the main task set, model IDs, temperature, and expanded variant matrix be frozen.
