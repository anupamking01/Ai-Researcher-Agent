# Human-evaluation freeze verification

This implementation note describes the offline verification gate for a completed
blinded human-rating freeze. It does not amend the frozen rating rubric,
assignment plan, automated analysis plan, or any reported study result.

## Why verify before unblinding

`freeze_human_eval_ratings.py` writes fingerprints and normalized blinded
outputs, but a later accidental edit, file replacement, partial copy, or manual
manifest change could otherwise go unnoticed before treatment identities are
opened.

Run the verifier while ratings are still blinded. New freezes retain the exact
raw annotator CSV bytes inside the freeze bundle, so the canonical check is
self-contained:

```bash
python scripts/verify_human_eval_freeze.py \
  --freeze-root outputs/human_eval/frozen-v1
```

You may additionally pass the original annotator CSVs before the options. When
provided, they are checked in the original freeze order against the in-bundle
archive and manifest. Legacy freezes created before raw-input archival still
require those external files.

## Checks performed

The verifier never reads `blinding_key.csv`. It fails closed unless all of the
following agree:

- freeze manifest schema, study ID, status, and `blinding_key_used=false`;
- SHA-256 and byte counts for the blinded packet and frozen output files;
- protocol and assignment-plan fingerprints;
- deterministic in-bundle raw-rating archive paths, byte counts, and SHA-256
  fingerprints, with no undeclared archive files;
- frozen normalized ratings versus normalization of the retained raw inputs;
- optional external raw-rating copies versus the retained archive when supplied;
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
