## Original source-outcome ordering (28 November 2026)

The pinned treatment implementation (commit `c3c15e46`,
`logic/research_agent.py`) awaits each query sequentially and appends
successful and failed URLs by iterating `zip(new_search_urls, responses)`
after `asyncio.gather`. Gather returns responses in input order, not
completion order. Consequently each outcome ledger is an ordered
projection of the scheduled URL ledger. Set partition and frozen source
counts alone previously accepted reversed outcome ledgers.

Archive readiness now requires the exact relative scheduling order within
both outcome ledgers. Synthetic full-matrix regressions reverse successful
URLs in direct and planner arms without altering frozen counters; focused
tests cover both outcome ledgers and valid interleaved successes/failures.
This checks source-contract consistency, not browser completion timing,
actual retrieval, historical custody or human validation. It does not
modify or rerun any treatment, evaluator, or frozen result.

## Combined source snapshot path custody (26 November 2026)

The source-concordance comparator fingerprints both historical archives
before their structural audits and again at combined comparison checkpoints.
These preliminary hash reads previously used a leaf-only no-follow open:
a symlinked parent could be followed, a hard-linked ZIP could be hashed,
and redirecting a parent to the relocated original directory could preserve
the leaf inode and bytes. Later structural or semantic checks are not a
substitute for safe preliminary reads. The combined snapshots now reuse
the structural preflight's descriptor-relative, pinned-parent opener,
reject multi-linked archives before hashing, and translate preflight
failures to the comparator's error type. Synthetic regressions cover a
stable nested ZIP, ancestor symlinks, parent traversal, hard links, and
an observed parent redirect preserving the leaf inode and digest.

This is local observation-window custody, not an atomic filesystem
transaction or independent authentication of the original archives. It
does not authorize human-evaluation distribution or change any frozen
scientific outcomes.

## General-purpose ZIP flag semantics (26 November 2026)

Recovery preflight accepts ordinary STORED and DEFLATE members only.
Agreement between local and central flags is not sufficient: CPython
rejects patched-data and strong-encryption flags at member open (after
decompression reservation), and can silently ignore other reserved or
unsupported flags. The metadata check now permits only the streaming
descriptor and UTF-8 filename flags, plus DEFLATE's two compression-option
bits. Encryption remains separately rejected. Unsupported flags fail
before any decompression reservation, while raw ZIP reservations remain
spent. Synthetic regressions cover unsupported bits in matching headers
and valid flag combinations with unchanged member digests; existing
streaming descriptor and Unicode-name tests remain applicable.

This enforces the supported recovery format, not historical authenticity.
It does not recover reports, authenticate original custody, authorize
human distribution, or change frozen or exploratory scientific results.

## ZIP64 locator ambiguity in recovered ZIPs (26 November 2026)

An ordinary, bounded end-of-central-directory (EOCD) record is not enough
to rule out ZIP64 parsing. CPython also probes the 20 bytes immediately
preceding the selected EOCD for a ZIP64 locator, regardless of ordinary
EOCD sentinel values. A central member comment can contain a ZIP64 record
and locator at that position, overriding the preflight's directory size
and offset before the eager ZIP parser runs. A synthetic archive reproduced
this discrepancy with the same readable report but a silently discarded
member comment. Preflight now rejects the locator signature at that exact
position before constructing ZipFile, even for a maximum-length archive
comment. Non-probed occurrences remain allowed. This intentionally
conservative rule enforces the existing non-ZIP64 recovery contract; it
does not establish independent custody or authenticate historical evidence.

## Local ZIP filename checks before decompression reservation (26 November 2026)

A local filename differing from its central-directory record was previously
detected only by opening the member after charging the batch decompression
budget. A structurally invalid earlier candidate could therefore prevent
inspection of a later intact candidate even though no decompression was
necessary to detect the discrepancy. Preflight now compares the original
encoded local filename with the central filename during bounded metadata
inspection, before reserving decompression. Both UTF-8 and legacy CP437
names are supported without rewriting. The raw archive reservation is
still spent, and genuine post-reservation integrity failures still receive
no refund. Synthetic tests cover a mismatched final member, malformed local
UTF-8, valid encodings, and a two-candidate batch under a tight budget.
This is structural verification only, not independent historical
authentication or human-evaluation readiness; no treatment or rating was
generated.

## Portable directory identity in recovered ZIPs (26 November 2026)

Checking only full normalized member paths misses aliases of implicit
directories: `Reports/a.md` and `reports/b.md` have distinct normalized file
keys, but their directory structure differs between case-sensitive and
case-insensitive extraction. Compatibility-equivalent Unicode directory names
have the analogous ambiguity under downstream normalization. Preflight now
records the exact original spelling of every normalized directory prefix,
including explicit directory records and implicit parents, and rejects a
second spelling before reserving decompression. It does not rename entries.
Synthetic regressions cover nested aliases, Unicode compatibility aliases,
explicit directories in either archive order, and valid shared or independent
parents. This protects portable inventory identity only; it neither recovers
nor authenticates original historical reports or permits human distribution.
No treatment, evaluator, frozen result or human rating was changed.

## Complete DEFLATE stream accounting (26 November 2026)

A ZIP reader can report a matching CRC and declared output size even when
the raw DEFLATE stream has no end marker, has trailing compressed bytes, or
decodes to additional output beyond a declared prefix. After reserving the
existing declared uncompressed-byte budget, recovered-ZIP preflight now
decodes each DEFLATE member directly from its verified local payload offset
using bounded input and output chunks. It requires the stream to reach EOF,
consume exactly the declared compressed payload, and match the declared
uncompressed size and CRC, including empty directory entries. At most one
extra output byte is decoded to detect an understated size. Local filename
and flag checks still use the standard ZIP reader. Synthetic regressions
cover missing stream termination, trailing bytes, understated report and
directory output, and valid multi-chunk/empty entries. This establishes
complete stream accounting, not canonical compression encoding or
independent historical archive authenticity.

## Stored ZIP payload accounting (26 November 2026)

The standard ZIP reader can return a CRC-valid prefix of an uncompressed
(STORED) entry when the declared uncompressed size is smaller than the
stored payload. Even an ostensibly empty directory can conceal bytes.
The recovery preflight now requires equal compressed and uncompressed
sizes for STORED members before reserving decompression or hashing member
contents. Synthetic tests construct consistent local/central headers with
a prefix CRC, demonstrate ordinary reader acceptance, and require rejection
of both report and directory cases. Valid empty and nonempty STORED entries
remain supported. This check is not a general proof of DEFLATE stream
canonicality or historical archive authenticity.

## Original ZIP member name integrity (26 November 2026)

Python's ZIP reader can silently truncate a decoded filename at an embedded
NUL even when both local and central headers contain that same malformed name.
A safety check on the already-truncated filename would then hash and inventory
a different path from the one recorded in the archive. The recovered-ZIP
preflight now rejects any member for which the reader's original decoded
filename differs from its exposed filename, before reserving decompression
or reading member contents. Synthetic regressions patch both headers with
embedded and terminal NULs, including a UTF-8 filename, and confirm that
ordinary ZIP reading would otherwise accept the rewritten name.

This is a structural path-identity check only; it does not authenticate
historical custody, recover reports or authorize human evaluation.

## Candidate receipt reservation accounting (26 November 2026)

Before reopening any candidate ZIP, schema-v3 receipt replay now checks the
declared batch reservations against the recorded per-candidate dispositions.
Every structurally verified archive spent its exact observed raw byte count;
a decompression-budget rejection already spent a positive raw size, while an
archive-budget rejection spent neither reservation. Structural failures may
have spent either reservation, so only conservative upper bounds apply to
their unknown sizes. A fully verified roster must have a raw reservation
equal to the sum of its observed archive sizes, including duplicate backups.

The new synthetic regressions reject impossible in-range reservation totals
before ZIP I/O, including mixed failure/skip inventories. This is an early
internal-accounting check, not authentication or a substitute for full ZIP
replay. Original report/trace custody, blinded human distribution and genuine
human ratings remain pending; no treatment, evaluator or outcome was changed.

## Ordered candidate declaration snapshot (26 November 2026)

The direct archive triage API previously validated the caller's mutable roster,
then iterated it again during ZIP inspection. A mutation could substitute a
different role/path or append unvalidated candidates after the 16-candidate
limit had been checked. Receipt replay also reread the caller roster after
opening the receipt; switching to a different directory's same-basename ZIP
could make a receipt appear to replay against the intended candidate.

Both paths now use one bounded, copied ordered role/path roster. The candidate
limit applies to actual iteration, not a reported sequence length; duplicate
paths and invalid declarations are rejected before candidate reads. Synthetic
regressions exercise in-place row edits and roster growth during archive
inspection, an underreported count, and a same-basename substitution during
receipt capture. The immutable roster is reused for all subsequent accounting
and replay. It does not guarantee an atomic view during initial roster capture
or authenticate any historical archive; original report/trace custody and
genuine human validation remain pending. No treatments, evaluators, frozen
outcomes or human ratings were generated or changed.

## Coordinator packet output directory custody (19 November 2026)

The offline human packet builder previously rejected a symlink at its output
*leaf* but used ambient pathnames for four publications. A symlinked parent
could silently redirect the coordinator-private blinding key and seed-bearing
manifest. Publication now requires no-follow directory support, pins the entire
visible output ancestry, creates each artifact exclusively relative to the held
output-directory descriptor, and hashes the same pinned files. It rechecks the
ancestor chain after each publication, including the private key, and refuses
an initial symlink ancestor. Synthetic tests cover direct and intermediate
ancestor aliases and replacement of the visible output root with an external
symlink immediately before publishing the private key. The write remains in
the originally opened directory, and the operation fails closed rather than
publishing under the replacement pathname. Interrupted partial outputs remain
create-only and must never be reused.

This is local output-path/secret custody, not independent historical source
attestation, protection against an attacker already controlling the original
directory, authorization to distribute any blinded reports, or proof of
human scores. The original report/trace sources remain unavailable; the pilot
is diagnostic, historical automated findings remain post-collection/fixed-order
and evaluator-qualified, retrospective work is exploratory, and genuine human
validation is pending. No treatment, evaluator, frozen result or human rating
was regenerated.

# Recover the original automated-to-human VERA evidence (no outcome reruns)


## Candidate-triage receipt ancestor path custody (17 November 2026)

The offline schema-v3 candidate-triage receipt replay previously checked the
receipt leaf's regular-file identity, size and timestamps before and after the
read, but opened it through the ambient pathname. A symlinked ancestor or a
parent swapped to a symlink pointing at a **relocated copy of the same directory**
could pass those leaf-only checks; the receipt bytes and inode need not change.

The read-only receipt reader now opens each directory component using
descriptor-relative, no-follow operations, rejects explicit \`..\` traversal and
symlinked parents, and rechecks that the visible ancestor chain still identifies
the opened directories after reading. This is fail-closed on platforms without
the required no-follow directory-opening facilities. Synthetic regression tests
cover ordinary nested paths, initial symlink aliases, parent traversal, and an
after-open parent alias swap preserving the receipt inode.

This protects **local receipt source-path continuity** before any potentially
large candidate ZIP rescan. It is not an independent historical source pin,
does not authenticate original trace/report custody, and cannot authorize
blinded human distribution or fabricate ratings. The five-task pilot remains
diagnostic; frozen automated findings have post-collection, fixed-order and
evaluator-comparability limitations; retrospective sensitivity analyses remain
exploratory rather than prospective confirmatory evidence. No experimental
treatments, evaluator outputs or frozen outcomes are changed.

## Original treatment duration/UTC-start nonoverlap (17 November 2026)

At pinned treatment source `c3c15e46`, `logic.run.run_agent` records
`started_at_utc` from the UTC wall clock and `latency_seconds` from
`time.perf_counter()` in the same completed run. The main-study runner awaits
each `run_agent` before starting its next treatment cell; it does not execute
D3/D6/P6/P6V cells concurrently. A recovered 40-cell matrix could previously
pass all individual frozen-CSV duration checks and strictly ordered start
timestamps while making **completed run intervals grossly overlap**.

The read-only archive consistency diagnostic now compares each completed
run's frozen-aligned monotonic duration with the wall-clock gap to the next
task-interleaved run. It rejects gaps more than **five seconds shorter** than
the preceding duration. The five-second allowance is an intentionally
conservative local clock-domain tolerance, **not** a measured bound on historic
clock drift or independent timestamp attestation. Synthetic full-matrix tests
exercise within-task and between-task gross overlaps while preserving frozen
CSV agreement, plus a small permitted cross-clock discrepancy.

This is an **internal plausibility gate**, not a reconstructed schedule,
proof of sequential historical execution, independent artifact custody, or
source-authenticated permission to distribute blinded packets. The original
trace/report archives remain missing; the pilot remains diagnostic, historical
automated findings retain post-collection planning, fixed-order and evaluator
comparability limitations, retrospective work is exploratory, and prospective
confirmatory/human validation is not established. No treatment, evaluator,
frozen outcome or genuine human rating was rerun or altered.

## Original treatment run-start chronology and interleaving (17 November 2026)

At the pinned September 2026 treatment checkout (c3c15e46), the ten frozen
tasks ran sequentially with **D3, D6, P6, P6V interleaved for each task**;
the runner stops on failed treatments rather than selecting replacements.
The original logic.run.run_agent persisted a timezone-aware UTC
started_at_utc in every trace. GitHub's original treatment Actions run
34620917346 records run_started_at=2026-09-11T16:15:15Z and
updated_at=2026-09-11T17:22:43Z (whole-second provider metadata). These
times belong to the original treatment run, not evaluator-only recovery.

The read-only archival preflight now rejects missing, malformed, naive,
non-UTC or out-of-window trace start times and an otherwise internally aligned
40-cell matrix whose timestamps contradict the original task-interleaved
execution order. The provider-reported last second is inclusive. Offline
synthetic regression cases exercise within-task reversal, between-task
reversal, malformed/out-of-window clocks and valid sequential timestamps.
This checks **temporal treatment-exposure plausibility** even when frozen
source counts, model-usage costs, latency and report metrics still agree.
It does not reconstruct missing timing or remove the acknowledged fixed-order
confounding limitation.

Same-provider workflow times and self-reported trace starts are not
independent clock attestation, authenticated ZIP/report custody or proof
of genuine treatment execution. Original artifacts remain unavailable and
blinded human distribution still needs independent source-pinned custody.
The five-task pilot stays diagnostic; published automated analysis remains
post-collection with fixed-order and evaluator-recovery qualifications;
retrospective sensitivity work is exploratory, not prospective confirmatory
evidence or completed human validation. No treatments, evaluators, frozen
outcomes or human ratings were rerun, selected, fabricated or changed.

## Historical provider-accounting model identity (16 November 2026)

The pinned September 2026 treatment runner (commit `c3c15e46`) creates one
`UsageTracker` for each research run. Treatment-agent completions use the
shared `CFG.smart_llm_model` or `CFG.fast_llm_model`; the tracker indexes
`provider_usage_by_model` buckets by the requested model argument, not a
provider-returned alias. The trace independently records both runtime
model controls. After ledger and frozen-cost consistency checking, the
recovered-archive auditor now rejects provider usage bucket names outside
those two recorded controls. Both keys need not appear: one model may
remain unused, and smart/fast controls may have the same name.

Before this safeguard, a differently named model with identical frozen
prices could replace a bucket without altering token, model-call, latency
or cost measurements, obscuring treatment-model comparability. Synthetic
40-cell regression tests cover both priced unauthorized substitution and
legitimate two-model ledger accounting.

This is an outcome-blind **internal plausibility diagnostic**, not proof
of the actual model served by a provider or independent custody of any
historical report/trace. It does not revise the five-task diagnostic pilot,
the post-collection automated estimates or exploratory sensitivity bounds,
establish prospective confirmatory findings, or complete real human
validation. No treatments, evaluators or human ratings were regenerated.

## Historical treatment-time verification consistency (16 November 2026)

The pinned September 2026 ResearchAgent.write_report invoked the
**treatment-time claim verifier** only for the P6V arm, after writing its
report. A completed P6V trace therefore records either
verification_status="ok" with citation_count equal to the sum of
supported, partially supported, unsupported, and contradicted claims, or
verification_status="parse_error" with all five claim counters zero.
Completed D3/D6/P6 traces instead record verification_status="not_requested"
and zero treatment-time claim counters.

The read-only 40-cell archival readiness auditor now checks this distinction
and rejects absent, type-confused, negative or inconsistent counts and arm
status. Synthetic full-matrix cases include a false P6V "not_requested",
falsely verified D3, parse failure with fabricated claims, and count mismatches
despite unchanged frozen CSV source/cost/token outcomes. This addresses
**treatment exposure fidelity**, not the separate *common post-hoc support
evaluator*: "parse_error" is a legitimate completed P6V treatment verifier
response, not an excuse to replace or rerun the cell.

These checks establish only internal plausibility relative to the historical
runner. They cannot authenticate expired original reports or traces, prove
what an external model actually returned, or authorize blinded distribution.
The pilot remains diagnostic, frozen automated findings retain their
post-collection planning, order and evaluator-comparability qualifications,
and human ratings and prospective confirmatory evidence remain absent.
No outcomes, original treatments or evaluator calls have been changed.

## Historical metasearch outcome/exception ledger (16 November 2026)

The September 2026 original treatment checkout
`c3c15e46a8eec3a8bbc24c968eedc0548172a897` calls
`web_search(query, num_results=candidate_limit)` only for positive query
allocations. That search implementation returns a **nonempty** normalized
candidate list when a backend responds, or raises `RuntimeError` after
all fixed backend-pool attempts fail. The treatment's `async_search`
persists the exception as a `search_error` field truncated to 1,000
characters, with empty candidate and scheduled lists.

The read-only recovery auditor now rejects a claimed successful search with
**zero candidates and no error marker**, as well as empty or overlong
error markers. A legitimate bounded error and later planned queries remain
valid. Previously the same URL, budget, source-count and search-call ledgers
could conceal a fabricated no-results outcome. Synthetic direct checks and
a forty-cell diagnostic integration regression cover this distinction;
the common synthetic fixture now records its intentional search outages.

This tests **internal plausibility against historical source**, not actual
provider calls, archival byte custody, the cause of any outage, or independent
authentication of the original reports and traces. Blinded human distribution
and actual ratings remain blocked, the pilot stays diagnostic, frozen
automated comparisons retain their timing/order/evaluator qualifications,
and the new test is exploratory provenance checking rather than confirmatory
or human-validation evidence.

## Historical planned-search execution completeness (16 November 2026)

The read-only recovered-trace consistency diagnostic now checks **query
invocation completeness**, in addition to the prior URL/candidate-budget and
search-order ledgers. In the original treatment checkout
`c3c15e46a8eec3a8bbc24c968eedc0548172a897`,
`ResearchAgent.conduct_research` attempts each planned query with a positive
per-query allocation while the global browse budget remains. A search outage
produces an error record; it does not silently skip that query. Previously
the archive audit allowed an omitted *eligible* middle query or trailing
query, accepting later records and coherent candidate/URL totals. It now
rejects both cases while permitting zero-allocation slots and legitimate
recorded search errors; synthetic regressions cover each boundary.

This is only **internal consistency against original runner code**, not
independent authentication of a historical archive. Source-custody pins,
40 original reports and traces, blinded distribution and genuine human
ratings remain outstanding. No pilot, frozen automated, exploratory or
human-validation outcomes are changed or inferred.

## Whole-matrix candidate observation window (16 November 2026)

The read-only original-archive readiness diagnostic now binds each of the 40
candidate JSON traces and 40 Markdown reports to its captured SHA-256 and
filesystem generation (device, inode, mode, hardlink count, size, mtime,
ctime). After all per-cell frozen-input and report-content checks, it
**re-reads every candidate** and rejects persistent replacement or rewrite,
including a byte-identical atomic replacement or an in-place same-size edit
with restored mtime. Previously individual captures could all be internally
stable while earlier sources changed before the full-matrix status was
returned. An observed change now blocks readiness instead of producing a
misleading complete 40-cell consistency finding. Synthetic tests cover
unchanged candidates, rewrites, replacements, and redirected parent paths.

This is a two-observation local consistency check, not an atomic snapshot;
transient replace-and-restore cannot be ruled out. Historical report/trace
custody remains unauthenticated; independent source-pinned handoff and actual
human raters are still required. No treatment or evaluator was rerun,
frozen result changed, or human rating generated.

## Recovered ZIP ancestor-directory custody (14 November 2026)

The read-only offline candidate-ZIP preflight now opens each directory
component from the filesystem root using pinned, descriptor-relative
`O_NOFOLLOW` opens, then rechecks those ancestors before it accepts a
structural ZIP receipt. Previously, no-follow protection covered only the
ZIP leaf: a stable symlink in an upper backup directory could redirect
an apparently regular candidate, and replacing a parent directory with
a symlink back to the **same opened ZIP inode** could escape final
file-inode and digest comparisons. Explicit `..` parent traversal and
platforms lacking these directory-open safeguards fail closed.

Synthetic regressions reject pre-existing ancestor aliases *before ZIP
hashing*, and a post-open ancestor swap even where the original archive
bytes and inode remain identical. Nested ordinary directories still pass.
The existing batch triage and receipt replay inherit the source guard;
the offline packet CI lane now tests it directly. This establishes only
present-day local candidate-path consistency. It does **not** recover
original expired treatment/evaluator artifacts, establish independent
historical custody, authenticate original reports/traces, authorize
blinded human distribution, or change pilot, frozen automated, exploratory,
or human-validation claims.


## Indirect source-directory alias custody (14 November 2026)

Original-source capture now opens **each absolute directory component** from
the filesystem root with a no-follow directory descriptor, not just the
immediate leaf parent. It rechecks directory identity from those pinned
descriptors after the captured file read and before accepting source bytes.
This rejects an indirect symlink such as `backup-alias/outputs/experiment_traces`
where the trace file, variant directory, and leaf parent themselves are
regular paths, as well as observed ancestor replacements during capture.
The guard applies to the frozen task manifest, treatment traces, reports
and pinned evaluator inputs, including prepublication rereads.

Synthetic negative tests cover alias-based task-manifest and trace-tree
substitutions; a positive nested-path fixture preserves ordinary reads. This
is a prospective local path-custody check on platforms supporting
`O_NOFOLLOW`/descriptor-relative opens, **not** an external archive
attestation, a guarantee against every concurrent filesystem adversary, or
proof that the historical reports actually exist. Original treatment and
evaluator-recovery archives remain independently unauthenticated; blinded
human packet distribution remains blocked. No frozen automated scores,
pilot findings, exploratory sensitivities, or human ratings were changed.

## Single-link original-source preflight (14 November 2026)

The offline human-evaluation packet builder now fails closed if a captured
task manifest, treatment trace, Markdown report, or pinned evaluator input
has more than one filesystem hardlink. An additional hardlink is an alternate
writable path to the **same inode**, even if the source bytes and SHA-256
currently match; checking only symlinks or reuse of a report *within* the
selected matrix does not detect an unselected external alias. Source
capture also rechecks file mode and link count against the opened descriptor
and pathname, alongside inode, size, and mutation timestamps. This applies
to source prepublication rereads as well as initial capture, before any
annotator-facing file is reserved. Synthetic tests cover unselected external
aliases for each source category and reuse of one report across two cells.

This is a prospective local custody guard, **not** proof of independent
archival provenance or of the original treatment/evaluator report contents.
It does not recover expired GitHub artifacts, establish an independent
attestation, authorize human-evaluation distribution, modify the frozen
automated results, or generate human ratings. Any legitimately deduplicated
source archive must be restored as distinct regular files and independently
authenticated before packet publication; no scientific evidence is silently
replaced by this check.

**Status (2026-11-05): blocked on original report and handoff custody.**
This is an operational inventory and recovery plan, not an experiment or human-evaluation result.

## Retained canonical provider-metadata file custody (2026-11-12)

Before making any read-only historical Actions metadata request, the inventory
checks the byte-pinned canonical-analysis provider record in the checkout.
The preflight now rejects hardlink aliases as well as symlinks, and requires
the opened descriptor and the pathname after capture to identify the same
single-link regular file (device, inode, mode, link count, size, and modification
metadata). This detects a byte-identical atomic replacement or unlink during
capture; matching SHA-256 bytes alone cannot demonstrate stable source custody.
Offline synthetic tests cover a hardlinked byte-identical record and a same-byte
replacement during the read, without requesting GitHub data or running models.

This guards only the *local retained provider metadata input*; its hash is pinned
inside this repository, not to an independently held external attestation. It
cannot recover unavailable original report/trace ZIPs, authenticate those
experiments, or authorize human annotation. Original experimental evidence and
independent human-validation gates remain outstanding.

## Run-scoped inventory as-of chronology gate (2026-11-11)

The read-only run-scoped auditor `scripts/audit_historical_workflow_artifacts.py`
now samples the local UTC start clock once and rejects explicitly supplied
`checked_at` timestamps in the future or more than 60 seconds older. These
checks occur before any GitHub API request, including both-empty-listing
cases. It additionally rejects a historical workflow or listed artifact whose
provider `updated_at` postdates the recorded observation. This prevents
a current missing/present ZIP from receiving a fictional future or historical
availability timestamp despite matching IDs, digests, and double scans.
Deterministic offline tests inject the observation clock for historical
expiry scenarios; they are not retrospective API observations.

This safeguard depends on the local system clock and same-provider timestamps;
it is not independent timestamp attestation, proof of original report/trace
custody, successful ZIP download or human-evaluation authorization. Missing
GitHub artifacts do not rule out authorized offline backups. No treatment,
evaluator, or human rating was generated or changed.

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
manifest. If the previously anchored task manifest disappears or becomes
unsafe before the content check, the audit now records
`invalid_frozen_task_or_evaluator` and adds
`original_trace_report_content_alignment` to the blockers, even when the
earlier resource inventory was complete. Such a late failure is not a
dependency skip and must not yield `candidate_inputs_present_not_verified`.
These per-capture checks do not make mutable directories an atomic
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
an internally contradictory URL/source ledger. The content preflight also
recomputes the original `RunTrace.to_dict()`'s four **redundant derived
measurements**: `source_success_rate`, `verified_claim_count`,
`claim_support_rate`, and `citation_precision_proxy`, from the archived
source and treatment-time verification counters. Missing, nonnumeric,
nonfinite or contradictory rates and claim totals block readiness, including
when all frozen CSV aggregates still match; legitimate zero-source and
zero-claim denominators yield zero. These are treatment-trace diagnostics,
**not** the common post-hoc support-evaluator scores, independent custody
authentication, new confirmatory findings, or human ratings. The diagnostic additionally
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
evidence about cached-token discounts. The recovered raw trace must also
retain the original execution-time cost-accounting semantics: at the pinned
September 2026 `logic/run.py`, every completed treatment recorded
`cost_accounting_status="not_computed_without_frozen_pricing_table"` and a
floating-point `estimated_cost_usd=0.0` **placeholder**, before subsequent
offline frozen-rate cost estimation. Missing, forged, nonfinite or nonzero
raw cost telemetry now blocks archival content alignment even if the published
frozen CSV estimate remains identical. This prevents the archive from
misrepresenting an offline research cost estimate as provider-observed billing;
it does not authenticate original custody, establish actual charges, or change
any frozen outcomes. This does **not** prove any
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


## Historical metasearch candidate-ledger preflight (2026-11-16)

The read-only archive readiness diagnostic now validates search-result
*candidates*, not only successfully scheduled URLs. The original treatment
checkout `c3c15e46` (`scrape/web_search.py` and
`logic/research_agent.py`) requested three candidates per available
browse slot (maximum 20) and normalized provider output to unique,
nonempty, trimmed hrefs. Using each arm's fixed source budget and planned
query allocation, the auditor rejects oversized, duplicate, and untrimmed
candidate lists even when frozen scheduled-source counts still match.
Valid repeated URLs **across different queries** remain allowed.

Synthetic unit and full 40-cell integration regressions verify this
historical-source contract. They do not authenticate missing original
reports/traces, prove that a search request occurred, establish historical
custody or authorize blinded human distribution. The five-task pilot stays
diagnostic, historical automated inference retains its post-collection
planning/order/evaluator qualifications, and no human-validation result or
new confirmatory evidence is created.

## Cross-checking recovered execution metadata (16 November 2026)

The pinned historical treatment implementation (`logic/run.py` and
`logic/experiment.py` at `c3c15e46a8eec3a8bbc24c968eedc0548172a897`)
saved planning mode, verification mode, and source budget both in the
`ExperimentConfig` envelope and in the per-run trace. It also copied
`browse_timeout_seconds` and `run_timeout_seconds` from the config into
the trace. A recovered archive with contradictory duplicate metadata is
inconsistent with that source, even when its 40 frozen treatment CSV rows,
source budgets, result counts, costs, latency and report words still agree.

The read-only archive-readiness audit now checks the trace's planning and
verification modes against its frozen D3/D6/P6/P6V treatment arm and
requires the exact original config and trace timeout defaults:
`browse_timeout_seconds=60.0` and `run_timeout_seconds=480.0` (JSON
floating-point values). The pinned `c3c15e46` variant factory did not
override either default, the main-study runner replaced only task IDs,
and `logic/run.py` copied the configured values into the trace.
Synthetic 40-cell regressions cover both direct/planner arm substitutions,
missing or mistyped trace mode, changed timeout values on either side,
and concordant changes to both copies (including integer substitutes).
Agreement between duplicated metadata is not sufficient to establish
fidelity to the original censoring guardrails.
This does **not** authenticate original custody, prove the guardrails were
honored during execution, recover missing artifacts, or establish a new
confirmatory or human-evaluation result. The five-task pilot remains
diagnostic; the frozen automated analysis retains its post-collection
planning, fixed-order and evaluator-comparability limitations.

## Shared execution-factor fidelity in recovered configurations (16 November 2026)

The pinned original treatment checkout
`c3c15e46a8eec3a8bbc24c968eedc0548172a897` defines
`ExperimentConfig.from_variant()` in `logic/experiment.py`.
The historical `scripts/run_budget_main_study.py` constructs every D3,
D6, P6 and P6V configuration from that method, replacing **only**
`task_set_id` and `task_id` before calling `run_agent`.
Consequently the non-treatment settings were shared across all 40
treatments: `search_candidate_multiplier=3`,
`max_concurrent_browses=2`, `stream_report=False` and
`trace_root="outputs/experiment_traces"`.

The read-only recovered-archive diagnostic now rejects missing, mistyped
or altered values for those four original execution factors. Candidate
multiplicity affects search exposure, browser concurrency affects latency
and resource pressure, and report streaming affects generation behavior.
These are distinct from the arm-defining planning, source-budget and
verification settings, and from the duplicated timeout fields already
checked. A semantically plausible 40-cell archive with mutated shared
settings can no longer be described as aligned with the original runner
merely because published outcomes and counters still agree.

Nine synthetic full-matrix adversarial cases exercise changes, missing
fields, and Python boolean/numeric equality confusion. This validation
establishes **internal source-contract consistency only**: it cannot prove
the settings were actually used, establish independent original-report
custody, restore expired Actions artifacts, or authorize human distribution.
The pilot remains diagnostic; historical automated analysis retains its
post-collection planning, treatment-order and evaluator-comparability
qualifications. No new confirmatory or human-validation result is produced.


## Runtime model-control comparability across original treatment cells (16 November 2026)

The pinned original checkout `c3c15e46a8eec3a8bbc24c968eedc0548172a897`
runs all 40 main-study treatment cells sequentially within one
`scripts/run_budget_main_study.py` Python process. `logic.run` instantiates
module-level `CFG = Config()` once and persists its `smart_llm_model`,
`fast_llm_model` and `temperature` as `smart_model`, `fast_model`,
`temperature` in **every** saved `RunTrace`. These settings are not the
planned treatment interventions: drifting settings could confound arm
comparisons without changing published browse counts, model-call counts,
token totals, estimated cost, or report lengths.

The original treatment [workflow run 34620917346](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34620917346)
identifies the checkout above. Its [job environment](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/.github/workflows/budget-main-study.yml)
explicitly sets `SMART_LLM_MODEL=gpt-5.6-terra`,
`FAST_LLM_MODEL=gpt-5.6-luna`, and `TEMPERATURE="1"`.
The original `settings/config.py` gives these environment variables
precedence over dotenv and converts temperature to a float. The recovery
preflight therefore requires **those exact configured model names and the
floating-point temperature 1.0 in every candidate**, not merely agreement
across the matrix. Synthetic regressions include uniform substitutions of
each model or temperature across all 40 cells, including a same-price
synthetic usage-ledger substitution and an integer temperature, in addition
to later-cell drift and malformed controls. No observed experimental
outcomes or historical traces have been changed.

This is **source-anchored configuration concordance, not model attestation**.
It cannot determine which particular models the original provider served,
prove the workflow environment was honored, or authenticate a recovered
archive. Independent original source custody is still needed for stronger
identity claims. Human handoff remains blocked until independent original evidence
and eligible real blinded annotators are available. The five-task pilot is
diagnostic, frozen automated results retain post-collection/ordering and
historical evaluator limitations, and this gate adds neither confirmatory
nor human-evaluation evidence.


## Saved-trace UTC persistence chronology (17 November 2026)

The pinned treatment implementation at
`c3c15e46a8eec3a8bbc24c968eedc0548172a897` calls
`logic.experiment.save_run_trace` after `run_agent` finishes its timed
run and writes a top-level `recorded_at_utc` timestamp. This is distinct
from the trace's `started_at_utc` and its independently measured
`latency_seconds`. The archived 40-cell preflight previously checked
the start order and run durations but ignored the save timestamp.

The read-only diagnostic now requires the original UTC timestamp form,
a plausible save time relative to the run start and measured duration,
the original treatment-workflow window, and a save that does not grossly
extend past the next sequential treatment start. The existing five-second
wall-clock/monotonic-clock discrepancy allowance is retained. Synthetic
tests exercise missing, malformed, off-window, prematurely recorded, and
cross-run contradictory saved timestamps without adjusting frozen results.

These checks establish *internal chronology plausibility*, not proof that
the file was actually saved at the recorded instant, independent GitHub
runner attestation, original archive custody, or the absence of smaller
clock shifts. Missing historical reports and traces still block source-
authenticated blinded distribution. The pilot remains diagnostic;
the historical automated analysis retains post-collection statistical
planning, fixed-order, and common-evaluator comparability qualifications;
exploratory audit findings are not prospective confirmatory or completed
human-validation evidence.

### Bind semantic ZIP rereads to the structurally audited source (26 November 2026)

The original/recovery source-concordance verifier performs three semantic
passes over each ZIP (saved retrieval evidence, evaluator caches, and
treatment traces/reports). Each pass now checks the already-audited archive
byte count and SHA-256 on a no-follow, single-link regular-file descriptor,
bounds the central-directory records again before constructing the eager ZIP
reader, and rechecks the descriptor, pathname, digest and parent chain after
the pass. A substituted archive must not reach semantic parsing merely because
the earlier structural audit passed. The existing combined comparison-window
checks remain in place. These are bounded local consistency checks, not an
atomic multi-file snapshot or independent historical authentication. No
treatments, evaluators or human ratings are generated.

### Portable evidence namespace completeness

The recovered 40-cell matrix inventory uses the structural ZIP preflight's
portable path identity (NFKC normalization and case folding) to detect
unselected trace/report members and to enumerate evaluator-cache candidates.
For example, an extra `backup/EXPERIMENT_TRACES/D3/hidden.json` or
`extra-run/RESEARCH_REPORT.MD` can otherwise escape a case-sensitive reserved
namespace check without colliding with any selected full path. An alternate
evaluator-cache namespace is included in the inventory so the original/recovery
concordance check rejects it. Selected paths must still match the original
case-sensitive published run identities exactly; no member is renamed or
substituted. Unrelated filenames that merely contain similar substrings are
not selected. This is a local completeness safeguard, not independent original
custody, report authenticity, or authorization for human-evaluation handoff.

The per-run saved query-output schedule check applies the same portable
namespace rule to direct `research-query-*.txt` members in each selected
run directory. An unscheduled `RESEARCH-QUERY-99.TXT` or compatibility-Unicode
alias is rejected even if it has no exact-path collision, and even if both
archive copies contain it. Scheduled files still require exact original
spelling; backup suffixes outside the query namespace remain unrelated.
The evaluator-input reconstruction continues to read only exact original
names; the broader inventory is a rejection check, not an alternate input
selection or a change to historical evaluator semantics.
