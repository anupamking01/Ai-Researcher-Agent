# Offline CI escrow for two exploratory measurement diagnostics

**Scope:** reproducible **post-hoc descriptive** checks, not new confirmatory
analysis, provider-trace authentication, or human validation.

The research branch's `.github/workflows/exploratory-measurement-replay.yml`
runs two already-implemented read-only diagnostics against the *exact* published
main-study treatment/evaluator CSVs: realized retrieval exposure and
checked-claim denominator sensitivity. Each producer first verifies the frozen
source fingerprints, full 40-cell task matrix, and summary-input integrity.
The workflow then runs a distinct verifier for **each** saved JSON: the
verifiers recompute the reported arithmetic from the pinned CSVs, without
importing the corresponding exploratory producer. Both check all 40 cells and
30 paired task rows. The workflow aborts before publication if a source
fingerprint, result, scientific-scope declaration, or verifier receipt differs.

A successful run retains **five** files together: two generated diagnostics,
two independent verification receipts, and `artifact_index.json`. The index
records the exact GitHub checkout commit and run ID plus SHA-256 hashes for the
other four files. Retention is **90 days**; export those exact bytes and the
GitHub run link into an independently controlled archive if durable external
custody is required. CI artifacts alone are not independent historical
authentication, nor do they recover any missing original report or trace.

## Independently verify a downloaded five-file bundle

After downloading and extracting a retained artifact, independently obtain
its **repository, exact workflow checkout commit, Actions run ID, and run
attempt** from the GitHub Actions run page/API (not from the bundle itself).
Check out that exact commit with the pinned frozen CSV inputs and run:

The replay verifier now independently checks that the running source repository's
Git `HEAD` equals the externally supplied checkout SHA, that the code is at
the repository root, and that the tracked or untracked replay scripts and
frozen source files have **no local changes**. Missing Git metadata, altered
verifier code, untracked replacement scripts, or a mismatched checkout fail
closed even when an extracted bundle rehashes consistently. A clean checkout
is only a *local source-continuity condition*: Git HEAD and a clean worktree
do not cryptographically attest GitHub's remote execution or the historical
original report/trace custody. The two frozen CSV fingerprints remain required.


```bash
python -m scripts.verify_exploratory_measurement_bundle \
  --directory /path/to/extracted-five-json-files \
  --expected-repository anupamking01/Ai-Researcher-Agent \
  --expected-checkout-sha <full-40-character-run-checkout-SHA> \
  --expected-run-id <GitHub-Actions-run-ID> \
  --expected-run-attempt <GitHub-Actions-attempt-number> \
  --expected-index-sha256 <independently-retained-artifact_index.json-SHA256>
```

The final `--expected-index-sha256` flag is optional for older downloaded
bundles, but strongly recommended when a trusted index digest was retained
**outside the bundle before download or subsequent replay**. Retrieve the
index digest from an independently controlled archival receipt, not by
hashing the untrusted extracted bundle during verification. A valid external
index SHA-256 anchors its four recorded member hashes and therefore the exact
bytes of all five files. Without this external pin, the verifier continues
to provide **local consistency only**, even when its independently replayed
diagnostic arithmetic passes. The JSON replay receipt says whether an
expected index hash was checked; it does not prove its custody or age.

**Separately archivable CI fingerprint:** After the full bundle verifier passes,
Actions prints the exact verified `artifact_index.json` SHA-256 and the
run/attempt URL in the **job log** and **job summary**, before artifact upload.
The new `artifact_index_sha256` verification-receipt field is computed from
the same descriptor-held bytes used for the five-file replay, not from a
later path read. Neither log nor job summary is included in the downloaded
five-file artifact. A custodian can preserve the digest, checkout SHA and
run/attempt identity in a separate controlled archive, then supply the
recorded digest through `--expected-index-sha256` for a later replay.
**External retention is not automatic or currently established.** Logs and
summaries are GitHub-controlled channels, not independent timestamps,
signatures, original-treatment custody, confirmatory results or human ratings.

The verifier rejects missing or extra members, symlinks/hardlinks, changed
bundle bytes, duplicate JSON keys, false research-status claims, missing or
altered run/attempt identity, and mismatched file digests. It independently
recomputes both saved verification receipts against the pinned CSVs and
requires exact typed equality; simply rewriting a JSON result and updating
the index hashes cannot make a changed measurement pass. The CI workflow
runs this same check **before upload**, and each workflow re-run uses a
distinct run-attempt artifact name. Manifest schema v2 records that attempt.

**Trust boundary:** The index is a self-declared digest ledger, not a
signature or trusted original-execution attestation. An externally supplied
index hash detects bundle reserialization/substitution only when the original
pin was independently retained; a hash computed from the download itself
does not provide this protection. The externally checked
run identity and independently verified **published summary CSVs** are
necessary; neither establishes original treatment report/trace custody.
A downloaded v1 bundle from an earlier run is not silently upgraded: replay
that run's original files or use the new v2 workflow on a current checkout.
This process adds no tests of significance and no human rating.

The workflow is triggered by relevant edits on
`research-paper-eval-2027`, qualifying PR changes, or manual dispatch. It
uses read-only repository permissions, a pinned Python interpreter, and
minimal version-pinned parser dependencies. No treatment execution, model or
evaluator requests, human scoring, confirmatory inference, or outcome-based
selection is performed. The generated diagnostics remain exploratory even if
every CI check succeeds.

To replay on a research checkout without relying on the CI service:

```bash
python -m scripts.analyze_main_study_retrieval_exposure > exposure.json
python -m scripts.verify_main_study_retrieval_exposure_artifact --artifact exposure.json
python -m scripts.analyze_main_study_claim_denominators > denominators.json
python -m scripts.verify_main_study_claim_denominator_artifact --artifact denominators.json
```

The frozen **equal-report** confirmatory support estimand, original confidence
intervals and multiple-comparison corrections are untouched. Diagnostic pilot
observations must not be conflated with the frozen main-study inference or the
new descriptive comparisons. The original treatment reports/traces remain
unauthenticated independently, historical fixed-order temporal confounding
remains unresolved, and blinded human validation still requires original
source custody plus two eligible, independent annotators and real ratings.


### Cross-file pathname custody during independent replay

A retained five-file bundle is now captured through held, no-follow descriptors
for every ancestor directory and every single-link member. Its exact inventory,
bounded bytes, inode/metadata identity, and full ancestor chain are rechecked
after both independent diagnostic verifiers have run. A same-byte replacement
of an individual file, or a same-byte swap of the entire downloaded bundle
directory during replay, fails rather than acquiring a misleading PASS.
Regression fixtures cover these substitutions, symlinked ancestors and parent
traversal. The original frozen inputs and exploratory arithmetic are unchanged.

This is **local verification-window continuity**, not an independent external
signature or a guarantee against an attacker who can substitute and restore
an object invisibly between observations. It does not recover or authenticate
historical report/trace custody, establish prospective confirmatory evidence,
or create human-evaluation observations.
