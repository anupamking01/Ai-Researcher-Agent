# Diagnostic-pilot cost coverage and missingness accounting

**Scope:** Forward-looking reporting integrity for the five-task D6/P6/P6V
**diagnostic pilot**. This is not a new trial, a revision of the frozen ten-task
automated analysis, or a human-validation result.

## Problem and correction

The offline diagnostic-pilot summarizer already left unknown-model pricing and
missing provider-usage ledgers explicitly **uncosted**, and its per-arm
`costed_runs` denominator was available. But its paired cost delta was
calculated over costed treatment/task pairs while `n_pairs` counted *all*
operational pairs. A reader could therefore mistake a complete-case price
average for a mean over the whole paired task set. The absence of prices also
lacked paired-task reason accounting.

`scripts/summarize_pilot.py` now preserves the **existing** numerical cost
means and observed-pair selection rules, and adds:

- Per variant: `uncosted_runs`, `uncosted_task_ids`, and
  `cost_accounting_status_counts` alongside `n_runs` and `costed_runs`.
- Per contrast: `n_costed_pairs`, `n_uncosted_pairs`,
  `costed_pair_task_ids`, and `uncosted_pair_details`. Each uncosted
  shared-task pair retains both arms' reported accounting statuses or `costed`
  for the arm with an available estimate.
- `n_tasks_union` and missing-left/right task IDs continue to identify
  **unmatched treatment/task cells separately from paired cost missingness**.

A genuine reported USD value of `0.0` is costed, not missing. Unknown model
rates are not estimated or imputed. If no paired tasks have cost in *both*
arms, the reported mean cost difference remains `null`, not zero. This change
does **not** discard an operational pair, change the paired support outcomes,
change the task selection, or promote diagnostic-pilot observations to
confirmatory inference.

## Verification

```bash
python -m pytest -q tests/test_pilot_cost_coverage.py
python -m pytest -q tests/test_pilot_source_selection_integrity.py tests/test_pilot_cost_ledger_integrity.py
```

All regression cases use synthetic offline records. Original pilot records and
the frozen ten-task analysis are not edited or replayed.

## Interpretation boundaries

`avg_estimated_cost_usd` is calculated over `costed_runs`, and
`avg_estimated_cost_usd_delta` over **`n_costed_pairs`**, *not* necessarily
`n_runs` or `n_pairs`. Report both coverage denominators and uncosted
statuses alongside any illustrative cost comparison. Missing or unknown-cost
measurements are **not assumed missing at random**. These additions improve
transparent missingness diagnostics; they cannot recover unpriced model rates,
authenticate lost original main-study artifacts, remove fixed-order confounding,
supply precollection statistical preregistration, or replace independent
blinded human ratings.
