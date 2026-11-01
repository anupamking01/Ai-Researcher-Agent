# Noncanonical evaluator replay: complete treatment-matrix preflight

The original VERA main study is a frozen 4-variant × 10-task experiment.
Its historical 40 treatment traces and evaluator-recovery outputs must **not**
be regenerated to improve the reported automated outcomes. The direct
post-hoc evaluator now requires explicit noncanonical replay acknowledgment
**and** a complete, uniquely identified treatment matrix before any model
invocation. This supplements the GitHub Actions recovery workflow's historical
cardinality checks for operators invoking the Python script directly.

The offline structural preflight in
`scripts/evaluate_posthoc_support.py` rejects:

- task contracts that do not have exactly `main-01` through `main-10`;
- missing or repeated `(variant, task)` cells among D3, D6, P6, P6V;
- different cells referencing the same run ID (shared report identity);
- incomplete treatment traces, even if a full set of other traces exists;
- JSON trace files under unselected variant directories.

The direct replay now also performs a **closed-world trace-directory
inventory** before loading treatment JSON. Every immediate entry under the
dedicated trace root must be one of the four frozen variant directories; each
variant directory may contain only regular, non-symlink `.json` trace files,
with no nested directories, hidden backup files, alternate variants, or
misnamed traces. The scan stops after five root entries or eleven entries
inside any arm, rather than sorting an unbounded untrusted directory. A
missing variant directory is left to the existing complete-40-cell gate to
reject. This prevents a valid selected matrix from masking additional
unselected treatment evidence. It does not inspect ancestor symlinks, make
the directory tree an atomic snapshot, or authenticate the original reports.

No candidate is selectively dropped to make the available evaluator results
look complete. Missing, failed, or incomplete treatments require provenance
adjudication, **not** a replacement rerun. The original 40-cell evaluation
matrix is unchanged; the evaluator may still resume only missing post-hoc
measurements from a complete and otherwise validated treatment corpus, but
all new measurements remain noncanonical.

The guard operates on selected local trace records and the supplied task
contract. It does **not** authenticate those bytes against independently
retained 2026 archives, prove report/evidence integrity, eliminate fixed-order
temporal confounding, or establish blinded human-evaluation readiness. Existing
frozen automated confirmatory statistics and diagnostic pilot findings are not
recomputed or updated; exploratory analyses and future human judgments remain
separately classified. Synthetic offline tests establish rejection behavior
only, not a scientific result.

**Remaining gate:** the original treatment run 34620917346 and evaluator
recovery run 34783525480 currently have no downloadable Actions artifacts;
an independently authenticated original report/trace archive and two eligible
blinded human annotators are still required for human-validation claims.

## Strict numeric integrity for local replay JSON

Treatment traces and cached evaluator records are **untrusted local JSON inputs**.
The common decoder now rejects `NaN`, `Infinity`, `-Infinity`, exponent
overflow (for example, `1e400`), numeric tokens longer than 128 characters,
and structures beyond the JSON parser nesting limit. Checks apply recursively,
including unconsumed metadata; ordinary finite integers and floats are retained.
Duplicate-key rejection remains in effect. Malformed local trace/cache JSON
fails before importing the model client or generating additional measurements.

This safeguard does not authenticate the lost historical sources or authorize
a treatment/evaluator rerun. It does not change the frozen pilot, confirmatory
or exploratory analyses, and real blinded human evaluation remains pending.

## Closed-world cached-measurement inventory

The direct noncanonical evaluator previously used `*/*.json` globbing for
cache preflight and existing-spend accounting. That selected only JSON files
under immediate directories and silently omitted differently named backups,
nested folders, alternate variant directories, and non-JSON leftovers. A
seemingly complete set of selected cached scores could therefore mask other
local evaluation records, while the spend helper did not account for them.

Both the resume preflight and historical-cache spend helper now use the same
bounded, closed-world cache inventory. The absent cache root is permitted
(no measurements yet). An existing root must be a regular, non-symlink
directory; its immediate children must be D3, D6, P6, or P6V directories,
and each arm may contain at most ten regular, non-symlink `.json` files
with no nested directories or extra backup files. Unexpected JSON cache
cells still fail the separate expected-path check. All checks happen before
a new model call, without deleting, selecting, or recomputing any results.

The guard is **not** an independent authentication of any cached
measurement, a provider-billing audit, an atomic filesystem snapshot, or
a means to recover expired historical evaluator artifacts. Pilot, frozen
confirmatory, exploratory, and pending human-evaluation evidence retain
their separate classifications. These checks use synthetic offline tests;
the historical 40 treatments, common evaluator, and human raters were
not rerun.

## Closed-world report and retrieved-evidence inventory

The direct noncanonical common evaluator previously selected evidence through
a wildcard query-text glob. Other local files could enter the original
research-agent text loader but be silently omitted from replay; alternate
source backups, nested directories and symlinks could also go unreported.

Before evaluator prompt preparation or any provider call, the new bounded
inventory checks all immediate entries in each selected treatment run folder.
It permits only the frozen writer's research-query-01.txt through
research-query-04.txt, research_report.md, optional research_report.pdf and
optional verification.json. It rejects unexpected files, nested paths,
symlinks, alternative query-file names, and gaps in the numbered query
sequence. Enumeration stops after eight entries (one beyond the seven
allowed names), avoiding a full unbounded directory listing. A valid
zero-source treatment can still have no query files; the existing
report-integrity and zero-evidence rubric checks remain in effect.

This is prospective local evidence-selection consistency, not independent
2026 historical-archive authentication or an atomic filesystem snapshot.
It neither authorizes selective reruns nor changes pilot, frozen automated
confirmatory, exploratory, or pending human-validation claims. Regression
tests are synthetic/offline and produce no experimental measurements.

## Source-count agreement for noncanonical evaluator replay

Before constructing a common-evaluator prompt, the direct replay now checks
that each completed treatment's recorded `successful_source_count` agrees
with its saved, selected retrieval text. The count must be a nonnegative
integer (not a boolean, string or rounded float). A **zero-source** run may
contain missing or whitespace-only query files and continues to receive the
predeclared no-evidence sentinel. If nonempty saved retrieval text exists
despite a recorded zero successful sources, replay **fails closed** rather
than silently treating that cell as evidence-backed. A positive source count
still requires nonempty saved retrieval text.

The original runner counts successful browse responses and saves their text
to numbered query files, so this is a consistency check between existing
recorded fields, not a new scientific outcome definition. It neither repairs
a contradictory trace nor discards a treatment from analysis: discrepancies
require provenance review. The source count is not an independent authenticity
proof of the historical files, and this check cannot recover expired Actions
artifacts or establish blinded human-evaluation readiness. All regression
cases use synthetic local files without model calls. The frozen pilot,
confirmatory, and exploratory findings remain unchanged, and human validation
remains pending.

## Fingerprintless historical caches cannot be reused in direct replay

The common evaluator historically stored some valid schema-1 measurements
without hashes of the question, report, retrieved evidence, or exact evaluator
prompt. Identity, score, and pricing checks alone cannot show that a saved
schema-1 score measured the same bytes now found in a local treatment folder.
Before this guard, the direct **noncanonical** replay preflight could count
such an unbound cache as a reusable measurement despite recomputing the
current prompt fingerprints.

When the preflight supplies expected evaluator-input fingerprints, the cache
validator now **fails closed** on schema-1 records, even if their cell identity
and numeric accounting are internally consistent. This happens before any
provider/model call. Schema-2 records remain reusable only when all four
recorded source/prompt fingerprints match the current prepared inputs. The
read-only legacy validation path, without an expected fingerprint, remains
available to inspect preserved historical records; this does **not** certify
their original source bytes.

A schema-1 historical cache must **not** be silently promoted to schema 2 by
attaching hashes computed from today's local files. The discrepancy calls for
independent provenance adjudication. Do not replace frozen historical results
or rerun evaluator treatments merely to make a cache pass this check.

These tests are entirely synthetic; no original runs, evaluator measurements,
or human ratings have been generated or changed. This is a prospective replay
integrity guard, not independent authentication of missing original archives.
Diagnostic pilot, frozen automated confirmatory, exploratory, and pending
blinded human-validation claims remain separate.


## Bounded noncanonical replay input reads (operational safety)

Direct evaluator replay previously read complete local JSON treatment traces,
cached evaluator records, Markdown reports, and retrieved query text into
memory without a byte ceiling. A very large input could exhaust resources
before JSON validation or provoke an unexpectedly large model prompt. The
closed-world directory inventory limits *file counts*, not file sizes.

The evaluator now fails closed on any JSON trace or cache exceeding **16 MiB**,
any single report/query-text input exceeding **2 MiB**, or joined selected
retrieval evidence exceeding **4 MiB** (UTF-8 encoded bytes, including the
joining separators). Bounded reads consume at most one byte beyond the
per-file ceiling to detect an oversized file; no prefix is parsed, scored,
cached, or silently substituted. A file exactly at its limit is permitted.
All input checks run before the replay's provider import/model calls.
Oversized or contradictory source material requires provenance review, not
truncation or treatment/evaluator reruns to force a passing result.

These are deliberately generous operational resource ceilings, **not** new
scientific exclusion criteria, an authentication of original historical
archives, or a claim that all original files fit those limits (the historical
report and trace archives remain unavailable). Their noncanonical replay
failure must not alter the frozen pilot, automated confirmatory, or
exploratory results. The tests use synthetic local files only; real blinded
human annotations remain pending. The existing filesystem checks are not
an atomic snapshot and cannot exclude every concurrent mutation.


## Descriptor-pinned local evaluator source capture

The pre-existing regular-file check preceded a separate pathname-based open.
Another process could replace the checked input or its immediate parent with a
symlink or a FIFO between those operations. A replay might then consume
different bytes from those inventoried, or block on a nonregular file before
evaluating the frozen 40-cell matrix.

Direct **noncanonical** evaluator reads now open the immediate parent with a
no-follow directory descriptor, then open the leaf by name relative to that
descriptor with no-follow and nonblocking flags. The opened descriptor must be
a regular file. Before/after descriptor metadata (device, inode, length,
modification and change times) must agree; observable in-place modifications
cause rejection rather than measurement or automatic repair. The existing
16 MiB JSON and 2 MiB text limits still apply. On platforms lacking these
POSIX safeguards, direct replay fails closed instead of silently downgrading
the read guarantees.

This narrows local time-of-check/time-of-use exposure; it **does not** prove a
filesystem-wide atomic snapshot, protect every ancestor component from
concurrent replacement, or defeat adversarial same-size/timestamp-preserving
rewrites. In particular, it does not independently authenticate unavailable
2026 original traces, reports or retrieval evidence. The synthetic offline
regressions exercise swapping symlinks, a replaced parent, a FIFO, and an
in-place file mutation without invoking models. Historical treatment, frozen
confirmatory measurements, exploratory analyses and pending real human
validation remain unchanged and distinct.

## Prevent post-preflight evidence drift during noncanonical replay

The complete-matrix preflight previously prepared and fingerprinted each
evaluator prompt once, then could spend time making other evaluator calls
before using that cached in-memory prompt. Descriptor-pinned file reads make
each capture safer but do not establish continuity over this interval.

Pending noncanonical measurements now regenerate their report and retrieval
context and compare **all** preflight SHA-256 question/report/evidence/prompt
fingerprints, the full prompt and the zero-evidence classification immediately
before each provider call. They perform the same check **after** the call and
before publishing its evaluator cache. Observed changes abort instead of
silently refreshing, selectively rerunning, or publishing a result against
altered local evidence. The original treatment trace parsed at preflight stays
the fixed in-memory reference.

These checks cannot provide atomic multi-file snapshots, authenticate missing
original historical source archives, or detect transient modifications undone
between checks. A detected mid-call change may incur provider cost without a
publishable result. The new tests use only synthetic local inputs and static
call-order inspection. No treatment or evaluator run, scientific measurement,
pilot finding, frozen confirmatory result, exploratory result, or human rating
is generated or revised. Independent source custody and two real eligible
blinded annotators remain outstanding.

## Byte-exact treatment-trace custody across noncanonical evaluator replay

Preflight already checked each complete treatment trace, and source-continuity
checks protected the report, retrieved evidence and evaluator prompt around
provider calls. However, the frozen in-memory trace itself had no byte-level
continuity check: a local trace could change after parsing (including unused
metadata, cost counters or run identity) without changing the prompt. A fully
cached replay could similarly publish an aggregate after such a mutation.

Direct **noncanonical** replay now retains a SHA-256 of the **exact bounded
JSON bytes consumed by the decoder**, rather than hashing a later pathname
read or reconstructed JSON. It checks that each pending trace still has those
bytes immediately before a model invocation and after its response but before
cache publication. Before publishing even an all-cached aggregate, it rechecks
all 40 source traces. Missing/replaced/nonregular or oversized files fail
closed; bytes are never repaired, substituted, or selected based on results.

This local continuity control does **not** independently authenticate the
original September 2026 traces, establish an atomic multi-file snapshot, or
observe mutations that were undone between checks. Historical treatment and
evaluator Actions artifacts remain unavailable. Synthetic tests exercise
metadata changes and byte-identical semantic JSON rewrites without making
model calls. Diagnostic pilot, frozen automated confirmatory, exploratory,
and pending blinded human-validation conclusions remain distinct and unchanged.


## Aggregate-publication source continuity for cached and pending cells

Post-preflight report/evidence continuity originally bracketed **new model calls**
only. A fully cached noncanonical replay (or one whose other cached cells were
processed before a slow pending call) could publish an aggregate after a cached
cell's source report or retrieved-evidence files changed. The previous
aggregate-time treatment-trace SHA-256 recheck does not detect those changes.

Immediately before aggregate publication, direct noncanonical replay now
reconstructs the common evaluator inputs for **every** expected treatment
cell, including cells whose schema-2 measurements were reused from cache. It
requires the observed evidence classification and question/report/evidence/
prompt SHA-256 fingerprints to match the exact in-memory measurement records
validated against preflight inputs. A missing/duplicated measurement or a
changed source fails closed, without refreshing, rerunning, selecting, or
altering any scientific score. Pending model calls retain their independent
pre- and post-call guards; all 40 treatment trace bytes retain their separate
aggregate-time continuity check. Regression tests are synthetic and offline.

This is a **prospective local replay integrity safeguard**, not recovery or
authentication of the unavailable original historical treatment archives, an
atomic 40-cell filesystem snapshot, or assurance that files cannot change
after the final check. No diagnostic pilot, frozen automated confirmatory,
exploratory, or human-validation result is changed or newly claimed. Real
blinded human validation remains blocked on independently authenticated
original sources and eligible annotators.
