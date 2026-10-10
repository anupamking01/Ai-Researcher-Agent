# Human-evaluation packet and blinding-key verification

This implementation note adds a coordinator-side integrity gate for the
deterministic human-evaluation packet. It does not amend the frozen annotation
rubric, assignment plan, automated analysis plan, or any experimental result.

## Why this gate exists

The blinded packet is useful only if its coordinator mapping still points to the
same frozen treatment reports that were randomized into the packet. A packet
hash alone cannot detect a blinding key that was accidentally edited, reordered
incorrectly, copied from another run, or paired with different trace/report
files.

The packet builder therefore records byte counts and SHA-256 fingerprints for
packet.jsonl, ratings_template.csv, and blinding_key.csv in manifest.json.
The verifier checks those fingerprints and independently checks the semantic
mapping back to the frozen task manifest, experiment traces, and Markdown
reports.

## When to run it

Run the verifier immediately after packet generation and before distributing
annotator-facing files:

    python scripts/verify_human_eval_packet.py

Run it again after the blinded rating freeze has passed
scripts/verify_human_eval_freeze.py and before treatment-level human analysis.

This verifier is coordinator-side because it reads blinding_key.csv. Do not run
it in an annotator environment and do not expose the key or treatment mapping to
annotators.

## Checks performed

The verifier fails closed unless:

- the packet manifest has the expected study, task-set, variant, and artifact
  fingerprint contract;
- the frozen task manifest fingerprint still matches packet generation;
- packet blind IDs are unique and cover exactly the frozen tasks;
- packet questions still match the frozen task questions;
- the coordinator key contains one mapping for every blind ID and exactly one
  D3, D6, P6, and P6V report for each frozen task;
- every key row agrees with its persisted trace identity, task-set ID, run ID,
  completion state, and question;
- every persisted Markdown report exactly matches the report text shown in the
  packet;
- the ratings template covers exactly the packet IDs and remains unscored.

The command prints a compact verification receipt. It does not read annotator
rating files and does not compute a treatment effect or human-validation result.

## Existing packets

Packets created before artifact fingerprints were added do not satisfy this
gate. Because real annotations are still pending, rebuild the deterministic
packet from the canonical preserved traces before it is distributed. Once
annotation starts, preserve that exact packet/key/manifest set and do not
silently regenerate it.

## Limits

This detects accidental provenance drift and inconsistent copies; it is not a
cryptographic signature or an external timestamp. An actor able to rewrite the
repository, all source artifacts, and the manifest can create a new internally
consistent history. Preserve Git history and canonical research artifacts as the
external provenance anchor.

Passing packet verification also does not substitute for the separate blinded
rating freeze, agreement checks, or a preregistered human-evaluation analysis
plan. No human-quality claim should be made until real ratings have been
collected and the relevant post-freeze gates have passed.

## Report-to-run binding

Before distributing a newly generated packet, the builder and independent
coordinator verifier require each Markdown report to resolve to
`outputs/<run_id>/research_report.md` for the originating trace, with that
trace stored as `outputs/experiment_traces/<variant>/<run_id>.json`.
The trace's recorded PDF path may resolve to the sibling Markdown report,
but it must not point to a different completed run, a symlink, or a
traversal path. The verifier checks the blinding key against the trace's
recorded report source in addition to comparing the report text and hashes.

This is a source-provenance guard, not evidence of human agreement or a
change to treatment outcomes. It does not regenerate published packets.

## Strict completion-state typing

Both packet construction and independent coordinator verification require the
persisted trace's `completed` field to be **JSON boolean `true`**. Python
truthiness is not a completion guarantee: strings such as `"false"` and
`"true"`, numeric `1`, and nonempty objects must all fail closed even when
other trace and packet provenance checks pass. Existing valid Boolean completion
traces are unaffected. This is a source-validity check only; no completed
experiment is rerun and no rating or treatment result is inferred.
