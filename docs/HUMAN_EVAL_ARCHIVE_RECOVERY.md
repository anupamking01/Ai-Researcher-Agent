# Recover the original automated-to-human VERA evidence (no outcome reruns)

**Status (2026-11-05): blocked on original report and handoff custody.**
This is an operational inventory and recovery plan, not an experiment or human-evaluation result.

## Run-scoped GitHub metadata origin boundary

The read-only historical **run-scoped** workflow/artifact inventory now rejects
all HTTP 301/302/303/307/308 redirects rather than accepting a JSON response
from a different endpoint, and checks the final response URL and HTTP-error
origin against the exact pinned GitHub Actions API URL. This prevents a
redirected response from being mistaken for an original-run inventory and
prevents automatically forwarding authenticated requests to a redirect target.
Actual original-endpoint HTTP 404/401/403 and transport failures remain hard
errors, not evidence that an archive is missing. The inventory still checks
historical execution metadata in two passes and makes no original-data custody
or human-evaluation readiness claim. Offline synthetic tests exercise the
redirect, relocated-404, valid-origin, and transport boundaries. This safeguard
does not recover any original ZIP, alter automated results, or authorize rating.

## Historical job-log workflow-clock attribution

The read-only `scripts/audit_historical_artifact_job_logs.py` auditor now
requires each selected original-upload, recovery-download, and recovered-upload
job-log event to fall within its **own** original GitHub Actions workflow's
recorded `run_started_at`–`updated_at` window. The pinned UTC windows are
2026-09-11 16:15:15–17:22:43 for original run `34620917346` and
2026-09-13 21:20:32–21:21:40 for recovery run `34783525480`; the end
second includes subsecond log timestamps because the workflow API reports
only whole seconds. Previously a synthetic transcript with matching IDs,
ZIP digests, event order, and shifted dates could pass the log audit despite
falling outside the original workflows. Offline tests exercise date shifts
on both logs and a valid end-of-second boundary. This is a **same-provider
chronology consistency check**, not independent log authentication, ZIP
recovery, proof of report/trace custody, or permission to begin annotation.

## Direct-ID HTTP redirect custody boundary

The read-only historical direct-ID auditor opens only the **two pinned GitHub
artifact metadata endpoints** with HTTP redirect following disabled. Redirects
(including redirects whose destination returns HTTP 404) fail closed rather
than being mistaken for a genuine 404 from the original GitHub artifact ID.
The transport additionally checks the response URL and any HTTP-error URL
against the pinned endpoint. Synthetic offline regressions cover standard
redirect status codes and an indirect 404. For available direct-ID metadata,
creation must also fall within the **original GitHub Actions run's** pinned
start-to-last-update window: treatment run 34620917346 (2026-09-11
16:15:15–17:22:43 UTC) or evaluator-recovery run 34783525480 (2026-09-13
21:20:32–21:21:40 UTC). Synthetic tests reject pre/post-run creation dates
while admitting exact endpoints. These GitHub-provider chronology pins only
reject inconsistent upload metadata; they do **not** authenticate report or
trace contents. A genuine 404 is still only an
access observation; it does **not** prove destruction or exclude authorized
offline backups. This diagnostic neither downloads original archives nor
authenticates original experimental traces, reports, or human ratings.

## Direct-ID metadata update versus observation time

The read-only direct-ID artifact auditor now rejects provider metadata whose
`updated_at` is later than the recorded UTC observation timestamp, even
when its original run ID, ZIP SHA-256 digest, name, size, and creation window
otherwise match. Both reads are checked independently; an impossible first
read stops before any redundant second request. A timestamp **equal** to
the observation boundary is accepted. This complements the post-upload
observation-time floor: an artifact cannot truthfully be described as
already updated at an earlier observation time. Synthetic offline tests
exercise both historical artifact roles and either metadata read.

The recorded time is a caller-supplied audit as-of boundary (normally the
current UTC clock), not an independently trusted timestamp authority.
The check cannot establish which offline archive is original, authenticate
reports or traces, recover missing ZIPs, or make human annotation ready.
An ordinary direct-ID 404 remains an access observation only, not proof
of destruction or of a missing backup.

## Direct-ID observation timestamps cannot be future-dated

The direct-ID auditor now captures its local UTC audit-start time before any
metadata request. A caller-supplied `checked_at` later than that timestamp
fails **before either endpoint is contacted**; default runs reuse that same
captured instant. This prevents a current 404 or accessible metadata object
from being labelled as an observation made in the future. Synthetic offline
regressions cover future timestamps expressed in different UTC offsets and a
legitimate past observation. Earlier post-upload and metadata-update chronology
checks remain in force.

A caller-supplied observation time must also be no more than **60 seconds
before** the audit's sampled start time. Older backdated times now fail before
either direct-ID endpoint is queried, including double-404 results. Deterministic
offline tests use an injected clock for historical boundary simulations; those
simulations are not retrospective GitHub API observations. Use the default
real-time timestamp for live historical-artifact availability checks.

This check uses the auditor's local clock, **not** an independent timestamp
authority. It does not verify backdated caller-supplied timestamps, authenticate
original ZIP custody, or prove that an unavailable archive was destroyed.
Source-bound original report/trace recovery and blinded human-evaluation gates
remain unresolved.

## Blinded packet physical-record integrity across handoffs

The coordinator packet verifier requires the packet builder's exact canonical
JSONL serialization, LF-only records, and final LF. Independently, the
annotator-bundle reader and blinded ratings freezer/retained freeze verifier now
reject **every extra blank or whitespace-only physical LF record**, including
between items and after the final item. Previously these paths silently
discarded such lines even when a candidate was self-consistently rehashed.

These downstream readers retain compatibility with legacy synthetic/archived
packet JSON serialization, optional terminal newline, and CRLF: they do not
replace the **stricter production coordinator source-bound verifier**. They do
not rewrite any packet bytes or fingerprints. This prospective integrity check
does **not** authenticate unavailable original reports, allow an otherwise
unverified human distribution, or create human-evaluation evidence.

## Why this is a research gate

VERA's versioned checkout contains the frozen automated-treatment/evaluator
CSVs and published input-manifest aggregate, but not the original 40 treatment
traces, Markdown report sources, coordinator blinded packet, or two distributable
annotator bundles. The combined automated-to-human handoff verifier is designed
to run against **original** sources with **independently retained** archival
manifest-file SHA-256 pins. Synthetic tests and a locally regenerated packet
cannot meet that original-evidence claim.

On 2026-10-27 the GitHub Actions artifacts endpoint returned **no artifacts**
for the original treatment workflow run 34620917346 and evaluator-recovery
run 34783525480. The canonical-analysis run 36070798723 still exposed its
10,270-byte analysis artifact (artifact ID 10837878458, expiry listed as
2026-12-23). This is an observation about artifact availability at that time,
not proof that the original reports are destroyed: local, restricted, offline
or institutional backups may exist.

## Original ZIP recovery triage by immutable GitHub upload identity (2026-11-05)

The ordinary run-scoped Actions artifact listings are empty for both historical
source-bearing runs. A separate read-only **direct lookup by their exact
historical artifact IDs** was also attempted on 2026-11-05 using the connected
GitHub repository access. Both returned GitHub API **404 Not Found**. This is a
second access path, not another test of whether the original research succeeded.
A 404 can reflect expiration/removal **or** access constraints; it is neither
proof that no offline backup exists nor evidence that the original reports
have been recovered. Do not retry model treatments or re-create missing reports
to make an artifact-availability check pass.

The following **GitHub upload-artifact@v4 job-log metadata** is pinned in
`scripts/audit_historical_artifact_job_logs.py`. It provides concrete
candidates to search for in authorized organizational/offline backups and
helps reject an unrelated ZIP presented under a plausible archive name:

| Original role | Historical Actions run | Artifact ID | Recorded ZIP size | Recorded ZIP SHA-256 |
| --- | --- | --- | ---: | --- |
| 40 treatment reports/traces | `34620917346` | `10275100801` | 608355 bytes | `878205ff42267b85d71f478520a4a3ebe520915f22ae2d2307e930fa39545400` |
| Evaluator-only recovered archive | `34783525480` | `10324954205` | 618586 bytes | `c357b068fa4c0b7e86f7c56cd1d3e346f6922106d7bde644db92feb7f8fc84cc` |

For reproducible subsequent triage of this **alternate GitHub API access
path**, run the following read-only metadata-only command (the connected
account's access may differ from an unauthenticated request):

```bash
python -m scripts.audit_historical_direct_artifact_ids
```

The diagnostic makes **two metadata observations of each exact historical
artifact ID** and fails closed if access/identity changes between them. It
checks an accessible object's original upload-artifact name, ID, ZIP byte count,
optional provider digest, repository, branch, run ID and head commit against the
historical pins. Only HTTP 404 is reported as direct-ID inaccessibility; HTTP
401/403/429, transport errors and malformed metadata are errors, not
evidence of archive absence. It never downloads or extracts a ZIP. Even a
matching provider digest is **same-provider job-log concordance**, not an
independently archived report/trace fingerprint. Record each receipt's UTC
observation time; do not present prior 404s as a permanent availability state.
The original report/trace custody and independent human-evaluation gates remain
mandatory.

### Account for every explicitly located offline ZIP candidate

When one or more unchanged ZIPs are found in authorized backups, a bounded
read-only batch diagnostic now compares **every supplied candidate** against
the two historical GitHub upload-artifact job-log ZIP byte-count/SHA-256 pins:

```bash
python -m scripts.triage_historical_archive_candidates \
  --original-treatment /path/to/original-a.zip \
  --original-treatment /path/to/original-b.zip \
  --evaluator-recovery /path/to/recovered.zip
```

`scripts/triage_historical_archive_candidates.py` accepts at most 16
**explicitly named** candidates, without recursively scanning backup locations.
Arguments may be interleaved in any order: the receipt's candidate indices
and `first-seen` duplicate pointers follow the **exact command-line order**
of both role switches, instead of silently grouping all original-treatment
candidates ahead of evaluator-recovery candidates. Keep the exact invocation
with the receipt so each index can be traced back to its supplied backup path;
the receipt deliberately records only filenames, not full local backup paths.
For unreadable or absent backup files, filesystem exceptions are reduced to
stable errno categories (for example, `ENOENT` or `EACCES`) instead of
embedding absolute backup paths in the receipt's diagnostic field. Ordinary
structural ZIP errors retain their bounded explanatory diagnostics. This is a
local-path disclosure safeguard, **not** anonymization of archive filenames,
ZIP member names, or anything written to shell history; treat receipts and
original command lines as coordinator-only recovery records.
This is an input-order provenance guarantee, not evidence of independent
custody or a reason to prefer a particular candidate.

It invokes the existing bounded ZIP structural preflight on each input,
records structural failures and same-provider size/digest mismatches as well
as matches, and returns per-role counts without picking a favorable archive.
The preflight also requires a single, parser-consistent ZIP end-of-central-directory
(EOCD) record. Python's ZIP reader uses the last EOCD signature even when that
signature is embedded in a ZIP comment; the bounded pre-parser previously could
select an earlier valid terminal record instead. A second plausible terminal
EOCD, or a later spurious EOCD signature in the comment, now fails **before**
the standard reader opens the archive. Ordinary comments without the EOCD
signature remain supported; deliberately rejecting ambiguous comments avoids
different tools reporting different member inventories for the same backup.
This is a structural-consistency check, not historical source authentication.
To prevent a batch of up to 16 otherwise individually valid ZIPs from
requiring up to 8 GiB of decompression, the triage also enforces a **1 GiB
batch-wide declared-uncompressed-byte budget**. The structural preflight
reserves each candidate's full declared regular-member byte total **before
opening any ZIP member stream**. Reservations are deliberately not refunded
on later CRC/decompression failures: unsafe sources cannot exhaust resources
through repeated unsuccessful inspection attempts. A candidate larger than the
remaining allowance is retained as
`not_inspected_batch_decompression_budget_exceeded` (not misreported as a
structurally invalid or matching ZIP). Later smaller candidates may still be
inspected in original CLI order. The receipt records the total budget,
reserved bytes and number of candidates not inspected due to this limit.
A separate **1 GiB batch-wide raw ZIP-byte budget** also bounds the I/O cost
of initial/final SHA-256 passes and structural reads across as many as 16
individual input ZIPs (which can otherwise total 4 GiB of compressed input).
The preflight reserves each candidate's full on-disk ZIP size **after validating
its stable file metadata and before hashing or reading ZIP contents**. This
reservation is never refunded after later parsing, CRC or consistency failure.
If the next candidate will exceed the remaining raw-byte allowance, its row
is retained as `not_inspected_batch_archive_byte_budget_exceeded`; it has
**not** been inspected or found historically mismatched. The original
argument order and subsequent smaller candidates remain eligible for inspection.
The receipt separately reports `batch_archive_byte_budget`,
`batch_archive_bytes_reserved`, and
`batch_candidates_not_inspected_due_to_archive_budget`.
Both SHA-256 passes now read exactly the archive size already checked and
reserved for that candidate, then probe at most one extra byte. If a source
grows or truncates during hashing, preflight fails before ZIP parsing rather
than scanning an unbounded appended tail or charging more bytes than reserved.
Descriptor/path checks still reject visible in-place modification and
replacement; these are bounded, observational checks, not filesystem locks.
This raw-input limit and the distinct declared-uncompressed-byte limit are
inspection-resource constraints, **not** evidence of treatment failure,
archive unavailability, independent provenance, or human readiness.
A structurally valid ZIP can have **different ZIP bytes** (for example, a
different compression method or member order) while containing **the same
regular-file paths and decompressed bytes**. The batch receipt now records a
canonical SHA-256 over the sorted regular-member path, uncompressed byte count,
and per-file SHA-256 tuples. It flags
`same_regular_members_as_candidate_index` across *all* submitted candidates
and reports `distinct_regular_member_content_count` independently of distinct
ZIP-byte count. Empty directory entries and ZIP-only metadata intentionally
do not affect this content identity. A failed ZIP preflight gets no content
identity; every supplied row is still retained. These are **content-equivalence
diagnostics**, not a proof of historical execution, independent backup custody,
source/report authenticity, or readiness to distribute human-evaluation packets.
Do not select a candidate according to support scores or reported outcomes.

It also marks repeated **structurally verified ZIP byte identities** across
candidate paths and declared roles using the first candidate index. Per-role
raw candidate/concordance counts remain available; distinct verified-ZIP and
distinct provider-concordant-ZIP counts avoid mistaking multiple filesystem
copies of one archive for multiple independent sources. Unsafe/failed candidates
remain in the inventory but are not deduplicated without a verified digest.
Distinct ZIP bytes do **not** prove independent backup custody, and even
matching historical GitHub-provider pins are not independent authentication.
The schema-v3 receipt also detects a structurally valid ZIP whose byte count
**and** SHA-256 match the *other* historical role's GitHub job-log pin.
Such a candidate is marked `matches_other_historical_role_not_declared_role`,
with `other_role_github_provider_zip_match` and separate per-role/global
counts. The original caller-declared role is preserved; an other-role match is
not counted as concordance for that declared role, does not authorize
reassignment, and is not independent archive custody proof. If only one
fingerprint field matches, no alternative-role match is recorded. Investigate
backup custody without selecting candidates by experimental outcomes.
No files are extracted, renamed, copied, regenerated, or overwritten. The
receipt does not name or attest to unsubmitted backup candidates, and CLI exit
success means only that every specified input was **accounted for**, not
necessarily inspected (budget-exceeded rows are explicit), and **never** that
any artifact is historically authentic.

An observed matching ZIP would corroborate **GitHub-provider upload metadata**
only. It cannot establish a separately retained custody chain, independently
authenticate any original report/trace, validate 40 run IDs, or unblock human
packet distribution. Archive candidate checks are offline; no experimental or
evaluator treatment is rerun and no human rating is created. Preserve each
candidate and record where it was originally found, including any mismatch.
If only a directory tree exists, use the original-tree inventory instead;
do not repackage it simply to obtain a ZIP match.

**Recovery order, without outcome reruns:** First locate original, unmodified
ZIP bytes (or independently retained original directory trees) in an
authorized backup. Record the backup's location, custody history and
pre-existing independent checksums *before* manipulating a working copy.
If intact ZIP bytes are available, compare their byte count and SHA-256
against the table as a preliminary **GitHub-service log concordance** check.
If they differ, preserve both original files and document the discrepancy;
do **not** repack/rename/rewrite evidence or select whichever candidate
produces favorable research results. If only unpacked directories exist, ZIP
byte hashes do not apply to those files: keep the original directory tree and
its independently retained file/manifest pins, and use the documented
read-only structural inventory and source-bound handoff verifiers.

Even a byte-for-byte ZIP match establishes concordance with **recorded GitHub
upload metadata**, not independent authentication of historical execution.
Original trace/report content, all 40 published treatment/run IDs,
coordinator/annotator handoff fingerprints, and independent archival custody
must still pass the downstream research gates **before** blinded packet
distribution. The still-listed, smaller canonical automated-analysis ZIP
(`10837878458`) is an analysis snapshot and cannot substitute for either
missing source-bearing archive. Pilot diagnostics, frozen automated
confirmatory results, exploratory material, prospective verification
procedures, and pending human validation remain separate.

For a current, read-only GitHub Actions artifact inventory that pins the three
historical run identities and distinguishes absent, expired, and merely listed
artifacts, see [Historical Actions artifact availability](HISTORICAL_ACTIONS_ARTIFACT_INVENTORY.md).
It cannot establish original custody or replace a missing trace/report archive.

## Prepublication binding to the original evaluated run IDs

A frozen original task list is necessary but insufficient for publication:
two different executions could answer the same question with different reports.
The production packet CLI now additionally requires every one of its 40
`(treatment, task, run_id)` identities to match the original frozen
`outputs/posthoc_support_runs.csv` matrix. It checks the exact evaluator
file-byte SHA-256
`5acd80d6115f269c7fab40180dec0d778a45eaafd7d5c23cb79c43fd7837773c`
from the published canonical-analysis inputs before parsing the 40-cell
identity matrix. Substituted or swapped run IDs, missing cells, duplicate
cells, and modified evaluator CSV bytes all fail **before** packet publication.
The synthetic Python API can still omit this production-only source gate
for offline fixture testing; genuine callers must enable the original-source
gate. Additionally, every schema-v2 treatment trace must contain its own
explicit, nonempty string `trace.run_id` exactly matching its trace filename.
The packet builder no longer invents a missing run ID from the filename:
otherwise an anonymous recovered trace renamed to a published run ID could
pass the subsequent source-identity comparison. The original main-study
treatment runner already required this persisted run-ID invariant. Missing,
nonstring and whitespace-normalized identities are rejected before packet
publication; do not rewrite an original trace merely to satisfy this guard.
This does **not** independently authenticate recovered trace contents,
original reports, or historical custody. Those remain blocked pending
independent archives and their externally retained fingerprints.

## Unique run-to-report binding before human packet publication

The offline blinded packet builder now requires each treatment/task cell to
reference a globally unique `run_id`, in addition to its balanced matrix
and per-cell trace/report checks. Each run ID selects one Markdown report
directory; reusing the same ID for two different treatment/task cells would
silently duplicate that report and misrepresent the experimental inputs as
independent outputs. Such candidates fail **before any packet, ratings
template, blinding key, or manifest is published**. This is a prospective
validity guard, not evidence that unavailable original traces or reports have
been recovered or independently authenticated. Do not change identifiers or
copy reports merely to make a failed recovery pass.

## Shared report-inode guard for independent runs

The packet builder also rejects two distinct run IDs whose Markdown report
paths refer to the **same filesystem file identity** (device and inode), as
can happen with hard links. A unique run ID and an individually valid path
cannot on their own prevent this report reuse. File identity is captured from
the same descriptor as the report bytes, after descriptor/path stability
checks, before any annotator-facing output is published. Equal report bytes
in **separate** files remain allowed: matching text is not proof that two
executions were duplicated. This is a local source-alias safeguard, not
cryptographic authentication of original historical report custody; changes
to the source tree between separate reads are not an atomic snapshot.
Do not relink, copy, or rewrite original reports to force packet acceptance.

## Complete source-tree selection before packet publication

The packet builder now inventories the **entire dedicated treatment-trace
directory**, rather than selecting only files matching `*/*.json`. It
rejects unexpected root entries, unfamiliar treatment directories, nested or
non-JSON files, and symbolic links before it can publish a blinded packet.
A fully balanced selected matrix is insufficient when additional source
material is silently omitted: that would leave report inclusion under the
control of an unnoticed filename or directory layout decision.

Inventory enumeration is bounded by the four frozen variants and the number of
tasks in the supplied frozen task manifest, with one additional candidate
allowed for diagnosis. Duplicate-cell, missing-task, and incomplete-run
checks continue to apply to the selected JSON files. Recovery coordinators
must preserve unexpected historical material separately with provenance
documentation; **do not delete or rename original evidence merely to make
the gate pass**. This is a local anti-selection safeguard, not an independently
authenticated historical archive or an atomic multi-file source snapshot.
The unavailable original treatment reports remain a blocker.

## Original treatment-run task-list anchor

The two frozen automated CSVs are SHA-256-anchored, but that published
aggregate does **not** include `experiments/main_budget_tasks.json`.
Checking a recovered trace's question against a *locally edited* copy of that
JSON could therefore create a self-consistent but false task-alignment claim.

`scripts/verify_frozen_main_study_tasks.py` now checks the exact task
manifest bytes against the **original treatment workflow source**, GitHub
Actions run 34620917346, head commit
`c3c15e46a8eec3a8bbc24c968eedc0548172a897`. At that revision the task
manifest is Git blob `68316fdb00631856006119370f9f549b23d1bee3`,
whose file-byte SHA-256 is
`5701df80036edb354f4f7d1efc409ea8f554a215f8c37da9d1a0b8ed01fdfd5f`. Run it offline with
`python -m scripts.verify_frozen_main_study_tasks`.

The recovery inventory exposes `frozen_task_manifest_anchor`, blocks on a
mismatch, and **skips** its 40-trace question-content concordance claim
unless this original-run source anchor verifies. This prevents changing both
a local task list and recovered trace questions while retaining the already
published evaluator CSVs. The anchor is grounded in the repository revision
recorded by the historical workflow, **not** an independent signed archive;
it cannot authenticate missing report bytes or prove historical custody.
Tests using synthetic task lists mock this source-only check explicitly.
Neither treatments nor the evaluator are rerun.

## Read-only inventory

Run this diagnostic in the checkout, optionally passing external archive
locations and two *previously retained*, independently sourced file-byte
SHA-256 values:

```bash
python -m scripts.audit_human_eval_archive_readiness \
  --repo-root . \
  --trace-root <original-experiment-traces-directory> \
  --report-root <original-outputs-directory-containing-run-id-folders> \
  --packet-root <original-coordinator-packet-directory> \
  --canonical-root <original-canonical-distribution-directory> \
  --reverse-root <original-reverse-distribution-directory> \
  --research-manifest <original-archived-research-manifest.json> \
  --research-manifest-sha256 <independent-file-byte-sha256> \
  --coordinator-manifest-sha256 <independent-file-byte-sha256>
```

Trace-tree enumeration is bounded before sorting: at most five root entries
(four frozen treatment directories plus one unexpected entry) and 41 entries
per treatment directory (40 total runs plus one overflow) are ever captured
for inventory. Larger directories fail closed as
`trace_root_entry_limit_exceeded` or
`trace_variant_entry_limit_exceeded`, rather than materializing and sorting
arbitrarily many untrusted paths. These statuses are archive-structure
blockers, not evidence that historical runs failed. The scan remains read-only
and preserves the existing diagnosis for a single unexpected root entry and
41 trace files. Move unrelated files out of a **working copy** of the recovery
location only if their independent archival provenance is preserved; never
delete or rewrite original evidence to force a passing inventory.

The JSON enumerates missing or unsafe file paths, the original-trace candidate
counts **by frozen treatment** and the Markdown report candidate count, plus
the canonical published automated-input fingerprint check. By default,
traces are sought under `outputs/experiment_traces/<variant>/<run-id>.json`
and reports under `outputs/<run-id>/research_report.md`; the two new root
arguments allow a read-only inventory of separately recovered evidence without
copying or rewriting it. A `40_matrix_candidates_unverified` status means
exactly 10 regular trace candidates exist under each of D3, D6, P6 and P6V,
with no duplicated run-id filenames or unexpected root entries. A
`40_report_candidates_unverified` status means that the corresponding 40
regular Markdown filenames were present. Neither status validates JSON,
run/task identities, report content, report-to-trace linkage, or historical
custody. The additional `trace_to_published_evaluator` check compares the
40 candidate **(treatment, run-id filename)** pairs with the frozen canonical
evaluator CSV only after the published automated-input aggregate has verified.
It detects wrong run IDs and treatment-swapped trace filenames even when all
40 expected filenames, counts and report paths exist. A match means only
`40_run_ids_match_published_evaluator_not_authenticated`: trace JSON and report
contents, report-to-run linkage, independent custody and historical authenticity
are **still unverified**. A missing archive, absent published anchor or invalid
evaluator matrix cannot produce an identity match. Only mismatch/invalid-matrix
results add an extra blocker; skipped comparisons remain blocked by their
underlying missing-trace or missing-anchor requirements. Symlinks and missing/unsafe report candidates block readiness; a
balanced but incoherent archive can still pass this **structural inventory**.
Each independent downstream capture of the frozen treatment or evaluator
CSV is rechecked against that file's SHA-256 recorded in the published,
aggregate-anchored input manifest. The original task manifest is also
rechecked against its original-run source SHA-256 **after** its own later
content load. A source replaced between the initial published/task-source
verification and a subsequent run-identity, recovery-target, or trace-content
read fails closed, even if the replacement is a well-formed table or task
manifest. These per-capture checks do not make mutable directories an atomic
snapshot and do not authenticate missing historical reports.

The additional `trace_report_content` preflight runs only after the
fingerprint-verified evaluator's 40 frozen run IDs agree with the candidate
filenames. It uses bounded, descriptor-based reads and duplicate-key-rejecting
JSON parsing to check the actual 40 trace bodies: schema version, treatment,
task, run ID, task-set identity, exact frozen research question, completion
status, and the trace's recorded report path. It additionally compares the
recovered trace's source budget, successful/failed source counts, search/model
call counts, token usage and recorded report-word count with the **published
frozen treatment CSV for the same treatment/task cell**. The trace experiment
configuration must have the original arm's direct/planner and verification
settings. Missing, noninteger or mismatched counters fail the diagnostic even
when the 40 filenames and embedded run IDs appear valid. It additionally
checks the completed-run source-provenance ledgers using the original runner's
invariants: nonnegative integer source/query counts, total source count within
the frozen arm budget, completed source outcomes accounting for all scheduled
URLs, unique/nonblank URLs in the scheduled/success/failed lists, disjoint
success/failure partitions, search calls within the query count, and completed
provider-usage accounting. Thus matching aggregate CSV counters cannot mask
an internally contradictory URL/source ledger. The diagnostic additionally
reconciles each trace's actual `search_queries` and `search_records` with its
query/search-call counters and globally scheduled URLs: recorded queries must
follow the planned order (allowing budget-skipped queries), search-result
candidate URLs must contain newly scheduled URLs in their original order,
and transient failed-search records cannot claim successful scheduling.
The recovery preflight also enforces the original **query-plan execution
contract**: direct arms must search the exact frozen task question; planner
arms must record four planned queries; and individual search records must
respect the source budgets deterministically allocated by the original
runner (6 sources across four planner queries yields [2, 2, 1, 1]).
It allows unused per-query budget, genuine search errors, and duplicate
planned query text without reallocating budget to other queries. It now also
replays the original runner's **greedy candidate URL scheduling**: for each
query it takes the first not-yet-visited candidate URLs up to the allocated
budget and retains the visited set across queries, including failed browses.
This prevents an altered result list from placing a previously unseen URL
ahead of the recorded scheduled set while preserving every frozen source
count, candidate-subsequence constraint, and per-query budget. Repeated
candidate URLs and candidates visited in prior queries remain legitimate;
a search-error record still schedules no URLs. This deterministic
consistency rule is not independent evidence that any candidate was returned
by a real search engine. An altered
search strategy can otherwise leave frozen total source/search counts intact
while invalidating the direct/planning comparison. These checks only establish
internal consistency with version-controlled runner behavior, **not** that
searches occurred or retrieved source documents are authentic.
This catches tampered nested retrieval records even if the frozen aggregate
counters and URL partitions agree. It does not demonstrate that a search
engine returned those candidates, or that URLs were genuinely visited.
A separate provider-usage
concordance check now requires each recovered model's nonnegative integer call
and token counters, positive call count, zero unavailable-usage calls, and
`total_tokens = prompt_tokens + completion_tokens`; their sums must exactly
match the trace-level prompt/completion/total token counts and model-call
totals. This mirrors the original treatment runner's complete-provider-usage
contract, so unchanged frozen aggregate CSV counters cannot hide a corrupted
per-model cost basis. The recovery diagnostic now also requires a finite,
nonnegative original trace latency equal to the frozen treatment CSV latency,
and independently recomputes each treatment's cost from the captured per-model
token ledger using the dated *uncached* price table in the original treatment
checkout. That table is SHA-256-bound to historical workflow run 34620917346
(source commit `c3c15e46a8eec3a8bbc24c968eedc0548172a897`;
file digest `35eb6aea8a4e494ea6b94a0905e893849958d37ac386915aac7958b00c4eeace`).
An unknown priced model, mismatched cost or latency, or edited/missing pricing
source blocks content readiness. Costs use the historical `math.fsum` method
with a small floating-point tolerance; they are research estimates, **not**
independently authenticated provider billing, real-world charged costs, or
evidence about cached-token discounts. This does **not** prove any
URL was actually retrieved, link any individual source to a report claim, or
authenticate historical archive bytes. It also reads each corresponding Markdown report, rejects empty or non-UTF-8
content, and checks the whitespace-split word count against the frozen trace
and treatment CSV. The original runner recorded `len(report.split())` before
writing that unchanged text to Markdown; the new comparison catches nonempty
replacement/truncated reports whose counts differ. This prevents a matching
*filename* from masking a different embedded task, swapped trace,
report-path substitution, truncated JSON, empty report, or changed report length. Separately
recovered trace/report directories are supported without copying them into
the repository. Unreadable, unstable, oversized, or internally contradictory
sources add `original_trace_report_content_alignment` as a blocker. The
output deliberately contains no report text or new research scores.
`40_trace_report_contents_align_to_frozen_cells_not_authenticated` is
**still diagnostic only**: even valid internal metadata cannot authenticate
historical bytes, confirm report custody, prove exact text correspondence to
the automated evaluator, or substitute for the independently pinned integrated
handoff. A substituted report with the same word count can still pass this diagnostic:
word-count concordance is **not** a report-content hash, exact text match to
the original evaluator, or independently authenticated custody. The read-only
preflight additionally runs the **same source/runtime-pinned annotator-facing
content validator used by the actual packet builder** on every frozen research
question and recovered Markdown report. It blocks candidate readiness if
rendered text, Markdown links/attributes, images, or raw HTML could reveal
treatment/coordinator markers or hide treatment identity; a changed content
validator contract also fails closed. This is an early blinding and distribution
safety diagnostic, **not** independent authentication, approval to distribute,
or evidence that any annotator has rated a report. A different, non-leaking
report of the same length can still pass. Mutable directories are not an atomic
snapshot.

### Exact run-by-run recovery targets for partial backups

The coordinator-only JSON field `expected_recovery_paths` lists the **exact**
missing or unsafe archived files for each frozen treatment/task/run ID, even
when zero or fewer than 40 traces have been recovered. It derives the expected
file names from the already published, fingerprint-verified evaluator CSV,
**not** from filenames found in a partial archive. Entries contain the
treatment, task ID, historical run ID, path relative to `--trace-root` or
`--report-root`, and the reason (`missing`, `unsafe_file_type`, etc.).
The separate `traces_present` and `reports_present` counts tally only
ordinary file candidates; neither count proves their contents. The list can
guide targeted searches in authorized local/offline backups, without
regenerating or cherry-picking experimental outputs.

If the published automated-input anchor cannot be verified, status is
`not_checked_without_published_input_anchor` and **no run identities are
asserted**. If its evaluator run-ID matrix is invalid, the result is blocked
rather than presenting misleading missing-file targets. Even
`expected_paths_present_not_authenticated` verifies only expected paths,
not historical custody or report integrity. Keep the receipt coordinator-only
and never distribute run/treatment mappings to blinded annotators.

When a historical manifest-file SHA-256 is supplied, the inventory now compares
it against the bounded, descriptor-captured bytes of the corresponding research
or coordinator manifest. A mismatch, missing/unsafe manifest, or unstable/oversized
capture is an explicit blocker; syntax-valid pins alone no longer satisfy the
readiness preflight. `pin_matches_file_not_authenticated` means only that the
local bytes match the supplied value, **not** that the pin has trustworthy
independent historical custody. Never compute a new pin from a suspect archive
and present it as an earlier retained fingerprint.
Even the zero-blocker
`candidate_inputs_present_not_verified` status is **not** an acceptance receipt.
The command performs bounded, read-only inspection of recovered report and
trace contents, but never reads rating submissions or a blinding key, writes
files, or calls live APIs. Matching trace counters are corroboration, not a
cryptographic match to the original report bytes or independent authentication
of archival custody. Even with external
archive roots, the full handoff verifier requires approved original evidence
staged in its documented source layout, with independent archival pins. `--require-candidates` exits nonzero for missing inputs.

## Accept only independently retained evidence

1. Search authorized offline storage or archival exports for the **unchanged**
   completed 40 experimental traces and each trace's associated Markdown report,
   preserving original paths and original bytes. Do not regenerate treatments
   or choose newer/better reports to fill missing cells.
2. Recover the original coordinator packet and both treatment-blind
   counterbalanced distribution bundles, if already created. If they were
   never generated, distinguish first-time prospective packet preparation from
   recovery of historical source reports; do not describe new packets as
   historical originals.
3. Recover the original research-input manifest JSON and the coordinator
   manifest. Their file-byte SHA-256 hashes must be obtained from independently
   retained trustworthy records, not recomputed from possibly altered copies.
   The published aggregate `4e94308472e87cc14b85e5911c40b5f72c63225862a347e624fc0725afd632aa`
   is **not** either manifest-file hash.
4. Only once genuine sources and independent pins are available, run
   `python -m scripts.verify_human_eval_automated_handoff` as documented in
   `docs/HUMAN_EVAL_AUTOMATED_HANDOFF_GATE.md`. Investigate mismatches; never
   rewrite the inputs, re-pin inconsistent archives or rerun treatments to
   obtain a passing result.
5. Retain the approved coordinator receipt separately and verify actual
   delivery copies against its individual bundle-manifest hashes before
   independent blinded scoring by two eligible annotators.

The pilot remains diagnostic, automated confirmatory findings remain frozen,
secondary/Pareto observations remain exploratory, and **human validation
remains pending**. Neither the inventory nor a passing archival handoff
constitutes an independent human judgment.


## Production packet task-source identity gate

The command-line entry point `python -m scripts.build_human_eval_packet`
now requires the supplied `--task-manifest` to match the **exact original
treatment-run task-manifest bytes**, SHA-256
`5701df80036edb354f4f7d1efc409ea8f554a215f8c37da9d1a0b8ed01fdfd5f`
from source revision `c3c15e46a8eec3a8bbc24c968eedc0548172a897`.
It checks the already captured source fingerprint before reading traces or
creating any annotator-facing/coordinator outputs. Agreement between an
altered task manifest and correspondingly altered trace questions is no
longer sufficient for the **production CLI** to generate a packet. The
subsequent prepublication source-window recheck still protects the captured
task bytes and filesystem identity.

The lower-level Python `build_packet` API keeps
`require_original_task_manifest=False` for deliberately synthetic/offline
test fixtures; callers preparing genuine study packets must set it to
`True` (the CLI does so unconditionally). The original task-source pin is
a version-controlled checkout identity, **not** an independently retained
hash of the recovered 40 traces/reports, proof of archive custody, approval
to distribute any packet, or evidence of human validation. The separate
independent automated-handoff and original-evidence gates still apply.

## Fail-closed numeric parsing in packet source evidence

The offline blinded packet builder reads the frozen task manifest and every
candidate treatment trace through one duplicate-key-rejecting JSON parser.
This source boundary now also rejects the nonstandard `NaN`/`Infinity`
constants, ordinary JSON exponents that overflow finite floating-point values
(e.g. `1e400`), overlong integer/floating-point tokens, and unparseably deep
JSON objects. The policy applies recursively, including metadata not used for
blinded report selection. A malformed source must not pass merely because a
particular field is ignored by the packet builder. Ordinary finite JSON
numbers and `null` remain valid; duplicate-key checks remain in force.

These checks are **prospective source-input integrity safeguards**. They do not
establish that the original 40 treatment traces or Markdown reports have been
recovered, authenticate historical custody, establish source-to-evaluator
continuity, or authorize human-evaluation distribution. The tests are entirely
synthetic and do not change the frozen automated confirmatory results, the
exploratory analyses, the human rubric, or the pending human-validation status.

## Run-scoped artifact metadata self-link attribution (prospective audit guard)

The read-only `audit_historical_workflow_artifacts` inventory now checks both
`url` (the GitHub artifact **metadata** endpoint) and
`archive_download_url` (the ZIP endpoint) against the same pinned
repository and artifact ID. Previously it checked the ZIP link but could
accept a missing, substituted, cross-repository, or wrong-ID metadata
self-link even when a listing's name, `workflow_run` attribution, and ZIP
link otherwise matched. The self-link check is required for each listed
artifact, not only the named recovery candidates; ambiguous records fail
closed instead of being called unavailable or recovered. Synthetic offline
tests exercise the rejection cases and the unchanged canonical-link path.

This is **only consistency checking of GitHub-reported metadata**. It does
not authenticate original ZIP bytes, recover historical reports or traces,
establish external archive custody, permit blinded packet distribution, or
change pilot, frozen automated confirmatory, exploratory, or pending human
validation results.


### Replay a saved recovery-triage receipt

A saved JSON inventory can be altered or detached from the ZIPs originally
inspected. The separate **read-only** replay tool recomputes all candidate rows,
negative observations, candidate order, duplicate links, and batch resource
budgets against the same explicit archive paths/roles in the same CLI order:

```bash
python -m scripts.triage_historical_archive_candidates \
  --original-treatment /authorized/original.zip \
  --evaluator-recovery /authorized/recovered.zip > triage-receipt.json
python -m scripts.verify_historical_archive_triage_receipt \
  --receipt triage-receipt.json \
  --original-treatment /authorized/original.zip \
  --evaluator-recovery /authorized/recovered.zip
```

For **structurally verified ZIPs**, replay compares their present-day
SHA-256/size and content inventory, so a changed candidate cannot silently
satisfy the saved receipt. For **missing, corrupt, rejected, or budget-skipped
candidates**, the triage receipt contains no verified source-byte digest:
different invalid byte streams can produce the *same* failure diagnostic.
The replay tool therefore returns a diagnostic-only partial result
(`diagnostic_inventory_replayed=true`,
`full_recorded_inventory_replayed=false`, with 1-based
`unverified_candidate_indexes`) and exits **nonzero** after printing it.
A repeated failure message is never treated as proof that the failed source
bytes were unchanged. Preserve negative observations for investigation, but
do not use a partial receipt replay as an affirmative source-continuity gate.

A complete replay fails closed on changed verified source bytes, reordered or
relabelled candidates, changed status/count/budget values, JSON type
substitutions, duplicate JSON keys, or an oversized/linked/unstable receipt.
Before scanning candidate ZIP bytes, a bounded JSON parse and strict
ordered-roster check reject excessive nesting, oversized numeric tokens,
nonfinite ordinary JSON exponents, missing/reordered candidate rows, and
changed index/role/filename declarations. Invalid receipts therefore cannot
force avoidable batch ZIP reads or decompression merely to establish an
already-obvious mismatch. Later full replay still independently checks every
recorded candidate's observed status, hashes, duplicate links and budget
accounting; the early roster check is not a historical custody proof.
Before any ZIP rescan, the verifier now cross-checks the saved receipt's\nfixed non-authentication/readiness declarations, role-level candidate and\nprovider-concordance counts, duplicate/budget-skip counters, and bounded\nresource reservations. Boolean-as-integer substitutions and impossible\nbudget values fail closed. This avoids expensive source I/O for a receipt\nthat already contradicts its own research-integrity or accounting contract;\nfull byte-for-byte inventory replay is still required after this preflight.\nThis check does not authenticate historical execution, backup custody, or\nhuman-evaluation readiness.\nThe replay additionally rejects impossible candidate-level source claims **before**
scanning any ZIP bytes. The receipt's declared ZIP size and SHA-256 must agree
with the pinned historical GitHub-provider digest for its declared role (or
the other role, if explicitly reported), the associated status and booleans,
and first-seen duplicate-source indices. Verified and failed rows must carry
their respective exact fields and numeric types. This is a fail-fast,
resource-safety and provenance-consistency check of the *saved receipt*, not
proof that a ZIP currently contains those bytes: the full bounded replay is
still mandatory. It never authenticates independent original custody or
unblocks blinded human evaluation.

Its complete success result fingerprints the exact saved receipt bytes; it
does not modify or extract candidate ZIPs.
It requires a new bounded scan, so budget for that I/O separately. The receipt
contains only filenames, not backup-directory paths: preserve the original
exact command and independent custody records separately. Success proves
only present-day consistency with the recorded GitHub **same-provider** metadata,
not independently authenticated historical reports/traces, a valid human
evaluation handoff, or any human scores. No treatments/evaluators are rerun.

## Complete receipt-schema and interpretation preflight

The replay verifier now checks the **complete** top-level schema of a saved
historical-candidate triage receipt, including the producer's exact research
interpretation text, **before** reading candidate ZIP bytes. Missing or extra
fields and edited, omitted, or non-string interpretations are rejected even
if all archive hashes and counters would otherwise match. The producer's
interpretation remains the same; it is shared with the read-side verifier to
prevent a duplicate, drifting copy of the scientific qualification.

Malformed candidate status types, including JSON objects or arrays in a failed
candidate row, also fail with a controlled verification error before ZIP I/O.
This keeps corrupt receipts from inducing needless bounded archive rescans or
an uncontrolled type error. Synthetic offline tests cover both valid producer
receipts and these altered-claim cases; no experimental or human data is used.

This is **local receipt integrity**, not proof of independently retained
historical report/trace custody. Neither a clean receipt nor its successful
replay permits blinded distribution, establishes human ratings, or changes the
diagnostic pilot, qualified frozen automated results, or exploratory analyses.
