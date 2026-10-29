# Offline verification of preserved canonical-analysis bundles

**Purpose.** The original canonical-analysis GitHub Actions artifact
`10837878458` expires on **2026-12-23T23:03:46Z**. The concordance
workflow (successful run `40795590062`) retained a copy in preservation
artifact `12863262840`, scheduled to expire on **2027-01-27**. GitHub
expiration of the *source* must not make a previously retained, byte-verified
archive impossible to audit offline.

`scripts.verify_preserved_canonical_bundle` replays verification using the
three files retained together:

- `canonical-source-metadata.json` — GitHub metadata captured when the
  original source existed, including its *historical* `expired=false` value.
- `retained-canonical.zip` — unextracted original canonical-analysis ZIP.
- `retained-canonical-verification.json` — initial GitHub source/concordance
  verification receipt, created before preserving the bundle.

The replay checks the original artifact identity and pinned raw-ZIP SHA-256,
validates ZIP structure, re-executes published analytical provenance against
the exact frozen checkout, checks the seven archived members, and requires
the stored initial receipt to match the newly recomputed original receipt
**exactly**, including all nested fields and JSON scalar types. It does
not rely on the original source still being online. All checks remain
read-only, bounded, and fail-closed; the new audit receipt is create-only.

## Reproduce, including after the source expiration date

Retrieve the preservation ZIP from
[Actions run 40795590062](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/40795590062)
before **2027-01-27**, and safely unpack its three expected files into an
isolated directory. Keep the raw inner `retained-canonical.zip` unchanged.
Use a separate worktree checked out at provenance-compatible revision
`f333623380526fa05dcb14110e7ec1fb72d2d0e2`, then run:

```bash
python -m scripts.verify_preserved_canonical_bundle \
  /path/to/canonical-source-metadata.json \
  /path/to/retained-canonical.zip \
  /path/to/retained-canonical-verification.json \
  --root /path/to/frozen-analysis-checkout \
  --receipt-out /path/to/new-offline-reverification.json
```

The *ordinary* `verify_retained_canonical_download` audit **still fails**
after the source artifact's expiry; only this explicit preservation replay
skips the **current-clock source-expiry check**. It does **not** ignore a
different source ID, a changed ZIP, source metadata claiming `expired=true`
at capture, changed analysis results, missing members, or a forged verification
receipt.

A passing replay means a previously retained **GitHub-provider-observed**
canonical-analysis snapshot remains consistent with the published pinned
checkout. It does not prove independent historical custody or present
availability of the source. It does not recover or authenticate the 40
original treatment traces/Markdown reports. It does not generate human
ratings, support new inferential claims, or turn a diagnostic pilot,
confirmatory automated study, exploratory analysis, or pending human
validation into another evidence category.

Preserve a separate copy **outside GitHub Actions retention** if long-term
independent inspection is required. A preservation copy is not itself an
independently collected historical fingerprint.
