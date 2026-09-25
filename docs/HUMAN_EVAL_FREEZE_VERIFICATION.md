# Human-evaluation freeze verification

This implementation note describes the offline verification gate for a completed
blinded human-rating freeze. It does not amend the frozen rating rubric,
assignment plan, automated analysis plan, or any reported study result.

## Why verify before unblinding

`freeze_human_eval_ratings.py` writes fingerprints and normalized blinded
outputs, but a later accidental edit, file replacement, partial copy, or manual
manifest change could otherwise go unnoticed before treatment identities are
opened.

Run the verifier while ratings are still blinded and while the exact archived
annotator CSVs, packet, protocol, and assignment plan used for the freeze are
still available:

```bash
python scripts/verify_human_eval_freeze.py \
  outputs/human_eval/annotator-a.csv \
  outputs/human_eval/annotator-b.csv \
  --freeze-root outputs/human_eval/frozen-v1
```

The raw rating files must be supplied in the same order used by the freeze
because the manifest records an ordered input list.

## Checks performed

The verifier never reads `blinding_key.csv`. It fails closed unless all of the
following agree:

- freeze manifest schema, study ID, status, and `blinding_key_used=false`;
- SHA-256 and byte counts for the blinded packet and frozen output files;
- protocol and assignment-plan fingerprints;
- ordered raw-rating input names, byte counts, and SHA-256 fingerprints;
- frozen normalized ratings versus normalization of the archived raw inputs;
- complete independent-rater coverage for every blinded packet item;
- manifest row, annotator, blind-ID, and per-dimension counts;
- stored agreement JSON versus agreement independently recomputed from the
  frozen blinded ratings.

A successful command prints a compact verification receipt and the line
`HUMAN EVAL VERIFY: PASS (ratings remain blinded)`. It does not persist a new
research result or treatment-level artifact.

## Scope and limits

This gate is designed to catch accidental provenance drift and inconsistent
freeze artifacts before unblinding. It does not prove that annotators were
independent humans, authenticate filesystem history, or protect against an actor
who can rewrite every archived input and its external history. Keep the original
files under controlled, versioned storage and retain Git history or another
external provenance anchor.

If more than two annotators rated items, the verifier preserves the freeze
tool's `requires_predeclared_multi_rater_statistic` flag. Verification does not
satisfy that separate analysis-plan requirement.

Passing this gate does **not** create human-evaluation findings. Treatment
identities should remain unopened until real annotations have been collected,
the blinded freeze has been verified, and any required multi-rater analysis
choice has been documented. Pilot, automated confirmatory, exploratory, and
human-validation claims remain separate.
