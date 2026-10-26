# Direct main-study analyzer: frozen input preflight

The canonical, manuscript-facing path is
`scripts/run_verified_main_study_analysis.py`, which independently pins and
snapshots the original treatment and evaluator artifacts before analysis.
The smaller offline `scripts/analyze_main_study.py` entrypoint is also
invocable directly and is used by the isolated snapshot analysis driver.

## Closed evaluation-validity gap

Before this change, the direct analyzer used permissive `csv.DictReader` and
converted evaluator counts through `round(float(...))`. It required a balanced
10-by-4 matrix, but did not independently require the **frozen task IDs**,
budget assignments, exact integer counts, claim cap, consistent evaluator
mirrors, pricing snapshot or treatment-cost methodology. Aligned, re-exported
but scientifically invalid CSVs could therefore yield numeric estimates when
the direct entrypoint was used outside its verified wrapper.

The direct analyzer now uses the **existing canonical strict CSV reader and
frozen scientific preflight** before it joins or analyzes data. The validation
runs on the *same in-memory rows* used for inference, avoiding a redundant
preflight read of potentially different source bytes. No frozen statistical
estimator, contrast, seed, task, or observed result changes.

Synthetic regression tests exercise valid 40-cell inference and reject
fractional counts, nonfinite costs, cost/provenance relabeling, source-budget
drift, contradictory evidence status, cross-export accounting mismatch,
coherently changed task IDs, malformed duplicate CSV headers, and premature
result publication. They are not new treatment/evaluator runs.

## Boundary

This is scientific-domain validation, **not** a cryptographic source-of-truth
check. A direct caller supplying internally valid but unpinned CSV files still
has no independent artifact provenance. For paper/report claims use the
existing manifest-bound verified runner, not this direct entrypoint alone.
The original diagnostic pilot, frozen automated confirmatory analysis,
post-hoc exploratory studies, and pending independent human ratings remain
separate. No human-evaluation result is implied.
