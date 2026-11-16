# Complete offline pytest via deterministic CI shards

At the 14 November 2026 predecessor, the ordinary `tests` workflow's
20-minute `unit-tests` job was cancelled while the complete firewalled
pytest step ran; passing selected fast lanes did not verify the full suite.

On 16 November 2026, the eight-way predecessor at commit
`5c36e62bdd725a6fc47a4e9256ad3ce301167b93` had seven successful
unit-test shards but an unfinished/cancelled shard 5 in both independently
triggered full suites (push run `43799707883`, pull-request run
`43799712961`). All specialist PR checks completed, but **neither full-suite
replay qualified as successful**. The per-job 20-minute limit and concentrated
test workloads motivated a deterministic split into smaller complete modules;
the cancellations alone do not prove which individual test consumed the time.

The ordinary suite now runs in **sixteen independent matrix jobs**, with at
most **eight active shard jobs per workflow** (`strategy.max-parallel: 8`).
The same research-branch update triggers both push and pull-request suites,
which previously could fan out to 32 simultaneously eligible shard jobs.
Bounding the per-workflow fan-out reduces simultaneous runner demand while
preserving every shard, its pinned checkout, exact-run evidence retention,
and the mandatory sixteen-shard aggregate replay. This is a prospective CI
resource safeguard, **not** evidence that runner pressure caused any past
cancelled job, a guarantee that future cancellation cannot occur, or a
substitute for all sixteen successful jobs and replay.

The ordinary suite now runs in **sixteen independent matrix jobs**. The
dependency-free selector `scripts/select_full_ci_shard.py` recursively
discovers both default Python pytest filename conventions in `tests/`,
sorts modules, and partitions them round-robin by index. Before testing,
each job verifies that all sixteen partitions cover every discovered module
once. Duplicate inputs, invalid indices and empty shards fail closed. Directory
traversal now fails on symlinked test subtrees, dangling directory aliases,
symlinked support files or test modules, and unreadable nested directories;
none can silently disappear from the sixteen-shard source inventory. These
failures reject the checkout instead of following links outside the test tree. The full job preserves pinned Python/dependencies, source
and runtime checks, strict pytest modes, blocked outbound IPv4/IPv6, and
independent replay of a per-shard exact-commit test receipt. Each passing
shard retains its uniquely named module list, log and pre-install gate receipt; the module list is also prepended
to the receipt-hashed transcript.

On 16 November 2026, the subsequent PR test run `43811549386` also
cancelled shard 5 after its runner logged `621 passed in 56.53s`, before
post-test checkout verification, receipt generation, and successful evidence
retention. The cancellation was *not* a passing CI job; the log alone does
not establish a completed full-suite proof or the cause of cancellation.
The workflow now requests **best-effort unverified diagnostic retention on
both failure and cancellation**, capturing the raw log and selected module
list without any verified success receipt. GitHub may interrupt a cancelled
job before this upload can execute; missing cancellation artifacts are
therefore not proof that no tests ran. Such bundles are excluded from the
success-only full-set replay and must never be promoted to scientific or CI
attestation.

**Only sixteen passing jobs at the same commit constitute a full-suite pass.**
Passing one shard, one fast lane or the pre-install diagnostic gate does
not. The full-suite receipt now additionally hashes the retained newline-delimited
selected-module file, checks that its exact bytes equal the deterministic
selection recomputed from the checked-out source tree for that shard, and
requires the same ordered module records after the shard header in the
receipt-hashed pytest transcript. The independent retained-evidence replay
requires that same module file and externally supplied shard index. A changed,
missing or exchanged selection file can no longer accompany an otherwise
valid per-shard test receipt. This strengthens source-to-evidence custody; it
does not independently attest collection of every test function or runner
honesty. This covers the source-tree default Python test-file conventions,
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
