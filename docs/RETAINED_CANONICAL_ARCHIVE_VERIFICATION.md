# Retained canonical ZIP: executable provenance-concordance gate

The original canonical analysis workflow **36070798723** uploaded a seven-file
analysis archive named `canonical-main-study-analysis-36070798723`, artifact
**10837878458**. On **2026-10-29**, the GitHub-reported artifact SHA-256
`226f009ba6b158b77fc98f4e56ec96e1943d1749bc818b0876e90f76077de4b5`
matched a downloaded raw ZIP. The reported expiration is **2026-12-23T23:03:46Z**.
These are **GitHub-provider observations**, not pre-existing independently
retained hashes or authentication of the original treatment evidence.

`.github/workflows/retained-canonical-archive-audit.yml` is a dedicated,
read-only GitHub Actions audit on `research-paper-eval-2027`. It runs on an
explicit workflow-file change or manual dispatch; it does not rerun treatments,
evaluators, analysis, or human annotations. The action:

1. Retrieves metadata for the exact historical artifact ID from GitHub's API.
2. Downloads its **raw ZIP** without extraction or re-encoding.
3. Validates the source run/branch/commit/repository identity, ID, name, expiry,
   reported byte size, provider digest, and actual downloaded ZIP digest.
4. Invokes `scripts.verify_canonical_archive_checkout` to recompute current
   checkout provenance, validate archive structure and fingerprints, and bind
   all seven archive members to the verified checkout. The historical v1
   provenance-receipt exception remains restricted to its exact observed hash;
   the other six artifacts must match current verified checkout bytes.
5. **Only after a passing end-to-end verification**, uploads the original raw
   ZIP, GitHub metadata response and machine-readable audit receipt as a new
   GitHub Actions artifact, for the repository's configured retention period.

The independent-custody flag remains **false**: re-uploading GitHub's own ZIP
is a preservation copy, not a new independent historical anchor. A PASS does
not recover the missing original **40 treatment traces and Markdown reports**, prove
those reports' authentic historical custody, validate human-evaluation readiness,
or justify any new scientific conclusion. The pilot, frozen automated
confirmatory results, exploratory diagnostics, and pending human validation
remain separate.

For offline reproduction, retain the raw ZIP and GitHub artifact metadata JSON,
then run from a checked-out `research-paper-eval-2027` revision:

```bash
python -m scripts.verify_retained_canonical_download \
  /path/to/canonical-source-metadata.json \
  /path/to/retained-canonical.zip \
  --root /path/to/Ai-Researcher-Agent \
  --receipt-out /path/to/new-verification-receipt.json
```

The receipt is **create-only**, and verification requires no provider token
after the two inputs have been fetched. The metadata is API-supplied and
thus does not establish historical origin independently of GitHub. Artifacts
can disappear or expire; in that case, the workflow fails rather than claiming
a substitute archive has passed. The previously preserved local ZIP remains a
separate recovery candidate and can be verified offline with captured metadata.
