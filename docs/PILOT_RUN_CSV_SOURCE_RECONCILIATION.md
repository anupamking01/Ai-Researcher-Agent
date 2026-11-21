# Diagnostic pilot: independent per-run CSV reconciliation (schema v5)

The pilot publishes both `pilot_summary.json` and `pilot_runs.csv`. Through
schema v4, the independent postrun validator checked trace identities,
token/cost accounting, and arm/paired JSON summary metrics, but did **not**
check the CSV export itself. A stale, omitted, duplicated, or modified per-run
CSV row could therefore accompany a green validation and be used for further
analysis despite disagreeing with the validated trace inventory.

New pilot summaries use **schema v5**. After all prior validation gates pass,
`scripts/audit_pilot_runs_csv.py` reads `pilot_runs.csv` using a strict CSV
reader and independently reconciles **every exported column** against each
manifest-selected source trace. The source filename supplies the identity
fallback only for a legacy trace without an explicit run ID. The audit checks:

- Exact column headers, all and only the selected treatment/task cells, and
  no duplicated or unselected rows.
- Run IDs, task-set identity, completion flags, model/verification/status
  fields, source/call/token counters, report length, and recorded claim
  support counters and rates.
- Recorded latency and complete-case USD estimates against the frozen rate
  document and provider model-usage counters. Missing/unknown prices remain
  empty rather than being represented as measured zero.

Rows may be reordered without selecting more favorable outcomes; content
must reconcile by the unique assignment key. Numeric tolerances only allow
ordinary floating-point serialization rounding, not meaningful differences.
The auditor does not import the CSV producer or use the summary as its
reference. The earlier schema-v4 immutable frozen-price byte pin remains in
force. Schema versions 1–4 retain only their original audit scopes, and
absence of a CSV under those older schemas is not retroactively certified.

Reproduce entirely offline with synthetic inputs:

```sh
python -m pytest -q tests/test_pilot_csv_source_reconciliation.py
python -m pytest -q
```

For a genuine pilot workspace, run
`python scripts/validate_pilot_artifacts.py` only after collecting and
summarizing the existing pilot artifacts. Do not rerun live treatments merely
to get different outcomes.

**Research boundary:** This is an internal export-consistency guarantee, not
external authentication of original experimental traces, actual provider
billing, source truth, or causal validity. The five-task pilot stays
diagnostic. Frozen automated main-study results preserve the documented
post-collection analysis-plan, fixed-order, and evaluator-recovery caveats;
retrospective sensitivity is exploratory. Independent original 40-run
report/trace custody and genuine blinded human evaluation remain unresolved.
