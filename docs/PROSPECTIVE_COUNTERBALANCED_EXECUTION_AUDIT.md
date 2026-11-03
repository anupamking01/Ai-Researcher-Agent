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

The audit receipt separately reports 40 `recorded_cells` (planned ledger entries), `attempted_cells`, `unattempted_cells`, `all_planned_cells_attempted`, and counts by status. It also records `recorded_status_counts_by_variant` (five status counts for each of D3/D6/P6/P6V), `recorded_fully_completed_task_count` (tasks with all four arms logged as completed), and `recorded_completed_primary_pair_task_counts` (per-task jointly completed D6–D3, P6–D6, and P6V–P6 pairs). These diagnostics expose arm-specific missingness that a single aggregate completed count can conceal after failures or a sequential interruption. They are **self-reported chronology counts**, not verified report/trace completeness, validated scores, or proof of execution. A passing chronology audit is **not a pass of full execution or of paired-inference completeness**. Do not compute a full 40-cell confirmatory analysis from a partial ledger or use missingness to select favorable results. A new design that permits skipping a planned cell and later continuing execution requires a separately defined protocol and auditor; this sequential fail-closed convention does not authorize such gaps.

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
