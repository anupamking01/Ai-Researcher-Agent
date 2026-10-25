# Blinded ratings freeze — bounded source intake

This engineering safeguard applies to the **existing** human-evaluation ratings
freeze and its independent verifier. It does not amend the frozen rubric,
assignment, statistical estimands, hypotheses, or any stored research result.

The original descriptor-bound freeze capture already checked non-symlink regular
files, parent/path identity, modification metadata, and preserved the **same
bytes for hashing and parsing**. But its EOF-driven reader had no size ceiling:
a malformed large or append-only growing ratings CSV (or retained artifact)
could exhaust memory or prevent a verification result.

The shared `freeze_human_eval_ratings._capture_regular_input` reader now
requires an **initial observed size of at most 64 MiB per file**, reads no more
than that initially observed length in 1 MiB chunks, rejects early EOF, and
probes one extra byte to detect growth. It retains the existing post-read
metadata and pathname/parent-identity checks. Files exceeding the ceiling
fail closed before their contents are read. The same function is used by the
producer, per-annotator submission preflight, and
`verify_human_eval_freeze._require_regular_file` for retained artifacts.

These are **per-file** bounds, not a transactional multi-file filesystem
snapshot, a limit on the total number of submitters, proof of historical input
authenticity, verification of human identity/independence, or evidence of
collected human ratings. A concurrent modification outside the observation
window cannot be ruled out. Actual 40-report submissions should be small;
if a legitimate input exceeds 64 MiB, fail and review the input/protocol rather
than silently truncate, skip reports, loosen the cap after inspecting scores,
or unblind early.

Synthetic regressions cover normal and empty reads, exact/oversize limits,
short reads, truncation, single and continuous growth, same-byte pathname
replacement, FIFO and symlink rejection, and inheritance by the independent
verifier. No experimental treatment or human annotation is executed.
