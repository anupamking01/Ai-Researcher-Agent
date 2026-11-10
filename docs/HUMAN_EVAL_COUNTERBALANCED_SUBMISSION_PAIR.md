# Counterbalanced blinded submission-to-handoff provenance gate

**Status: optional, read-only coordinator pre-freeze audit.** No human ratings have been collected or evaluated as part of developing this gate. This does not amend the frozen protocol or the main-study confirmatory analysis.

## Gap closed

The existing pre-distribution handoff gate verifies that the canonical and reverse annotator bundles derive from one independently pinned coordinator packet. Separately, the retained submission-preflight verifier checks one rating CSV against one annotator bundle. Neither standalone check proves that the **two returned rating CSVs** came from the **two different source-bound presentation orders**. Two locally valid canonical-order submissions, for example, could pass independent preflights without demonstrating counterbalancing.

The new read-only script composes the existing handoff and retained receipt verifiers. It requires one canonical and one reverse submission, each matched to its own retained receipt and verified source bundle; an independent coordinator-manifest SHA-256 pin; all expected reports in both; distinct rating files and receipt directories; and two distinct pseudonymous annotator IDs under the frozen Unicode NFKC/case-fold identity rule. It never reads the blinding key, discloses score or note content, contacts anyone, or mutates evidence.

## Procedure

Before distribution, follow the existing counterbalanced handoff guide and independently retain the coordinator manifest SHA-256. After receiving **genuine** completed submissions, run the existing treatment-blind submission preflights and retain a create-only preflight receipt directory for each. Run the following before freezing or unblinding (default 40 reports):

    python -m scripts.verify_human_eval_counterbalanced_submission_pair \
      --packet-root outputs/human_eval \
      --canonical-root outputs/human_eval/annotator-canonical-v1 \
      --reverse-root outputs/human_eval/annotator-reverse-v1 \
      --canonical-submission path/to/annotator-canonical.csv \
      --reverse-submission path/to/annotator-reverse.csv \
      --canonical-receipt-root path/to/canonical-preflight-receipt \
      --reverse-receipt-root path/to/reverse-preflight-receipt \
      --coordinator-manifest-sha256 '<independently-recorded-digest>'

Retain the coordinator-only JSON receipt separately. It includes source and submission SHA-256 fingerprints, report and missing-dimension counts, order labels, and a distinct-pseudonym claim, but no scores, free-text notes, or annotator IDs. Preserve the underlying original CSVs, receipts, bundles, and coordinator packet: this gate archives none of them.

The actual blinded freeze still requires the frozen eligibility/independence attestations, original submissions, verified preflights, and independent verification of the retained frozen snapshot. This optional audit is not a new exclusion rule on an existing frozen dataset. Additional raters or procedural deviations must be addressed under the frozen assignment plan, rather than assuming one canonical/reverse pair covers every possible design.

## Interpretation and limitations

A passing result establishes consistency between the *declared* pair of submissions and source-bound, counterordered packet evidence under the existing validators. SHA-256 means byte identity, not human authorship, consent, eligibility, independent scoring, or continued blinding. Validation is serial, not an atomic filesystem lock over all evidence; changes restored between checks can escape detection. Retain exact input bytes and revalidate before use. This receipt is **not** a human-validation result, reliability estimate, treatment effect, or permission to open the blinding key. Pilot, frozen automated confirmatory, exploratory, and pending human-evaluation findings remain separate.


## Pair-wide submission and retained-receipt observation window

The verifier now pins **both** original rating CSVs and **both** retained
preflight receipts before starting the serial handoff/submission checks. It
captures bounded raw bytes with the existing descriptor-based freeze reader
and records path/parent object identities, size, modification/change timestamps,
and SHA-256. After both order-specific verifications finish, it re-reads and
compares all four sources and the two receipt-directory identities. Any
observable intermediate rewrite or byte-identical file/directory replacement
that persists through the final observation fails closed, rather than
returning a stale first-submission provenance claim.

This guard is intentionally read-only, coordinator-only, and does not change
the frozen protocol, presentation order, or the ratings. Tests inject file
mutation and same-byte inode replacement *between* verification of the two
orders; all inputs are synthetic. The observation is not an atomic filesystem
snapshot, tamper-proof storage, external SHA-256 escrow, or human identity
authentication; changes made and fully restored between observations can
escape detection. Retain originals and independently pinned fingerprints
until blinded freeze/archival.

## Cross-stage bundle-custody window (pre-freeze)

The source-bound **counterbalanced handoff** already snapshots and verifies both
annotator-facing bundle revisions while comparing the two presentation orders.
Previously, however, those bundle snapshots stopped at the end of the handoff
call, before the **two separate submission-preflight receipt checks**. A
canonical bundle changed after its earlier verification, during the reverse
submission check, could therefore leave a stale paired handoff claim even if
both submitted CSVs and retained receipts were unchanged.

The pair verifier now extends the existing bounded, inode-and-digest
snapshot/recheck of **both complete annotator bundle inventories** across the
whole handoff-to-submission window. A persistent changed byte, file replacement,
or changed bundle-root identity fails closed before any successful pair receipt.
Synthetic offline regressions inject a late canonical packet edit and a
byte-identical ratings-template inode replacement during reverse preflight;
neither represents an actual annotation or historical experiment.

This is observational source custody, not an atomic filesystem transaction,
independent evidence authentication, proof of annotator independence, or
authorization to distribute or unblind packets. The original source-archive
recovery and real-human evaluation gates remain blocked; no experimental or
human-evaluation outcomes are changed.


## Cross-stage coordinator and governing-input custody

The original coordinator packet's four artifacts (including the private
blinding key), frozen task manifest, and frozen annotator guide are verified
during each handoff-source check. Previously, these original sources could
change **after** handoff verification while the two returned submissions were
being checked, without altering either annotator-facing bundle or the retained
preflight receipts. A stale coordinator-source claim could then be returned.

The submission-pair verifier now records source inode/metadata signatures and
bounded SHA-256 digests for those exact governing inputs before the serial audit,
then rechecks identities and bytes after both order-specific preflights. It
retains only source digests in memory, does not expose the private key, and
does not change, unblind, or recreate any evidence. Synthetic regressions
modify every coordinator artifact and the task manifest after the handoff;
another swaps the private blinding-key file for identical bytes under a
different inode. All must fail closed.

This observational check does **not** authenticate original treatment
reports/traces, track filesystem mutations that are fully restored between
observations, implement atomic locking, or establish actual annotator identity,
eligibility, independence, or agreement. It is a pre-freeze custody guard,
not new human-evaluation evidence or a change to frozen analysis.
