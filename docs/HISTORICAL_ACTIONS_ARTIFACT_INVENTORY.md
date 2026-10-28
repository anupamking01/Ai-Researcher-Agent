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
