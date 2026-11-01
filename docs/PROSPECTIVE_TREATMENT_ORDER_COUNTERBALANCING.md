# Prospective treatment-order counterbalancing (design-only)

**Status: optional future-study design tool, not a historical repair, not a registered replication, and not a result.** No treatment, common evaluator, statistical inference, or human annotation is executed by this tool.

## Problem addressed

The frozen September 2026 ten-task VERA main study ran each task's variants in the fixed sequence **D3 → D6 → P6 → P6V**. Retrieval and provider conditions could change between calls. Paired-by-task inference does not remove this treatment-versus-time confounding; exact paired sign-flip inference should not be described as randomization in the original study. See MAIN_STUDY_EXECUTION_ORDER_VALIDITY.md and paper/ANALYSIS_PLAN.md.

To remove *systematic* treatment/position coupling in a **separately defined, prospective** ten-task replication, the new offline helper **scripts/plan_counterbalanced_replication.py** creates a reproducible ten-row ordering plan. It is intentionally **not wired into** the original runner or its Actions workflow. Its output cannot replace or repair the historical 40 treatments, and its source manifest must be a *new* independently selected task set fixed before the proposed replication begins.

## Pre-execution design contract

The helper accepts exactly ten distinct new task IDs and questions in a bounded UTF-8 JSON file using **only** these fields:

~~~json
{
  "schema_version": 1,
  "task_set_id": "new-independent-task-set-identifier",
  "frozen_before_execution": true,
  "tasks": [
    {"id": "new-01", "category": "research", "question": "A new research question"},
    {"id": "new-02", "category": "research", "question": "A different question"}
  ]
}
~~~

This is a **schema illustration, not a valid runnable manifest**: the actual file must contain ten distinct entries; do not pad the manifest with historical tasks or select tasks based on the original result directions.

Run in an offline checkout after an independently selected future task set is frozen:

~~~bash
python -m scripts.plan_counterbalanced_replication --task-manifest /path/to/new_frozen_ten_tasks.json > /path/to/proposed_order_receipt.json
~~~

The helper itself writes **only to stdout**. It refuses the original historical task-set ID, unknown or outcome-bearing JSON fields, duplicate keys, IDs or questions, non-finite JSON, missing freeze flag, ambiguous source types, symlinks, oversized inputs (>256 KiB), and an incomplete matrix. This is a structural guard only: it cannot prove that a *different ID* hides reused original questions, or that a manifest was actually frozen before outcome inspection. A coordinator must independently document task independence, pre-execution timestamp, and integrity and ensure there is no treatment outcome feedback into task selection.

The printed receipt includes both the exact SHA-256 of the source manifest bytes and a separate canonical-semantic task-manifest SHA-256 used to assign slots, plus a deterministic design-version identifier, ordered treatment IDs by task, positional counts, pairwise precedence counts, and a SHA-256 of the canonical receipt fields. Reformatting JSON or changing key order does **not** change arm assignment, but does change the source-byte custody hash and full receipt hash. The receipt hash is **not** an external timestamp or independent pre-registration attestation. Preserve the actual manifest and the receipt in a separately reviewable pre-execution location before authorizing future work.

## Design guarantees

The fixed even-order four-treatment Williams Latin square has rows (using the arm index order D3, D6, P6, P6V):

- D3, D6, P6V, P6
- D6, P6, D3, P6V
- P6, P6V, D6, D3
- P6V, D3, P6, D6

Two copies cover eight tasks; the final two schedules are D3, D6, P6, P6V and its reversal. A deterministic SHA-256-based, canonical-task-manifest-bound slot permutation assigns the ten rows to the ten new task IDs. No treatment measurements or adjustable outcome-tuning seed enter the schedule.

For **each** of the six unordered treatment pairs, each member precedes the other on exactly **5 of 10 tasks**. Each variant occurs at every within-task position either **2 or 3 times** across ten tasks—the mathematically closest possible balance because ten is not divisible by four. Every task receives all four conditions exactly once, for **40 planned cells**. Offline regression tests verify these invariants and the receipt digest.

This balances *position* and *pairwise ordering*, **not** total tokens, latency, dollar budget, or time-varying web content. It does not guarantee independence, remove across-task temporal drift, or imply random assignment in the original study. There is no claim of a causal effect or inference validity from a schedule alone. An actual future independent replication would need its own ethics/provenance, predeclared budget and inference decisions, clean source custody, and separate human validation.

## Research claim separation

- **Original pilot:** diagnostic operational evidence only.
- **Original 2026 confirmatory analysis:** frozen paired automated measurements from the historical fixed-order main study; unchanged by this design.
- **Exploratory robustness checks:** retain exploratory status and cannot choose a favorable future schedule from observed results.
- **Human validation:** still pending two eligible blinded annotators and authenticated original reports; this prospective schedule produces none.

This work neither recovers the absent original treatment/recovery artifact listings nor resolves the historical source-to-evaluation custody gate. Do not distribute human packets or represent VERA as fully validated on the strength of this planning tool.
