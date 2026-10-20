# Human-evaluation packet task provenance

This implementation note documents how `scripts/build_human_eval_packet.py`
binds the blinded packet to the frozen main-study task set. It does not amend the
frozen human-rating rubric, assignment plan, confirmatory analysis plan, or any
reported automated result.

## Frozen-task binding

Packet generation now requires a task manifest that was explicitly marked
`frozen_before_execution`. For the canonical study this is
`experiments/main_budget_tasks.json`.

Before any annotator-facing file is written, the builder requires all of the
following:

- every trace belongs to the task manifest's exact `task_set_id`;
- trace and experiment sections agree on treatment variant and task identity
  whenever both declare those fields (legacy one-sided metadata remains valid);
- every trace task ID exists in the frozen task manifest;
- every trace's research question exactly matches the frozen question for that
  task after surrounding whitespace normalization;
- the observed task IDs exactly equal the frozen task IDs, so losing all four
  treatment traces for one task cannot silently shrink the evaluation packet;
- every frozen task still has exactly the expected D3, D6, P6, and P6V cells.

The generated `manifest.json` records the task-set ID plus the raw byte count
and SHA-256 fingerprint of the task manifest used to build the packet.

## Why this matters

The previous per-task matrix check could detect one missing treatment within an
observed task, but it inferred the task universe from the traces themselves. If
all four traces for a frozen task were absent, that task disappeared from the
inferred universe and packet generation could still succeed. That would make
human validation cover a different task set from the automated main study.

Binding packet construction to the frozen task manifest makes a missing task,
question drift, task-set drift, or an unfrozen replacement manifest a hard
failure before packet publication.

This safeguard validates identity and coverage only. It does not generate human
ratings, alter treatment outputs, rerun the automated evaluator, or change any
pilot, confirmatory, exploratory, or human-validation claim.

## Capture-time path binding

The packet builder reads the frozen task manifest, treatment traces, and source
reports through retained non-symlink file descriptors. After each read it
requires the descriptor identity, file metadata, parent-directory identity,
and final pathname binding to remain unchanged. Packet verification applies
the same capture rule to the packet manifest, annotator-facing artifacts,
blinding key, task manifest, traces, and reports.

This prevents a concurrent pathname replacement from becoming trusted merely
because the replacement bytes are the ones subsequently hashed. A detected
file or parent-directory replacement fails before packet publication or a
successful verification receipt. The rule strengthens provenance capture only;
it does not alter packet randomization, blinding, rubric semantics, or any
research result.

## Cross-section identity consistency

Persisted experiment traces can carry `variant_id` and `task_id` in both the
`experiment` metadata and the `trace` body. Packet construction and independent
packet verification must reject conflicting non-empty values rather than
implicitly trusting one copy. Otherwise a report could be assigned to the
wrong treatment or task even though its path, source text, and packet hashes
are consistent. Legacy traces with an identity in only one section remain
supported. This is a source-integrity guard, not a change to experimental
results or the frozen human-evaluation analysis.
