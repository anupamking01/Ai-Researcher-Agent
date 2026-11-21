# Diagnostic pilot: complete trace-inventory and identity custody

**Scope:** Standalone, offline summaries of the five-task D6/P6/P6V
**diagnostic** pilot. Neither the pilot source runs nor the separate frozen
ten-task automated analysis is changed.

## Threat model and safeguard

Previously, `scripts/summarize_pilot.py` used `glob("*.json")` separately
inside the three expected treatment directories. An extra treatment directory,
nested retry, unexpected file, or symlink was silently excluded from the
selected evidence set. A trace could also claim a different `run_id` from its
create-only published filename: the summarizer would attribute its
measurements to the claimed identity. Finally, a present but falsey
`variant_id`, `task_set_id`, or `task_id` (such as an empty string or
`null`) could be replaced by the other record's field through truthy
fallback, masking invalid source metadata.

The summarizer now checks the **entire** trace-root inventory before selecting
any row: only ordinary directories `D6`, `P6`, and `P6V` containing
ordinary `.json` files are accepted. Unknown directories, nested files,
temporary leftovers, non-JSON files, and symlinked roots, arm folders, or
trace files are rejected rather than silently ignored. Every *supplied*
trace/experiment identity must be a nonempty, unpadded string; supplied
identities must agree, and all three experimental identities must be present
in at least one record. A supplied `trace.run_id` must equal the JSON
filename stem. For legacy records in which `run_id` was absent entirely, the
existing filename-based fallback is retained; it is not independent proof of
the historical run identity.

Invalid input stops the standalone summary before its JSON or CSV
publication step. The previous unique-(arm, task), task-set, run-ID, strict
JSON, numeric telemetry, and provider-usage safeguards still apply.

## Offline regression

```sh
python -m pytest -q tests/test_pilot_trace_inventory_identity.py
python -m pytest -q tests/test_pilot_source_selection_integrity.py tests/test_pilot_summarizer_source_integrity.py tests/test_pilot_cost_ledger_integrity.py
```

All negative examples use synthetic temporary traces. No treatment, external
retrieval, automated common evaluator, frozen measurement, or human rating is
rerun. This validates ordinary static local artifact selection, not a
cryptographic signature, a race-free snapshot under concurrent filesystem
mutation, or independent authentication of missing historical main-study
report/trace artifacts. The diagnostic pilot must not be called
prospectively confirmatory; frozen automated designated-primary findings retain
their analysis-timing and temporal-order qualifications, retrospective
sensitivity analyses remain exploratory, and blinded human validation is
still pending authentic source custody and independent annotations.
