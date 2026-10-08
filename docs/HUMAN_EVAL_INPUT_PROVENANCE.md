# Human-evaluation input snapshots

This implementation note describes input provenance for
`scripts/freeze_human_eval_ratings.py`. It does not amend the frozen rating
rubric, assignment plan, or automated analysis plan.

## What the manifest binds

Each ratings CSV is read once into an in-memory byte snapshot. The importer
computes its SHA-256 and byte count from that snapshot and decodes those same
bytes for CSV validation and scoring. An editor saving the path after capture
cannot cause one revision's digest to attest to another revision's scores.

The blinded packet is also captured once. Its allowed blind IDs, recorded byte
count, and SHA-256 all describe the same captured content. Protocol and assignment
plan fingerprints are captured before processing ratings, not after agreement
has been calculated. Output fingerprints still describe the generated files.

Raw input hashes are not hashes of normalized CSV text: UTF-8 bytes and line
endings are retained for fingerprinting. The exact captured bytes that were
parsed are also written create-only inside the freeze as
`raw_rating_inputs/0001.csv`, `0002.csv`, and so on. The manifest binds each
ordered input to its deterministic archive path, byte count, and SHA-256.
Existing CSV structure, score, note, and independent-rater coverage checks still
apply. No treatment key is read.

## Raw submission identity gate

The importer enforces the already-frozen assignment rule: every raw submitted
CSV must contain annotation rows for exactly one non-empty, stable
`annotator_id` (using the existing whitespace normalization). A file that mixes
annotators, or a header-only file alongside otherwise complete submissions, is
rejected before any output directory is reserved. Keep separate original
submissions; do not split a combined file after the fact and claim that doing so
establishes independent human provenance.

`verify_human_eval_freeze.py` applies the same checks to archived raw inputs and
optional external copies. Only its explicit read of the normalized
`frozen_ratings.csv` permits multiple annotators, and those rows must still match
the validated raw submissions exactly. Naming a raw input `frozen_ratings.csv`
does not bypass the guard. The manifest schema, retained raw bytes, scores,
missingness rules, agreement calculation, and full-packet coverage rule are
unchanged. Historical nonconforming bundles fail this current gate; retain their
original bytes and document the protocol deviation rather than rewriting them.

This is a file-level provenance check, not proof of distinct eligible humans.
Coordinator eligibility, independence, and correction responsibilities remain
those in `paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md`.

## Coordinator responsibilities and limits

Keep the original submitted files under controlled, versioned storage when
practical, but the freeze no longer depends on those external paths for later
verification: it retains the exact rating bytes that were actually parsed.
Use a fresh output directory for a later freeze rather than replacing a snapshot.

These are **per-file snapshots**, not an atomic transaction across all inputs,
a filesystem lock, or proof that a submitted score came from an independent
human. The tool does not prevent another process from editing source files after
capture. Later edits do not change the retained archive; supplying the external
files to the verifier is an optional additional cross-check against that
in-bundle source. The manifest attests to captured input bytes, not the latest
contents of a path.

## Offline regression coverage

`tests/test_human_eval_input_snapshots.py` simulates saves at deterministic
parsing and agreement boundaries. It checks that scores, allowed IDs, sizes,
and hashes stay consistent, including after packet replacement or deletion.
Compatibility cases cover LF/CRLF, quoted multiline Unicode notes, and rejection
of invalid UTF-8 before outputs are written. All ratings in these tests are
synthetic fixtures, not collected human annotations or research results.

`tests/test_human_eval_submission_identity.py` covers combined raw submissions,
header-only inputs, an output-like raw filename, a rehashed combined archive,
valid multi-annotator normalized output, optional external verification, and
CLI rejection before publication. The snapshot fixtures keep each synthetic
annotator in a separate raw file without weakening their byte-capture checks.
