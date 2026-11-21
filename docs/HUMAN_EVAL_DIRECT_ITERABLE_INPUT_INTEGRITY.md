# Bounded one-shot input custody for human-analysis helpers

Status: engineering safeguard only; genuine blinded human annotations are pending.

## Distinct failure mode

`report_scores(rows)` previously traversed `rows` to validate identities, then
traversed it again to validate and aggregate individual ratings. A caller
supplying a one-shot generator could have that iterator exhausted during the
first pass. The helper would silently return empty score/count maps instead of
analyzing supplied rows or rejecting invalid/duplicate later observations.

This differs from existing per-row rubric and identity validation: valid
records could disappear simply because of the shape of the input iterable.

## Implemented contract

* Capture any iterable of rows **once**, before validating or aggregating it.
  Validation and aggregation consume that same in-memory list.
* Use a bounded `islice` read of at most 81 records; reject inputs exceeding
  the frozen 80-rating limit (40 blind reports x exactly two annotators).
  No aggregate is returned from an oversized input. This is a **row-count**
  bound, not a byte-size guarantee on arbitrary Python objects.
* Reject empty inputs instead of returning an apparently successful empty
  summary; reject noniterable inputs with an explicit error.
* Retain existing treatment-blind row schemas, 1–5/blank score domain,
  canonical annotator identity checks, duplicate rating rejection, and
  explained missing/end-point rules. Valid list inputs behave as before.

This guards direct/notebook helper use only. The canonical workflow still
requires independent verification of the complete retained blinded freeze,
annotator attestations and packet provenance **before unblinding**. The
helper does not authenticate raters and does not create, change or validate
real human annotations. The 80-row ceiling must be deliberately reconsidered
before any future predeclared change to the frozen exactly-two-annotator
analysis plan; it is not a rule for all conceivable human-evaluation studies.

Synthetic tests cover complete generator aggregation, suppressed duplicate and
out-of-domain records, identity aliases, empty/noniterable sources, bounded
oversize rejection, and the exact 80-record boundary. Neither frozen
confirmatory outputs nor treatments nor the human-evaluation protocol change.
