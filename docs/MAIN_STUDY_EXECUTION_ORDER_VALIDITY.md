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

## Scientific reporting and unresolved gates

Disclose fixed-order temporal confounding explicitly in the eventual manuscript's threats to validity even if it complicates an appealing interpretation. Preserve the exact first complete 40-cell treatment dataset, recorded zero-evidence outcomes, the existing post-hoc evaluator, all preregistered paired estimates and Holm-adjusted p-values. Do not select reruns, reorder observed cases, or claim that retrospective timestamp checks repair the allocation design.

A separately authorized future replication could prospectively predeclare randomized/counterbalanced order and time-sensitive evidence capture, but must be labeled separately; it does not retroactively randomize the original main study. Full recovery and independent custody of original treatment traces, reports, retrieval evidence and progress remain blocked, as does distribution to two eligible blinded human annotators.

Keep the five-task pilot diagnostic; label the original ten-task automated inference as frozen confirmatory **under its assumptions**, the task-influence/Pareto diagnostics exploratory, and genuine independent human validation pending. Human ratings, even when available, cannot repair treatment-order confounding or prove historical archive authenticity.
