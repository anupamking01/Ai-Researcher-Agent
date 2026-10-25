# Blinded packet verification: whole-window source custody

The independent coordinator-side packet verifier already checked individual
files through descriptor-bound reads. That rule protects a file **during its
own capture**, but did not prevent a previously verified trace, report, frozen
task manifest, or packet artifact from changing while a later file was being
checked. A final PASS could therefore describe bytes or filesystem generations
that no longer coexisted at the end of verification.

`scripts/verify_human_eval_packet.py` now records each input's regular-file
generation (device, inode, mode, length, mtime and ctime in nanoseconds) and
its exact SHA-256/byte-length fingerprint. Before issuing PASS it reopens and
rechecks every pinned input through the established bounded regular-file
reader. The frozen task manifest is independently captured and checked against
the parser's own byte fingerprint as well. Missing, replaced, modified, or
observably changing inputs fail closed.

This is an **independent packet-verification** safeguard, distinct from the
producer's earlier per-file capture and size-limit improvements. It does not
change packet randomization, the human rubric, assignment rules, frozen
statistical analyses, treatment outputs, or the contents of the canonical
packet. No model/API calls or human ratings are involved. Synthetic regressions
cover unchanged input, changed earlier trace/report/task manifest, and
byte-identical inode replacements.

The verifier still cannot provide an atomic filesystem transaction. Changes
occurring after its last recheck, undetectable storage-layer tampering, and
historical source authenticity remain outside this guarantee. Preservation of
verified artifacts and real blinded two-rater annotation remain required.
