# Blinded human-rating correction custody (coordinator only)

The frozen [human assignment plan](../paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md)
allows a clerical correction **only before** an annotator sees treatment
identity or another annotator's ratings. The full superseded file must be
retained; selectively combining favorable rows across versions is prohibited.
Previously the final freeze retained only the submitted final file, leaving
the optional, legitimate revision chain without a source-bound offline check.

`scripts/verify_human_eval_correction_custody.py` adds a separate **read-only
post-freeze, pre-unblinding** reconciliation. It requires the existing verified
blinded freeze first, then SHA-256 checks *every* original and replacement
CSV, enforces one stable pseudonymous annotator per chain, distinct complete
files, bounded neutral filenames, a reason code, and exactly the last version
in the verified freeze input inventory. The custody checker now obtains an
**opt-in SHA-256 fingerprint of the exact freeze-manifest bytes authenticated by
the independent freeze verifier** and compares that fingerprint to its own
later manifest capture before using any accepted-submission inventory. If the
manifest changes between verification and correction reconciliation, the
custody check fails closed rather than trusting a different, possibly
self-consistent inventory. Existing standalone verifier receipts remain
unchanged unless the fingerprint is explicitly requested. A superseded file
appearing in the freeze is rejected. Every parseable version must also have distinct, nonblank
blinded report IDs: ordinary clerical/format/validity corrections preserve the
*exact* report-ID set across whole-file revisions; a documented
`missing_row_completion` correction must add at least one new ID at each
version and cannot drop or substitute an existing one. For `missing_row_completion`, every previously submitted row must retain
identical **five rubric-field values and notes** after CSV parsing. For
`file_format_correction`, the **entire** parsed blind-ID-to-ratings-and-notes
mapping must remain identical, allowing harmless changes such as CSV line
endings or row order but rejecting any changed score or note. This closes
the possibility of disguising a substantive score revision as a format-only
fix. The verifier checks equality, **not score direction**, and does not emit
scores or report-level data. `clerical_transcription` and
`other_predeclared_validity_correction` retain the whole-file custody rule
without automatic value equality; their legitimacy still requires
independently retained, blinded coordinator approval evidence.

Coordinator-only ledger example (use only nonidentifying pseudonyms and neutral
filenames in a private directory, not actual annotation values here):

```json
{
  "schema_version": 1,
  "study_id": "budget-main-v1",
  "phase": "before_unblinding",
  "chains": [{
    "annotator_id": "Rater-A",
    "reason": "clerical_transcription",
    "versions": [
      {"file": "r001_v001.csv", "sha256": "<original file SHA-256>"},
      {"file": "r001_v002.csv", "sha256": "<corrected file SHA-256>"}
    ]
  }]
}
```

Supported reason codes: `clerical_transcription`, `missing_row_completion`,
`file_format_correction`, and `other_predeclared_validity_correction`.
Copy full unchanged files under neutral names `rNNN_vNNN.csv` in a
coordinator-controlled submissions directory, retaining the original
submission and any contemporaneous coordinator-private approval record.
Within each annotator's correction chain, use **one stable `rNNN` series**
and label every retained whole-file revision **contiguously in ledger order**
(`v001` original, `v002` first replacement, `v003` second replacement,
etc.). The offline auditor now fails closed on mixed series, skipped revision
numbers, and an inverted ledger order, even when hashes and accepted final
freeze inputs match. This prevents a misleading or fragmented version chain
from passing as complete. Filename ordinals document the submitted custody
sequence; they do **not** independently authenticate real-world submission
times or prove that unlisted files never existed.
Invoke after the blinded freeze and before unblinding:

```bash
python -m scripts.verify_human_eval_correction_custody \
  --ledger /private/corrections.json \
  --submissions-root /private/retained-versions \
  --freeze-root outputs/human_eval/frozen-v1
```

This check rejects retained CSV versions larger than **4 MiB each**, or
more than **64 MiB total** across all versions in the ledger. The stricter
per-file and remaining aggregate limits are checked against the securely
opened file descriptor **before reading or allocating the CSV bytes**, not
merely after a general packet-capture read. Ledger (64 KiB) and verified
manifest (1 MiB) captures also receive caller-specific pre-read bounds.
Unchanged captured bytes are still checked again after capture before
digest and CSV processing; the auditor does not silently truncate long
submissions or drop correction history.
Ordinary 40-report ratings CSVs should be substantially smaller. If
legitimate historical submissions exceed this offline resource budget,
preserve every original unchanged and document the exception for
coordinator review; do not split, trim, or selectively omit submissions
just to obtain a passing receipt.

This check is **only necessary if corrections actually occurred**.
Its receipt contains only counts, explicit non-attestation of timing, the
SHA-256 of the **exact frozen manifest bytes verified independently**, and
the SHA-256 of the **same correction-ledger bytes captured for parsing**.
These fingerprints distinguish equally sized but different custody ledgers,
bind a later replay to the checked source files, and do not include report
IDs, annotator pseudonyms, rubric values, or private file paths. Preserve the
unchanged ledger, frozen snapshot, and complete retained submissions in
coordinator-controlled storage; a receipt alone is neither the original
evidence nor a trusted timestamp and cannot prove that every correction was
reported. The ledger digest is taken from the single captured read, not from
a second potentially changed pathname.
The identity-set rule is deliberately conservative: an original with an
empty/duplicate blinded ID, or a version that needs to replace an incorrect
blinded ID rather than only add a missing row, is **not** automatically
certified. Preserve both unchanged files and obtain a separately recorded,
pre-unblinding protocol-validity decision/deviation instead of silently
relaxing this gate. Matching row identities or unchanged rows cannot prove that other permitted
clerical edits were legitimate, nor that every historical submission was
disclosed to the ledger. The source-bound manifest digest also cannot prove
historical submission time or prevent changes *after* audit completion; it only
prevents an unverified manifest revision being substituted at the consumption
boundary. If completing missing rows also requires editing
an existing score or note, preserve the originals and obtain a separate
blinded protocol-validity decision/deviation instead of calling it
missing-row completion.

The `phase` declaration is not an independent timestamp, consent/eligibility
record, proof of human independence, or proof of when an annotator saw other
ratings. Preserve approval/timing evidence separately under applicable
governance; do not insert identities, report content or scores into this
ledger or commit private submissions. This does not alter the frozen
protocol, assignment plan, rubric, automated scores, or frozen analysis.

All tests use synthetic submissions. The five-task pilot stays diagnostic,
the main automated results are post-collection and fixed-order/evaluator-policy
qualified, retrospective sensitivity work remains exploratory, and independent
blinded human validation remains pending. Missing original reports/traces still
block authorized handoff; this utility does not recover them or create ratings.
