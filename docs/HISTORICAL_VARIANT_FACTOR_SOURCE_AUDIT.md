# Original treatment-factor attribution: historical source audit

**Scope: retrospective, outcome-free, planned-factor provenance only.** This
complements `HISTORICAL_DESIGN_SOURCE_AUDIT.md`, which verifies the original
runner's fixed D3 → D6 → P6 → P6V order and treatment/position aliasing. That
order audit did **not** verify that the source code instantiated the expected
planning, retrieval, and verification factors for each treatment label.

Run from the full-history Git repository root:

```bash
python -m scripts.audit_historical_variant_factors
```

The read-only verifier checks the immutable September 11 treatment-runner commit
`c3c15e46a8eec3a8bbc24c968eedc0548172a897` and its existing pinned runner
blob (`1e509f8e2abbd2cf7601eafa06f4e20588bf7ff5`). It also requires the
historical `logic/experiment.py` Git blob at that commit to be exactly
`c98916c4a0aa17a94c38dd981489693bec5b87a7`. All historical Python is
parsed as source, **never imported or executed**. The check requires an
unambiguous literal `ExperimentConfig.from_variant` mapping and its original
`variant_id` lookup. It separately checks the runner's single awaited
`treatment -> ExperimentConfig.from_variant(variant_id) ->
replace(..., task_id=...) -> run_agent(experiment_config=config)` source route.

The verified *planned source mapping* is:

| Treatment | Planning | Maximum scheduled unique-URL browse calls | Treatment verification |
| --- | --- | ---: | --- |
| D3 | direct | 3 | none |
| D6 | direct | 6 | none |
| P6 | planner | 6 | none |
| P6V | planner | 6 | verify |

All four map to `stream_report=False` in the original factory. This establishes
that the intended retrieval-depth, planning, and verification contrast labels
have matching **historical source definitions**; it is not proof that the
agent honored the budgets or settings in actual treatments. A scheduled
browse-call cap is not a guarantee of completed retrievals or **equal total
compute** across arms.

The source-bound JSON receipt includes the original Git IDs, SHA-256 source
fingerprint, the complete factor mapping, verified handoff and explicit false
scientific claim flags. The existing full-history `historical-design-source-audit`
GitHub Actions workflow now checks this receipt and archives it alongside the
execution-order and task-freeze provenance receipts. Offline regression cases
reject factor substitution, dynamic values, duplicate keys, unexpected return
logic, broken runner config wiring, and mismatched historical blob identity.

**Evidence limits:** The September 11 original treatment and evaluator-recovery
artifacts are no longer listed for download. Therefore original trace/report
custody and actual per-treatment settings remain unauthenticated. The
retrospective source audit cannot resolve the fixed-order time-position
confound, prove historical runtime behavior or establish causal effects. Nor
can it independently establish preregistration of the exact statistical
analysis (committed after treatment/recovery). The pilot is diagnostic; the
frozen automated main-study analysis remains methodologically qualified;
post-hoc diagnostics are exploratory; and genuine blinded human validation
remains pending. This audit runs no treatments, evaluators, or human ratings.
