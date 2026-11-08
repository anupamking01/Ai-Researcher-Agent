# Diagnostic-pilot paired operational summary cross-check

## Gap and scope

The postrun validator checked the pilot's trace count and per-variant run
counts, but a stale or edited `pilot_summary.json` could retain those counts
while publishing incorrect task-level token, latency, model-call, or successful
source contrasts. Such numbers are *descriptive diagnostics*, not confirmatory
treatment-effect estimates. This check prevents silent drift between selected
raw trace evidence and the reported paired operational comparison.

The offline summarizer now marks newly produced summaries with
`schema_version: 1`. For that version, the postrun validator requires the
paired-comparison section. It independently rebuilds the two frozen
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

The check **does not** validate price estimates, model-rate applicability,
long-context surcharges, or cost-missingness denominators; those require
independent frozen-pricing and accounting review. It does not score report
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
