# Human-evaluation analysis output verification

This implementation note covers the publication boundary for
`scripts/analyze_human_eval.py`. It does not change the frozen human-evaluation
rubric, assignment plan, treatment-level estimands, bootstrap settings, or the
automated confirmatory analysis.

## Literal data labels in the manuscript view

The canonical analysis JSON retains the exact task identifiers and pseudonymous
annotator IDs. Those data-derived labels can contain Markdown links, image
syntax, code delimiters, or raw HTML-like text even when the earlier rating
inputs satisfy the frozen rubric. In a GitHub-rendered `analysis.md`, ordinary
table delimiter escaping alone would leave such material active or visually
misleading. The deterministic renderer now HTML-escapes markup and escapes
inline Markdown syntax **only when displaying variable labels**, while retaining
ordinary Unicode text, the original canonical JSON values, and all computed
statistics. Regression tests exercise active-link, tracking-image, raw-HTML,
formatting, and multilingual controls through a Markdown parser.

This is publication-display integrity, not proof of annotator independence,
protection against every downstream renderer, or a scientific-data change.
Older result bundles must still be verified using their generating commit.

## Why this gate exists

The human-validation analysis has two manuscript-facing representations:
`analysis.json` is canonical machine-readable output and `analysis.md` is a
deterministic view of that JSON. Without an explicit publication check, a manual
edit, partial copy, or later source-code drift could make a result bundle look
valid while no longer representing the analysis that produced it.

The analysis command now writes a third file, `analysis_manifest.json`, last.
That manifest SHA-256-binds:

- `analysis.json`;
- `analysis.md`;
- `scripts/human_eval_analysis_core.py`;
- `scripts/analyze_human_eval.py`;
- `scripts/verify_human_eval_analysis_outputs.py`;
- `scripts/verify_human_eval_freeze.py`, which validates the blinded ratings
  snapshot consumed by the analysis;
- `scripts/build_human_eval_packet.py`, whose parsing and identity helpers are
  consumed by the analysis core and packet verifier;
- `scripts/verify_human_eval_packet.py`, which validates the packet and
  coordinator mapping inputs before unblinding; and
- `scripts/freeze_human_eval_ratings.py`, which owns the frozen governing-input
  paths and SHA-256 anchors consumed by the verifier.

The manifest schema is closed at the root. Artifact and implementation
fingerprints are also closed records containing only their canonical path, byte
count, and SHA-256 digest. The integrity note must equal the generator-owned
statement exactly. Verification therefore rejects undeclared result claims,
extra provenance metadata, and rewritten notes even when every recorded digest
still matches. These checks authenticate the bundle structure; they do not turn
human-validation artifacts into confirmatory evidence.

The command first verifies the persisted bundle, then independently recomputes
the complete canonical payload from the rating inputs and governing artifacts
before printing its success message. This second pass covers variant summaries,
paired effects and confidence intervals, missingness, agreement, and provenance;
it does not trust the persisted result values or their self-reported hashes.
The verifier first opens and validates every manifest-bound implementation
source through a retained non-symlink descriptor, then captures the pinned
environment files and frozen governing documents designated by that validated
implementation. All provenance opens are nonblocking. Manifest checks consume
the captured bytes, and the descriptors, file identities, contents, and
pathname bindings are checked again after independent recomputation. A
byte-identical source-file replacement can therefore not coexist with a
successful receipt merely because its digest is unchanged, and a substituted
FIFO is rejected rather than blocking verification.
The verifier captures the canonical JSON, deterministic Markdown, and output
manifest against their verified digests before recomputation, then rereads all
three afterward. If any byte stream differs at that final reread, verification
fails instead of issuing a receipt for the older revision.

Before reserving the create-only output directory, publication also validates
the human-analysis identity and captures every implementation fingerprint needed
by the manifest. Identity, serialization/rendering, plan-provenance, and source-
provenance failures detected during this preflight therefore leave the requested
version path untouched and available for a corrected retry. The canonical
payload directly records the frozen protocol, assignment-plan, and
annotator-guide fingerprints and logical paths; the standalone verifier checks
those entries against the generating checkout and its literal freeze anchors,
and verifies the anchor implementation itself before trusting those constants.
The final directory creation remains exclusive, so a concurrent publisher is
never adopted after preflight. Any missing output-parent hierarchy is created
one directory at a time through retained descriptors, synchronizing each new
directory and its parent before staging begins. Before verification, publication
flushes and `fsync`s all three artifacts plus the candidate and staging
directories. After the atomic no-replace rename, it `fsync`s both the source and
destination directories before reporting success. This makes the completed
publication crash-durable rather than merely atomically visible. Independent
recomputation still runs before the rename; a failure at that stage preserves
the create-only staging artifacts for inspection.

## Independent verification

From the repository revision that produced an analysis bundle, run:

```bash
python -m scripts.verify_human_eval_analysis_outputs \
  --output-root outputs/human_eval/analysis-v1
```

By default, independent verification reads the exact CSV byte streams retained
under `outputs/human_eval/frozen-v1/raw_rating_inputs/`. Explicit rating paths
may instead be supplied as positional arguments when validating a not-yet-
archived production invocation. The verifier reuses the frozen packet, protocol,
assignment plan, annotator guide, analysis plan, task manifest, and treatment
mapping gates; it makes no model/API calls and reruns no treatments.

Verification fails closed when:

- canonical JSON or Markdown is missing, malformed, or a symbolic link;
- canonical JSON or the provenance manifest contains duplicate object member names
  (including escape-equivalent keys), even when its recorded hash is consistent;
- Markdown is not byte-for-byte the deterministic rendering of canonical JSON;
- either output no longer matches its recorded byte count or SHA-256;
- the manifest contains undeclared root claims, artifact metadata, or
  implementation metadata, or its integrity note is not canonical;
- the current analysis core or renderer source bytes do not match the generating
  implementation recorded in the manifest;
- the current publication verifier source bytes do not match the verification
  implementation recorded in the manifest;
- the current blinded-freeze verifier, packet builder, or packet verifier source
  bytes do not match the upstream input-validation implementations recorded in
  the manifest;
- result identity fields attempt to relabel human validation as automated
  confirmatory analysis, claim generated human ratings, claim treatment reruns,
  or add undeclared human-validation hypothesis tests.
- a self-consistently rehashed canonical result changes the frozen report-score
  aggregation rule, bootstrap seed, or 20,000-draw bootstrap configuration;
- the canonical result does not affirm that verification and analysis consumed
  the same captured input bytes;
- the recorded analysis-plan byte count or SHA-256 does not match the literal
  preregistered plan anchored by the generating implementation.
- the recorded protocol, assignment-plan, or annotator-guide path, byte count,
  or SHA-256 does not match the frozen governing document and its literal
  implementation anchor;
- any canonical result value differs from a type-strict, independently
  recomputed payload, even when an editor has regenerated Markdown and updated
  every output hash consistently.
- canonical JSON, Markdown, or the output manifest differs from its captured
  bytes when reread after independent recomputation.
- any bound implementation source, environment pin, analysis plan, protocol,
  assignment plan, or annotator guide changes content, file identity, or
  pathname binding during verification or independent recomputation.

A successful receipt is a publication-integrity check, not a new scientific
result.

## Archive and checkout rule

Keep the analysis bundle together with the exact repository commit that produced
it. Because implementation hashes are checked, verifying an old bundle from a
newer checkout may intentionally fail after analysis code changes. Check out the
recorded generating commit and rerun the verifier instead of rewriting the old
manifest.

`analysis_manifest.json` is written last, so a missing manifest means the bundle
must not be treated as successfully published. Deterministic identity and
provenance failures happen before the output path is reserved. Once writing has
started, the output directory remains create-only; interrupted I/O attempts are
preserved for inspection and a new versioned output path should be used for a
retry.

## Limits

This gate detects output/renderer drift, binds the analysis and verification
implementation sources, and recomputes descriptive human-validation outputs
from retained inputs. Its retained output and provenance descriptors detect
persistent mutation or replacement visible at the final observation, but they
are not filesystem locks: a transient replacement restored to the original
inode before the final observation is outside this guarantee, and the check
makes no claim about changes after verification returns. It does not prove that
annotators were independent humans, replace the earlier
packet/freeze verification gates, or make multiple filesystem writes an atomic
transaction. The upstream human-analysis code still verifies and snapshots the
blinded and coordinator artifacts before treatment-level analysis. Real blinded
ratings remain required before any human-quality finding can be reported.

## Producer-side source fingerprint capture

The analysis publisher now uses a bounded, descriptor-bound, path/parent-
verified snapshot when computing the implementation and Python-environment
file hashes recorded in `analysis_manifest.json`. A preliminary file-type
and 16 MiB size check prevents normal oversized inputs from being read; the
shared captured-byte reader also detects symlink substitution, concurrent
append/truncation or rewrite, and source-path replacement. This closes the
previous check-then-`read_bytes()` window at the producer's fingerprint
boundary. The independent output verifier continues to hold and recheck its
own provenance descriptors through recomputation. These are observational
filesystem checks, not a global lock or historical archive custody proof.

All synthetic tests use temporary source files; no treatments, automated
support evaluations, or human scores are produced. Pilot results, frozen
automated confirmatory inference, exploratory analyses, and pending human
validation remain separate.

## Rehashed paired-effect arithmetic checks

The standalone bundle verifier now independently checks the **internal**
arithmetic of each published human paired-contrast block before accepting a
manifest whose JSON/Markdown and SHA-256 values agree. For the frozen task IDs
declared as included, task-difference keys must match exactly; effects must
lie on the achievable half-point lattice within [-4, 4]; positive, negative,
and tied task counts must agree with the differences; and their mean and
median must match the reported values. The two arm means must have the same
paired mean difference. A zero-pair cell cannot claim non-null inference
statistics. These checks also run before create-only publication.

Seven synthetic rehashed tampering cases and a no-pair case exercise this
cross-field check. This is a **published-data consistency audit only**: it
does not establish that source ratings were authentic or independently provided,
or that task-level effects reflect genuine observations. The existing
`verify_bundle_against_inputs` continues to independently recompute the full
payload (including bootstrap) from the retained frozen ratings; the ordinary
`verify_bundle` receipt explicitly reports that recomputation as *not* done.
No human ratings were generated or evaluated for this check.


## Standardized-effect and bootstrap-support integrity

The standalone result-bundle verifier also recomputes the **paired standardized
mean difference (\\(d_z\\))** directly from the published per-task effects,
using their sample standard deviation. A one-task sample or constant task
differences must report a null `paired_dz`; an invented finite estimate,
wrong sign, or nonnumeric standardized effect fails verification even if the
bundle's hashes and Markdown are regenerated. For nonconstant task differences,
the recorded value must agree with the calculated standardized effect within a
strict numerical tolerance.

Each published bootstrap confidence interval must consist of two ordered finite
numeric endpoints inside the range of the observed paired task differences.
The bound is mathematical: resampling paired task differences cannot yield a
mean smaller than the smallest observed difference or larger than the largest.
For one pair or constant paired differences, the confidence interval is
necessarily degenerate.

The verifier now also **replays the frozen 20,000-draw paired bootstrap** from
the published per-task effects, lexically sorted by frozen task identity and
using the exact per-contrast/per-dimension seed offset. It independently
implements the seeded resampling and linear percentile interpolation rather
than trusting a claimed interval inside the mathematically possible range.
This rejects self-consistently rehashed but numerically fabricated confidence
intervals even without an archived ratings directory. A small bounded cache
makes repeated verification of the same ten-or-fewer task values practical.
The stronger source-bound verifier still recomputes the entire payload from
independently verified frozen ratings; neither path authenticates the original
human participants from summary values alone. All added cases are synthetic.
This produces no human annotations, experimental outcomes, or new statistical
procedures, and does not promote pilot or exploratory findings to confirmatory
or human-validation results.
