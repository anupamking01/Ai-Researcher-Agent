# Frozen diagnostic-pilot treatment-factor integrity

The five-task diagnostic pilot compares three *predeclared* arms, not arbitrary
configurations that happen to share a variant label:

| Arm | Planning | Scheduled sources | In-treatment verification |
| --- | --- | ---: | --- |
| D6 | direct | 6 | none |
| P6 | planner | 6 | none |
| P6V | planner | 6 | verify |

Previously, postrun validation compared source counts with the `source_budget`
**declared by the same trace**, derived expected query counts from the trace's
own `planning_mode`, and enforced verification status according to the
trace's own `verification_mode`. A self-consistent mislabeled record could
therefore satisfy those checks: for example, `P6V` with verification disabled
and a `not_requested` status, or `D6` with planner-mode queries.

`scripts/validate_pilot_artifacts.py` now independently binds those three
factors to each arm. It rejects inconsistent or missing trace factors and
disagreements in any explicitly recorded experiment metadata. Legacy
experiment metadata may omit optional factor fields only when the trace itself
contains the correct frozen assignment. Count/query and verification checks
now use the arm's frozen assignment, not a factor supplied by the trace.

The factor table is intentionally separate from
`ExperimentConfig.from_variant()`: an accidental change to the live producer
must not silently redefine what the independent postrun validator considers
a valid treatment. Offline synthetic regressions check both components,
including self-consistent factor tampering, missing/null values and the
distinction between `True` and integer source budgets.

Reproduce without credentials or treatment execution:

```sh
python -m pytest -q tests/test_pilot_treatment_factor_identity.py \
  tests/test_pilot_plan_identity.py tests/test_pilot_source_url_accounting.py
```

This is a **prospective diagnostic-pilot integrity guard**, not retroactive
authentication of historical pilot traces. The existing five-task pilot remains
diagnostic; the frozen ten-task automated analysis remains methodologically
qualified, with historical fixed-order and analysis-plan timing limitations.
Retrospective measurement-sensitivity and Pareto analyses remain exploratory.
No missing original evidence is recovered by this check, and independent
blinded human ratings and automated–human reconciliation remain pending.
