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

The one-element events array above is **schema illustration only**, not a valid full-run log. The actual audit requires all 40 planned cells in task-major order, preserving each task's four assigned treatments exactly as frozen. Every cell needs a distinct safe run ID and an explicit nonzero interval within the study's UTC window; intervals must not overlap. Accepted recorded statuses are `completed`, `failed`, `timeout` and `cancelled`. Failed and timed-out cells are **retained** in the ledger, never silently discarded or replaced by favorable reruns. A passing chronology audit does not mean all 40 cells completed successfully.

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
