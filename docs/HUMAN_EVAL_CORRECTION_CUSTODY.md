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
in the verified freeze input inventory. A superseded file appearing in the
freeze is rejected. Every parseable version must also have distinct, nonblank
blinded report IDs: ordinary clerical/format/validity corrections preserve the
*exact* report-ID set across whole-file revisions; a documented
`missing_row_completion` correction may only add IDs, never silently drop or
substitute previously submitted reports. This prevents a correction chain
from masking selective deletion or substitution of unfavorable report rows.
The check compares **identities only**; scores are neither compared nor
reported.

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
Invoke after the blinded freeze and before unblinding:

```bash
python -m scripts.verify_human_eval_correction_custody \
  --ledger /private/corrections.json \
  --submissions-root /private/retained-versions \
  --freeze-root outputs/human_eval/frozen-v1
```

This check is **only necessary if corrections actually occurred**.
Its receipt is limited to counts and explicit non-attestation of timing.
The identity-set rule is deliberately conservative: an original with an
empty/duplicate blinded ID, or a version that needs to replace an incorrect
blinded ID rather than only add a missing row, is **not** automatically
certified. Preserve both unchanged files and obtain a separately recorded,
pre-unblinding protocol-validity decision/deviation instead of silently
relaxing this gate. Matching row identities cannot prove that changes to
scores or notes were genuinely clerical, nor that every historical submission
was disclosed to the ledger.

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
