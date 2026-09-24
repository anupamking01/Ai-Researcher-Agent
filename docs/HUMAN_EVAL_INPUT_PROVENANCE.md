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
endings are retained for fingerprinting. Existing CSV structure, score, note,
and independent-rater coverage checks still apply. No treatment key is read.

## Coordinator responsibilities and limits

Archive the exact original packet, protocols, and submitted ratings as versioned
files before freezing. Stop editing that archived set. Keep it with the resulting
freeze manifest and outputs; hashes alone cannot restore an overwritten source.
Use a fresh output directory for a later freeze rather than replacing a snapshot.

These are **per-file snapshots**, not an atomic transaction across all inputs,
a filesystem lock, or proof that a submitted score came from an independent
human. The tool does not prevent another process from editing source files and
does not archive raw input copies automatically. If source files are edited
later, compare their hashes with the manifest to identify the revision used.
The manifest attests to captured input bytes, not the latest contents of a path.

## Offline regression coverage

`tests/test_human_eval_input_snapshots.py` simulates saves at deterministic
parsing and agreement boundaries. It checks that scores, allowed IDs, sizes,
and hashes stay consistent, including after packet replacement or deletion.
Compatibility cases cover LF/CRLF, quoted multiline Unicode notes, and rejection
of invalid UTF-8 before outputs are written. All ratings in these tests are
synthetic fixtures, not collected human annotations or research results.
