# Main-study CSV numeric integrity: independent offline preflight

**Scientific status:** Input-consistency audit only. This does not create new
experimental, inferential, exploratory, or human-evaluation outcomes.

The frozen automated inference implementation is SHA-256-bound by the
historical canonical-analysis receipt. **Do not edit or rebind
`scripts/analyze_main_study.py` to add a new input rule.** This verifier
is deliberately separate and read-only, preserving the published result
and its ability to be independently recomputed with the exact historical
implementation. The verifier checks CSV source-internal numeric validity
before a reviewer or later analysis trusts an input table; it is not a new
estimator and does not modify any frozen output.

The preflight rejects nonfinite/negative numeric fields, fractional
integer counts (without rounding them into observations), nonpositive
or over-cap evaluator claim counts, count partitions that do not add up,
missing/duplicate treatment/task cells, and rates inconsistent with
supported/checked counts. It crosschecks the treatment CSV's mirrored
post-hoc claim count, strict rate and evaluator cost with the common
evaluator CSV, and verifies the frozen treatment browse-budget limits.
Small decimal export discrepancies up to absolute `1e-12` are accepted
for rates and cost mirrors. Each observed 10-task × four-arm cell is
included; zero-successful-source treatments remain valid.

The generated receipt contains the original input CSV byte SHA-256
fingerprints and only counts, not scores or new treatment comparisons.
This is **internal consistency**, not proof that the original reports
or traces were authentically archived, nor that automated evaluator policy
was identical across historically recovered cells.

## Offline verification

```bash
python -m scripts.audit_main_study_numeric_inputs
python -m pytest -q tests/test_main_study_numeric_integrity.py
```

These commands make no network/model calls, do not regenerate treatments,
evaluator results or historical statistics, and do not edit canonical
inference artifacts. The dedicated CI workflow runs the same read-only
checks on subsequent source changes. The existing frozen-recomputation
suite independently protects the **original** historical analyzer bytes.

The five-task pilot remains **diagnostic**; the September automated
main-study outcomes retain their post-collection statistical-plan
chronology and fixed-order/evaluator-recovery qualifications; retrospective
sensitivity analyses remain **exploratory**; and human validation remains
pending original-source custody and two independent blinded annotators.
