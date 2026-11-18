# Complete offline pytest via deterministic CI shards

## Unambiguous line-delimited shard evidence — 19 November 2026

Full CI writes selected test-module paths to a **newline-delimited file** and
replays that file against a hash-bound test transcript. A filename with a POSIX
legal newline, carriage return or Unicode line separator previously passed
test-module discovery, but could split one pathname into multiple apparent
`mapfile` records and make the receipt's selected-module lines ambiguous.
This is a test-source provenance and completeness risk, not an experimental
outcome issue.

The selector now rejects ASCII control characters and Unicode NEL/line/
paragraph separators in **all** leaves and subdirectories beneath `tests/`,
including non-test-named fixtures; directly supplied module tuples receive
the same check. Ten synthetic rootless regressions cover filenames,
support-file names, nested directory components, and direct shard selection.
Ordinary regular files and deterministic 16-shard allocation retain their
existing behavior. This does not independently attest GitHub runner custody,
fix external CI cancellations, authenticate original expired treatment
archives or produce genuine human ratings. The diagnostic pilot,
post-collection automated analysis and exploratory sensitivities keep their
existing distinct interpretation.


## Test-tree leaf custody and nonblocking inventory — 19 November 2026

Before assigning modules to the sixteen full-suite shards, the deterministic
selector now checks **every** file leaf under `tests/` with `lstat`, including
`conftest.py`, helpers and non-test-named fixtures. It rejects hardlinked
files (link count other than one) and nonregular entries such as named pipes,
in addition to the existing symlink and symlinked-directory rejection. A
hardlinked helper could be changed from a pathname outside the checkout;
opening a FIFO as Python source or fixture could block pytest collection.
Previously such non-test-named leaves were skipped before regular-file
checking. Valid single-link regular helper files are still allowed, while
test-module selection and all sixteen partitions remain unchanged.

Seven synthetic rootless regressions cover aliased test modules and helper
files, named pipes at selected and nonselected paths, and valid helpers.
This is local source-tree preflight, **not** an atomic filesystem snapshot or
proof of independent CI runner custody; concurrent replacement after preflight
still requires the existing source-bound checkout and evidence checks.
It does not execute treatments or evaluators, revise frozen results, or
constitute human validation. The pilot remains diagnostic, designated-primary
automated inference retains post-collection, fixed-order and evaluator-policy
limitations, and retrospective sensitivity work remains exploratory.

## Python assertion-semantics isolation — 18 November 2026

The shared firewalled pytest entrypoint now rejects any nonempty inherited
`PYTHONOPTIMIZE` value **before sudo and firewall setup**, including explicit
`0`, `1`, or `2`. With `PYTHONOPTIMIZE=1` or `2`, CPython can remove
ordinary `assert` statements in imported helper and verification modules.
Pytest's own assertion rewriting does not establish the semantics of every
imported module: an optimized interpreter could otherwise make a source-identical
CI test run exercise different guards. The wrapper requires an unset variable
for the normal pinned-interpreter path; it does not change Python dependencies,
test selection, test outcomes, or the host egress firewall.

Three rootless synthetic cases reject optimizer values before any fake sudo
invocation. A fourth regression demonstrates that a normal Python assertion
fails while the identical script under `PYTHONOPTIMIZE=1` succeeds. This
protects *future offline verification*, not earlier CI runs, and does not prove
that inherited optimization caused any historical cancellation. Full sixteen-
shard exact-run certification and original report/trace custody remain separate
requirements. The pilot remains diagnostic, frozen automated inference remains
post-collection and qualified, retrospective sensitivity remains exploratory,
and human evaluation has not been completed.

## Host Python import-root isolation — 18 November 2026

The shared firewalled pytest entrypoint now rejects nonempty inherited
`PYTHONPATH` or `PYTHONHOME` **before** privileged firewall setup and forces
`PYTHONNOUSERSITE=1` even when the caller supplied a false value. Those
variables can otherwise redirect Python's pre-pytest imports to unreviewed
packages, startup hooks or user-site code before the project's socket guard
is installed. This complements the existing inherited `PYTEST_ADDOPTS` /
`PYTEST_PLUGINS` rejection and disabled third-party pytest entry-point
autoload; pinned dependencies and repository modules remain importable
through the normal CI interpreter and current checkout.

Synthetic rootless tests cover both rejected ambient import roots before
any sudo call and a forced user-site exclusion observed by the pytest stub
after simulated IPv4/IPv6 firewall setup. The safeguard does not prevent
imports from compromised installed packages, global site startup hooks,
explicitly executed code, or sources outside the Python interpreter. It
does not alter or validate historical treatment archives, run a research
treatment, revise frozen automated outcomes or create human annotations.
The pilot remains diagnostic; the frozen automated results remain
post-collection with fixed-order and evaluator-comparability qualifications,
and later sensitivity analysis remains exploratory.

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

## Interrupted-shard visibility — 17 November 2026

On exact-head push run [44018470493](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/44018470493)
and PR run [44018475946](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/44018475946),
shard 5 was cancelled during firewalled pytest, at about 35% and 46% of
its visible progress respectively. Other shards completed. Those partial
dot-only logs did not reveal the active test node, and cannot establish
whether a test, host, or external cancellation caused the interruption.
Neither run established the required complete sixteen-shard replay.

The **same complete, strictly selected, firewalled test suite** now invokes
pytest with `-vv --durations=10` instead of `-q`. Each test's node ID
is printed when execution begins, enabling the existing best-effort
unverified cancellation transcript to identify the last started test.
For *completed* suites, pytest additionally reports the ten slowest
test phases to inform future **outcome-blind** CI workload analysis.
This changes diagnostic verbosity only. A listed in-progress node is not
proof that the test hung or caused GitHub to cancel the job. An interrupted
run has no successful pytest summary, verified shard receipt, or aggregate
replay, regardless of the last visible node. The existing 16 MiB test-log
capture bound and strict source-bound receipt checks remain in force; an
oversized log fails rather than silently truncating evidence. New synthetic
regressions verify node-ID visibility on failure and the firewalled
invocation's preserved ordering and strict flags. No study outcomes or
human ratings are changed.

The five-task pilot remains diagnostic; the designated-primary automated
results retain post-collection plan timing, fixed treatment ordering and
historical evaluator-recovery comparability limitations. Retrospective
sensitivities remain exploratory. Original report/trace authentication,
human distribution, independent annotators, genuine ratings, agreement,
and reconciliation remain blocked or pending.

## One complete suite per open research PR — 18 November 2026

The prior `tests.yml` automatically launched a sixteen-shard push suite **and**
a sixteen-shard pull-request suite for each research-branch commit associated
with an open PR, in addition to specialist workflows. Each full suite allowed
up to eight concurrent shards, so the two events could make sixteen shard
jobs eligible simultaneously. At commit
`ea5f240d875623950888e8712c4ac45cd84a32c6`, [push run 44276856620](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/44276856620)
had a cancelled shard 8, while [PR run 44276865248](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/44276865248)
had cancelled shards 4 and 13. Their aggregate replay jobs were skipped.
Different cancelled shards do not establish a single test failure or prove
runner saturation; neither incomplete run certified the full suite.

The ordinary suite now runs automatically on **all pull requests** and on
**pushes to `main`**, but not on ordinary research-branch pushes. The open
research PR's full 16-shard suite is still mandatory, including exact-tested
checkout, strict firewalled pytest, complete per-shard receipts, and the
success-only downloaded sixteen-shard replay. A standalone research branch
**without a pull request** must use `workflow_dispatch` against that branch
(or open a PR) to obtain full-suite certification. Specialist fast lanes
retain their own push/PR triggers. This routing reduces duplicate full-suite
work for an open research PR; it does **not** show that CI cancellation is
fixed or relax the sixteen-shard success criterion. The GitHub PR integration
checkout SHA may differ from the source branch head; all receipt verification
continues to bind to the actual tested checkout SHA.

Synthetic offline trigger-policy regressions in
`tests/test_full_ci_event_isolation.py` reject research push duplication,
removal of pull-request/manual triggers, and pull-request path or branch
filters that could silently skip a complete research validation.

Scientific boundaries are unchanged: the pilot is diagnostic; frozen
main-study automated inference has post-collection plan, fixed-order and
evaluator-comparability limitations; retrospective sensitivities are
exploratory. Historical original treatment artifact authentication and
blinded human evaluation remain incomplete. No treatment, evaluator, or
human ratings were rerun or generated to change outcomes.

## Live-smoke regression inclusion after event isolation — 18 November 2026

[PR test run 44287360341](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/44287360341)
for source commit `8e3a89d32d9494a072d8eb59164a714e1eab3b21` exposed a
**deterministic, non-scientific CI contract failure** in shard 15:
`test_live_smoke_safety_checks_run_in_ordinary_offline_ci` still required a
`research-*` push trigger. That expectation conflicts with the reviewed
one-suite-per-PR policy above. Shard 15 reported **338 passed, one failed**;
shard 5 was separately **cancelled**, so the full-set replay was skipped.
Neither partial result is a complete CI certification.

The live-smoke test now requires the **exact unfiltered pull-request event**,
`main`-only push, and manual dispatch as parsed by PyYAML BaseLoader, while
still requiring a pipefail-protected offline pytest invocation and forbidding
live smoke execution inside ordinary CI. This restores the safety check to
the intentional event policy rather than weakening it or reinstating the
duplicate suite. The separate synthetic trigger mutation tests continue to
reject filtered or missing PR events. Only a fresh, complete sixteen-shard
passing workflow plus evidence replay can establish full-suite success.
No research treatment, evaluator, frozen analysis or human rating is changed.
