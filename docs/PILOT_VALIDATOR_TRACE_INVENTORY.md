# Postrun pilot trace-inventory and execution-identity custody

The diagnostic-pilot postrun validator (`scripts/validate_pilot_artifacts.py`)
now inspects **every immediate entry** under `outputs/experiment_traces`
before selecting treatment/task traces. Prior to this safeguard, a
`*/*.json` glob could count the expected number of apparently valid files
while silently ignoring an unselected treatment directory, nested retry,
staging file, or symlinked evidence source. A matching aggregate count alone
could not establish complete input selection.

The validator now rejects unexpected arm directories (including arms not
selected by the run manifest), non-JSON entries, nested directories,
symlinked output roots, symlinked required JSON files, symlinked treatment
directories, and symlinked trace files. For a supplied `run_id` in either
the trace or experiment record, it requires the **exact** source filename
stem; a missing legacy run ID is not invented and remains a provenance
limitation. It still reconciles the observed treatment/task cells with the
frozen manifest, progress-event ledger, source-budget checks, and summary
cardinality.

The standalone summarizer independently checks its own source inventory;
this safeguard closes the **postrun validator** path, which can be called
directly on an existing workspace or on artifacts changed after summarization.
It does not hash-anchor a historical archive, authenticate original reports,
or prove that a runner's recorded treatment was actually executed. Existing
pilot results are unchanged. The original main-study report/trace recovery
and genuine two-rater human validation remain blocked.

Reproduce offline with:

```bash
python -m pytest -q tests/test_pilot_validator_trace_inventory.py
python scripts/validate_pilot_artifacts.py  # needs a completed pilot workspace
```

Tests create only synthetic files; no paid model runs, evaluator
recomputations, frozen-outcome edits, or human ratings are performed.
