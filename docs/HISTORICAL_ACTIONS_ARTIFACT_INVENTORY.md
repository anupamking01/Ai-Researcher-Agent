# Historical GitHub Actions artifact availability inventory

**Purpose:** Identify which original VERA run artifacts are still *listed* by GitHub Actions without downloading data, replacing missing reports, or rerunning any treatment/evaluator. This is a recovery-triage diagnostic, **not** an authenticity check or a human-evaluation result.

Run:

    python -m scripts.audit_historical_workflow_artifacts

The tool makes read-only GitHub REST requests. Public requests work without authentication subject to rate limits; set an appropriately scoped environment variable named GITHUB_TOKEN (or GH_TOKEN) when needed. Never place a token on the command line or in a published research receipt. The command prints a JSON inventory; it does not create files or use a browser, and its offline unit tests mock the API.

## Historical anchors

The tool validates both identity and workflow conclusion **before** examining any artifact listing:

| Role | Run | Historical head SHA | Workflow conclusion | Exact expected artifact |
| --- | --- | --- | --- | --- |
| 40 treatment executions | 34620917346 | c3c15e46a8eec3a8bbc24c968eedc0548172a897 | failure | budget-main-study-34620917346 |
| Evaluator-only recovery | 34783525480 | 8733ce492abc74e7b2966ed22ce08d3fddec43ca | success | budget-main-study-recovered-34783525480 |
| Canonical analysis | 36070798723 | 06c6a9ab0b1d01257e8985fbb09c999cef115779 | success | canonical-main-study-analysis-36070798723 |

The original workflow concluded *failure* because the common evaluator did not finish in that run; it is not a claim that any of the original 40 treatment cells failed. The original and evaluator-recovery workflow definitions used **30-day artifact retention**, while the canonical-analysis snapshot used **90 days**. Version-controlled canonical CSVs and verified analysis outputs do not replace the missing 40 original report/trace sources.

## Checks and interpretation

The inventory pins the historical run ID, workflow name, source SHA, completion status, and conclusion. It walks bounded artifact-listing pages, checks total-count consistency, rejects duplicate artifact IDs or cross-run associations, and counts only the **exact expected artifact name**. A different artifact on the same run cannot stand in for original evidence.

The output distinguishes **named artifact absent**, **named artifact expired**, and **named nonexpired artifact listed**. An API error, bad metadata, or incomplete pagination is an explicit failure, never silently reported as absent. Nonexpired means the GitHub API lists an unexpired artifact; it does **not** prove that its ZIP can actually be downloaded, unpacked, matched to the intended 40 cells, or authenticated against independently retained archival fingerprints.

As observed on **2026-10-28**, the two original/recovery runs returned no artifacts in their run-scoped listings. The canonical-analysis run still listed artifact **10837878458**, expiry **2026-12-23T23:03:46Z**. These are point-in-time API observations; the inventory command must be rerun for current status. Nothing here proves an original archive was destroyed or rules out authorized institutional/offline backups. Do **not** treat a newly generated pin for recovered material as an independently retained historical fingerprint.

Even if both original artifacts become listed, the JSON still sets historical_evidence_authenticated and human_evaluation_ready to false. Recovery must satisfy the independent trace/report source-custody checks and the blinded packet/handoff gates in HUMAN_EVAL_ARCHIVE_RECOVERY.md. No pilot, confirmatory, exploratory, or pending human-validation conclusion is changed by this read-only availability audit.

The tool performs **two complete run-scoped artifact-listing scans** before
reporting any availability status, including an absent expected artifact. It
reconciles artifact IDs and custody-relevant fields (name, expiry, timestamps,
ZIP size/digest/download endpoint, and historical workflow source identity)
across both scans. A same-count ID swap, newly listed artifact, or metadata
change fails closed instead of becoming a false missing/present assertion.
Pagination order and volatile download counts are intentionally ignored.
Each successful run receipt identifies the two-pass reconciliation. This is
only a consistency check between two API observations, **not** an atomic
GitHub snapshot, proof of absence after the scan, ZIP verification, or an
independent historical fingerprint.

## Workflow identity across the inventory window

For each historical run, the audit now **re-reads execution metadata after
both artifact listings** and requires matching run ID, workflow name/path,
head SHA/branch, event, status, conclusion, attempt, start time and last-update
time. A workflow rerun or changed execution record during inspection cannot
produce a passing absence or availability receipt merely because both
artifact-listing pages happen to match. A boolean replacing an integer attempt
also fails. The receipt separately records two matching workflow snapshots
and the already-existing two-pass artifact reconciliation.

This remains a read-only, observational consistency check. It does not make
GitHub metadata atomic, authenticate historical report bytes, prevent later
changes, or establish independent custody. An unstable listing is an inventory
error, not evidence of destroyed source archives. No treatment or evaluator is
rerun.


## ZIP metadata and expiry checks (availability, not custody)

For each listed artifact, the inventory checks that the GitHub-provided ZIP
size is a positive integer, that its archive download endpoint points to
the expected artifact in this repository, and that its expiry is an unambiguous
UTC timestamp. The output records zip_size_in_bytes, archive_download_url,
and github_zip_digest (when GitHub supplies a well-formed sha256 value),
so an operator can identify the specific ZIP advertised at inventory time.
This SHA-256 is GitHub-generated ZIP metadata, NOT an independently retained
file-byte fingerprint for the original 40 traces or Markdown reports.
A missing GitHub digest is represented as null, not silently synthesized.

All three run listings are evaluated against one checked_at_utc timestamp.
An artifact with expired=false but expires_at at or before that instant is
reported as named_artifact_listed_elapsed_expiry and cannot count as a
nonexpired candidate; expired=true remains expired even with a future
deadline. Ambiguous timestamps, zero-size ZIPs, malformed digest metadata,
or an unrelated ZIP endpoint fail closed. No listed metadata proves download
success, ZIP content validity, independent historical custody, or human
evaluation readiness.


## Historical workflow-source and creation-window concordance

A listed ZIP also has to be attributed to **the original first attempt** of
the pinned push workflow on branch research-paper-eval-2027, at the exact
workflow source path. The audit checks the artifact's embedded workflow-run
SHA, run ID, stable repository identity and head-repository identity against
the run's pinned metadata. Missing source associations fail closed. It also
checks that the artifact's GitHub-reported creation time falls between the
workflow's reported start and last-update timestamps, that update time is not before
creation, and that expiration follows creation. Malformed or ambiguous time
metadata is rejected. The receipt exposes run start/last-update and artifact
creation/update times for reviewer inspection.

This blocks a same-name artifact associated with a different branch, commit,
repository, or later workflow attempt from masquerading as the historical
candidate. These are **GitHub-reported metadata consistency checks only**:
timestamps and association fields are not independent cryptographic
attestations. They do not prove ZIP byte identity, that an archived report is
genuine, or that the original source contents survive. The canonical-analysis
ZIP remains a secondary analysis artifact, not a substitute for the missing
treatment and evaluator-recovery archives.

The GitHub run API exposes last-update time, not a separately authenticated
completion timestamp. An update after execution could broaden that interval;
the audit cannot prove the precise moment a job finished or establish custody
from these timestamps alone.


## Offline preflight for a recovered candidate ZIP (not authentication)

If a ZIP is later recovered from an authorized original or offline backup,
inspect it **before any extraction**:

    python -m scripts.preflight_recovered_artifact_zip <candidate.zip>

An optional previously retained **independent ZIP-byte SHA-256** can be checked
with `--expected-archive-sha256 <lowercase-64-hex>`. Never derive this
historical pin from the ZIP being evaluated. This offline, read-only verifier
rejects path traversal, nonportable/colliding names, links, encrypted entries,
unsupported compression methods, oversized members, excessive expansion, and
invalid ZIP/CRC content. Name safety is checked both before and after Unicode
NFKC/casefold normalization: compatibility characters must not introduce dot
traversal segments, new path separators, backslashes, or drive-like prefixes.
It also rejects Windows/NTFS-unsafe component names (reserved device names,
trailing periods/spaces, alternate-data-stream colons, and forbidden filesystem
characters) after normalization. These otherwise create aliases, inaccessible
paths, or streams on a different platform despite appearing valid in a ZIP.
Names merely resembling device names remain valid. These checks reduce
cross-platform recovery hazards, but do not authorize extraction or establish
evidence authenticity. Harmless Unicode filenames remain supported, and original member spellings are
preserved in the current-observation receipt. Empty directory entries are also read through the
ZIP decoder, so their local headers, compressed streams, and CRCs cannot evade
verification just because directory names are omitted from the file inventory.
The decoder validates the declared zero-length directory contents; this
preflight is not a substitute for independent historical provenance checks. To avoid an archive with thousands of tiny central-directory records
exhausting memory before Python's eager `zipfile.ZipFile` parser returns,
the verifier now scans the bounded central-directory headers **before**
constructing `ZipFile`. It enforces the declared and actual record counts,
an 8 MiB central-directory cap, consistent offsets, and a canonical single-disk,
non-ZIP64 ZIP layout. Ordinary ZIP comments remain supported; ambiguous
trailers, self-extracting prefixes, inconsistent member-count claims, and
unsupported central-directory extensions fail closed. This is an intentional
conservative restriction for candidate GitHub Actions artifact ZIPs, not a
general-purpose ZIP compatibility promise.

The preflight cross-checks each member's local ZIP header against the
central-directory record: compression method and flags must match, and local
CRC/compressed/uncompressed sizes must agree unless the streaming flag permits
zero placeholders. For streaming entries, it additionally reads and checks the
**actual on-disk data descriptor** (CRC and both sizes, with or without the
optional signature) against central metadata. It rejects missing or
contradictory descriptors even if Python's ZIP decoder could read the payload.
Local member regions, including any data descriptors, must not overlap.
They must also cover **every byte from the beginning of the ZIP to the
central directory**: unindexed prefixes or gaps between/after members are
rejected even when Python can decode every advertised file. Otherwise bytes
omitted from the per-file fingerprint receipt could be concealed in the
archive and later misrepresented as part of an authenticated research bundle.
Ordinary ZIP comments after the end-of-central-directory header remain
supported. This is conservative structural triage, not historical custody proof.
These checks prevent ambiguous ZIP byte interpretations; they are not
independent evidence of original experimental provenance. Ordinary signed
and unsigned non-ZIP64 streaming descriptors remain supported.


It bounds ZIP input size, entry count, and total
uncompressed bytes; reads members in chunks; checks for changes during its
inspection; and never extracts or rewrites candidate evidence. It produces
an observed-current ZIP SHA-256 and per-file SHA-256 inventory on stdout.

A structurally valid ZIP is **not** evidence that its report contents came from
the original experiments. A newly calculated hash is not an independently
retained provenance anchor, and an independently retained ZIP hash is not
a substitute for the original trace/report and integrated human-evaluation
handoff checks documented in HUMAN_EVAL_ARCHIVE_RECOVERY.md.
The command does not regenerate reports, evaluator results, or human ratings.

## Newly recovered contemporaneous upload and download fingerprints (2026-10-30)

Although the two original run-scoped artifact listings are empty, their **GitHub
Actions job logs remain readable**. They contain historical upload-artifact v4
ZIP digests and artifact IDs, including a later successful download in the
evaluator-recovery job. These are useful **GitHub-service-reported, contemporaneous
ZIP-byte identifiers**, *not* independently retained out-of-band manifest hashes,
original report or trace fingerprints, proof of present-day downloadability,
or an independent signed archival attestation.

| Evidence | Run / job ID | Artifact ID | ZIP bytes | GitHub-logged ZIP SHA-256 |
| --- | --- | --- | ---: | --- |
| Original treatment upload (2026-09-11) | 34620917346 / 103334373932 | 10275100801 | 608355 | `878205ff42267b85d71f478520a4a3ebe520915f22ae2d2307e930fa39545400` |
| Evaluator recovery upload (2026-09-13) | 34783525480 / 103794737655 | 10324954205 | 618586 | `c357b068fa4c0b7e86f7c56cd1d3e346f6922106d7bde644db92feb7f8fc84cc` |

The original job logged ZIP upload completion with the original digest, size,
and artifact ID. Two days later the evaluator-only recovery job logged
downloading that **same artifact ID, size, and expected digest**, then a
computed downloaded SHA-256 equal to the original log and a successful
download, before uploading its own separate ZIP. This confirms log-level
continuity of the original ZIP *within GitHub Actions*. It does not mean the
original ZIP remains available, or that all its internal reports/traces are
authentic or independently archived.

To rerun the **offline** correspondence audit, securely save the existing
original **job 103334373932** and recovery **job 103794737655** text logs
from their GitHub Actions pages (do not commit full logs, which contain
research text and external URLs), then run:

```bash
python -m scripts.audit_historical_artifact_job_logs \
  --original-job-log <original-job.log> \
  --recovery-job-log <recovery-job.log>
```

The auditor accepts at most 2 MiB per log, reads without following symlinks,
requires the named upload/download action boundaries and unique ordered event
lines, and compares all artifact IDs, byte sizes, ZIP digests, run-scoped URLs
and the cross-run original download digest against the recorded metadata.
An invalid, ambiguous or modified transcript fails closed. The audit also
parses full-precision UTC event timestamps, rejects impossible calendar dates
or event-time reversals even when log *line order* is plausible, and requires
original upload to precede the recovery download and recovery download to
precede the evaluator-recovery ZIP upload. It permits equal timestamps when
the logger cannot distinguish two adjacent events; log line order still must
be valid. These checks establish **internal recorded chronology only**:
caller-supplied GitHub logs are not independently authenticated, clock
metadata is not a cryptographic custody attestation, and no ZIP or report
bytes are recovered by this audit. Offline tests
use only synthetic log excerpts. These supplied logs are not cryptographically
authenticated as genuine GitHub output by the offline parser; retaining them
separately along with signed or independently archived source bytes is still
necessary for historical custody. The Git commit records **the discovery of
the two historical GitHub-generated ZIP fingerprints** for recovery triage,
not an independent historical research-manifest checksum.

## Automated same-provider ZIP correspondence (without claiming independent custody)

For an **authorized copy of the exact original GitHub artifact ZIP** (not a
freshly re-zipped folder or regenerated report), run the existing read-only,
bounded ZIP structural preflight with the historical GitHub job-log role:

```bash
python -m scripts.preflight_recovered_artifact_zip <original-candidate.zip> \
  --github-job-log-artifact original_treatment
```

For an authorized copy of the distinct evaluator-recovery ZIP, select
`--github-job-log-artifact evaluator_recovery` instead. The selector binds the
comparison to the immutable role, run ID, job ID, artifact ID, ZIP byte count,
and SHA-256 **recorded in the contemporaneous GitHub job logs**. A byte-size or
SHA-256 mismatch fails the preflight; otherwise the normal comprehensive ZIP
structure and per-member checks must still pass. No extraction, treatment
generation, model inference, or human scoring occurs. A successful receipt
reports `github_job_log_zip_correspondence` separately from
`expected_archive_sha256_matched`. It explicitly labels the correspondence
`github_actions_same_provider_job_log`, with
`independent_archive_pin: false` and
`historical_evidence_authenticated: false`.

The existing `--expected-archive-sha256` remains **reserved exclusively for
a previously, independently retained ZIP-byte pin**; do not copy the
GitHub-logged digest into that flag. Both checks may be supplied if genuinely
independent evidence also exists, and their receipt fields remain distinct.
The software cannot authenticate the asserted source of an operator-supplied
independent pin. Matching the GitHub-logged ZIP digest verifies ZIP-byte
correspondence to a *same-provider record*, **not** original trace/report
historical authenticity, archival custody, or human-evaluation readiness.
Those separate gates in `HUMAN_EVAL_ARCHIVE_RECOVERY.md` remain mandatory.

## Recovered-ZIP 40-run source inventory before extraction

A ZIP matching a historical GitHub upload fingerprint can still be an
**uninterpreted archive**: the ordinary structural preflight does not check
that its member paths are exactly the treatment/report sources measured by
the frozen automated evaluator. The following separate, offline, read-only
triage check enforces that distinction **without extracting an untrusted ZIP**:

```bash
python -m scripts.audit_recovered_artifact_treatment_matrix <authorized-candidate.zip> \
  --artifact-role original_treatment
```

Use `--artifact-role evaluator_recovery` only for the separately recovered
and byte-matching evaluator ZIP. The role is mandatory: both size and SHA-256
must first agree with the corresponding **GitHub-service-reported** historical
job-log ZIP, and the complete conservative structural/CRC preflight must pass.
An optional `--expected-archive-sha256` may be supplied **only** when a
historical ZIP-byte pin was independently retained before recovery; never
reuse the GitHub job-log digest as an allegedly independent pin.

The audit reads `outputs/posthoc_support_runs.csv` from the checkout and
requires its **exact published file-byte SHA-256** before using any run IDs.
It checks the full frozen 40-cell D3/D6/P6/P6V task matrix and the uniqueness
of all execution IDs, then requires **40 exact treatment trace member paths**
(`experiment_traces/<variant>/<run_id>.json`) and the **40 corresponding
Markdown report paths** (`<run_id>/research_report.md`). Since ZIP packaging
may omit the shared `outputs/` parent, either a single root-level layout or
a single `outputs/`-prefixed layout is accepted, never mixed. Unexpected
trace or Markdown-report members anywhere else in the archive are rejected
rather than silently excluded from the proposed human-evaluation corpus. The
published evaluator CSV is recaptured after ZIP verification, and changed
bytes or a replaced file generation invalidate the result.

The verifier now also emits an `observed_source_content_manifest`, with one
deterministically ordered entry per frozen (treatment, task ID, run ID) cell.
Each entry binds the preflight-verified **decompressed** SHA-256 and byte size
of that cell's trace and Markdown report to the exact published evaluator
identity. Its compact, sorted-key UTF-8 JSON encoding is summarized by
`observed_source_content_manifest_sha256` (schema v1). This content digest
is stable when source bytes are unchanged but ZIP compression, member ordering,
the optional `outputs/` wrapper, or unrelated auxiliary files differ. Unlike
a raw ZIP hash, it supports meaningful run-by-run comparisons between
authorized original/recovery backups without extracting report text. One
modified report or trace changes the corresponding cell hash and aggregate.
It is **computed at inspection time**, is **not** a historical pin, and cannot
authenticate the original report, a GitHub artifact, or any recovery source.
Keep the complete receipt if later comparing two candidate archives; never
treat matching present-day hashes as proof of independently retained custody.

A caller-provided independent fingerprint is recorded as a **claim**; the tool cannot
verify that the pin was independently retained. The receipt therefore keeps
`independent_archive_custody_verified` false even when that supplied hash matches.

The successful receipt reports **member-path completeness and frozen
execution-ID correspondence only**. It does not read or validate JSON trace
semantics, check the actual Markdown report contents against source provenance,
authenticate the original run's independent archival custody, prove the ZIP
was recoverable on GitHub at inspection time, or authorize sending reports to
annotators. The same-provider digest, path list, and observed-current member
hashes are explicitly **not historical independent source fingerprints**.
Original trace/report content validation, independently retained archival
manifests, coordinator blinding packet checks, and two independent real human
annotators remain separate mandatory research gates. No new pilot,
confirmatory, exploratory, or human-validation outcome is inferred.


## Comparing original and evaluator-recovery treatment bytes

A source-completeness receipt from one archive cannot prove that evaluator-only
recovery preserved the **same** reports and traces as the original treatment
run. When authorized, unchanged copies of **both** historical GitHub artifact
ZIPs become available, run the new read-only concordance check:

```bash
python -m scripts.compare_recovered_artifact_treatment_sources \
  --original-zip <original-treatment.zip> \
  --recovery-zip <evaluator-recovery.zip>
```

The command independently applies the bounded ZIP preflight and the frozen
40-cell run-identity inventory to **each** archive using its distinct
historically logged GitHub artifact ID, ZIP size, and SHA-256. It then requires
all 40 pairs of **decompressed** trace/report bytes (their SHA-256 hashes and
sizes) to agree, independent of ZIP compression, member order, optional
`outputs/` prefix, or unrelated evaluator bookkeeping. A changed report or
trace, missing source, incorrect historical ZIP, or reuse of the same archive
for both roles fails closed. It never extracts archives, reruns treatments,
resumes evaluation, or manufactures human ratings.

Optional `--original-expected-archive-sha256` and
`--recovery-expected-archive-sha256` arguments allow separately retained
**independent historical** byte pins to be checked; do not supply hashes
computed from the candidate ZIPs as though they were archived provenance.
The success receipt names both GitHub-log correspondences, the deterministic
40-cell content digest, and the equality result, but deliberately keeps
`independent_archive_custody_verified`, `historical_evidence_authenticated`,
and `human_evaluation_ready` false. Even a verified original-to-recovery
byte match from two GitHub-sourced records is **not** an independent custody
attestation, source-semantics audit, or permission to start blinded annotation.
The separate historical trace/report, coordinator, and human-evaluation gates
still apply. All unit tests for this comparison use synthetic sources only.


## Cross-archive comparison-window source custody

The recovered-source concordance command snapshots the two role-specific ZIPs
and the fingerprint-pinned evaluator CSV **before** either archive audit, then
recaptures all three **after both audits**. Each ZIP snapshot uses no-follow
regular-file descriptors, records filesystem generation metadata (including
device/inode, size, mode, modification and change times), and hashes its bounded
byte stream. The initial ZIP digests must agree with the digests returned by
their respective structural audits. Same-byte file replacement, altered ZIP
bytes, a moved pathname, or replacement of the evaluator CSV anywhere across
the combined inspection window invalidates the comparison receipt.

This closes the interval between two independently passing per-archive audits:
a previously audited original ZIP must not be swapped while the recovery ZIP is
being inspected, nor can a same-byte evaluator CSV replacement between scans
silently authorize a report-source concordance claim. These are present-day
read-consistency checks, **not** atomic filesystem snapshots, a defense against
post-receipt changes, historical ZIP authentication, or independent archival
custody proof. The required original trace/report authentication and human
evaluation handoff gates remain unchanged. Regression tests use synthetic
ZIPs and unchanged synthetic research outcomes only.


## Original-to-recovery evaluator-cache byte continuity (offline; not human validation)

The two-archive source comparator also now verifies that the evaluator-only
recovery **retained all 37 pre-existing cached evaluator JSON outputs
byte-for-byte**, and added exactly the three historical missing cells:
P6V/main-02, P6V/main-08, and P6V/main-10. These cells are fixed by the
historical evaluator-recovery workflow's *pre-execution* validation step,
not chosen after inspecting research outcomes.

Each archived JSON member is read through the bounded ZIP/CRC/SHA-256 preflight
already used for trace/report concordance. The comparator requires the
original ZIP to contain the exact 37 expected evaluator-cache member paths
and the recovery ZIP to contain exactly 40. Any overwritten original cache,
missing new member, unexpected treatment/task cache, or mixed directory
layout blocks the comparison. This makes the "evaluator-only recovery" source
integrity claim independently testable when both original ZIPs are recovered,
without running the evaluator again or extracting potentially unsafe files.

Run the same two-archive comparison command described above; the receipt now
also reports 37 byte-identical preserved evaluator caches and three new
cache members. **It does not parse or validate the semantic contents of the
three new evaluator JSONs**, prove the accuracy of automated scores, or establish
the truth or independent historical custody of an archive. The published frozen
40-row evaluator CSV and its independent aggregate-verification gates remain
separate prerequisites. Until two authorized historical archives are recovered,
the new integrity check is validated only with synthetic fixtures; no real
archive comparison or human annotation has occurred.


## Frozen evaluator numeric-score correspondence (offline; not independent grading)

The original-to-recovery comparator now also checks the **published numeric
measurement lineage** of every evaluator-cache JSON against the exact
SHA-256-pinned `outputs/posthoc_support_runs.csv` bytes. It checks all 37
original and 40 recovered cache records for exact claims-checked, support
category counts, total tokens, strict support rate, and estimated evaluator
cost. Integer/bool substitution, nonfinite values, score/cost disagreement,
incorrect category totals, impossible claim counts, and a zero-retrieved-source
cell credited with positive support fail closed. Decimal comparisons preserve
the published numeric values without tolerance-based score drift.

A passing receipt reports `original_evaluator_cache_published_measurements_matched: 37`
and `recovery_evaluator_cache_published_measurements_matched: 40`.
This detects a cache/CSV mismatch even when all 37 preserved cache files
are byte-identical between ZIPs. It **does not** independently grade the
research reports, verify the evaluator's evidence/prompt input fingerprints,
prove the score truthfulness, establish independently retained historical
custody, or unblock human evaluation. Published CSV and archived caches can
share a common upstream measurement error. Tests use synthetic ZIP contents
and copy reference numeric values from the frozen CSV; the historical ZIPs
have not been recovered or scored by this change.

## Historical evaluator-cache JSON identity audit (offline, not score validation)

The two-archive concordance check additionally reads the bounded archived JSON
bytes of all **37 original and 40 recovery evaluator caches** without extracting
them. It checks every record against the **frozen published run ID for its
treatment/task cell**, requires the original study ID `budget-main-v1`, the
canonical treatment/task identities, and an integer schema version 1 or 2.
Malformed UTF-8/JSON, duplicate JSON keys, nonfinite JSON constants, top-level
nonobjects, wrong execution IDs, and evaluator-cache files exceeding 4 MiB
fail closed. Every reread byte stream must also agree with the decompressed
SHA-256/size from the earlier bounded ZIP verification; archive and evaluator
CSV source generations are checked again **after** these reads.

This closes the possibility that a misleading JSON file under a valid cache
filename appears to belong to a different treatment execution while still
passing the historical 37-to-40 byte-continuity check. The success receipt
separately records the two JSON-identity inspection counts. It deliberately
leaves `evaluator_cache_payload_semantics_verified: false`: the separate
numeric correspondence check does not independently score evidence, verify
evidence-to-report fingerprints, model outputs, or scientific
correctness are established by these identity checks. It does not establish
independent historical custody, genuine human-validation outcomes, or packet
distribution readiness. Tests use synthetic cache records only; no original
experimental ZIP has been recovered or scored during development.


## Schema-v2 evaluator-to-report input correspondence (offline; not source authenticity)

The recovered-archive concordance check additionally verifies an important
evaluation-lineage distinction: a schema-v2 cached evaluator may report the
correct treatment/run ID and numeric score while having **evaluated different
report bytes**. For every schema-v2 cache, its recorded
`input_fingerprints.report` SHA-256 and UTF-8 byte size must now match the
corresponding original Markdown report's decompressed SHA-256 and size from
the independently scanned archive member inventory. The complete
schema-v2 input-fingerprint shape (question, report, evidence, prompt,
algorithm, and encoding) must be well-formed. A schema-v1 cache must not
claim fingerprint metadata, consistent with the original evaluator schema.

The receipt separately counts verified schema-v2 report-input bindings for
the original and recovery archives. **Schema-v1 caches never recorded input
fingerprints**, so they cannot be retrospectively claimed as linked to the
report input; a zero count is not a failed score but a limitation of the
historical schema. The verifier does not claim to validate evidence or prompt
*content* from their format-valid fingerprints, nor does report-input
correspondence prove that any automated judgment is correct, an original
report is historically authentic, or independent evidence custody has been
established. No new scores or human evaluations are produced; all new test
fixtures are explicitly synthetic.

## Schema-v2 evaluator-to-frozen-question source binding (offline; not human validation)

A schema-v2 evaluator cache also carries a SHA-256 and byte length for the
research **question it evaluated**. A correct run ID and report-byte hash do
not rule out a substituted question. The concordance check now compares
each schema-v2 `input_fingerprints.question` with the *exact UTF-8 bytes*
of the corresponding original frozen task question. This is sourced from
`experiments/main_budget_tasks.json` only after requiring its original
treatment-run source SHA-256
`5701df80036edb354f4f7d1efc409ea8f554a215f8c37da9d1a0b8ed01fdfd5f`.
The task source is captured before both ZIP audits and checked again after
them and after evaluator-cache JSON inspection, including detection of
same-byte file replacement. A modified task manifest blocks the comparison;
the verifier never recalculates a new authoritative question pin from a
possibly edited local checkout.

The receipt reports separate schema-v2 question-fingerprint counts for the
original and recovered evaluator caches, plus the pinned task-manifest SHA-256.
Schema-v1 records provide **no** question-input fingerprint and cannot
support this backward-looking assertion. The task pin comes from the
original Git source revision, **not** independently authenticated archival
custody. This check does not authenticate the evaluator's evidence or prompt,
the original treatment report, the score's correctness, or human-annotation
readiness. Only synthetic fixtures exercise the new gate while historical
archives remain unavailable; no treatments or scoring are rerun.

## Historical treatment-trace completion and frozen-assignment gate (offline)

A ZIP path matching the published run ID is not proof that the enclosed
**treatment trace JSON** actually records that treatment, task, or completion.
The original/recovery concordance verifier now inspects all **40 original** and
**40 recovered** trace JSON members after bounded ZIP preflight and
source-hash comparison. Each independently reread member must retain the
previously scanned decompressed SHA-256 and byte length. The verifier rejects
ambiguous or malformed UTF-8/JSON, duplicate keys, nonfinite constants, and
records larger than 16 MiB before semantic inspection.

It requires trace schema v2, two matching experiment/trace identities and
original task-set ID, the published execution ID, an explicitly completed
run with complete provider usage status, and the **exact original frozen task
question** from the SHA-256-pinned original-run task file. The recorded
planning/verification modes and maximum source budget must match the
predeclared D3/D6/P6/P6V assignments; completed source-success and -failure
counts must sum to attempted sources and never exceed the assigned budget.
A consistent pair of falsified trace documents can therefore no longer pass
merely because filenames and report/cache bytes agree.

The receipt separately counts 40 inspected original and 40 recovered traces.
This check validates recorded metadata and budget-ledger consistency, **not**
the truth of web retrieval, source attribution, report quality, independent
historical archive custody, or automated measurement correctness. The original
40 source traces remain unavailable for this inspection; regression tests use
synthetic fixture archives only. It does not rerun treatments or evaluators,
create human ratings, or permit human packet distribution.


## Frozen published treatment-resource ledger correspondence (offline)

An archived treatment trace may have the correct run ID, completed status,
question, assigned treatment, and a *self-consistent* source budget while
still contradicting the measurements in the published cost-quality study.
The original/recovery ZIP comparator now checks every trace's source budget,
successful and failed source counts, search/model call counts, treatment-token
count, and report-word count against the **same frozen treatment/task cell**
in `outputs/main_study_runs.csv`. That CSV must match the canonical-analysis
input SHA-256 `966ea80519af5ea7b832c86d7868525a4ef75874f396f242291e3be949382a0e`
before either archive audit. The source is captured before and reread after
both inspections, including same-byte replacement detection.

The receipt counts original and recovery published-resource ledger checks
separately (40 each). This subsection establishes recorded resource-count
correspondence only; the later frozen-price gate separately recomputes the
published estimated cost and compares the recorded latency. Neither gate
independently measures provider billing, wall-clock time, web-source
authenticity, or report quality. A matching published table does not
establish independent historical custody. Original historical ZIPs remain
unavailable; only explicitly synthetic ZIP fixtures test the new gate.
No treatments, evaluators, or human ratings are run or generated.


## Historical trace-to-Markdown correspondence (offline, not authentication)

The two-role archive comparator now reopens each original and recovered
Markdown source after ZIP preflight, checks its SHA-256 and decompressed byte
size against the prior verified member scan, and decodes it as UTF-8. Each
schema-v2 completed trace must point to that frozen run's report
(`outputs/<run_id>/research_report.pdf` or the recorded Markdown fallback)
and its `report_words` must equal the actual whitespace-split Markdown word
count. This follows the treatment runner's `len(report_text.split())`
instrumentation and the unchanged Markdown write path. The published treatment
CSV is already checked separately; a trace and CSV can agree while a different,
byte-concordant archived Markdown report contradicts both.

All 40 original and 40 recovered cells are inspected within the existing
two-ZIP source-generation consistency window. The check is read-only and
enforces the preflight member-size cap again on semantic report reads. It
does **not** establish that the report was originally generated by the agent,
that its citations are true, that word count measures quality, or that the
archival chain of custody is independently authenticated. Synthetic fixtures
exercise the consistency gate while the historic ZIPs are unavailable; do not
alter original research reports to make a mismatch pass or describe this as
human validation.

## Historical treatment source-query scheduling provenance (offline)

The original/recovery ZIP comparator now checks nested **planned queries, search-result records and scheduled source URLs** for all 40 treatment traces in each archive. A frozen treatment CSV can agree on total retrievals and model/search-call counts while a byte-identical original/recovery trace assigns the same URLs to different queries or silently skips an earlier candidate. These are material differences when interpreting the D3/D6 retrieval and P6/P6V planning contrasts.

Each role-pinned trace must preserve the original runner's URL-ledger partition, query count and execution order, direct-arm exact-question search versus planner-arm four-query plan, per-query browse budget distribution, and greedy earliest-unvisited-candidate scheduling. The comparison reuses the independent extracted-archive recovery-diagnostic validators rather than maintaining a conflicting copy of the protocol. It remains offline, read-only and inside the existing preflight ZIP-byte and source-generation checks. The receipt reports `original_treatment_query_and_url_scheduling_checked: 40` and `recovery_treatment_query_and_url_scheduling_checked: 40` only when all checks pass.

This is **internal recorded-provenance consistency**, not proof that the search service returned those URLs, that any source page was genuine or correctly interpreted, or that either historical ZIP was independently retained. The missing original/recovery archives still block authentic historical comparison; synthetic regression fixtures are not scientific observations, confirmatory outcomes or human annotations.


## Historical provider-reported token/model-call ledger consistency (offline)

The original/recovery comparator now verifies each completed treatment trace's
**per-model provider usage**, not only its aggregate model-call and token counts
in the frozen treatment CSV. Both candidate ZIPs must retain a nonempty
`provider_usage_by_model` dictionary whose model names and entries are valid,
whose calls and prompt/completion/total tokens are nonnegative integers, whose
per-model token totals equal prompt plus completion tokens, and whose
`unavailable_calls` remain zero under the recorded
`provider_usage_complete` contract. The sum across models must reproduce the
trace's model-call, unavailable-call, and prompt/completion/total-token
fields. The fingerprint-pinned treatment CSV separately checks the aggregate
model-call and total-token counts; it does not publish prompt/completion splits
or independently authenticate provider billing.

The comparator reuses the original-run extracted-archive readiness validator
and rejects the same falsified per-model ledger in **both** otherwise matching
archives. The receipt reports original and recovered provider-usage checks
separately (40 each). This is an internal accounting-consistency check, **not**
verification that the provider billed those tokens, that every real API call
was logged, that model prices/costs are accurate, or that historical ZIP custody
is authenticated. The regression fixtures use a deliberately synthetic model
and usage split, not reconstructed historical outcomes. Original/recovery ZIPs
are currently unavailable; the gate is not a real historical-source audit and
does not authorize human evaluation or change pilot, confirmatory, exploratory,
or pending human-validation findings.


## Historical treatment latency and frozen-price cost lineage (offline)

The original/recovery ZIP comparator now binds **both historical 40-cell trace
matrices** to the frozen treatment CSV's recorded `latency_seconds` and
`treatment_cost_usd`, in addition to the existing source, token, and
provider-usage checks. Identical token totals are insufficient: changing
prompt/completion splits or model names can alter estimated cost while
preserving all aggregate counts. The verifier reuses the original
extracted-archive readiness validator's uncached-token pricing method and
the historical price table, pinned to SHA-256
`35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace`.
It rechecks the price-source generation before ZIP inspection, after both
ZIP audits, and after JSON inspection. Nonfinite/negative or mismatched
latencies, unsupported cost methods, unpriced models and incompatible
cost estimates fail closed. Receipt fields identify the 40+40 checks.

This verifies internal correspondence of recorded estimates, not provider
billing, independently timed latency, historical pricing correctness, or
original ZIP custody. The tests use deliberately synthetic prices, models
and usage splits; they do not reconstruct historical treatment outputs.
Unavailable original/recovery ZIPs still prevent a real-archive comparison.

## Historical evaluator retrieval-evidence continuity (offline; not source authenticity)

The post-hoc support evaluator consumes saved research-query text, not just
the final Markdown. The two-ZIP verifier now checks every frozen run's sorted
research-query-*.txt files without extraction. It compares original versus
recovered raw member names, byte sizes and SHA-256 hashes across all 40 runs,
including zero-evidence runs. Each file must be valid UTF-8 and satisfy a
separate 8 MiB per-file / 32 MiB per-run / 64-files-per-run reading bound.

It reconstructs the historical evaluator input by stripping each saved text,
dropping empty snippets and joining the remainder with blank lines, or by using
the frozen explicit no-evidence sentinel only when the published successful
source count is zero. For schema-v2 evaluator caches, the reconstructed
evidence bytes must match the cache's evidence input fingerprint (SHA-256 and
byte count). The historical 37 schema-v1 caches do not have input fingerprints:
saved-file continuity is **not** retroactive proof of which evidence they
actually consumed. Receipt fields distinguish all-40 raw evidence-file
continuity from schema-v2 evidence-input correspondence.

This guards against an evaluator-only recovery changing the saved evidence
while preserving the final report/trace, and against schema-v2 caches claiming
different inputs while retaining frozen published measurements. It does
not independently authenticate original archives, verify web source truth,
validate evaluator judgments or prompts, or authorize human-evaluation packet
distribution. The regression tests use synthetic snippets only; no treatment,
web retrieval, automated evaluator or human rating is run.


## Historical schema-v2 evaluator prompt lineage (offline; not scoring validation)

A cache can report the correct 40-cell run identity, frozen automated score,
question, report and saved-evidence fingerprints while declaring an unrelated
*prompt* fingerprint. That weakens the claim that a common evidence-only rubric
measured every treatment. The two-ZIP comparator now reconstructs the precise
post-hoc 12-claim verification prompt from each frozen research question, the
unchanged UTF-8 Markdown report (including its original newlines), and the
sorted saved evidence snippets or original no-evidence sentinel. It checks
both SHA-256 and UTF-8 byte length against the `prompt` input fingerprint of
every schema-v2 evaluator cache. Prompt/report reads have an independent
16 MiB per-report bound. The original treatment and recovery workflow source
revisions (`c3c15e46a8eec3a8bbc24c968eedc0548172a897` and
`8733ce492abc74e7b2966ed22ce08d3fddec43ca`) contain the same rendered
12-claim rubric. A fixed template canary, SHA-256
`cdc7a77cb3e8334722d768afbd71a033c51a2006793992ab670a1ff10c4aac4f`
for the sentinel question/report/evidence inputs, detects ordinary later
changes to the rendering contract. The receipt distinguishes the schema-v2
prompt bindings from schema-v1 records, which contain no input fingerprints.

A matching hash establishes **recorded prompt-input consistency**, not that a
specific remote API request used that prompt, that the model complied with the
rubric, that its scores were correct, or that the missing archives have
independent historical custody. It does not reconstruct experimental evidence,
rerun automated/human evaluation, or authorize blinded packet distribution.


## Historical common-evaluator configuration metadata gate (offline)

The original and recovered caches must now retain the **same frozen post-hoc
measurement configuration**, not just the correct run IDs, input fingerprints
and published numeric summaries. The archive comparator requires the historical
`gpt-5.6-terra` evaluator model, temperature `1.0`, 12-claim cap, and
`frozen uncached rates` accounting label on each of the 37 original and 40
recovery JSON records. These constants follow the original treatment and
recovery workflow environments and evaluator record writers at source revisions
`c3c15e46a8eec3a8bbc24c968eedc0548172a897` and
`8733ce492abc74e7b2966ed22ce08d3fddec43ca`.

When a cache declares `evidence_status`, it must match the **independently
reconstructed status** of the archived saved retrieval evidence. Schema-v2
caches must declare it; schema-v1 caches may omit it because the original
schema-v1 treatment-run writer did not yet record this field. Omission is
reported as a historical limitation, not evidence that the original evaluator
saw the reconstructed evidence. The success receipt separately reports original
and recovered configuration-validation counts.

These checks reject metadata claiming a different common measurement setup
without changing a single frozen score. They do **not** independently attest
the actual remote model request, verify provider token accounting or billing,
authenticate the historical ZIP archives, or substantiate the automated
judgments. All new regressions use synthetic fixture caches. The original and
recovery ZIPs remain unavailable for authentic inspection, and neither
treatments, automated evaluations, nor human ratings are rerun or generated.


## Historical evaluator provider-usage ledger consistency (offline)

The original treatment and evaluator-only recovery source revisions both wrote
`provider_usage_by_model` into each saved post-hoc evaluator JSON. The
two-ZIP comparator now validates that this ledger identifies exactly the
frozen `gpt-5.6-terra` model, records one model call with no missing usage,
contains nonnegative integer prompt/completion/total token counts, and
reconciles the per-model token sum to the frozen published evaluator
`total_tokens`. Both the original 37 cache records and the complete
recovered 40-record set must satisfy this check; byte-identical erroneous
ledgers cannot pass simply because aggregate scores are unchanged.

This is an **internal recorded-usage integrity check**, not verification of
provider invoices, independently logged API calls, evaluator cost-estimate
recomputation, model compliance, historical ZIP authenticity, or the accuracy
of the automated scores. It cannot infer the original prompt/completion split
from the published total alone. Tests use synthetic ledger fixtures and do
not create, replace, select, or rerun experimental results. The authentic
historical original/recovery ZIPs remain unavailable; human-validation
distribution remains blocked pending independent source custody.

## Historical evaluator frozen-price cost recomputation (offline)

Recorded evaluator token totals and the SHA-256-pinned published cost column
do not, by themselves, establish that a saved prompt/completion split was
priced correctly. The two-archive source comparator now recomputes each
historical post-hoc evaluator cache's `estimated_cost_usd` from its already
validated `provider_usage_by_model` ledger, using the original evaluator
writer's `scripts.summarize_pilot._estimate_reported_token_cost` method.
The exact dated price table is pinned to SHA-256
`35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace`
and is generation-checked across the comparison window. Both original
(37 cells) and recovered (40 cells) cache costs must exactly match their
recorded split at the original uncached per-model rates. An unpriced model,
invalid cost, or an internally consistent but mispriced token split fails
closed. Success receipts identify both cache counts separately.

This verifies **internal cost-estimate lineage**, not invoices, charged API
usage, proof of a historical model call, archive custody, or evaluator
judgment correctness. The regression test archives contain explicitly
synthetic token splits that satisfy the frozen published cost equation;
they are neither recovered historical usage nor experimental results.
The original and evaluator-recovery ZIPs remain unavailable, so no authentic
archive has passed this gate and blinded human-evaluation distribution
remains blocked.

## Historical evaluator-cache normalized qualitative fields (offline)

The original treatment and evaluator-only recovery source revisions
(`c3c15e46a8eec3a8bbc24c968eedc0548172a897` and
`8733ce492abc74e7b2966ed22ce08d3fddec43ca`) called
`normalize_verifier_output` before persisting each common-evaluator cache.
That historical normalizer always wrote an `examples` **list of at most
eight entries**, even if the model response omitted examples. Because these
illustrative claim excerpts are the only qualitative evaluator output retained
alongside the frozen counts, the two-archive comparator now verifies their
historical *stored shape* on both the 37 original and 40 recovered cache
records. Malformed or omitted lists and more than eight entries fail even
when the published numeric scores and costs are unchanged. Existing receipt
fields separately count the original/recovered example-list checks.

The read-only JSON audit also rejects floating-point exponents that overflow
to infinity anywhere in a cached record and converts excessive JSON nesting
into an explicit validation failure rather than an uncontrolled recursion
exception. The historical numeric claims, input-fingerprint, configuration,
cost, and provider-usage checks remain unchanged. Example content itself is
**not** reclassified: the original normalizer did not require a schema for
individual example entries, so imposing one retrospectively would fabricate
a stricter historical contract.

Passing proves only bounded recorded-cache shape and finite JSON parsing.
It cannot establish that illustrative examples correspond to actual
retrieval evidence, that a model produced them, or that a claim judgment is
correct. Tests use synthetic archives only; authentic historical treatment
and recovery ZIPs remain unavailable. The automated confirmatory analysis
is untouched, exploratory findings are not promoted to confirmatory claims,
and human-validation ratings and independent custody remain pending.

## Historical per-query evidence-file scheduling integrity (offline)

The historical treatment agent persisted a `research-query-NN.txt` file after
**every executed search query**, including an empty file when no browse returned
content. The ordinal is the position in the planned query list, not the
successful-source count. The common evaluator later reconstructed its evidence
from the saved files in sorted order. Published total retrieval counts alone
cannot detect an absent query file if another query still supplied some text.

The two-ZIP concordance audit now cross-checks the exact direct-child
`research-query-NN.txt` member set for each of the 40 original and 40
recovered traces against the trace's validated ordered search records and
planned-query ordinals. It also checks the original writer's empty/nonempty
rule against each query's successful browse URLs. Missing, inserted, or
contradictory query files fail even when **both** archives contain the same
alteration and their published aggregate counts agree. The earlier independent
byte-fingerprint and schema-v2 input checks remain in place; new regression
cases use synthetic query schedules and archives only.

This verifies **recorded query-to-evidence-file consistency**, not the truth
or completeness of source text, that a remote browse actually occurred,
the authenticity of historical archives, or independent evidence custody.
The original 40-trace and evaluator-recovery ZIP artifacts remain unavailable,
so no authentic archive has passed this new gate. No treatments, evaluators, or
human ratings were run or fabricated, and human distribution remains blocked.

## Bounded archive JSON integer parsing (offline robustness)

The concordance audit inspects both historical treatment traces and evaluator
cache records as untrusted JSON. A ZIP member can be within its byte-size limit
yet contain an integer literal with thousands of digits. Depending on the
Python runtime configuration, unbounded integer conversion may raise an
unhandled interpreter exception or consume disproportionate CPU and memory.
This can prevent auditors from receiving a controlled source-validation error.

Both semantic JSON readers now reject integer tokens longer than **1,024
decimal digits before conversion**, regardless of runtime integer-string
settings. Normal recorded run IDs, counts, sizes and token ledgers are far
below this intentionally generous parsing boundary. The check also applies to
integers nested in ignored metadata or illustrative examples, so a matching
original/recovery ZIP pair cannot bypass the limit. Both readers retain their
existing duplicate-key, nonfinite-number, and recursion safeguards.

Offline synthetic regression fixtures test both original and evaluator-recovery
cache roles plus treatment trace identities. This is bounded input handling,
not stronger proof of historical authenticity, report correctness, external
archive custody, or human-evaluation readiness. No treatment, evaluator, or
human study was rerun.
