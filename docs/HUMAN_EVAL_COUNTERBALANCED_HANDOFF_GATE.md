# Coordinator preflight: counterbalanced blinded presentation

**Status: optional operational safeguard before human rating collection.** This
is not a protocol amendment, human result, or substitute for eligibility review.
The frozen human-evaluation protocol requires every report to be independently
rated by at least two eligible human annotators. The existing distribution
exporter supports canonical and reverse report orders, but checking two
exports separately does not establish that the coordinator prepared both orders
from **the same independently pinned coordinator packet**.

Use the new read-only scripts/verify_human_eval_counterbalanced_handoff.py to
verify that an original-order bundle and reverse-order bundle each pass the
existing full source-bound packet validator and share an independently retained
coordinator-manifest SHA-256. This helps counterbalance possible positional
fatigue/order effects across the two planned raters, without assigning human
identities or selecting reports based on treatment outcomes. The original 40
reports and fixed rubric are unchanged. The verifier never opens the blinding
key, annotator submissions, scores, or treatment identities.

## Coordinator-only recruitment and release checklist

The source gates below certify files, not people. Recruitment preparation can
proceed separately from archive recovery, but **do not release study reports
until the original evidence and all applicable source handoff gates pass**.
This checklist is an operational aid for the already frozen
[assignment plan](../paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md),
[protocol](../paper/HUMAN_EVAL_PROTOCOL.md), and
[human analysis plan](../paper/HUMAN_EVAL_ANALYSIS_PLAN.md). It is not a new
rubric, rater exclusion criterion, or retroactive amendment.

### Before report access

1. Establish the applicable institutional ethics/consent, compensation,
   withdrawal and data-retention requirements with the responsible human
   investigator. Do not infer exemption or approval from an offline software
   verifier. Record the actual determination privately before collection.
2. Invite potential raters without the project repository URL, hypotheses,
   treatment names, results, reports, or a coordinator receipt. A neutral
   invitation can describe the work as independently reading and scoring 40
   English research reports on five rubric dimensions, using only one's own
   judgment. Supply the approved consent information and realistic workload
   expectations; do not imply participation or payment is contingent on
   producing favorable scores.
3. Before any report access, privately check the assignment-plan eligibility
   conditions: English/rubric ability, no role in generating/editing/selecting
   reports, no access to the key, treatment-specific metadata or other raters'
   scores, and willingness to score independently without automated scoring
   assistance. Ask about prior project exposure without supplying the material
   that would reveal the mapping. Familiarity alone is not disqualifying under
   the frozen plan; document and resolve material conflicts before assignment.
   Do not use familiarity with the expected result as a selection advantage.
4. Select two distinct eligible people and assign neutral, stable pseudonyms.
   Keep their identities and consent records separately under restricted
   access. Decide which person receives canonical versus reverse order before
   observing any rating; record the choice and use only that person's bundle.
   Do not invite a candidate to inspect both orders. No public recruitment
   record should contain the private mapping or link a person to a pseudonym.

### Evidence to retain privately

Maintain a dated coordinator record outside the repository, source archives
and annotator bundles. The following are suggested fields for the operational
record, **not a populated record, a new CSV schema, or substitute attestations**:

| Stage | Minimum record |
| --- | --- |
| Governance | Responsible investigator; applicable approval/consent determination and date; secure reference to consent records |
| Eligibility | Pseudonym; distinct-person check; screening date; prior exposure/conflict decision and rationale; investigator decision before report access |
| Assignment | Pseudonym, presentation order, decision date before scoring |
| Release | Source-authentication decision and evidence reference; verified pair receipt; actual delivered bundle-manifest digest; recipient/order and delivery date |
| Submission | Exact original file fingerprint and receipt date; order-specific blinded preflight receipt; whole-file correction or withdrawal records if applicable |
| Freeze | Post-scoring independence/blinding confirmation; actual frozen attestation and snapshot references; recorded deviations and their disposition |

Do not populate a post-scoring declaration such as `scored_independently`
or `treatment_identity_unseen_during_scoring` based only on an invitation
or a bundle hash. Confirm the conditions with the actual annotator and retain
the supporting coordinator record before creating the protocol's exact
`annotator_attestations.csv`. A successful software freeze preserves those
declarations; it cannot independently authenticate them.

### Release and incident handling

Use the [original-source recovery guide](HUMAN_EVAL_ARCHIVE_RECOVERY.md),
[automated-to-human handoff gate](HUMAN_EVAL_AUTOMATED_HANDOFF_GATE.md) and
[private-seed addendum](../paper/HUMAN_EVAL_BLINDING_SEED_ADDENDUM.md) before
the pair procedure below. Recheck the delivery copy, not only the local export.
Send each rater only the verified annotator-facing bundle through the approved
private channel; do not attach the coordinator checklist, key, full manifest,
pair receipt, or links to this research branch.

If a rater reports exposure, a conflict, another person's scores, a wrong
bundle, or accidental disclosure, stop the affected handoff and preserve the
original materials and any submitted scores privately. Record the incident and
its scope while still blinded; apply the frozen assignment plan's objective
validity rules without looking at treatment-level results. Do not silently
repair the ratings, replace selected rows, backdate declarations, or rerun
reports. If replacement is required, use a fresh eligible blinded person and
retain the superseded submission. A disclosed packet seed/key is a
packet-wide risk, not something that a new file hash can undo; follow the
private-seed addendum and document any deviation if scoring has already begun.

After genuine submissions, follow the
[counterbalanced submission-pair audit](HUMAN_EVAL_COUNTERBALANCED_SUBMISSION_PAIR.md)
and the frozen blinded freeze/verification procedure. Do not open the
treatment mapping to resolve uncertainty about rater eligibility or scores.

No invitation, consent, eligibility decision, assignment, release, or rating
is established by this checklist. The diagnostic pilot, frozen post-collection
automated analysis, retrospective exploratory findings, and pending human
validation remain separate.

## Reproducible coordinator procedure

With a *previously verified* coordinator packet, independently record the SHA-256
of its manifest.json in the coordinator's restricted provenance log. Do not
calculate the expected digest only after receiving the bundles: that would not
provide an independent source pin.

    python -m scripts.export_human_eval_annotator_bundle \
      --packet-root outputs/human_eval \
      --output-root outputs/human_eval/annotator-canonical-v1 \
      --presentation-order canonical

    python -m scripts.export_human_eval_annotator_bundle \
      --packet-root outputs/human_eval \
      --output-root outputs/human_eval/annotator-reverse-v1 \
      --presentation-order reverse

    python -m scripts.verify_human_eval_counterbalanced_handoff \
      --packet-root outputs/human_eval \
      --canonical-root outputs/human_eval/annotator-canonical-v1 \
      --reverse-root outputs/human_eval/annotator-reverse-v1 \
      --coordinator-manifest-sha256 '<independently-retained-64-character-sha256>'

The read-only command fails on missing/extra/mutated distribution artifacts,
inconsistent source bindings, missing external pin, duplicate same-path
bundles, wrong presentation order, or an unexpected report count (40 by default).
It emits a coordinator-only JSON receipt containing only the verified source
manifest digest, report count, order labels, and digests of the three
annotator-visible files per bundle. It neither persists a new directory nor
contacts anyone. Retain that receipt *outside* annotator-facing bundles.

Assign each of the two bundles to a different **independently eligible** blinded
human rater using the existing assignment and consent procedure; do not send
both bundles to one rater or treat two bundles as two independent human scores.
The order check cannot establish annotator independence, eliminate all order
bias, authenticate any human rating, or guarantee treatment concealment from
semantic hints in a report. Revalidate the selected bundle before distribution
and freeze genuine submissions using the existing unblinded-key-free workflow.
No report may be added, removed, rewritten, rerun, or selected using its scores.

## Pair-wide custody across serial bundle verification

A successful source-bound audit of the canonical bundle does not by itself
guarantee that those original files still exist unchanged after the reverse
bundle has been audited. The counterbalanced gate now captures the exact four
annotator-visible artifacts in **both** directories before either source-bound
verification. It preserves bounded SHA-256 digests, file identities and the
directory inventory, then rechecks both bundles after the two verifiers pass.

This rejects a first-bundle edit, same-byte inode substitution, or a newly
injected file during verification of the second bundle. The new pair-wide
checkpoint never opens the coordinator blinding key, annotator submissions,
or rating files; the pre-existing one-bundle source verifier separately handles
the restricted coordinator evidence. This is observable filesystem custody,
not an atomic snapshot or cryptographic proof of historic origin. A transient
change restored between observations may be missed. A passing pair receipt
does not mean source reports have been recovered, eligible humans recruited,
or blinded evaluations completed.

The pair gate also rejects **hard-linked annotator-facing files** at both
initial capture and final recheck (filesystem link count must be one). This
covers sharing the byte-identical instructions file between the two bundle
directories, and aliases outside either directory. A file shared by inode can
be altered through the other path after it has been certified for one rater;
independent copies with identical bytes remain acceptable. This prevents
mutable filesystem aliasing, not unauthorized post-verification access,
physical distribution mistakes, or an absence of genuinely independent human
annotators.

