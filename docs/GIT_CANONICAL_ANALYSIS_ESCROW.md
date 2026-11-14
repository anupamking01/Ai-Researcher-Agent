# Durable Git escrow of provider-observed canonical analysis

The original seven-file canonical-analysis GitHub Actions ZIP is an expiring
source artifact, even though its scientific results are checked into Git.
This workflow makes a **byte-for-byte Git-tracked copy** of the actual ZIP,
the GitHub artifact metadata, and an independently recomputed *analysis
concordance* receipt. The process is strictly archival: no treatment,
evaluator, analysis-generation or human-rating job is rerun.

## Identity and procedure

- Source: run `36070798723`, artifact `10837878458`, name
  `canonical-main-study-analysis-36070798723`.
- Original ZIP (10,270 bytes) SHA-256, **observed from GitHub**, not from
  independent historical custody:
  `226f009ba6b158b77fc98f4e56ec96e1943d1749bc818b0876e90f76077de4b5`.
- Original artifact expiration: **2026-12-23T23:03:46Z**.
- Immutable analysis checkout: `f333623380526fa05dcb14110e7ec1fb72d2d0e2`.
- Git destination: `research-evidence/canonical-analysis-36070798723.zip`,
  alongside `.metadata.json` and `.verification.json`.
- One-time publisher: `.github/workflows/durable-canonical-git-escrow.yml`.

The publisher requires exact agreement of the current nine frozen-design /
scientific files with the immutable checkout; authenticates the provider run
ID, source commit, artifact ID, byte size, reported SHA-256, source expiry,
ZIP structure and seven-member contents; then independently replays the saved
verification receipt. It **refuses to overwrite existing Git evidence files**
or to push over a concurrent branch update. No credential is written to
artifacts or committed into the repository.

After the publisher succeeds, the Git-tracked files are no longer subject to
GitHub Actions artifact expiration. The repository must itself be backed up:
Git history is more durable than a time-limited Actions artifact, **not an
independent historical source, permanent escrow guarantee, or proof of
original treatment-trace authenticity**. Do not rewrite a missing source as
independently authenticated just because its provider-observed SHA-256 matches.

To replay the resulting three-file bundle completely offline from a
provenance-compatible frozen checkout:

```bash
python -m scripts.verify_preserved_canonical_bundle \
  research-evidence/canonical-analysis-36070798723.metadata.json \
  research-evidence/canonical-analysis-36070798723.zip \
  research-evidence/canonical-analysis-36070798723.verification.json \
  --root /path/to/frozen-analysis-checkout
```

This verification does not require the original Actions artifact to remain
available. The **40 original experimental traces and Markdown reports**
still have no independently authenticated copy, so this escrow alone cannot
open blinded human-evaluation or manuscript-confirmation gates. Diagnostic
pilot, frozen automated confirmatory, exploratory and uncollected human data
retain their separate statuses.
