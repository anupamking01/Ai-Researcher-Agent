# Complete offline pytest via deterministic CI shards

At the 14 November 2026 predecessor, the ordinary `tests` workflow's
20-minute `unit-tests` job was cancelled while the complete firewalled
pytest step ran; passing selected fast lanes did not verify the full suite.

The ordinary suite now runs in **eight independent matrix jobs**. The
dependency-free selector `scripts/select_full_ci_shard.py` recursively
discovers both default Python pytest filename conventions in `tests/`,
sorts modules, and partitions them round-robin by index. Before testing,
each job verifies that all eight partitions cover every discovered module
once. Duplicate inputs, invalid indices, empty shards and symlink modules
fail closed. The full job preserves pinned Python/dependencies, source
and runtime checks, strict pytest modes, blocked outbound IPv4/IPv6, and
independent replay of a per-shard exact-commit test receipt. Each passing
shard retains its module list and log; the module list is also prepended
to the receipt-hashed transcript.

**Only eight passing jobs at the same commit constitute a full-suite pass.**
Passing one shard, one fast lane or the pre-install diagnostic gate does
not. This covers the source-tree default Python test-file conventions,
not an independent attestation of every collected pytest test function.
New custom discovery patterns require a separately reviewed selector
update. Sharding changes execution scheduling only: no estimates,
outcomes, frozen inputs, analysis policies or rating data are changed.

The five-task pilot remains diagnostic; the designated-primary automated
results retain post-collection plan timing, fixed treatment ordering and
historical evaluator-recovery comparability limitations. Retrospective
sensitivities remain exploratory. Original report/trace authentication,
human distribution, independent annotators, genuine ratings, agreement,
and reconciliation remain blocked or pending.
