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
