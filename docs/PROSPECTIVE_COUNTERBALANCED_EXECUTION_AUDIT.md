# Prospective counterbalanced replication: recorded-order audit

**Scope: new, independent future tasks only; no experimental runs or ratings are produced by this tool.**

VERA's 2026 main study ran the fixed D3 → D6 → P6 → P6V order, creating a temporal confound. The separate prospective ten-task Williams design in `scripts/plan_counterbalanced_replication.py` and its independent receipt verifier address order selection for a *future* study; they cannot fix that historical confound.

A design receipt alone does not establish that any treatments were actually executed in the assigned order. `scripts/verify_counterbalanced_replication_execution.py` provides a **read-only check of a candidate execution log** against the original manifest and fully recomputed plan. It does **not** execute treatments, repair logs, verify experiment traces, infer causality, or claim that self-reported timestamps occurred.

## Recording contract (schema v1)

Keep the exact original new-task manifest bytes and the exact plan receipt bytes. For a future sequential task-major replication, the coordinator preserves an **unchanged** JSON log with exactly these fields:

```json
{
  "schema_version": 1,
  "classification": "prospective_replication_recorded_chronology_only",
  "task_set_id": "<new task-set ID>",
  "source_manifest_sha256": "<sha256 of original manifest bytes>",
  "plan_file_sha256": "<sha256 of exact plan JSON file bytes>",
  "started_at_utc": "2027-03-02T12:00:00Z",
  "finished_at_utc": "2027-03-02T13:00:00Z",
  "events": [
    {
      "task_id": "<first manifest task ID>",
      "variant": "<first arm from its frozen plan row>",
      "run_id": "<stable unique run ID>",
      "status": "completed",
      "started_at_utc": "2027-03-02T12:00:00Z",
      "finished_at_utc": "2027-03-02T12:01:00Z"
    }
  ]
}
```

The one-element events array above is **schema illustration only**, not a valid full-run log. The actual audit requires all 40 planned cells in task-major order, preserving each task's four assigned treatments exactly as frozen. Every cell needs a distinct safe run ID and an explicit nonzero interval within the study's UTC window; intervals must not overlap. Accepted **attempted** statuses are `completed`, `failed`, `timeout` and `cancelled`. Failed, timed-out, and cancelled attempts retain their real run IDs and timestamps; they must never be silently discarded or replaced by favorable reruns.

**Interrupted-study retention:** If a sequential run stops after one or more attempts, preserve all remaining planned rows in order with `status: "not_started"` and JSON `null` for **each** of `run_id`, `started_at_utc`, and `finished_at_utc`. These unattempted rows must form a contiguous **suffix**: recording a later attempted treatment after a purported unstarted cell is rejected. Every planned cell remains present exactly once; omission, invented run IDs/timestamps, and zero-attempt logs fail the execution audit. A planned arm that actually began and was subsequently cancelled is **`cancelled` with real timestamps**, not `not_started`. The study-level start/finish times bound attempted events but remain self-reported.

**Portable run identity:** The run-ID uniqueness check is now keyed by ASCII
case-insensitive spelling, not only byte equality. A candidate ledger with
`Future-Run-A` and `future-run-a` cannot claim two independently identifiable
report/trace files on case-insensitive Windows or macOS volumes. The auditor
also rejects Windows device basenames (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`,
`LPT1`–`LPT9`, including extension spellings such as `con.notes`) and trailing
dots that can disappear from directory names. Distinct mixed-case slugs remain
valid. Existing valid receipts and the planned treatment order do not change;
the stricter prospective log gate detects identifier collisions before a log
can be reported as internally consistent. This is filesystem portability and
candidate-lineage consistency only; it does not authenticate run execution,
archived report bytes, or historical evidence.

The audit receipt separately reports 40 `recorded_cells` (planned ledger entries), `attempted_cells`, `unattempted_cells`, `all_planned_cells_attempted`, and counts by status. It also records `recorded_status_counts_by_variant` (five status counts for each of D3/D6/P6/P6V), `recorded_fully_completed_task_count` (tasks with all four arms logged as completed), and `recorded_completed_primary_pair_task_counts` (per-task jointly completed D6–D3, P6–D6, and P6V–P6 pairs). These diagnostics expose arm-specific missingness that a single aggregate completed count can conceal after failures or a sequential interruption. They are **self-reported chronology counts**, not verified report/trace completeness, validated scores, or proof of execution. A passing chronology audit is **not a pass of full execution or of paired-inference completeness**. The receipt additionally distinguishes the **realized** treatment-order exposures from the planned Williams balance: `recorded_attempted_position_counts_by_variant` and `recorded_completed_position_counts_by_variant` show each arm at within-task positions 1–4, while `recorded_completed_primary_pair_order_counts` splits each logged completed primary contrast into `left_before_right` and `right_before_left`. Fully completed synthetic schedules retain two or three occurrences of each arm per position and 5:5 precedence per contrast; interruption or failed treatments can break that balance even though the frozen *plan* stays balanced. Completed-pair direction counts always sum to the previously reported completed-pair task count. These are **self-reported exposure/missingness diagnostics only**, not observed web/model drift, source authentication, an adjusted estimator, proof of randomization, or a reason to select favorable observations. The original 2026 fixed-order findings remain unchanged. Do not compute a full 40-cell confirmatory analysis from a partial ledger or use missingness to select favorable results. A new design that permits skipping a planned cell and later continuing execution requires a separately defined protocol and auditor; this sequential fail-closed convention does not authorize such gaps.

**Frozen task-category position and attrition diagnostic (prospective; outcome-blind):**
The chronology receipt also reports
`recorded_position_exposure_by_frozen_task_category`. Each exact category
label from the **pre-execution task manifest** has a task count and three
arm-by-position (slots 1–4) matrices: `planned`, `attempted`, and
`completed`. Unlike pooled Williams balance, these matrices expose unequal
within-category order exposure and category-specific attrition: failed,
timed-out, or cancelled cells remain attempted but not completed, and a
`not_started` suffix remains planned only. Full 40-cell plans retain exactly
one scheduled occurrence of each arm per task, but **do not guarantee** equal
positions within each coordinator-assigned category. Categories are copied
verbatim from the originally frozen source; the auditor neither validates
the scientific meaning of those labels nor changes assignments, outcome
values, the prespecified analysis, or inclusion rules. These are self-reported,
descriptive exposure/coverage checks, not stratified treatment effects,
independent evidence of execution, a post-hoc reclassification license, or
a correction to historical fixed-order confounding. Do not use them to
exclude inconvenient tasks or to rerun treatments for a preferred result.

**Direction-label interpretation and correction (November 3, 2026):**
For a contrast named `A_minus_B`, `left_before_right` means **A was
recorded before B**, and `right_before_left` means **B was recorded before A**.
Earlier versions of the prospective chronology auditor inadvertently reversed
these *labels* by unpacking subtraction operands in the wrong order. In
receipts produced by those earlier versions, the two direction-count strata
and the corresponding timing-separation strata were **interchanged**.
Pooled completed-pair counts and pooled elapsed-time totals were unchanged.
Previously exported direction-stratified receipts should **not** be silently
reinterpreted: preserve the prior receipt and exact verifier revision, and
regenerate a corrected receipt offline from the **same unchanged task manifest,
plan and execution-log bytes**, recording the verifier revision. This correction
does not modify the frozen 2026 experiment, any treatment outcomes, or the
confirmatory analysis.

**Within-task idle-gap exposure (prospective; outcome-blind):** A planned
Williams order and symmetric start-to-start separations can conceal unequal
idle time *between* consecutive treatments inside the same research task.
The receipt separately reports
`recorded_attempted_within_task_boundary_gap_by_successor_us` and
`recorded_completed_within_task_boundary_gap_by_successor_us`. Each is a
per-successor-arm summary of the **predecessor finish to successor start**
gap (count, minimum, maximum, total in integer microseconds). The complete
sequential 10-task schedule has 30 such boundaries, versus nine cross-task
boundaries. Attempted links retain pauses after failed, timed-out or cancelled
predecessors; completed links require **both** adjacent arms completed.
An interrupted study adds no gaps for an unattempted successor, and empty
groups have null extrema. These are self-reported wall-clock pauses, not
execution durations, drift measurements, causal adjustments, exclusion
criteria, independently authenticated timestamps or evidence of treatments.
They do not modify the frozen 2026 analysis or justify rerunning experiments.

**Within-task primary-pair timing diagnostic:** The receipt additionally reports
`recorded_completed_primary_pair_start_separation_us` for each primary contrast,
stratified into `left_before_right` and `right_before_left`. Each stratum has
the count, minimum, maximum and sum of **absolute start-to-start separations in
integer microseconds**, calculated only when both treatments were logged
`completed`. Divide by 1,000,000 to express seconds; divide the sum by
the count for the descriptive mean when the count is nonzero. Empty strata
have `null` extrema rather than misleading zero-second observations. This
exposes long or asymmetric **recorded** elapsed-time separations that an
otherwise balanced planned/realized order can hide in live-web research.
It does **not** measure actual web/provider drift, establish a tolerance
threshold, reclassify incomplete tasks, change the frozen inferential plan,
or independently authenticate timestamps or execution. It must not guide
outcome-chasing reruns or post-hoc selection of favorable observations.

**Immediate-predecessor / first-order exposure diagnostic:** Pairwise precedence does not tell reviewers which treatment **immediately preceded** an arm within the same task. For each successor arm, the new `planned_immediate_predecessor_counts_by_variant`, `recorded_attempted_immediate_predecessor_counts_by_variant`, and `recorded_completed_immediate_predecessor_counts_by_variant` matrices count each distinct preceding arm (no cross-task adjacency). An additional `recorded_completed_after_noncompleted_predecessor_counts_by_variant` count flags a completed successor following a failed, timed-out, or cancelled predecessor rather than silently treating it as an intact completed pair. The full ten-task plan contains 30 within-task adjacent links; after attrition, logged attempted and jointly completed links may differ. These are descriptive, outcome-blind, **self-reported first-order exposure** checks. They do not measure actual carryover, certify independence or randomization, authenticate execution, establish causal drift adjustment, or imply that a completed successor after a failed predecessor is invalid. No ratings or treatment results are used.

**Cross-task boundary / possible carryover diagnostics:** A task-major
sequential experiment also has nine boundaries between the last scheduled
treatment of one task and the first treatment of the next. Williams balance
within each task does **not** balance or erase these cross-task adjacencies.
The chronology receipt now reports separate
`planned_cross_task_transition_counts_by_variant`,
`recorded_attempted_cross_task_transition_counts_by_variant`, and
`recorded_completed_cross_task_transition_counts_by_variant` 4×4 matrices
(indexed by successor and then predecessor, **including same-arm** boundaries).
The first always totals nine; a stopped suffix reduces recorded attempted and
jointly completed counts. The distinct
`recorded_completed_after_noncompleted_cross_task_predecessor_counts_by_variant`
counts completed first arms whose preceding task's last arm was logged failed,
timed out, or cancelled rather than silently crediting a completed pair.
`recorded_attempted_cross_task_boundary_gap_us` summarizes the nonnegative
recorded predecessor-finish to successor-start pauses, with null extrema
when no boundary was attempted. These are **outcome-blind, self-reported**
exposure and clock diagnostics; they cannot measure actual psychological/model
carryover, environmental drift, causal effects, or external execution
authenticity. They do not alter the frozen schedule, scores, paired inference,
historical fixed-order experiment, or any future prespecified exclusion rule.

**Successor-arm pause exposure (prospective, descriptive only):** The aggregate
`recorded_attempted_cross_task_boundary_gap_us` can conceal whether most of
the recorded idle time occurs immediately before one treatment. The additional
`recorded_attempted_cross_task_boundary_gap_by_successor_us` breaks the same
nonnegative finish-to-start gaps down by the **first arm of the following
task**, including after a failed/timeout/cancelled predecessor. Each arm's
summary contains a count, minimum, maximum and total in integer microseconds;
zero-boundary arms have null extrema and a zero sum. Counts and totals across
arms must reconcile to the existing aggregate. An interrupted study invents no
unattempted boundary gaps. This exposes arm-correlated **recorded pause**
imbalance that a pooled mean or maximum could hide, but it does not measure
provider/web drift, prove carryover, identify a treatment effect, authenticate
the timestamps, change exclusions or justify outcome-guided reruns. The frozen
2026 experiment and prospective treatment schedule are unchanged.


**Per-arm recorded execution duration (prospective, descriptive only):**
A complete chronology can have balanced *scheduled positions* and nearly
identical cross-task pauses while still recording much longer treatment
intervals for one arm. The receipt therefore includes
`recorded_attempted_duration_us_by_variant` and
`recorded_completed_duration_us_by_variant`, each with count, minimum,
maximum and total wall-clock microseconds per D3/D6/P6/P6V arm. Attempted
durations include failures, timeouts and cancellations; completed-only
durations explicitly exclude them. Unstarted cells contribute no invented
duration (zero count and total, null extrema). The counts should reconcile
to the attempted and completed status counts, respectively. These diagnostics
use the supplied start/finish timestamps only: they are **not** token counts,
compute metering, externally authenticated latency, treatment scores,
automatic exclusions, or a new confirmatory analysis. They cannot establish
drift/carryover, repair fixed-order historical confounding, or justify
outcome-selective reruns. The 2026 data and frozen inference are unchanged.

**Within-task paired execution-duration contrast (prospective, descriptive only):**
Arm-wide durations can conceal a task-mix imbalance after a failed or
interrupted sequential execution. The receipt now also reports
`recorded_attempted_primary_pair_duration_delta_us` and
`recorded_completed_primary_pair_duration_delta_us` for the three named
primary pairs. Each signed delta is the first arm **minus** the second arm
(e.g. D6 minus D3) on the **same task**, computed from logged finish minus
start timestamps in exact integer microseconds. Both receipts include counts,
positive/zero/negative counts, minimum and maximum (null when empty), and
`signed_total_microseconds`. Attempted-pair results retain failed, timed-out,
and cancelled intervals; completed-pair results require both arms completed.
Missing or unstarted arms never contribute fabricated zeros. Completed-pair
counts must reconcile to the existing completed primary-pair task counts.
These are outcome-blind recorded-clock **descriptives**, not paired treatment
effects, objective runtime authentication, cost/compute benchmarks, significance
tests, new exclusions, corrections for actual environmental drift, or changes
to the frozen 2026 confirmatory analysis. Retain all recorded attempts;
never select replications based on the sign of these differences.

This is a **prospective sequential-execution convention** for a future study. It is not evidence that the historical study used the convention, and it must not be retroactively applied to historical logs. If the future research protocol predeclares parallel or interleaved execution, it requires a separately versioned auditor rather than silently weakening this one.

## Offline verification

```bash
python -m scripts.verify_counterbalanced_replication_execution \
  --task-manifest <frozen-new-task-manifest.json> \
  --plan-file <original-prospective-plan.json> \
  --execution-log <unaltered-recorded-chronology.json> \
  --expected-plan-file-sha256 <independently-preserved-prerun-sha256> \
  --expected-execution-log-sha256 <independently-preserved-postrun-sha256>
```

Both `--expected-*` pins are optional, but do not describe them as independent evidence unless they were retained separately from the candidate files at the appropriate times. The verifier uses bounded, non-symlink regular-file reads for all three files; rejects duplicate JSON keys, nonfinite numbers, altered plan receipts, missing cells, reordered treatments, duplicate run IDs, non-UTC clocks and overlapping/reversed timestamps; and prints a compact digest/status receipt without rewriting or publishing any research input.

A pass means **the supplied bytes are internally consistent with the frozen prospective design**. No independently authenticated event timestamps, model/provider interactions, retrieved sources, run traces or treatment outputs are established by this check alone. Archival custody, independent pre-execution registration, source-to-run linkage, and actual treatment execution remain separate evidence requirements. No experiment, evaluator, or human annotator was used to develop the synthetic tests for this feature.

The diagnostic pilot, frozen automated confirmatory results, exploratory analyses, this prospective design, and pending genuine blinded human validation are distinct. The 2026 temporal-confounding limitation and original-report recovery blockers remain unchanged.


## Optional independent task-source custody pin

A candidate execution ledger can be internally valid after all three candidate
files (task manifest, plan receipt and event log) have been replaced together.
If the coordinator separately retained the **exact task-manifest SHA-256 before
execution**, the same read-only chronology audit can compare that source pin:

~~~bash
python -m scripts.verify_counterbalanced_replication_execution \
  --task-manifest <frozen-new-task-manifest.json> \
  --plan-file <original-prospective-plan.json> \
  --execution-log <unaltered-recorded-chronology.json> \
  --expected-task-manifest-sha256 <independently-retained-prerun-source-sha256>
~~~

`task_manifest_external_pin_matched` separately records the result, alongside
existing plan-file and post-execution log pins. All three are optional and
verify only equality to coordinator-supplied values; the checker cannot prove
when, by whom or where those values were first preserved, nor that any
execution event occurred. This does not affect historical experiments or
authorize human-rating distribution.
