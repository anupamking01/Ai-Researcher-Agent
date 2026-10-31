# Verify an intact GitHub Actions preservation ZIP without manual extraction

The retained canonical-analysis copy in Actions artifact **12865837714**
(created by run **40801172761** on 2026-10-29; expiry
**2027-01-27T01:33:53Z**) is an **outer ZIP** containing a separately
verified inner canonical ZIP and verification receipts. GitHub reported the
outer SHA-256 `ea4930f9b897de86785ab12ccf0cab9d3781feb5e1d735f7aafa232c405b65f1`.
That is a **provider-observed digest**, not an independently retained
historical treatment pin.

The new `scripts.verify_preserved_canonical_package` validates the **entire
outer ZIP** before any member is written, without trusting ZIP filenames for
filesystem paths. It enforces a 2 MiB compressed-file cap, safe ZIP local and
central metadata, CRCs, exact allowed 3/4-member inventory, strict per-member
sizes and SHA-256 concordance, and no extra paths or directory entries.
The three required original files are `canonical-source-metadata.json`,
`retained-canonical.zip`, and `retained-canonical-verification.json`.
Modern packages additionally include
`retained-canonical-offline-reverification.json`; if present, **every field**
of that fourth saved receipt is recomputed at its recorded UTC check time and
compared with exact JSON types. Legacy three-member preservation packages
remain supported but are explicitly identified as lacking that fourth receipt.

After bounded validation, only these known filenames are staged in a private
temporary directory for the existing frozen-checkout provenance and inner
archive replay; it is removed on return or failure. No treatment, evaluator,
analysis generation, or human-annotation workload runs.

## Reproduce using the raw outer preservation ZIP

Download the **unextracted ZIP** from
[Actions artifact 12865837714](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/40801172761/artifacts/12865837714)
before expiry. Use an independently checked-out copy of frozen analysis commit
`f333623380526fa05dcb14110e7ec1fb72d2d0e2`, checking that the six
scientific published files have not changed, then run:

```bash
python -m scripts.verify_preserved_canonical_package \
  /path/to/preserved-canonical-outer.zip \
  --root /path/to/frozen-analysis-checkout \
  --expected-package-sha256 ea4930f9b897de86785ab12ccf0cab9d3781feb5e1d735f7aafa232c405b65f1 \
  --receipt-out /path/to/new-package-reverification.json
```

The expected hash above is GitHub's observation for this **specific** retained
outer ZIP; do not mistake its match for independent historical custody. The
receipt is create-only. The audit remains valid **offline after** the original
canonical-analysis artifact expires; it does not query or attest to live GitHub
source availability.

A dedicated read-only workflow,
`.github/workflows/preserved-canonical-package-audit.yml`, automatically
replays the actual preserved outer ZIP against the pinned source revision and
preserves only a verification receipt. If the retained outer artifact expires,
this online workflow fails; independently saved copies can still be verified
offline. The archive verifier never synthesizes historical fingerprints.

**Evidence limits:** Matching provider-observed ZIPs and JSON receipts only
establish concordance of retained canonical *analysis* evidence. They do not
authenticate the original 40 treatment traces and Markdown reports, recover
missing evaluator artifacts, generate independent human ratings, or close the
human-validation gate. Diagnostic pilot, frozen automated confirmatory,
exploratory, and pending blinded-human claims remain separate.
