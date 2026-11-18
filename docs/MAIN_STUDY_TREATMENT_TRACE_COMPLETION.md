# Noncanonical main-study treatment trace completion gate

An exception-free agent return is not proof of a completed treatment. An
empty report can yield an incomplete trace without an exception, and a
missing trace contributes zero reported usage to the next-treatment spend
guard.

The separately acknowledged noncanonical runner now inventories trace names
before each treatment, and requires exactly one new trace afterward, without
disappearance of previous names. It also pins earlier trace identities,
metadata and SHA-256 bytes before running the next treatment, rejecting an
observed in-place edit or same-byte inode replacement even if the prior filename
still exists. The trace must reside under the requested
variant, pass the existing scientific/provider usage ledger validator, declare
completed=true and match the requested variant, task set and task ID in both
its experiment configuration and trace record. **A trace alone is not sufficient:**
the matching `outputs/<run_id>/research_report.md` must be present as a
regular, unlinked UTF-8 file of at most 8 MiB, its word count must match
`trace.report_words`, and the recorded `report_path` must point to the same
run's Markdown or PDF export. This covers the generated Markdown that the
report writer retains even when PDF conversion fails. Earlier reports are
fingerprinted alongside earlier traces before each later treatment; observed
report content or inode replacement stops execution even when the new
trace and report look valid. Failure stops further
treatment execution; it never retries or replaces the attempted treatment.

Offline tests use synthetic traces and a stub agent, not real provider calls.
This does not modify canonical evidence or the original historical runner,
authenticate original missing archives, guarantee an atomic filesystem
snapshot against concurrent tampering, protect other files outside the
tracked trace/report paths, or prove recorded provider usage matches billing.
The Markdown validation checks observed content and declared word count,
not semantic factual correctness or independent provider provenance. Missing trace evidence
must be investigated rather than rerun to chase a preferred outcome.

The five-task pilot remains diagnostic. Frozen automated results retain
post-collection analysis-plan, fixed-order and evaluator comparability
limitations; retrospective sensitivities remain exploratory. Independent
blinded human validation is still pending.

### Bounded trace capture for noncanonical replication

The budget-runner cost guard and subsequent report-path/word-count gate now
read each JSON trace through a no-follow regular-file descriptor with an
**8 MiB maximum**, a single-link requirement, and file-generation/metadata
consistency checks before and after reading. Oversized or externally hardlinked
traces fail closed instead of being fully loaded into memory or accepted into
the next-treatment spend decision. The maximum is a conservative ingestion
limit for *new noncanonical execution*, not a finding about archived trace
sizes or a modification of the frozen September dataset. Regression cases use
synthetic oversized sparse files, hardlinks, symlinks, and simulated in-read
mutation; no treatment or evaluator is run. This is observed local custody
and bounded memory use, not an atomic snapshot, proof of provider billing,
or independent authentication of missing original artifacts.
