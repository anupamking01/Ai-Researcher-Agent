# Historical main-study order: a design-level validity limitation

**Status:** Retrospective, post-hoc design and provenance diagnostic. It is not a new confirmatory test or a recalculation of treatment outcomes.

## Historical implementation and identification limit

The original treatment runner at immutable revision [c3c15e46a8eec3a8bbc24c968eedc0548172a897](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/scripts/run_budget_main_study.py) iterated through ten fixed tasks and, **within each task**, executed **D3, D6, P6, P6V** in that order. Each run was awaited before the next began. Its progress writer recorded per-run start and finish timestamps in outputs/main_study_progress.json. This arrangement preserved matched task prefixes if a cost limit stopped execution; it did **not** randomize or counterbalance arm assignment.

Treatment identity was consequently tied to relative execution time within each task. Mutable search results, web availability, transient browsing failures, or provider behavior might differ as the successive treatments ran. The paired design controls task identity but cannot by itself remove within-task temporal-order confounding. The exact sign-flip calculation in paper/ANALYSIS_PLAN.md enumerates paired sign assignments; it must not be described as evidence of historical random treatment allocation. This is a validity caveat regardless of any observed effect direction, not permission to replace the preregistered analysis.

## Read-only archived progress-log diagnostic

Once an **unchanged original** outputs/main_study_progress.json is found in the historical treatment archive or authorized offline storage, run this from the research checkout:

    python -m scripts.audit_main_study_execution_order --progress-json /path/to/main_study_progress.json

If its file-byte SHA-256 was demonstrably retained independently **before** the candidate's recovery, optionally add:

    --expected-sha256 <independently-retained-original-file-sha256>

Never derive a new hash from a suspect candidate and represent it as a historical custody pin. The command checks the recorded original study and task-set identity, exact 40 completed event order, zero recorded failures/timeouts, non-overlapping explicit UTC run timestamps, and full task-major D3/D6/P6/P6V schedule. Reads are bounded and require an ordinary non-symlink file. Duplicate JSON keys, malformed/nonstandard JSON, contradictory counters and sequence/timing inconsistencies fail closed. The command prints a JSON receipt with status recorded_fixed_order_consistent_not_authenticated; it does not write evidence, re-execute treatments or evaluators, generate ratings, or modify measurements.

This structural test **cannot** independently authenticate the historical log, its timekeeping, external archive custody, or stable live-web conditions. Matching a supplied SHA-256 alone establishes file-byte consistency, not trustworthiness of the source of that pin. Original treatment Actions run 34620917346 and evaluator-recovery Actions run 34783525480 exposed no downloadable artifacts when checked October 31, 2026. **No authentic recovered log has passed this audit**. The published frozen treatment and evaluator CSVs omit event timestamps, and their row order must not be treated as chronological evidence.

## Retrospective clock-exposure diagnostic (not observed web drift)

The read-only receipt now also includes `recorded_clock_exposure`: the recorded
study start-to-finish window and, for **each of the ten tasks**, the difference
between treatment **start timestamps** for the three frozen primary contrasts
(D6 minus D3, P6 minus D6, P6V minus P6). It reports exact integer
**microseconds** to avoid rounding away short intervals, plus minimum and
maximum separations across tasks. These offsets describe how far apart the
compared arms began in the recorded task-major sequence; they do **not**
measure drift in web pages, model behavior, task difficulty, or outcome quality.
No additional hypothesis test, regression on outcomes, or replacement effect
estimate is computed. The fixed treatment order remains nonrandomized, the
sign-flip assumptions remain limited, and the output remains unauthenticated
until independent historical custody is established. Synthetic tests exercise
the receipt; no historical offsets are asserted while the original log is
unavailable. If an authentic log is recovered, cite the provenance and timestamp
receipt together and disclose the timing ranges as post-hoc descriptive context,
never as a correction for the design confounder.

## Strict parsing of recovered numeric fields

A recovered progress log is untrusted data even if its recorded task/arm
sequence looks consistent. The chronology auditor rejects JSON integer or
floating-point tokens longer than 128 characters **before conversion**, and
rejects decimal-exponent float values that overflow Python's finite range.
These rules apply to ignored metadata as well as the audited fields. This
prevents a long integer from aborting JSON decoding through Python's
interpreter-specific digit limit and prevents syntactically valid `1e400`
from silently becoming infinity. The observed final
`estimated_treatment_cost_usd` must also be a nonnegative finite JSON
number. These parser checks do not re-estimate costs, attest the historical
file or relax the need for independently preserved archive fingerprints.
They are covered only with synthetic, offline regression cases while the
original progress log is unavailable.

## Scientific reporting and unresolved gates

Disclose fixed-order temporal confounding explicitly in the eventual manuscript's threats to validity even if it complicates an appealing interpretation. Preserve the exact first complete 40-cell treatment dataset, recorded zero-evidence outcomes, the existing post-hoc evaluator, all preregistered paired estimates and Holm-adjusted p-values. Do not select reruns, reorder observed cases, or claim that retrospective timestamp checks repair the allocation design.

A separately authorized future replication could prospectively predeclare randomized/counterbalanced order and time-sensitive evidence capture, but must be labeled separately; it does not retroactively randomize the original main study. Full recovery and independent custody of original treatment traces, reports, retrieval evidence and progress remain blocked, as does distribution to two eligible blinded human annotators.

Keep the five-task pilot diagnostic; label the original ten-task automated inference as frozen confirmatory **under its assumptions**, the task-influence/Pareto diagnostics exploratory, and genuine independent human validation pending. Human ratings, even when available, cannot repair treatment-order confounding or prove historical archive authenticity.

## Prospective manual-run labeling boundary (31 October 2026)

The original main-study workflow at Actions run `34620917346` has already
executed. Re-running its historical treatment command to replace lost traces,
obtain more favorable outcomes, or fill the original evidence gap would
misrepresent the frozen first-execution dataset. The current
`.github/workflows/budget-main-study.yml` therefore requires an **explicit
manual acknowledgment** of `NONCANONICAL_REPLICATION` as its unconditional
first step, **before checkout, provider secrets, preflight, or paid model
execution**. The required text input has no accepting default. A missing or
different acknowledgement fails the workflow immediately. A future authorized
execution's artifact name begins `noncanonical-replication-budget-study-`
and its Actions summary warns that new outputs cannot substitute for original
historical evidence.

This is an **anti-accidental-rerun and provenance-labeling boundary**, not a
claim that future reruns are preregistered or scientifically comparable. The
legacy runner still emits its historical internal `study_id`, so the new
artifact label and execution date must be retained when interpreting any
future dataset. A genuinely independent replication still needs a separately
versioned, prospectively frozen protocol and should address fixed-order
time confounding through deliberate counterbalancing/randomization.
The guard applies to **dispatches using this updated workflow revision**; it
cannot retroactively prevent someone from executing an old commit or using
GitHub's rerun facility, and it cannot authenticate the missing original
archives. `tests/test_historical_treatment_dispatch_gate.py` checks the
dispatch restriction and explicit artifact separation in ordinary offline CI.
No treatment, evaluator, scientific result, or human-rating output was changed
by introducing this guard.

## Frozen published treatment-cost correspondence (offline, not provider billing)

A recovered main-study progress file may report the correct 40 events and
plausible chronological timestamps while its final cumulative cost contradicts
the original frozen treatment-resource ledger. The read-only chronology CLI now
requires the original `outputs/main_study_runs.csv` bytes to match their
published SHA-256
`966ea80519af5ea7b832c86d7868525a4ef75874f396f242291e3be949382a0e`.
It checks exactly 40 distinct completed treatment/task cells and sums their
`treatment_cost_usd` values. The progress log's final
`estimated_treatment_cost_usd` must agree within `1e-12` USD, an allowance
only for floating-point summation order. Changed CSV bytes, missing/duplicate
cells, irregular rows, nonfinite/negative costs and contradictory progress
totals now fail closed. The published CSV is captured with a size bound,
regular-file/non-symlink checks, and descriptor/path generation checks.

Use the original chronology command above; by default it reads the pinned
frozen CSV in this checkout. `--published-treatment-csv` may point at another
copy, but **cannot** override the immutable digest requirement. This is an
internal recorded-cost consistency gate, not verification of provider billing,
historical source authenticity, retrieval correctness or independent
archival custody. Original progress archives remain unavailable, so the
new behavior is validated only against explicitly synthetic progress fixtures
and the already frozen published CSV. No treatments, evaluator or human
ratings are produced or changed, and temporal confounding remains unresolved.

## GitHub Actions original-treatment step clock concordance (offline)

The original main-study workflow
[run 34620917346](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34620917346),
**attempt 1**, job **103334373932**, reports the **"Run 10-task
four-variant treatment matrix"** step at **2026-09-11 16:15:52Z to
17:12:08Z** (GitHub Actions jobs API, checked 2026-10-31). That treatment
step succeeded; the workflow's subsequent common-evaluator step failed.
The treatment step's time window must not be confused with the workflow's
later completion or with the independent evaluator-recovery run.

The production chronology CLI now fails closed if a candidate progress
log's enclosing study-start or study-finish timestamp falls outside the
original GitHub treatment-step window, with **five seconds of tolerance**
on either edge for second-resolution GitHub timestamps and modest clock
skew. The auditor already checks that all 40 sequential event intervals
fall inside those two enclosing timestamps. The read-only JSON receipt
includes `historical_actions_step_window_concordance`; the production
CLI does not offer an opt-out. Synthetic Python callers may explicitly
pass `require_historical_actions_step_window=True` to test the gate.

This rejects an internally consistent but **temporally impossible**
candidate history. GitHub's own service metadata is not an independent,
signed custody record. Matching this window cannot authenticate missing
historical trace/report bytes, prove wall-clock accuracy or web stability,
resolve fixed-order confounding, or authorize distributing blinded packets.
No recovered original progress log has yet passed this check.
