# Diagnostic pilot: progress-event ledger custody

**Scope:** Offline postrun validation of future D6/P6/P6V five-task
**diagnostic** pilot artifacts. No historical treatment, automated score,
inference, frozen report or human rating is changed.

## Distinct gap

The postrun artifact validator checked aggregate `attempted_runs` and
`completed_runs` against the expected treatment/task count, and separately
checked the set of trace cells. It did **not** inspect the runner's
`pilot_progress.json.events` log. A checkpoint with two claims of success
for the same cell and no terminal event for another could therefore pass
the count checks alongside otherwise valid traces. The runner emits one
terminal event for every attempted cell, independently of trace publication.

## Safeguard

When an event ledger is present, validate it as a list of objects with exact
unpadded treatment and task IDs and a `completed` terminal status. Reject
duplicates, unplanned cells, missing planned cells, invalid event records,
non-completed statuses, incorrect event counts, disagreement with aggregate
attempt/completion counts, and a still-active `current` entry. Event order
is deliberately **not** used to select or validate an experimental
treatment: this does not establish randomization or remove historical
fixed-order confounding.

The runner publishes `schema_version: 1` and `events`, so omitting that
ledger from a versioned checkpoint is also an explicit failure. Earlier
unversioned minimal checkpoints may omit `events` for compatibility;
such absence must **not** be described as authenticated event custody.
Neither file timestamps nor event logs independently authenticate original
treatment reports or GitHub Actions artifact custody.

## Offline reproduction

```sh
python -m pytest -q tests/test_pilot_progress_event_ledger.py
python -m pytest -q tests/test_pilot_plan_identity.py tests/test_pilot_json_document_integrity.py
```

All negative records are synthetic. This check does not rerun treatment
or common evaluation, upgrade a diagnostic pilot into a confirmatory result,
modify retrospective exploratory sensitivity findings, or replace genuine
independent blinded human ratings. The missing original main-study
report/trace custody, human-evaluation handoff, temporal confounding,
and prospective automated analysis-plan timing limitations remain unresolved.
