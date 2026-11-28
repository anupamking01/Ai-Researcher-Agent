# Diagnostic-pilot event clock-window integrity

The live diagnostic-pilot runner records `started_at_utc` and
`finished_at_utc` in its per-cell `pilot_progress.json.events`, plus
manifest creation, progress creation and final checkpoint times. Previously
the independent postrun validator verified complete, unique terminal events
but **did not verify any of those timestamps**. A versioned checkpoint
could therefore claim a completed experimental matrix with missing, naive,
non-UTC, inverted or overlapping event intervals, masking contradictory
timing metadata despite otherwise valid traces and counters.

`scripts/validate_pilot_artifacts.py` now fails closed on **versioned**
checkpoints when UTC instants are missing or invalid, when the progress
window precedes manifest creation or ends before it starts, or when cell
intervals fall outside the recorded checkpoint window. Because the frozen
pilot runner executes cells serially, intervals cannot overlap. Intervals
are sorted by their recorded start instants for this assertion: **the event
list's order itself is not asserted to be randomized, balanced or causal
evidence**, and the validator does not infer treatment-order validity.
Explicit `Z` and `+00:00` instants are accepted; naive/local timestamps
and implicit coercions are rejected.

The preexisting unversioned legacy-checkpoint allowance remains explicit;
missing historical time fields in unversioned fixtures are **not** claimed
to be authenticated. This audit checks internally reported clocks; it
cannot independently authenticate the clocks, original report/trace
custody, GitHub Actions artifacts, or treatment execution.

Reproduce entirely offline:

```sh
python -m pytest -q tests/test_pilot_progress_event_ledger.py
python -m pytest -q tests/test_pilot_validator_trace_inventory.py
```

All negative examples are synthetic. The safeguard does not rerun the
five-task **diagnostic** pilot, alter the ten-task frozen automated
analysis, reclassify retrospective **exploratory** sensitivity work as
confirmatory, fix the historical fixed-order confounding or prospective
analysis-plan timing limitation, or substitute for genuine independent
blinded **human validation**. Recovery of the original 40 main-study
reports and traces remains a separate unresolved provenance gate.
