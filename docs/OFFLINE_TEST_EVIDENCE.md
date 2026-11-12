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
