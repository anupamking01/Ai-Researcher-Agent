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
its experiment configuration and trace record. Failure stops further
treatment execution; it never retries or replaces the attempted treatment.

Offline tests use synthetic traces and a stub agent, not real provider calls.
This does not modify canonical evidence or the original historical runner,
authenticate original missing archives, guarantee an atomic filesystem
snapshot against concurrent tampering, protect files outside the trace
inventory, or prove recorded provider usage matches billing. Missing trace evidence
must be investigated rather than rerun to chase a preferred outcome.

The five-task pilot remains diagnostic. Frozen automated results retain
post-collection analysis-plan, fixed-order and evaluator comparability
limitations; retrospective sensitivities remain exploratory. Independent
blinded human validation is still pending.
