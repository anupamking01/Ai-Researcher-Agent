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
raw annotator CSVs, producer source, blinded packet, protocol, and assignment
plan. To audit a relocated bundle without external governing files, run:

```bash
python -m scripts.verify_human_eval_freeze \
  --freeze-root outputs/human_eval/frozen-v1 \
  --retained-inputs
```

Without `--retained-inputs`, the existing external packet/protocol/assignment
checks remain in force, using their default paths or explicit `--packet`,
`--protocol`, and `--assignment-plan` options. Any declared retained archive is
also verified in that mode: valid external files cannot hide archive damage.
Do not combine these external governing-file options with `--retained-inputs`;
the command rejects that ambiguity rather than silently ignoring supplied files.

You may additionally pass original annotator CSVs before the options in either
mode. They are checked in original freeze order against the in-bundle raw archive
and manifest. Legacy freezes without raw-input archival still require those
external CSVs.

## Retained governing inputs

The producer captures governing bytes before processing ratings and writes those
same bytes exclusively under these fixed paths before publishing the manifest:

- `governing_inputs/packet.jsonl`;
- `governing_inputs/HUMAN_EVAL_PROTOCOL.md`;
- `governing_inputs/HUMAN_EVAL_ASSIGNMENT_PLAN.md`.

Each corresponding manifest entry binds its archive path, byte count, and
SHA-256. Original packet names and existing protocol identifiers are retained as
metadata, not used to choose archive paths. Line endings and Unicode bytes are
preserved. A later save or deletion of a working file cannot replace the retained
version. An archive write failure leaves an incomplete reserved destination with
no published success manifest; retry requires a new destination.

The verifier rejects partial declarations, path redirection, missing or extra
archive entries, symlinked files/directories, and fingerprint drift. The human
analysis pipeline carries the archive into its temporary blinded snapshot, so
these checks still precede any treatment-mapping access.

Older freezes without governing-input archives remain verifiable with the
external files matching their original fingerprints. They cannot use
`--retained-inputs`. Never backfill a historical freeze using today's working
copies or rewrite an archived bundle to make it pass.

## Checks performed

The verifier never reads `blinding_key.csv`. It fails closed unless all of the
following agree:

- freeze manifest schema, study ID, status, and `blinding_key_used=false`;
- SHA-256 and byte counts for the blinded packet and frozen output files;
- protocol and assignment-plan fingerprints;
- declared retained governing-input paths, bytes, and fingerprints;
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
who can rewrite every archived input and its external history. Keep original
files under controlled, versioned storage and retain Git history or another
external provenance anchor.

Retention is a per-file snapshot, not a transaction or lock across working files.
Archive-only verification removes external governing-file dependencies for the
blinded freeze check; it does not archive a Python environment or make the full
treatment-level analysis standalone. That later analysis still needs the frozen
analysis plan, verified treatment mapping, task manifest, and canonical reports.

If more than two annotators rated items, the verifier preserves the freeze
tool's `requires_predeclared_multi_rater_statistic` flag. Verification does not
satisfy that separate analysis-plan requirement.

Passing this gate does **not** create human-evaluation findings. Treatment
identities should remain unopened until real annotations have been collected,
the blinded freeze has been verified, and any required multi-rater analysis
choice has been documented. Pilot, automated confirmatory, exploratory, and
human-validation claims remain separate.
