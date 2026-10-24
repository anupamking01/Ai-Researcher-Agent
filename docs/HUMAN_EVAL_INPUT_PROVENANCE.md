# Human-evaluation input snapshots

This implementation note describes input provenance for
`scripts/freeze_human_eval_ratings.py`. It does not amend the frozen rating
rubric, assignment plan, or automated analysis plan.

## What the manifest binds

Every file that determines the blinded freeze is read once into an in-memory
byte snapshot through a non-symlink regular-file descriptor under a bound
regular parent directory. This includes each ratings CSV, the blinded packet,
the three frozen governing documents, the coordinator attestation CSV, and the
archived freezer and annotator-content-validator implementations. Capture
fails closed if the file, its immediate parent, or the visible pathname is
replaced while bytes are being read.

The importer computes each ratings CSV's SHA-256 and byte count from its
captured snapshot and decodes those same bytes for CSV validation and scoring.
An editor saving the path after capture cannot cause one revision's digest to
attest to another revision's scores.

The blinded packet is also captured once. Its allowed blind IDs, recorded byte
count, and SHA-256 all describe the same captured content. Protocol,
assignment-plan, and annotator-guide fingerprints are captured before processing
ratings, not after agreement has been calculated. Output fingerprints still
describe the generated files.

The coordinator-only annotator attestation CSV is likewise strictly parsed
from its descriptor-bound bytes, retained at
`governing_inputs/annotator_attestations.csv`, and bound by byte count, SHA-256,
and annotator count. Its pseudonymous ID set must exactly equal the IDs in the
raw submissions. The independent verifier repeats the strict parse from the
retained bytes and rechecks that set equality; rehashing a declaration with a
false literal or substituted ID cannot make it valid.

The captured protocol, assignment-plan, and treatment-blind annotator-guide
bytes must also match literal SHA-256 anchors in the freeze implementation.
This prevents substituted or post-hoc governing instructions from becoming
self-consistent merely because a new manifest fingerprints them. All anchors
are checked before any human-rating CSV is opened. Changing any frozen document
therefore requires an explicit, reviewed source change to its production
anchor; passing a different path is not sufficient.

The same captured guide bytes are retained as
`governing_inputs/HUMAN_EVAL_ANNOTATOR_GUIDE.md` and recorded in the freeze
manifest. This connects the distribution-stage instructions to the later
pre-unblinding rating snapshot without adding treatment identity or implying
that annotations have been collected.

The freeze also records the runtime contract for its archived annotator-content
validator: Python implementation/version, Unicode database version, exact
`markdown-it-py` and delegated `mdurl` versions, CommonMark preset, and renderer
options. Those values affect normalization and the rendered text inspected for
hidden treatment labels, so source bytes alone are not sufficient provenance.
Independent verification fails closed when its runtime contract differs; use
the recorded environment to reproduce verification rather than silently
accepting different rendering semantics.

Raw input hashes are not hashes of normalized CSV text: UTF-8 bytes and line
endings are retained for fingerprinting. The exact captured bytes that were
parsed are also written create-only inside the freeze as
`raw_rating_inputs/0001.csv`, `0002.csv`, and so on. The manifest binds each
ordered input to its deterministic archive path, byte count, and SHA-256. It
does not retain the caller-controlled ratings or attestation source filenames,
because those names may identify annotators or the coordinator. Original names
and any filename-to-person mapping remain outside the blinded research bundle.
Existing CSV structure, score, note, and independent-rater coverage checks still
apply. No treatment key is read.

When one `--submission-preflight RECEIPT_ROOT BUNDLE_ROOT` pair is supplied for
every ratings input, the freeze also retains treatment-blind intake replay
evidence under `submission_preflights/0001`, `0002`, and so on. Each neutral
directory contains a filename-neutralized receipt and the four
annotator-distribution artifacts; no caller-controlled source filename is copied
into the manifest or retained receipt. Before publication,
the producer replays the receipt against the already captured submission,
checks that the pseudonymous annotator is unique across receipts, and requires
the distributed packet rows to equal the final coordinator packet rows in the
declared canonical or reverse order. The manifest binds each evidence directory
to its ratings-input index, pseudonym, presentation order, receipt byte count,
and receipt SHA-256.

The independent verifier repeats that replay entirely from the raw-rating and
submission-preflight archives. Substituting a receipt, a distribution bundle,
or a different report order therefore invalidates the freeze even when the
ratings CSV alone remains syntactically valid. This proves a byte-level chain
between blinded intake and freeze; it does not prove who completed the file,
that scoring was independent, or that the declarations are true.

Every individual file read performed directly by the independent freeze
verifier uses the same descriptor-bound capture contract as freeze creation.
This includes the manifest, retained governing inputs and attestations,
archived producer and validator sources, normalized ratings, agreement output,
and any explicitly supplied external governing files. The verifier retains the
opened non-symlink file and parent-directory descriptors, parses and hashes the
captured bytes, then rechecks file identity, mutation metadata, parent identity,
and final pathname binding. A byte-identical pathname replacement during a
verification read therefore fails closed instead of becoming newly trusted.

The verifier also captures a descriptor-bound recursive inventory of the full
freeze tree before reading the manifest and compares it with a second stable
inventory immediately before returning its success receipt. The inventory binds
every regular file and directory by relative name, type, device, inode, size,
and mutation timestamps; existing path-specific checks continue to reject
symlinks and other special entries with artifact-specific diagnostics.
Consequently, a file or directory added, removed, replaced, or edited during
verification cannot coexist with a successful receipt merely because its
parent's closed-layout check happened earlier.

The independent verifier treats the freeze manifest as a closed schema at every
object boundary. The root, governing-input descriptors, coverage summary,
producer and validator identities, ordered rating-input descriptors, normalized
output summary, per-dimension counts, and agreement descriptor may contain only
the fields and JSON value types emitted by the freeze producer. Missing fields,
added metadata, and objects hidden in scalar fields are rejected before retained
inputs or computed outputs are trusted. It also requires each rating-input index
to match its archive order, rejects any reintroduced source-name field, and
requires the producer's exact blinded,
pre-unblinding integrity statement. Consequently, reserializing a manifest with
an added treatment label, coordinator field, redirected source identity, or
misleading integrity claim cannot produce a verified freeze even when every
artifact fingerprint remains unchanged.

## Raw submission identity gate

The importer enforces the already-frozen assignment rule: every raw submitted
CSV must contain annotation rows for exactly one non-empty, stable
`annotator_id` (using the existing whitespace normalization). A file that mixes
annotators, or a header-only file alongside otherwise complete submissions, is
rejected before any output directory is reserved. Keep separate original
submissions; do not split a combined file after the fact and claim that doing so
establishes independent human provenance.

Each annotator's one submitted CSV must also contain every blinded packet ID
exactly once. Aggregate coverage assembled from several partial annotators is
not a substitute for complete independent review of the packet, even when each
item happens to have two rows overall. This completeness check runs only after
the existing duplicate, split-submission, and minimum-rater gates, preserving
their more specific diagnostics. The independent freeze verifier recomputes the
same per-annotator coverage from retained raw inputs and normalized ratings.

`verify_human_eval_freeze.py` applies the same checks to archived raw inputs and
optional external copies. Only its explicit read of the normalized
`frozen_ratings.csv` permits multiple annotators, and those rows must still match
the validated raw submissions exactly. Naming a raw input `frozen_ratings.csv`
does not bypass the guard. The closed manifest schema, retained raw bytes, scores,
missingness rules, agreement calculation, and full-packet coverage rule are
verified together. Historical nonconforming bundles fail this current gate;
retain their original bytes and document the protocol deviation rather than
rewriting them.

The importer and verifier also reject non-overlapping fragments of one
annotator's ratings spread across multiple raw CSVs, including IDs that differ
only in surrounding whitespace. This enforces the frozen whole-submission
correction rule; it does not bar the one intentionally combined normalized
`frozen_ratings.csv`.

Annotator identity comparisons use Unicode NFKC compatibility normalization
before and after casefold. Canonically equivalent accents and compatibility
spellings (for example fullwidth Latin letters/hyphens or Roman-numeral glyphs)
therefore cannot be counted as two independent raters or split across
submissions. The submitted spelling and raw CSV bytes remain unchanged;
normalization is used only as an identity/coverage key, not to alter ratings,
rewrite pseudonyms, or authenticate humans. Compatibility aliases may refer to
different real people, so the coordinator must resolve any collision while
still blinded rather than silently merging scores or renaming raters after
scoring. The runtime Unicode database version is retained as provenance.

Annotator IDs must also be visible, auditable text: Unicode control and format
characters are rejected. This prevents zero-width or bidirectional-control
characters from creating identifiers that look identical while counting as
independent raters. Ordinary Unicode letters and combining marks remain valid,
and accepted raw CSV bytes are still retained unchanged.

## Spreadsheet-active text gate

The importer rejects `annotator_id` or `notes` values whose normalized text
begins with `=`, `+`, `-`, or `@`. Spreadsheet programs can interpret those
prefixes as formulas when a CSV is opened, even though CSV quoting is otherwise
valid. Rejecting the submission before publication keeps the frozen CSV inert
without silently escaping or changing the annotator's text; the coordinator
must ask for plain-text wording and retain the original submitted file outside
the failed freeze. The verifier applies the same rule to archived and normalized
ratings. This transport-safety check does not alter scores, missingness, the
rubric, the assignment plan, or treatment blinding.

The required retained attestation makes the coordinator's eligibility,
blinding, independence, human-only-scoring, and non-author declarations
machine-auditable. It remains a file-level provenance check, not proof of
distinct eligible humans or truth of those declarations. Coordinator
eligibility, independence, and correction responsibilities remain
those in `paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md`.

## Treatment-blind free-text rating notes

The retained `notes` column can otherwise reintroduce variant identifiers or
coordinator metadata after the packet itself passed its blinding audit. Each
nonempty note now undergoes the **same** renderer-aware, Unicode-aware treatment
marker audit as annotator-visible packet text before the coordinator can freeze
scores. This rejects exposed D3/D6/P6/P6V labels, coordinator field markers,
obfuscated Unicode markers, encoded Markdown link attributes, raw HTML, and
Markdown images instead of silently deleting or editing an annotator's words.
Valid plain-text justifications are retained byte-for-byte in the original
submitted CSV archive; the normalized output follows the existing whitespace
trimming rule, without any additional redaction or score modification.

The independent freeze verifier re-parses the archived ratings through this
same gate; the annotator submission preflight uses it as well. A rejected note
requires investigation while identifiers remain blinded. Preserve the original
failed submission, obtain a separately versioned correction under the frozen
correction rules if appropriate, and document any actual unblinding as a protocol
deviation. Passing this textual check cannot establish that annotators were
unaware of treatment identity, independent, or truthful. The rubric, frozen
scores, experimental treatments, and inference are unchanged.

## Rendered-note justification integrity

A syntactically nonempty `notes` cell is not necessarily a justification.
A required explanation consisting solely of zero-width Unicode, standalone
combining/variation marks, Markdown formatting, empty-link metadata, or
punctuation could previously satisfy the endpoint-score or missing-dimension
note rule while displaying no explanatory content to a reviewer. The freezer
and independent retained-input verifier now require any nonempty note to
contain at least one rendered Unicode letter, number, or symbol after the same
CommonMark parsing used by the blinding audit. This is a deliberately narrow
presence check, **not** an automated assessment that a rationale is sound,
accurate, or genuinely human-authored. Benign Markdown explanations and
international-language text remain supported; original submitted bytes remain
in the raw archive. Empty optional notes for ordinary scores still remain
allowed. Invalid submissions must be corrected while blinded rather than
silently rewritten or backfilled. No frozen ratings or human results exist
because of this check, and the frozen rubric is unchanged.

## Coordinator responsibilities and limits

Keep the original submitted files under controlled, versioned storage when
practical, but the freeze no longer depends on those external paths for later
verification: it retains the exact rating bytes that were actually parsed.
Use a fresh output directory for a later freeze rather than replacing a snapshot.

These are **per-file snapshots**, not an atomic transaction across all inputs,
a filesystem lock, or proof that a submitted score came from an independent
human. Concurrent replacement during an individual capture is rejected, but
the tool does not prevent another process from editing a source after that
capture finishes. Later edits do not change the retained archive; supplying the
external files to the verifier is an optional additional cross-check against
that in-bundle source. The manifest attests to captured input bytes, not the
latest contents of a path.

## Offline regression coverage

`tests/test_human_eval_input_snapshots.py` simulates saves at deterministic
parsing and agreement boundaries. It checks that scores, allowed IDs, sizes,
and hashes stay consistent, including after packet replacement or deletion.
Compatibility cases cover LF/CRLF, quoted multiline Unicode notes, and rejection
of invalid UTF-8 or malformed quoted CSV cells before outputs are written. CSV
quoting remains lossless but is parsed strictly: unterminated quoted fields and
non-delimiter text after a closing quote are rejected rather than normalized.
All ratings in these tests are synthetic fixtures, not collected human
annotations or research results.

`tests/test_human_eval_submission_identity.py` covers combined raw submissions,
header-only inputs, an output-like raw filename, a rehashed combined archive,
fragmented aggregate coverage, valid multi-annotator normalized output,
optional external verification, and CLI rejection before publication. The
snapshot fixtures keep each synthetic annotator in a separate raw file without
weakening their byte-capture checks.


### Invisible-mark pseudonym gate

Human-evaluation rater IDs are not identities verified by this software; they
are coordinator-assigned pseudonyms. To prevent visually identical aliases from
inflating the independent-rater count, both original ratings and coordinator
attestations reject invisible Unicode combining format-like marks (including
U+034F and Unicode variation selectors) even though those marks are categorized
as `Mn` rather than `Cf`. The same check applies when calculating blinded
assignment coverage and two-rater agreement. Ordinary diacritics are retained;
existing NFC/casefold equivalence checks remain in effect. Submissions fail
before any frozen snapshot is published, and the original bytes are not rewritten.
This is a data-integrity safeguard, not verification of actual human identity or
independent scoring, and it does not alter frozen rubrics or produce ratings.

## Agreement-helper input-domain integrity

The public `build_agreement` and `quadratic_weighted_kappa` helpers now enforce the
same integer 1–5 rubric domain as the frozen CSV importer, including for
otherwise-unpaired ratings. Direct helper calls with out-of-range scores,
non-integer scores, or duplicate annotator/blind-item rows fail closed instead
of silently overwriting a submission or allowing Python's negative list
indexing to turn score 0 into rating category 5. Blank dimensions remain
missing and are never imputed. This is an offline software-integrity boundary:
the production CSV intake already checked these inputs; no human results,
rater independence, or agreement outcomes are asserted.
