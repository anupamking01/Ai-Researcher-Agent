## Full-suite pytest collection-to-completion integrity (17 November 2026)

The ordinary 16-shard CI now requires three independently inspectable counts
from each *complete* verbose pytest transcript to agree before issuing a
source-bound success receipt: the single `collecting ... collected N items`
record, the number and categories of per-test `PASSED` / `SKIPPED` / `XFAIL`
terminal status records, and the single final pytest summary. Missing,
duplicated, reordered-before-collection or contradictory completion records
fail closed. The check accepts parameterized test identifiers containing spaces
and treats warnings as warnings, not completed tests. Legacy short specialist
receipts (without a selected-module inventory) still use the existing strict
terminal-summary contract. Both producer and independent replay perform the
new check, because replay recomputes the exact producer receipt.

This adds transcript-level completeness evidence to the already retained
source-bound module inventory and helps distinguish an interrupted job from a
finished one. It does **not** prove collection of all Python test functions,
attest GitHub runner honesty, prevent external cancellation, or authenticate
historical research artifacts. At predecessor SHA
`3590f96ef30a937a0791f917705eedf9767fb1f0`, both full CI suites
were cancelled (push run `44032344250` and PR run `44032352298`),
although 14 of 16 push shards and 15 of 16 PR shards completed. Neither
cancelled workflow qualifies as an independent complete-shard replay, and the
cause of cancellation remains unconfirmed. This change does not modify
treatments, evaluators, frozen numerical outcomes, analysis plans or ratings.

# Source-bound offline CI test evidence

The normal VERA `tests.yml` job retains a raw log and a small JSON receipt
for **both** push and pull-request test runs. The job still executes the
existing offline firewalled pytest wrapper; Bash `pipefail` prevents `tee`
from hiding a failing test exit code. On a successful run, the verifier
requires a single firewalled-wrapper activation marker and an unambiguous
pytest success summary, matches the checked-out Git commit to
`GITHUB_SHA`, fingerprints both dependency files, and records the log's
SHA-256 and exact run/attempt identity. Artifacts are retained for 90 days.

This is **CI reproducibility metadata, not scientific data**. A passing
receipt is neither independent attestation of GitHub's runner/firewall nor
evidence that original treatment archives were recovered. Cancelled, failed,
or incomplete runs cannot publish the verified receipt; check the exact
workflow conclusion rather than assuming a missing receipt means failure.

A pull request may test a synthetic merge SHA, whereas its head branch
points to a different commit. Always cite the receipt's `checkout_sha`
and workflow event, not merely the branch name. No experiment, evaluator,
provider call, human rating, or confirmatory analysis is invoked by this
addition. The five-task pilot stays diagnostic; original designated-primary
automated analysis retains the post-collection plan qualification; exploratory
bounds and future human validation remain separate.


## Verbose pytest completion receipts (17 November 2026)

The firewalled offline pytest runner now uses `-vv --durations=10` to
expose the active test node and report slow phases. Its successful stdout
ends with a **decorated** pytest footer (for example,
`================ 501 passed in 8.46s ================`), whereas the
original source-bound receipt parser only recognized an undecorated
`501 passed in 8.46s` line. This caused both full CI suites and several
specialist evidence jobs to fail *after pytest itself passed*, with
`offline pytest success summary missing or ambiguous`. This was a
producer/consumer formatting mismatch, not evidence of failed research
treatments or unsuccessful unit test assertions.

The receipt producer and independent replayer now accept **either** the
original plain pytest footer or a pytest-decorated footer with runs of at
least three `=` characters on **both** sides. They still require exactly
one complete physical terminal success line *after* the unique firewall
marker and reject malformed, duplicated, appended, failed, deselected or
unexpectedly passing records. They continue to bind original log bytes,
checkout SHA, dependencies, selected module inventory and run identity.
Synthetic tests exercise real-looking verbose duration output, CRLF and
independent replay, as well as ambiguous/one-sided/rejected summaries.

This restores the receipt contract while retaining per-test CI diagnostics;
it does not weaken suite scope, infer a successful cancelled CI run,
authenticate historical report/trace custody or generate any new
pilot, designated-primary, exploratory or human-validation measurement.

## Preserve failing CI transcripts without implying successful verification (15 November 2026)

Ordinary successful eight-shard CI retains one *verified* per-shard
`vera-offline-tests-shard-...` evidence bundle only **after** the exact-source,
installed-dependency, runtime, successful-pytest receipt, and independent
single-shard replay gates pass. This strict success contract is unchanged.

Previously, a failure in offline pytest, a source/dependency postcheck or
receipt replay skipped the normal success-only upload, so the per-shard
diagnostic log and selected-test inventory could disappear with the runner.
Each shard now has a separate `failure() && !cancelled()` upload step that
retains any extant raw `vera-offline-tests.log` and
`vera-offline-test-modules.txt` under a **distinct**
`vera-unverified-failure-shard-<shard>-<run>-<attempt>` artifact name
for 90 days. The upload intentionally **excludes** a success receipt;
`if-no-files-found: warn` preserves the original failure when setup exits
before files exist. An incomplete log is not repaired or silently certified.
Cancelled jobs may be unable to execute the failure-upload step at all.

The downstream eight-shard gate still depends on **all eight successful
unit-test jobs** and downloads only the `vera-offline-tests-shard-...`
pattern, never these unverified diagnostic artifacts. These negative-case
files are for investigation, not evidence of successful CI, runner attestation,
historical treatment/recovery source custody, or recovered human-evaluation
readiness. Offline workflow-contract and synthetic shell regressions pin the
separate naming, conditions, strict success-only gate and `pipefail` behavior.
No treatments, evaluators, frozen estimates or human scores are rerun or changed.

## Fail closed on pruned or unexpectedly passing test suites (13 November 2026)

A zero-exit pytest summary can still include **deselected** tests (for example,
from an accidental `-k`/marker filter) or **xpassed** tests (a regression
marked as expected to fail unexpectedly passed). The full and targeted
source-bound CI receipt producer now refuses to issue a green receipt when
either count is positive; independent receipt replay enforces the same
policy, even for a coherently rehashed old-style receipt. Synthetic tests
cover both green-looking cases. Legitimate `skipped` and `xfailed` cases
remain explicitly recorded in `test_counts` for review; they are not passed
cases. The GitHub workflow's actual conclusion remains a separate requirement.

This blocks **observably pruned/unexpected** pytest runs, not a suite whose
tests were silently omitted before collection, forged logs, or hidden skips.
It does not prove total source-test completeness or attest the runner,
historical treatment custody, automated results, or blinded human ratings.
No treatment, evaluator, experimental outcome, or human rating was changed.

## Replaying retained CI evidence after download

The companion **offline consumer** `scripts/verify_retained_ci_test_evidence.py`
lets a second checkout audit the log/receipt pair retained by GitHub Actions.
It recomputes the producer's success counts, log SHA-256, dependency-file
fingerprints, identity and fixed status fields. It rejects modified logs,
altered dependencies, missing or extra receipt fields, wrong GitHub run or
attempt, duplicate JSON keys, noncanonical JSON and Python bool/integer
substitution. Only the producer's informational Python patch version may differ
from the replay host; it is constrained to a numeric version string.

**Obtain the tested commit SHA, run ID, attempt and event independently from
the GitHub Actions run page/API, not from the downloaded receipt.** Download and
extract that run's `vera-offline-tests-<run-id>-<attempt>` artifact, then check
out the **exact tested SHA** (for PR runs this may be GitHub's synthetic merge
commit, not the pull-request branch HEAD). On that checkout, use:

```bash
python -m scripts.verify_retained_ci_test_evidence \
  --log /trusted-download/vera-offline-tests.log \
  --receipt /trusted-download/vera-offline-test-receipt.json \
  --checkout-sha <independently-verified-40-character-commit-SHA> \
  --run-id <independently-verified-GitHub-run-ID> \
  --run-attempt <independently-verified-attempt> \
  --event push
```

Replace `push` with `pull_request` or `workflow_dispatch` for that run.
This helper must exist in the checked-out revision and the two dependency files
must match those used by that revision. A local PASS means that the downloaded
files are **self-consistent under those independently supplied identifiers**,
not that GitHub ran the tests, that the runner's network was isolated, that the
upload was independently attested or that any scientific treatment artifact
has been authenticated. Inspect the original GitHub workflow/job conclusion
and the uploaded artifact's source separately. Offline synthetic regressions
cover clean replay and tampering; they create no experimental results or
human-evaluation ratings.

## CI-side replay publication gate

The job also runs the **independent-identity replay CLI** against the just
generated log and receipt *before* `upload-artifact`. Expected checkout SHA,
run ID, attempt and event are passed directly from the GitHub Actions
environment, not extracted from the receipt. A failed, missing or inconsistent
replay exits the job before the source-bound evidence pair is published as
verified. A workflow regression test pins the producer → replay → upload
ordering and all independently supplied CLI arguments.

This is an integration/cross-check on **the same CI runner**, not an independent
second machine, GitHub API attestation or evidence of successful treatment
execution. Downloaded artifacts should still be replayed later using
identifiers obtained separately from the GitHub run page/API.

## Exact source-byte checkout gates around pytest (12 November 2026)

Two fail-closed steps in 'tests.yml' verify the **actual tracked working-tree
bytes** against the exact 'GITHUB_SHA' immediately before and after offline
pytest. The source-checkout verifier compares every tracked blob to its Git HEAD
content hash, checks regular-file/symlink type and executable mode, rejects
unexpected nonignored untracked files and staged changes, and requires the
repository root to be the expected checkout. Unlike a HEAD-only check or a
Git-index-only diff, it also detects changes concealed by Git's
'assume-unchanged' flag. The logged pytest/receipt/replay/upload sequence is
unchanged; a failed source gate prevents publishing a successful CI evidence
artifact. Offline synthetic Git fixtures test clean revisions, staged/unstaged
and hidden edits, untracked files, mode changes and symlink substitution.
The verifier also rejects tracked regular files and tracked symlinks with
multiple hardlinks: otherwise a path **outside the checkout** could modify
the tested inode while every in-repository pathname, original Git blob hash,
and Git status remain unchanged at the preflight gate. It checks link count
both at initial pathname inspection and on the opened file descriptor,
then includes it in the before/after generation comparisons. Two synthetic
out-of-checkout alias regressions cover byte-identical files and symlink
inodes; no model or experimental data is read. Ordinary '.pytest_cache/'
test output is ignored explicitly.

This is a **bounded local-runner consistency check** rather than independent
attestation: ignored cache/build outputs are outside the Git-blob comparison;
a transient change restored before the post-test check may escape detection,
and GitHub/runner integrity must still be independently established. It does
not authenticate historical model reports/traces or establish real human
evaluation. The diagnostic pilot remains distinct from the qualified
post-collection designated-primary automated findings and exploratory
sensitivity analyses; no confirmatory precollection or human-validation
result is asserted by this change.


## Installed CI dependency verification (12 November 2026)

The test workflow now checks **installed** Python distribution metadata against
every exact version pin in `requirements.txt` and `requirements-ci.lock`
both after dependency installation and after offline pytest, before publishing
its source-bound test receipt. This closes a reproducibility gap left by
hashing requirement *files* alone: an unchanged lock file and successful
`pip check` do not themselves show that the runner has installed the
versions the experimenter intended. The gate requires exactly one installed
distribution per canonical PEP 503-style name and an exact pinned version;
missing, duplicated, unpinned requirement syntax, or drifted pinned packages
fail the workflow. Pure synthetic regression cases test each rejection without
installing anything or making network calls.

These are local installed-distribution **metadata** checks, not an immutable
environment digest, a complete software-bill-of-materials, source-distribution
hash validation, attestation of the GitHub runner, or proof that importable
module bytes match metadata. Packages not listed in the two CI pin files are
outside this check. The earlier exact Git checkout, firewalled pytest, and
retained evidence gates remain required and unchanged. No research treatments,
automated evaluators, or human ratings are run by this check.


## Physical and terminal pytest-log framing gate (12 November 2026)

The receipt producer and its independent offline replay consumer require one
**whole physical** firewall-activation record followed by exactly one pytest
success summary, with the summary as the **last nonempty physical record**.
Only LF and CRLF records are accepted; bare CR, NUL, Unicode line/paragraph
separators, and unterminated final records fail closed. This prevents an
embedded marker, a success line printed before firewall activation, or output
appended after an otherwise valid-looking success line from being treated as
a complete successful test transcript. Synthetic regressions cover normal
LF/CRLF logs and the rejected framing/order cases. The actual CI wrapper and
piped pytest invocation remain unchanged.

This tightens the *internal consistency* of a retained text transcript only:
it cannot prove that the GitHub runner genuinely executed pytest, that the
firewall was independently attested, or that omitted output before the final
summary was not suppressed. The GitHub workflow/job conclusion, independent
run identity, and original research-artifact custody remain separate checks.
It does not rerun experimental treatments, evaluators, or human annotation.


## Exact CI Python runtime verification (12 November 2026)

The workflow's `setup-python` configuration selects CPython 3.11.17, but a
workflow declaration alone does not prove that subsequent `python` commands
execute that interpreter. New fail-closed gates, **before dependency installation
and after pytest**, independently inspect the running executable's exact final
Python release, CPython implementation, Linux/x86_64 host, and 64-bit pointer
ABI. The gates are enforced before a successful source-bound test receipt can
be published. Offline synthetic tests reject older patch releases, prereleases,
other Python implementations, host-architecture changes, and 32-bit runtimes.

The retained receipt's independently replayable `python_version` must now
match **3.11.17**; previously any syntactically valid version was accepted.
This makes revision-specific CI receipts reject mismatched reported runtimes,
while leaving the local replay host free to run a different Python version.
The receipt format and all historical published receipts remain unchanged:
replaying older receipts with another runtime version will now fail this
stricter check instead of silently treating them as pinned 3.11.17 tests.

These checks do **not** authenticate the interpreter's executable bytes,
OS image, system libraries, GitHub runner, firewall, or original research
artifacts. They are CI environment reproducibility checks, not experimental
replication, outcome verification, or human validation.

## Fail-closed pytest collection and configuration (14 November 2026)

The shared firewalled pytest launcher now enforces `--strict-markers` and
`--strict-config` for every offline CI suite using it. Without these flags,
pytest can emit warnings yet exit successfully when a misspelled or unregistered
research test marker is present, or when a configuration option is unknown.
That can invalidate intended collection/selection while still permitting a
superficially green test receipt. Synthetic subprocess regressions demonstrate
both default-green cases and strict-mode rejection; the wrapper test also pins
the exact command. Existing firewall/cleanup ordering remains unchanged.

This safeguards **test discovery/configuration validity**, not completeness of
the underlying scientific evidence or independently attested CI execution.
Previously cancelled broad and diagnostic workflows remain cancelled, not
retroactively passed. The five-task pilot is diagnostic; frozen automated
contrasts remain post-collection and order/evaluator-qualified; retrospective
sensitivities are exploratory and real blinded human validation is pending.
No treatment, evaluator, historical source file, frozen outcome or rating
was regenerated or modified.


## Inherited pytest selection environment (14 November 2026)

The shared offline pytest launcher now **fails before modifying host firewall
rules** if either `PYTEST_ADDOPTS` or `PYTEST_PLUGINS` has a nonempty inherited
value. A caller can otherwise pass an apparently complete explicit test command
while `PYTEST_ADDOPTS=--ignore=...` silently removes source tests from
collection (with no `deselected` counter); a plugin named by `PYTEST_PLUGINS`
can alter collection similarly. Strict configuration/marker checks and the
existing no-deselection receipt gate do not close these two gaps. The launcher
continues to accept explicit, reviewable test file arguments, and the dedicated
lanes may still set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` to suppress unrelated
entry-point plugins. Synthetic regressions prove rejection precedes `sudo`
and firewall creation; existing fake-firewall regressions retain success and
cleanup coverage for the accepted empty/unset environment.

This is a fail-closed **test-selection validity** safeguard, not proof that a
workflow selected every repository test or independently attested GitHub Actions.
Cancelled broad-suite and diagnostic CI do not become passing because of this
change. It does not execute or alter research treatments, evaluators, frozen
automated scores, or human annotations: the pilot remains diagnostic; the
main-study designated-primary analyses remain post-collection, order- and
evaluator-qualified; sensitivity analyses are exploratory, and blinded human
validation remains pending original-source authentication and actual ratings.

## Byte-verified checkout required for offline receipt replay (15 November 2026)

The downloaded-receipt **CLI** now invokes the same complete tracked-source
checkout verifier used in CI before accepting a replay. Merely checking
`git rev-parse HEAD` was insufficient: an edited tracked source with a
still-matching commit ID, including an `assume-unchanged` edit, or an
unexpected nonignored untracked test/plugin file could survive that comparison
without affecting the retained log or receipt. This is especially important
when a second investigator replays the retained evidence in a separate checkout.
Synthetic Git fixtures cover clean replay, modified tracked content, hidden
tracked edits, and nonignored untracked files.

The verifier rejects local source changes before reading the retained
receipt, but it does **not** attest GitHub's execution, a genuine egress
firewall, ignored files, or exact source immutability during historical CI.
As before, obtain the expected SHA and run/attempt/event from an independent
GitHub workflow record. For pull requests use the tested synthetic merge SHA
if that was the checkout, not simply the branch tip. This safeguards
reproducibility metadata only; original treatment/archive custody, qualified
post-collection automated inference, exploratory bounds and independent
blinded human validation remain separate.


## Bounded stable evidence-file capture (15 November 2026)

The producer and downloaded-receipt replay CLI now share a bounded descriptor
reader for retained pytest logs (16 MiB), receipts (16 KiB), and optional
eight-shard module inventories (64 KiB). Earlier code checked the byte limit
inside the receipt builder (and stat-checked only some inputs) **after**
`Path.read_bytes()`; a large or concurrently growing untrusted download could
therefore allocate unbounded memory before it was rejected. The new reader
requires a real regular file, refuses a direct symlink or FIFO, reads no more
than limit + 1 bytes from one open descriptor, and rejects detected byte-count
or file-generation changes during capture. Both producer and replay enforce
the same limits before parsing or hashing. Synthetic tests cover boundary
sizes, oversize inventory rejection before eager read, symlink/FIFO inputs,
and in-place modification during capture.

This is local input-resource and point-in-time consistency protection, not
a cryptographic authentication of downloaded artifact origin, directory
ancestry, or the GitHub runner. It cannot recover the missing original
treatment traces/reports. The pilot remains diagnostic, the frozen automated
designated-primary contrasts remain qualified by post-collection plan timing
and evaluator comparability, retrospective sensitivities remain exploratory,
and genuine blinded human validation remains pending.


## Pytest singular warning receipt compatibility (15 November 2026)

Pytest emits the terminal category as "1 warning", but as "2 warnings"
for multiple warnings. The CI receipt parser previously accepted only the
plural spelling and could reject an otherwise successful exact-source shard
with a single warning, despite the actual test process exiting successfully.
Both producer and independent replay now parse either spelling and normalize
both to the single receipt field "warnings"; a transcript containing both
spellings is rejected as duplicate category data. Synthetic tests cover the
actual one-warning summary and ambiguous mixed tokens. This repairs evidence
accounting only, not a pytest failure, selection of research outcomes, or
the original experimental data.


## Full eight-shard replay as a downstream CI gate (15 November 2026)

The complete-set checker `scripts/verify_full_ci_shard_set.py` was initially an
optional offline command for a researcher after downloading eight shard
artifacts. The ordinary `tests.yml` workflow now runs it in a **separate
downstream job**, only when the eight upstream matrix test jobs all succeed.
It downloads the eight source-bound log/receipt/inventory bundles **from the
same current GitHub workflow run and attempt**, stages one bundle under
`shard-0` through `shard-7`, and independently replays all receipt identities,
source selections, byte hashes and union coverage against the checked-out
Git revision. The job retains the resulting machine-readable aggregate
receipt with the independently supplied run/attempt/event/checkout identifiers
and per-shard hashes. All downloaded files remain outside the checkout,
and exact source-byte verification runs before and after the replay.

A green test matrix **alone** is not the new whole-run evidence-replay result:
check that `replay-complete-shard-set` itself concludes success and that its
aggregate artifact exists. If only a failed shard is rerun at a later
`GITHUB_RUN_ATTEMPT`, surviving artifacts from a previous attempt are
intentionally **not** accepted as a single-attempt complete set. Rerun all
jobs to recreate all eight shard receipts for that attempt. An absent,
cancelled or mismatched shard fails closed; never reinterpret partial pytest
success as a full-run passing receipt.

This adds a CI integration and retained audit artifact, **not independent
attestation of GitHub's runner or actual collection of every test function**.
It does not recover the historical original treatment/report/trace archives,
validate experimental outcomes, or authorize blinded human distribution.
The pilot remains diagnostic, the frozen designated-primary automated
analysis retains post-collection/fixed-order/evaluator-comparability
qualifications, retrospective bounds remain exploratory, and real human
validation remains pending.


## Pathname and single-link custody of downloaded CI evidence (15 November 2026)

The shared bounded reader for the source-bound pytest log, JSON receipt, and
selected-test inventory now checks **both the opened file descriptor and the
downloaded pathname** before/after capture. A previous descriptor-only guard
could accept unchanged bytes after an atomic same-content replacement of the
pathname; the returned bytes would describe an inode no longer accessible
through the named downloaded evidence file. The reader also rejects files
with multiple hardlinks, which permit an external alias to mutate the same
inode without accessing the retained pathname. Synthetic regressions cover
hardlinked evidence, byte-identical replacement, and unlink during capture.
Existing byte ceilings, symlink/nonregular-file refusal, and post-read
generation checks remain in force; downstream eight-shard replay inherits
the check without altering receipt format or test selection.

This is a **local snapshot/path-consistency safeguard**, not a filesystem
transaction, immunity to transient changes reverted between checks,
independent authentication of GitHub's artifact upload, or evidence of
historical study report/trace custody. It changes no pilot, qualified frozen
automated primary, exploratory sensitivity, or pending human-validation
result; no treatments, evaluators, or ratings are run by the reader.

## Bounded dependency-free early CI evidence capture (15 November 2026)

The pre-install `verify_ci_early_gate_evidence.py` producer/replay CLI used
`stat()` followed by unrestricted `read_bytes()` for its early unittest
transcript and retained JSON receipt. A previously checked size did not bind
the opened pathname or bound a concurrently growing read; file aliases could
also be accepted. The CLI now reuses the project's **standard-library-only**
bounded, single-link, no-follow pathname-checked reader for the log, receipt,
and source files. The imported reader and its shard-selector dependency are
included in the early CI receipt's tracked-source SHA-256 inventory.

Synthetic CLI regression cases cover unchanged create/replay and symlink and
hardlink refusal in both modes. This is a local evidence-custody and resource
safety safeguard, **not** GitHub-runner attestation or recovery of the missing
historical 40 report/trace artifacts. Cancelled full CI runs remain incomplete;
no pilot, qualified automated primary, exploratory or human-validation result
is changed or newly asserted.


## Descriptor-bound CI evidence ancestry (15 November 2026)

The standard-library-only bounded evidence reader used by the full-suite CI
receipt producer/replay and by the pre-install early diagnostic receipt now
holds **no-follow directory descriptors for the entire pathname ancestry**.
Previously it checked the leaf's inode, link count, size and byte identity
before and after reading, but an otherwise regular file behind a **symlinked
parent** could still be accepted; swapping a parent directory while retaining
the originally opened leaf also could escape a leaf-only recheck. The reader
now rejects symlinked ancestors, parent-traversal components, and parent
replacements detected during capture, alongside the existing final-leaf,
hardlink, bounded-read and source-hash safeguards. It fails closed when the
platform lacks the required directory/no-follow primitives.

Synthetic regressions cover regular nested evidence, redirected parent
directories, an in-read same-byte parent replacement, parent traversal, and
the shared early/full CI reader. No receipt schema, historic test result,
scientific artifact or workflow permission changed. This is **local path
continuity only**: it does not independently authenticate GitHub's runner,
defeat a transient alteration entirely between observations, retrieve missing
historical reports/traces, establish preregistration or validate human
ratings. CI success on the exact commit is still required before relying
on this updated reader.


## Report observed evidence-directory changes even when replay fails (15 November 2026)

The complete eight-shard replay holds no-follow descriptors for the downloaded
evidence root and every shard directory. Previously it compared those held
directory descriptors to their visible paths **only after a normal return**
from the replay body. When a path was replaced during capture, the next
bounded leaf read could fail with a generic file-open error before the
directory check ran. Thus, although no false PASS was produced, a concrete
mid-replay namespace change was obscured, and both exact-head CI suites
rejected the expected custody-specific failure classification.

The directory-chain check now also runs while unwinding an unsuccessful
replay. If a parent pathname was visibly replaced, that custody violation
takes precedence over the downstream read/parse exception; otherwise the
original consumer error is preserved. Synthetic regressions cover both cases
and an ancestor removed during an unsuccessful replay. The existing complete
shard and retained receipt checks remain mandatory.

This is a **local, observed path-consistency and failure-diagnosis** safeguard,
not proof of continuous custody under unobservable races or independent
GitHub runner attestation. It does not authenticate missing historical
treatment reports/traces, establish human annotation readiness, alter frozen
automated outcomes, or run experimental treatments. Pilot, qualified
post-collection designated-primary, exploratory, and pending human-validation
claims remain separate.
