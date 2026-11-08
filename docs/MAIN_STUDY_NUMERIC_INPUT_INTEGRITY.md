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


## Local CSV capture and receipt continuity

The read-only numeric preflight now opens each fixed CSV using a held file
descriptor with no-follow directory and file flags. It requires a regular,
single-linked input no larger than 2 MiB, reads only the initially observed
length, detects append-only growth, and checks the opened inode, pathname,
size, link count, and modification/change metadata before accepting bytes.
After semantic validation it independently recaptures both original paths
and refuses to issue the receipt if either content changed. Synthetic
regressions exercise symlinks, hard links, oversized inputs, path replacement,
in-place modification, and post-parse edits; they do **not** use live treatment
or evaluator observations.

This is a **bounded, locally consistent capture**, not an atomic snapshot of
two files, and not proof of historical originality, collision resistance of
filesystem metadata, or protection against an attacker who changes bytes and
restores them between observation points. The auditor reports hashes of the
actual bytes it parsed; it does not revise or authenticate the original 40
reports/traces. The separately frozen September analyzer and all recorded
automated/pilot/exploratory results remain unchanged.
