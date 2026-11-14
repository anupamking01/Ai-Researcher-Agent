# Published canonical main-study input anchor

**Status:** Offline, read-only CI regression gate. No new experiments, statistical estimates, exploratory findings, or human ratings.

## Why this is useful

The existing research-artifact manifest verifier checks that files agree with the SHA-256 hashes in a supplied local manifest. An accidental rewrite of both a frozen CSV and its manifest could remain internally self-consistent. The canonical main-study analysis published input-manifest aggregate SHA-256
**4e94308472e87cc14b85e5911c40b5f72c63225862a347e624fc0725afd632aa**
before this additional gate. The same aggregate is recorded in draft PR #1's canonical-analysis history.

The command below verifies the checked-in research manifest and the exact original two CSV inputs using the existing strict verifier, then independently compares the verified manifest aggregate with that fixed historical fingerprint:

    python -m scripts.verify_published_main_study_inputs

This command also runs as part of the ordinary offline pytest suite. It rejects both missing/altered files and a *coherently regenerated* manifest that would silently redefine the original 40-cell evidence. Adversarial tests mutate temporary copies only; there is no treatment or evaluator rerun.

## Scope and provenance boundary

This is a version-controlled **regression guard against accidental outcome/data drift**, not a cryptographic third-party signature or proof of authentic historical runs. A collaborator capable of rewriting both the code's literal anchor and the data can still subvert it; review the expected hash against independently retained original analysis records or the published PR history before accepting such a change. A manifest **aggregate** hash is not the SHA-256 of the JSON manifest file. For archival authentication and run/report lineage, continue to use the existing external-file-pin and human handoff verifiers.

A passing result does not independently re-derive statistical estimates; use the independent arithmetic audit for that. The frozen automated confirmatory results, diagnostic pilot, exploratory analyses, and still-uncollected human validations remain distinct. This gate never reads human ratings.
