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
