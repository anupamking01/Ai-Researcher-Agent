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
raw annotator CSVs, coordinator annotator attestations, producer source, blinded
packet, protocol, assignment plan, and treatment-blind annotator guide. To audit a relocated bundle without
external governing files, run:

```bash
python -m scripts.verify_human_eval_freeze \
  --freeze-root outputs/human_eval/frozen-v1 \
  --retained-inputs
```

Without `--retained-inputs`, the existing external governing-input checks remain
in force, using their default paths or explicit `--packet`, `--protocol`,
`--assignment-plan`, and `--annotator-guide` options. Any declared retained
archive is also verified in that mode: valid external files cannot hide archive
damage.
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
- `governing_inputs/HUMAN_EVAL_ASSIGNMENT_PLAN.md`;
- `governing_inputs/HUMAN_EVAL_ANNOTATOR_GUIDE.md`;
- `governing_inputs/annotator_attestations.csv`.

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

It also requires the retained or external protocol, assignment plan, and
annotator guide to match their literal frozen anchors in
`freeze_human_eval_ratings.py`, before opening any raw or normalized ratings.
Rehashing a replacement document in the manifest cannot make that bundle valid.

Freezes predating either the annotator-guide manifest binding or the mandatory
annotator-attestation entry do not satisfy this verifier. The study has not yet
collected production annotations, so there is no observed-rating bundle to
migrate. Never backfill a historical freeze using today's working copies or
rewrite an archived bundle to make it pass.

## Checks performed

The verifier never reads `blinding_key.csv`. It fails closed unless all of the
following agree:

- freeze manifest schema, study ID, status, and `blinding_key_used=false`;
- the exact top-level bundle inventory declared by the fixed format, with no
  undeclared sidecars such as `blinding_key.csv`;
- the `provenance/` archive contains only the declared freeze-producer source;
- no duplicate JSON members at any depth in the freeze manifest or stored
  agreement output, including escape-equivalent names;
- exact annotator-packet row schema (`blind_id`, `task_id`, `question`, and
  `report_markdown` only), with every field containing non-empty text and no
  duplicate JSON members (including escape-equivalent names);
- SHA-256 and byte counts for the blinded packet and frozen output files;
- protocol, assignment-plan, and annotator-guide fingerprints plus their
  literal frozen anchors;
- declared retained governing-input paths, bytes, and fingerprints;
- retained attestation bytes and manifest summary, strict literal declarations,
  and an exact pseudonymous-ID set match to the raw rating submissions;
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

## Frozen-rating read consistency

The verifier checks `frozen_ratings.csv` against the manifest, then parses it
using the existing ratings loader. The loader's byte count and SHA-256 describe
the exact bytes it parsed. Those must match the previously checked bytes before
row comparisons, coverage checks, or agreement recomputation proceed.

This rejects edits between the two reads, including line-ending changes that
leave normalized ratings unchanged and same-length score substitutions. A
mismatch raises `frozen-ratings parsed fingerprint` and produces no success
receipt. The verifier does not repair files or rewrite their hashes. Unchanged
valid bundles retain the same format and verification receipt in both external
and retained-input modes.

This check is not a filesystem lock or a guarantee against changes after
verification returns. Keep the freeze stable under controlled storage; downstream
analysis must still use its verified input snapshot rather than reread mutable
working files. Never rehash an edited research artifact merely to make it pass.

## Scope and limits

This gate is designed to catch accidental provenance drift and inconsistent
freeze artifacts before unblinding. The retained attestation records the
coordinator's declarations; it does not prove that annotators were independent
humans, authenticate their identities or filesystem history, or protect against an actor
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


## Bounded verification of retained preflight receipts

Before a blinded annotator submission enters the final rating freeze, its
retained preflight receipt is independently checked against the same ratings
CSV and annotator distribution. The receipt directory must contain **only**
`preflight_receipt.json`. Both the initial check and the check after
recomputation now inspect at most **two** directory entries through the
already-open directory descriptor. A second entry fails immediately, avoiding
an unbounded `os.listdir` allocation on a supplied receipt directory.
The verifier continues to reject changed paths and nonregular receipts.

Synthetic tests cover early overflow with a simulated million-entry directory,
a late sidecar inserted during recomputation, and the existing successful
single-receipt flow. These are denial-of-service and custody safeguards, not
human ratings, proof of annotator independence, or historical archive
authentication. The frozen protocol, automated confirmatory measurements,
pilot, and exploratory findings are unchanged.
