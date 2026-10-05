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
Each captured ratings CSV must contain at least one annotation row and exactly
one non-empty `annotator_id` across all of its rows. The manifest records that
source annotator ID and row count next to the source hash. This makes the
file-level provenance match the intended one-submission-per-annotator workflow:
one mixed CSV cannot syntactically impersonate two independent raters and satisfy
the double-rating coverage gate by itself.

Existing CSV structure, score, note, and independent-rater coverage checks still
apply. No treatment key is read.

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
