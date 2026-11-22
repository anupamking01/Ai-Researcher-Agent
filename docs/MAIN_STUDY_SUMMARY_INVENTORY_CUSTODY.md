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
