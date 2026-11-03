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

