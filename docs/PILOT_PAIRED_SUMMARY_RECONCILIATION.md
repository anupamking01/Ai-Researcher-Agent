# Diagnostic-pilot paired operational summary cross-check

## Gap and scope

The postrun validator checked the pilot's trace count and per-variant run
counts, but a stale or edited `pilot_summary.json` could retain those counts
while publishing incorrect task-level token, latency, model-call, or successful
source contrasts. Such numbers are *descriptive diagnostics*, not confirmatory
treatment-effect estimates. This check prevents silent drift between selected
raw trace evidence and the reported paired operational comparison.

The offline summarizer now marks newly produced summaries with
`schema_version: 2` (legacy `schema_version: 1` is also accepted).
For either version, the postrun validator requires the paired-comparison section. It independently rebuilds the two frozen
comparison matrices (P6 minus D6; P6V minus P6) from the manifest-selected
trace cells. It checks the task union, paired denominator, missing-arm task
identities, exact per-task token/model-call/success-source differences, and
latency differences and means (finite values, tight floating-point tolerance).
A correct overall trace count or a matching aggregate mean cannot substitute
for correct individual source-linked pairs.

Previously generated unversioned minimal checkpoint fixtures are explicitly
compatible. If an unversioned summary *does* supply paired comparisons,
those comparisons are still checked; missing pre-version rows are **not**
represented as independently audited. This is an internal cross-artifact
consistency assertion, not signed historical source custody.

The legacy v1 paired-metric check **does not** validate USD estimates or
cost-missingness denominators; the schema-v2 independent frozen-price check
below adds those internal accounting assertions. Neither check can validate
external model-rate applicability, cached-input discounts or long-context
pricing surcharges; these still require independent review. It does not score report
quality or recover expired treatment/evaluator artifacts. It does not change
task selection, treatment ordering, collected traces, or frozen outcomes.

Reproduce the source/summary regression checks offline:

```sh
python -m pytest -q tests/test_pilot_paired_summary_reconciliation.py
```

All new cases use synthetic fixtures. The five-task pilot remains diagnostic;
frozen automated main-study results remain historically qualified by missing
independently authenticated original reports/traces, fixed treatment order,
and post-collection analysis-plan chronology. Retrospective sensitivities
remain exploratory, and no blinded human ratings or reconciliation exist yet.


## Schema-v2 frozen-price and cost-coverage cross-check

Newly produced offline pilot summaries use `schema_version: 2`. The independent
postrun validator now loads the repository's dated pricing document directly
(not a path supplied by the summary), recomputes model-bucket cost for each
manifest-selected experimental cell, and verifies published cost means,
per-task paired USD deltas, costed/uncosted denominators, task-ID sets,
missing-cost reasons and the declared price provenance. Absent/unknown prices
remain explicitly uncosted; genuine zero token usage is not fabricated as a
zero-dollar provider bill. Version-1 and unversioned legacy summaries retain
their existing checks and are not retroactively claimed to have cost custody.

Regression cases use entirely synthetic traces and local synthetic price
tables, including deliberate price changes, missing model rates, falsified
denominators, incorrect deltas and uncosted pairs. Reproduce offline with
`python -m pytest -q tests/test_pilot_paired_summary_reconciliation.py`.

This is internal **trace-to-summary consistency** under a dated uncached rate
table, **not** evidence of actual provider billing, cached-token discounts,
long-context repricing, independent archive custody, human validation, or
causal treatment effects. Frozen main-study automated results are unchanged.
