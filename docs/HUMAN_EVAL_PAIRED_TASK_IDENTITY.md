# Frozen paired human-analysis task identity guard

**Scope:** implementation-only defense in depth for the frozen ten-task human
validation analysis. No ratings have been collected, no experimental treatments
or evaluators were rerun, and the frozen analysis plan, bootstrap seed/draws,
outcomes, inclusion rules, and confidence-interval method are unchanged.

## Why task identity matters

The paired analysis unit is the frozen task, not an independent rating row
or a resampled copy of the same report. Passing 11 synthetic report pairs to
a direct statistics helper cannot represent eleven distinct tasks in this
ten-task study. Even a shorter vector may silently repeat the same task ID,
weighting that task twice and incorrectly increasing the apparent precision.
Per-score 1–5 and half-point lattice checks cannot detect pseudoreplication.

## Enforced contract

* `_paired_summary(left, right, *, seed, task_ids=None)` rejects more than ten
  paired entries. This applies even to legacy ID-free direct calls.
* Both left/right report-score vectors are likewise captured as bounded **ordered**
  iterables (at most eleven items inspected for the ten-task limit) before
  task-ID pairing or bootstrap. Mapping objects, dictionary views, sets,
  text, and byte sequences cannot silently supply positional scores. An
  integer-keyed dictionary previously happened to work by numeric indexing,
  but its key semantics were not an explicitly aligned observation sequence.
  One-shot numeric generators are consumed once and retained as a snapshot.
  Existing canonical lists and frozen 20,000-draw results are unchanged.
* This is a direct-helper input-contract safeguard, not atomic capture of two
  concurrently edited external files or independent task/report authentication.
* When task IDs are supplied, they must be a bounded **ordered** iterable
  with exactly one nonempty, trimmed **string** ID for each aligned vector
  position, without duplicates. Unordered sets and mappings are rejected;
  one-shot generators are consumed once, up to eleven elements.
  Mapping **views** (including `dict.keys()` / `dict.values()`),
  non-`dict` mapping implementations and custom set types are rejected too:
  their incidental iteration order does not establish positional score
  alignment, even if they yield distinct, well-formed string IDs.
  Identity validation happens before the frozen bootstrap.
* The paired task labels and both aligned score vectors are sorted together
  lexicographically by task ID **before** seeded bootstrap resampling. The
  same labelled task pairs therefore give identical finite-draw bootstrap
  results and ordered per-task differences regardless of the input row order.
  Previously an incidental permutation could change the Monte Carlo CI
  even though the complete set of observed pairs was unchanged.
* Canonical `analyze()` now supplies its already-verified, sorted, paired
  inclusion list (`complete`) to `_paired_summary`. The historical estimate
  and 20,000-draw bootstrap remain numerically unchanged for valid inputs.
* Legacy direct calls without `task_ids` remain supported with their
  original positional order for existing notebooks and tests; the helper can
  then enforce only the ten-pair ceiling, **not** detect repeated IDs or
  guarantee permutation-invariant seeded CIs. Direct callers should supply
  their task IDs.
* The optional ID check verifies alignment and uniqueness, **not** the
  authenticity of an ID against the frozen task manifest. Canonical analysis
  still requires the independent blinded freeze and packet/mapping verification
  before the task IDs are supplied.

All added regression cases are synthetic and check invalid vector sizes,
duplicate/missing/overlong/unordered identity streams, permutation-stable
labelled pairs, valid aligned pairs, and the
ten-task boundary. This does not provide human-validation evidence or repair
the unavailable original treatment-report and trace artifacts.


## Verified task-level attribution under reordered manifests

`_paired_summary` canonicalizes task-labelled score pairs by lexicographic
task ID. Its returned positional `task_differences` are therefore already
sorted even when the verified task manifest arrived in a different order.
Previously canonical `analyze()` zipped the sorted differences with its
**original** `complete` task list: a permuted manifest could silently
assign the right numerical effect to the wrong task in publication JSON.

The consumer now binds to the same canonical ordering using
`_label_paired_task_differences`, with explicit cardinality and unique-ID
checks. Synthetic reversed-order, distinct-effect cases verify that labels
remain attached to the correct tasks, and inconsistent label counts fail
closed. The normally sorted frozen manifest produces unchanged estimates,
bootstrap, inclusion, and output schema. This does not independently
authenticate original reports/traces or establish any human-validation result.
