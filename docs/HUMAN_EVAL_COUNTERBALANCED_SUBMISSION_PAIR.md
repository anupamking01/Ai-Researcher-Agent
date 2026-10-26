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
