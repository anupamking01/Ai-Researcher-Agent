# Main-study offline summary: complete local evidence inventory

The noncanonical/offline `scripts/summarize_budget_main_study.py` previously
enumerated only `experiment_traces/<variant>/*.json` and
`posthoc_evaluations/*/*.json`. A backup, misnamed or unexpected-variant
treatment trace or evaluator cache could be silently ignored when producing
a descriptive cost and support summary. Ignored attempted runs could
understate retained execution or measurement evidence.

The summarizer now reuses the **same fail-closed, bounded, no-follow
directory inventories** as `scripts/evaluate_posthoc_support.py`:

- Every entry under the trace root and each allowed variant directory is
  checked before any trace is used. Only regular, non-symlink JSON files
  inside the selected variant directories qualify.
- The evaluator cache root is likewise fully inventoried, including
  unexpected variant directories, non-JSON sidecars and dangling links.
  An absent evaluator cache root remains an empty inventory, after which
  a completed trace without a matching evaluation is still rejected.
- Only the complete inventories are parsed. An unselected entry stops
  the summary before its JSON/CSV outputs are written.

Synthetic offline regressions cover backup-like entries, unexpected variant
directories and dangling links in **both** inventories. The existing
one-cell acceptance case still exercises the valid descriptive path.
This change does **not** require a full 40-cell matrix in unit-level or
diagnostic summary fixtures; the separate frozen-matrix preflight remains
responsible for that requirement.

These are local record-selection checks, not independent authentication
of the inaccessible original 40 report/trace pairs or an atomic filesystem
snapshot. The five-task pilot remains diagnostic. Frozen automated
comparisons carry their post-collection planning, fixed-order and
evaluator-policy limitations. Exploratory sensitivity analyses are not
prospectively confirmatory, and blinded human validation remains pending.
No treatments, post-hoc evaluators or annotators need be rerun.

## Distinct run-ID custody across treatment arms (22 November 2026)

The offline summary also requires **one unique `run_id` per treatment cell,
across all variants**. Two independently labelled trace files in different
variant directories could previously name the same `outputs/<run_id>/research_report.md`.
Their individually validated evaluator caches and trace-ledger costs do not
make one physical report into two independent treatment outputs. Reuse now
stops descriptive publication before JSON or CSV writes, with both implicated
cells identified. This closes the summarizer path independently of the
prospective noncanonical runner's new-completion gate and the separate
40-cell evaluator replay preflight.

Offline synthetic cases exercise collisions for D3 against D6, P6 and P6V,
plus a positive two-arm case with distinct run IDs. Partial diagnostic
fixtures remain permitted; no historical source file is modified or recreated.
This is a local provenance/identity requirement, not source authentication or
human validation, and does not revise frozen automated outcomes.

## Cryptographic binding of descriptive summary to run table (22 November 2026)

The offline descriptive generator previously wrote its JSON summary and its
run-level CSV separately, without a digest linking the two generations.
A partial write or later replacement could leave a plausible summary paired
with different run rows, without visibly changing the stated aggregate means.

The generator now serializes the CSV once in memory, binds its exact UTF-8
bytes into the summary as `main_study_runs_sha256` and
`main_study_runs_size_bytes`, publishes the CSV before the JSON, and
independently re-reads the retained pair through the existing bounded,
no-follow source reader. The reusable
`_verify_main_study_summary_pair` rejects missing, replaced or
inconsistently fingerprinted output evidence. Four synthetic offline
regressions cover a valid replay, same-length CSV substitution, missing CSV,
and missing JSON fingerprint. The table row definitions and measured values
are unchanged.

This is a **local generation-consistency** check, not an atomic two-file
commit, a substitute for read-only source archive verification, or a claim
that any original historical source has been recovered. A crash can still
leave an incomplete pair; replay then fails closed. Existing frozen analysis
files and the pilot are not rewritten, automated retrospective sensitivities
remain exploratory rather than prospectively confirmatory, and genuine
blinded human-validation results are still absent.


## Optional post-hoc aggregate pair presence (22 November 2026)

A noncanonical descriptive summary does **not** require previously published
post-hoc aggregate JSON/CSV files: a local replay can use validated treatment
traces and per-cell evaluator caches directly. But if either optional aggregate
output is present, **both** must exist as independently readable regular,
non-symlink files and the JSON's recorded CSV digest must match the retained
CSV. Previously, a dangling `posthoc_support_summary.json` was silently
treated as absent by `Path.exists()`, and an orphaned
`posthoc_support_runs.csv` was never examined. These states could mask an
interrupted or mixed-generation upstream publication while producing a fresh
plausible descriptive report.

The preflight now detects both one-sided artifacts with `lstat`, including
dangling links, and refuses publication until source provenance is reviewed.
An absent pair remains allowed; a complete digest-matched pair is accepted.
Seven synthetic offline regressions cover incomplete/dangling pairs, linked
sources and the intact pair. This only strengthens local descriptive evidence
custody; it does not authenticate the inaccessible historical research
artifacts, alter the frozen outcomes or establish human validation.
