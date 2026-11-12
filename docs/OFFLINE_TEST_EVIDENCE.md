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
Ordinary '.pytest_cache/' test output is ignored explicitly.

This is a **bounded local-runner consistency check** rather than independent
attestation: ignored cache/build outputs are outside the Git-blob comparison;
a transient change restored before the post-test check may escape detection,
and GitHub/runner integrity must still be independently established. It does
not authenticate historical model reports/traces or establish real human
evaluation. The diagnostic pilot remains distinct from the qualified
post-collection designated-primary automated findings and exploratory
sensitivity analyses; no confirmatory precollection or human-validation
result is asserted by this change.
