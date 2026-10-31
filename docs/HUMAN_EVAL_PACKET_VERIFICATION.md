# Human-evaluation packet and blinding-key verification

This implementation note adds a coordinator-side integrity gate for the
deterministic human-evaluation packet. It does not amend the frozen annotation
rubric, assignment plan, automated analysis plan, or any experimental result.

## Why this gate exists

The blinded packet is useful only if its coordinator mapping still points to the
same frozen treatment reports that were randomized into the packet. A packet
hash alone cannot detect a blinding key that was accidentally edited, reordered
incorrectly, copied from another run, or paired with different trace/report
files.

The packet builder therefore records byte counts and SHA-256 fingerprints for
packet.jsonl, ratings_template.csv, and blinding_key.csv in manifest.json.
The verifier checks those fingerprints and independently checks the semantic
mapping back to the frozen task manifest, experiment traces, and Markdown
reports.

## When to run it

Run the verifier immediately after packet generation and before distributing
annotator-facing files:

    python scripts/verify_human_eval_packet.py

Run it again after the blinded rating freeze has passed
scripts/verify_human_eval_freeze.py and before treatment-level human analysis.

This verifier is coordinator-side because it reads blinding_key.csv. Do not run
it in an annotator environment and do not expose the key or treatment mapping to
annotators.

## Checks performed

The verifier fails closed unless:

- the packet manifest has the expected study, task-set, variant, and artifact
  fingerprint contract;
- the frozen task manifest fingerprint still matches packet generation;
- packet blind IDs are unique and cover exactly the frozen tasks;
- packet questions still match the frozen task questions;
- the coordinator key contains one mapping for every blind ID and exactly one
  D3, D6, P6, and P6V report for each frozen task;
- every key row agrees with its persisted trace identity, task-set ID, run ID,
  completion state, and question;
- every persisted Markdown report exactly matches the report text shown in the
  packet;
- the ratings template covers exactly the packet IDs and remains unscored.

The command prints a compact verification receipt. It does not read annotator
rating files and does not compute a treatment effect or human-validation result.

## Existing packets

Packets created before artifact fingerprints were added do not satisfy this
gate. Because real annotations are still pending, rebuild the deterministic
packet from the canonical preserved traces before it is distributed. Once
annotation starts, preserve that exact packet/key/manifest set and do not
silently regenerate it.

## Limits

This detects accidental provenance drift and inconsistent copies; it is not a
cryptographic signature or an external timestamp. An actor able to rewrite the
repository, all source artifacts, and the manifest can create a new internally
consistent history. Preserve Git history and canonical research artifacts as the
external provenance anchor.

Passing packet verification also does not substitute for the separate blinded
rating freeze, agreement checks, or a preregistered human-evaluation analysis
plan. No human-quality claim should be made until real ratings have been
collected and the relevant post-freeze gates have passed.

## Independent verification of execution IDs

The packet builder and the **independent coordinator-side verifier** both require
each persisted trace to contain a nonempty JSON string `trace.run_id` that
exactly matches the trace filename and the coordinator mapping. The verifier
must not reconstruct a missing run ID from a filename or silently trim one:
doing so would allow anonymous or renamed recovered material to appear to
retain its original execution identity after a manifest is rehashed.

The verifier additionally rejects reuse of one run ID by distinct
treatment/task cells, even when the coordinator CSV and per-source SHA-256
entries have been updated consistently. This mirrors the builder's
one-execution-per-cell rule without trusting a previous builder success as
sufficient evidence. Synthetic regression tests exercise both tampering
conditions. These checks do not authenticate the missing original archive:
independent historical pins and the source-bound handoff gate remain necessary.

## Complete trace-source inventory at independent verification

The coordinator-side verifier now enumerates the complete bounded treatment-trace
tree before verifying the selected key rows, rejects unexpected files,
directories, non-JSON backups, and symlinks, and requires that the selected
trace paths exactly equal the full inventory. It repeats the inventory after
rechecking captured artifact bytes and generations, so an extra trace added
during verification cannot be silently omitted from a successful receipt.

This closes a gap between the packet builder's complete-tree source selection
and independent verification of an already generated packet. A cryptographically
consistent key and source-fingerprint table alone would not prove that
unselected recovered traces were absent. This is an offline, read-only integrity
check. It cannot establish the historical authenticity of unavailable original
traces and reports or guarantee atomicity against hostile concurrent filesystem
mutation. Do not delete unexpected historical material to force acceptance:
quarantine the packet pending a documented source-custody review.

## Independent report-inode uniqueness check

The packet builder already rejects different run IDs that reference the same
underlying Markdown report through hard links. The coordinator-side packet
verifier now enforces the same condition independently. Otherwise two
run-scoped paths with identical report text and unchanged SHA-256 fingerprints
could pass verification even after one file was replaced by a hard link to
another run's report.

The verifier compares filesystem device/inode identities from the **same
captured file generations** used to verify report bytes and rechecks those
generations at the end of its verification window. It rejects any report
inode reused across different treatment/task cells. Byte-identical reports
stored in genuinely distinct files remain acceptable; equal text alone is
not evidence of reused execution. This guards local source aliasing only:
it does not authenticate missing historical report custody, establish
independent executions, or replace the original-archive handoff gate.
No treatments or human ratings are generated.

## Report-to-run binding

Before distributing a newly generated packet, the builder and independent
coordinator verifier require each Markdown report to resolve to
`outputs/<run_id>/research_report.md` for the originating trace, with that
trace stored as `outputs/experiment_traces/<variant>/<run_id>.json`.
The trace's recorded PDF path may resolve to the sibling Markdown report,
but it must not point to a different completed run, a symlink, or a
traversal path. The verifier checks the blinding key against the trace's
recorded report source in addition to comparing the report text and hashes.

This is a source-provenance guard, not evidence of human agreement or a
change to treatment outcomes. It does not regenerate published packets.

## Strict completion-state typing

Both packet construction and independent coordinator verification require the
persisted trace's `completed` field to be **JSON boolean `true`**. Python
truthiness is not a completion guarantee: strings such as `"false"` and
`"true"`, numeric `1`, and nonempty objects must all fail closed even when
other trace and packet provenance checks pass. Existing valid Boolean completion
traces are unaffected. This is a source-validity check only; no completed
experiment is rerun and no rating or treatment result is inferred.

## Trace symlink provenance guard

The packet builder rejects a symbolic-link trace root, trace file, or
treatment-directory component before emitting any blinded artifacts. The
independent coordinator verifier checks every segment of each recorded
repository-relative trace path **before** resolving it. This matters because
`Path.resolve()` follows symlinks: checking only the resolved file would
silently accept a replaced trace that points to another on-disk copy, even
with identical bytes and an unchanged coordinator manifest.

The check is about source identity and reproducibility, not human-evaluation
results. It neither regenerates reports nor changes the frozen assignment,
analysis, or treatment claims.

## Seed-bound blinding provenance

The coordinator verifier independently reconstructs the exact blind-ID assignment
from the manifest's integer `blind_seed`. It sorts the validated treatment,
task, and run identities in the same order as the packet builder, replays the
seeded shuffle, then compares that order with the coordinator blinding key. The
packet builder and verifier both require a true integer seed; booleans, floats,
and numeric strings are rejected rather than coerced into misleading manifest
provenance.

It also requires all three artifacts—the coordinator key, blinded packet, and
blank ratings template—to preserve the builder's sequential `H001`, `H002`,
... row ordering. Changed seeds, manually rearranged rows, and consistent blind-ID
renamings are rejected even if file fingerprints have been updated.

This is deterministic provenance checking, not a new measurement, an annotation,
or a signature against someone who can forge every archived input. Preserve
independent Git history and the frozen research-artifact fingerprints.

## Unambiguous JSON provenance

Packet construction and coordinator verification reject duplicate JSON object
keys at every nesting level in the frozen task manifest, experiment traces,
packet manifest, and blinded packet records. JSON escape-equivalent names are
decoded before comparison, so keys such as `"completed"` and
`"\\u0063ompleted"` are treated as duplicates.

The packet manifest is also a closed schema. The verifier rejects unknown
top-level fields, unknown artifact-table entries, and any change to the
coordinator-only blinding notice. This prevents injected or misleading metadata
from receiving a verification pass merely because all known fields still agree.

This fail-closed rule prevents Python's default last-value-wins decoding from
silently accepting contradictory provenance such as both `"completed": false`
and `"completed": true`. Reusing the same member name in separate objects is
still valid. This check changes neither treatment outputs nor human ratings; it
only rejects ambiguous source and packet artifacts.

## Exact source-byte binding

The packet manifest records byte counts and SHA-256 fingerprints for every
originating experiment trace and Markdown report, indexed by sequential blind
ID without embedding treatment labels in the fingerprint table. The
coordinator verifier derives each source path from the separate blinding key
and requires the current bytes to match the packet-generation snapshot.

This catches provenance drift that semantic checks intentionally normalize,
including whitespace-only trace edits and trailing-newline changes to reports.
Packets created before source fingerprints were recorded do not satisfy this
gate. Because real annotation remains pending, rebuild them from the preserved
canonical sources before distribution rather than editing a published manifest.
This adds no treatment run, evaluator output, rating, or research conclusion.

## Invisible combining marks and blinding integrity

The annotator-facing content audit normalizes Unicode and rejects coordinator
markers in source text, rendered Markdown, and repeatedly decoded link metadata.
Some visually invisible combining marks are **not** Unicode format characters
(`Cf`): a Combining Grapheme Joiner or variation selector inserted inside
`D3` or `P6V` previously obscured the identifier from literal marker detection.

The audit now removes U+034F, Mongolian free variation selectors, and the
basic/supplementary Unicode variation-selector ranges **for matching only**.
It does not rewrite the underlying question, report, or archived source bytes.
Ordinary combining diacritics remain significant, and a passing audit still
cannot guarantee that humans will never infer treatment identity from style.
All four experimental conditions, frozen measurements, and the human rubric
remain unchanged; genuine independent ratings are still outstanding.

## Production verification must check original treatment/evaluator identities

The standalone packet verifier previously accepted a locally coherent frozen
task manifest and 40 run mappings even when a coordinator had consistently
rewritten task questions or substituted different treatment executions.
The packet builder's production CLI already checked the historical source
fingerprints, but rebuilding is forbidden after genuine annotation starts;
independent verification of an existing packet must enforce those anchors too.

The `python -m scripts.verify_human_eval_packet` CLI now **requires** both:
the exact task-manifest SHA-256 recorded in the original treatment-run source
revision, and exact per-cell run IDs from the SHA-256-pinned original post-hoc
evaluator CSV. A changed task list, substituted run ID, missing evaluator CSV,
or altered evaluator export fails before a success receipt can be emitted.
The evaluator CSV is captured and rechecked over the complete packet
verification window, alongside all other evidence. The successful receipt
explicitly records that both source pins were checked.

For synthetic offline unit tests only, the direct Python API retains
`require_original_sources=False` by default; this intentionally **does not
claim historical anchoring**. Genuine packets checked through the Python API
must pass `require_original_sources=True`. An API receipt also expressly
states that historical trace/report authenticity remains unverified even when
source-identity pins pass. The original archived traces and reports still need
independent authentication; this check neither reconstructs them nor certifies
actual human blinding or collected ratings.

Do not edit the pinned CSV or task manifest, replace treatment runs, or
regenerate a packet merely to make this check pass. Preserve problematic
material and halt human-evaluation handoff pending original-source recovery.
