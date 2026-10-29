# Blinded packet producer: prepublication evidence-custody gate

**Scope:** prospective, offline human-evaluation packet generation. No original
treatments, post-hoc evaluator outputs, automated confirmatory results, or human
ratings are changed or created by this safeguard.

## Why a second check is required

The packet producer originally captured each frozen-task, trace, and Markdown
report file through a bounded descriptor and validated its pathname identity
*during that individual read*. A source file captured early could nevertheless
be replaced, edited, or relinked while the remaining reports were being read or
while their annotator-safe content was checked. The producer could then reserve
its create-only destination using a packet assembled from a source generation
that no longer existed. The independent verifier already performs a separate
whole-window check, but that is a later gate, not permission for the producer
to publish known-stale inputs.

## New producer-side contract

Before creating **any** packet file, the producer now re-enumerates the
complete bounded trace directory and requires its selected paths to match the
first scan. It then re-reads the frozen task manifest, every selected treatment
trace, and each corresponding Markdown report with the existing bounded,
descriptor-bound regular-file reader. The resulting byte-length/SHA-256 values
and filesystem device/inode identities must match those captured during the
initial read. A changed file, replaced inode (even with equal bytes), or added
source-tree entry fails before the output-root reservation.

For **production** packets, the separate historical run-ID lineage gate also
captures the exact fingerprint and device/inode of the pinned post-hoc evaluator
CSV after verifying all 40 treatment/task/run-ID identities. The producer now
re-reads this evaluator CSV after the trace/report source-window audit and before
reserving the output. A changed CSV or same-byte file replacement fails closed.
Direct synthetic test callers remain unpinned unless they explicitly request
production source checks; no original evaluator results are recalculated.

The original source fingerprints remain the ones recorded in the private
coordinator manifest. No new private source identifiers enter annotator
materials or the published packet schema. Regression tests inject source
changes **after initial collection** and assert that the destination is never
created.

This is not an atomic multi-file snapshot, a historical original-source
authentication, or a substitute for independent packet verification. A change
after the final recheck can still occur. Keep original archives immutable,
verify the completed packet independently, and do not generate human packets
from the still-unrecovered 40 historical traces/reports. Genuine blinded
two-annotator ratings and human–automated reconciliation remain pending.
