# Noncanonical main-study treatment trace completion gate

An exception-free agent return is not proof of a completed treatment. An
empty report can yield an incomplete trace without an exception, and a
missing trace contributes zero reported usage to the next-treatment spend
guard.

The separately acknowledged noncanonical runner now inventories trace names
before each treatment, and requires exactly one new trace afterward, without
disappearance of previous names. It also pins earlier trace identities,
metadata and SHA-256 bytes before running the next treatment, rejecting an
observed in-place edit or same-byte inode replacement even if the prior filename
still exists. The trace must reside under the requested
variant, pass the existing scientific/provider usage ledger validator, declare
completed=true and match the requested variant, task set and task ID in both
its experiment configuration and trace record. **A trace alone is not sufficient:**
the matching `outputs/<run_id>/research_report.md` must be present as a
regular, unlinked UTF-8 file of at most 8 MiB, its word count must match
`trace.report_words`, and the recorded `report_path` must point to the same
run's Markdown or PDF export. This covers the generated Markdown that the
report writer retains even when PDF conversion fails. Earlier reports are
fingerprinted alongside earlier traces before each later treatment; observed
report content or inode replacement stops execution even when the new
trace and report look valid. Failure stops further
treatment execution; it never retries or replaces the attempted treatment.

Offline tests use synthetic traces and a stub agent, not real provider calls.
This does not modify canonical evidence or the original historical runner,
authenticate original missing archives, guarantee an atomic filesystem
snapshot against concurrent tampering, protect other files outside the
tracked trace/report paths, or prove recorded provider usage matches billing.
The Markdown validation checks observed content and declared word count,
not semantic factual correctness or independent provider provenance. Missing trace evidence
must be investigated rather than rerun to chase a preferred outcome.

The five-task pilot remains diagnostic. Frozen automated results retain
post-collection analysis-plan, fixed-order and evaluator comparability
limitations; retrospective sensitivities remain exploratory. Independent
blinded human validation is still pending.

### Bounded trace capture for noncanonical replication

The budget-runner cost guard and subsequent report-path/word-count gate now
read each JSON trace through a no-follow regular-file descriptor with an
**8 MiB maximum**, a single-link requirement, and file-generation/metadata
consistency checks before and after reading. Oversized or externally hardlinked
traces fail closed instead of being fully loaded into memory or accepted into
the next-treatment spend decision. The maximum is a conservative ingestion
limit for *new noncanonical execution*, not a finding about archived trace
sizes or a modification of the frozen September dataset. Regression cases use
synthetic oversized sparse files, hardlinks, symlinks, and simulated in-read
mutation; no treatment or evaluator is run. This is observed local custody
and bounded memory use, not an atomic snapshot, proof of provider billing,
or independent authentication of missing original artifacts.


### Bounded prior-evidence fingerprints

Prior completed trace and Markdown report fingerprints now enforce their
respective **8 MiB limits** before reading and cap streamed bytes even if
a file grows while being hashed. They also require a single-link regular file
and use nonblocking, no-follow opens, so an externally hardlinked file or
a FIFO substituted for a prior trace cannot be silently accepted or hang the
fingerprinting step. The same bounds apply before and after each subsequent
noncanonical treatment. Synthetic offline regressions cover oversized sparse
prior evidence, untracked hardlink aliases, and FIFO substitution. These
checks do not authenticate the original inaccessible September artifacts,
provide an atomic or hostile-race-proof snapshot, establish true provider
billing, or create human-evaluation measurements.

### Nonblocking capture of newly completed reports

A newly generated report is untrusted local filesystem evidence until its
regular-file identity is checked. A read-only `open()` of an attacker- or
accidentally substituted FIFO can wait indefinitely for a writer **before**
the existing `fstat()` regular-file gate executes. The completed-report reader
now uses `O_NONBLOCK` alongside its existing `O_NOFOLLOW`, 8 MiB cap,
single-link requirement, bounded read, and before/after identity checks. A FIFO
therefore fails closed rather than stalling completion accounting or leaving
progress stuck at an active treatment. Synthetic POSIX tests check that the
open itself is nonblocking and that an external hardlink alias is rejected;
no live research treatment is launched. This is a local execution-robustness
safeguard, not archive authentication or protection against hostile ancestor
races. Frozen measurements and human-validation status are unchanged.

## Durable failure recording when post-treatment spend is unreadable

A malformed JSON trace can be present after a stub/agent returns, cause the
completed-evidence gate to fail, **and** cause a second spend-ledger read to
raise `SystemExit`. Previously that latter read occurred *after* the in-memory
failure event was constructed but before progress was written; consequently
the durable progress file could still show an active treatment and zero attempts.

The noncanonical runner now attempts post-treatment spend reconciliation
**before** committing the terminal progress event. If retained traces cannot
be accounted for, it records the attempted cell and its failure/timeout,
sets `estimated_treatment_cost_usd` to JSON `null` rather than a misleading
number, labels `trace_cost_reconciliation` as `unverifiable`, and stops further
treatment execution. The original failure classification is retained for
timeouts, and an otherwise completed treatment is not marked successful when
post-treatment accounting is invalid. A synthetic offline regression exercises
a malformed newly created trace as well as the existing missing-trace case.

This is not a recovered historical usage ledger or proof of actual provider
billing. It neither triggers retries nor updates original treatments, frozen
automated outcomes, exploratory sensitivity findings or human ratings.

### Bind captured bytes to the published evidence pathname

An unchanged descriptor does not prove that its published pathname still
resolves to that inode. Renaming the enclosing directory after opening a file
can preserve the file's existing metadata while a new directory publishes a
different inode under the same name. The noncanonical runner now checks the
no-follow *published path* after bounded captures of new traces, completed
Markdown reports, and prior trace/report fingerprints. It also rejects
incomplete bounded reads of traces or reports. Observed path redirection
therefore fails closed rather than being accepted into completion or
provider-spend accounting.

Three synthetic offline regressions simulate a same-byte path replacement by
moving the containing directory after the original descriptor was opened.
This detects the observed swap; it is not an atomic snapshot, complete defense
against hostile ancestor races, independent authentication of missing original
archives, or a claim about frozen automated or human results.

### Per-treatment Git source continuity for noncanonical replication

A clean, byte-verified Git checkout at manifest creation does not by itself
establish that the same tracked code remained in place during all later
treatments. The noncanonical runner now reattests the tracked Git source state
immediately before each agent call and again on exit, **including when the
agent raises an exception**. An observed dirty/unattestable checkout or changed
commit/tree is recorded as a failed treatment with durable progress, and no
next treatment is started. Three offline synthetic regression cases cover
pre-call drift, post-call identity drift, and failed post-call attestation,
without running a model or producing scientific measurements.

This detects observed local tracked-source changes at check boundaries; it
does not establish a continuous atomic snapshot, rule out changes reverted
between checks, protect untracked/ignored runtime dependencies, or authenticate
the missing original September artifacts. It does not promote the diagnostic
pilot, retrospective exploratory findings, or pending human validation into
confirmatory research evidence.

### Bounded, path-bound Git-source attestation

The per-treatment Git-source continuity gate also needs a safe reader:
a tracked pathname can become a FIFO before its file type is checked, a
sparse file can consume unbounded memory if hashed in one `read()`, and a
published pathname can be replaced while an opened descriptor remains stable.
The noncanonical runner now opens tracked blobs with `O_NONBLOCK | O_NOFOLLOW`,
rejects nonregular files, external hardlink aliases and files over **64 MiB
per tracked source file**, streams Git blob hashing in bounded chunks, and
rechecks descriptor metadata and the published pathname after reading.
Five synthetic offline regressions cover a clean attested blob, FIFO
substitution, an oversized sparse file, a hardlink alias and same-byte
pathname replacement. This caps a *new replication runner's* source ingestion;
it does not alter frozen September measurements, assert an atomic snapshot,
authenticate missing originals or infer a human-validation outcome.


### Bind completed treatment to the frozen task question (22 November 2026)

Previously a completed trace could claim the correct variant, task set and
task ID yet contain a different or absent `trace.question`. Its report and
cost ledgers could still reconcile, misattributing the report to the wrong
question in a paired comparison or eventual blinded human handoff.

For each **new** noncanonical completed cell the runner now compares the exact
trace question to the independently loaded, snapshot-pinned task-file question
it passed to the agent. Missing or differently typed values and even whitespace
changes fail closed; valid Unicode and punctuation remain unchanged. No query
or report is rewritten. General historical spend inspection stays compatible,
and the original September results are not retroactively certified.

Synthetic offline regressions cover missing, altered and mis-typed questions,
exact Unicode matching and wiring from the runner's task input. This is local
task-attribution integrity, not proof of model execution, original historical
report custody or human validation. The five-task pilot is diagnostic; frozen
automated results retain post-collection planning, fixed treatment-order and
evaluator-policy limitations, retrospective sensitivities are exploratory,
and independent human ratings remain pending. No treatment or evaluator reruns.

### Durable cancellation accounting (22 November 2026)

Python 3.11's `asyncio.CancelledError` inherits from `BaseException`, not
`Exception`. An interrupted agent task previously bypassed the runner's
ordinary error handler after the post-call Git check, potentially leaving the
durable progress record showing an **active but uncounted** treatment. This is
particularly misleading when an interruption occurs after model requests have
started, and must not be interpreted as an unattempted cell eligible for replay.

The noncanonical runner now catches this specific cancellation, marks the cell
**failed** (not completed or scientifically timed out), reconciles available
retained trace spend, writes the terminal progress event with `current=null`,
then **re-raises the original cancellation**. If trace spend cannot be verified,
the existing `unverifiable`/JSON-null accounting remains in force; cancellation
never silently resets costs to zero. No subsequent treatment runs. The offline
regressions inject synthetic cancellation both without a trace and with a
malformed trace; no provider calls, treatment reruns or research scores occur.

This only covers cooperative Python task cancellation after the runner reaches
its treatment exception handler. It cannot guarantee durable writes after
`SIGKILL`, process crashes, disk failure or a second interruption during
cleanup, nor authenticate historical September artifacts. The pilot remains
diagnostic, frozen automated comparisons retain post-collection and
fixed-order/evaluator-policy caveats, exploratory sensitivities remain
exploratory, and human validation has not taken place.

### Interrupted pre-agent trace inventory after selecting a cell

A trace-root inventory can become invalid **between** the successful initial
spend check and the final pre-agent evidence snapshot. Previously this second
inventory happened after `progress.current` was durably set but outside the
terminal-event exception handler. A displaced directory or unexpected trace
entry could therefore raise `SystemExit` and leave a selected treatment marked
active with no recorded failed event. The noncanonical runner now fails closed
*inside* the selected-cell handler: it records a failed selection, preserves an
explicit `unverifiable` spend reconciliation when retained traces cannot be
inventoried, clears `current`, and stops without invoking the agent or proceeding
to another cell. The attempt count is a **study-runner selection/failure count**,
not evidence of a model request or a completed experimental treatment.

A synthetic no-provider regression changes the inventory only after preflight
and the spend guard have succeeded, verifies no agent invocation, and checks the
durable failure event and unverified spend designation. This does not recover
September source artifacts, authenticate provider billing, make the local
filesystem atomic, or create confirmatory or human-evaluation evidence.

### Prospective absence of verifier artifacts in non-verifier arms (22 November 2026)

Schema-5+ metadata already rejects a D3/D6/P6 trace that *claims* verification
counts or a verifier digest. That did not detect a contradictory physical
`outputs/<run-id>/verification.json` file left in the report directory despite
`verification_mode: none`. In a future replication this could obscure whether
the no-verification treatment remained distinct from P6V.

After the completed Markdown report's existing validation, the noncanonical
runner now performs a no-follow directory-entry inspection using `os.lstat`
for schema-5+ completed no-verification arms. Any retained verifier receipt,
directory, or dangling symlink at that exact path causes the cell to fail
closed; an unexpected inspection error also fails rather than silently
assuming absence. P6V retains its separate positive receipt/content check.
Historical schemas 1–4 are not retroactively strengthened. Offline synthetic
tests distinguish missing, regular-file, dangling-link, and directory cases
across schema 4/5/6, plus the verifier-arm exception.

This is a **local evidence-consistency gate**, not independent proof that a
verification model did or did not execute, an atomic filesystem snapshot, or
authentication of the September 2026 original artifacts. No treatment or
common evaluator was rerun; the five-task pilot is diagnostic, automated
frozen findings remain post-collection and subject to fixed-order and
evaluator-policy limitations, retrospective sensitivity analyses remain
exploratory, and genuine blinded human validation remains pending.

### Prior verification-receipt continuity across later treatments (22 November 2026)

A prospective P6V trace can bind the digest of its retained
`verification.json`, but that digest alone cannot detect later **same-byte,
different-inode replacement**. The completed-cell absence gate for D3/D6/P6
previously checked only when that cell finished: an unexpected verifier
artifact could appear during a later cell without modifying the earlier trace
or report.

For schema-5+ completed prior cells, the noncanonical runner now snapshots
P6V receipts with bounded SHA-256, inode generation, size and timestamps, and
captures required **absence** in non-verification arms. After the next agent
attempt it repeats the independent checks. Missing, modified or same-byte
replaced P6V receipts, and newly present no-verifier entries (including dangling
symlinks), fail closed. Historical schema-1–4 traces are not retroactively
strengthened. Observed local filesystem integrity does not establish atomic
custody, external verifier execution or authenticity of September artifacts.

The synthetic regressions perform no provider calls, treatment/evaluator reruns
or human ratings. The pilot remains diagnostic; frozen automated comparisons
retain post-collection analysis and fixed-order/evaluator-policy limitations,
retrospective sensitivities remain exploratory and genuine human validation is
pending.


### Durable accounting of agent-originated process exits (22 November 2026)

The noncanonical runner already records ordinary exceptions, cooperative
`asyncio.CancelledError`, and pre-agent trace-inventory failures. An agent
invoking `sys.exit()` raises `SystemExit`, which is outside `Exception`:
after the selected cell has been persisted as active, this previously bypassed
the terminal progress event altogether. A zero exit code still cannot certify
a completed treatment.

The selected-cell handler now catches `SystemExit` narrowly, records a
**failed, uncertified attempt**, reconciles bounded retained-trace cost when
possible (or explicitly records `unverifiable`), clears the active marker
and stops the study without attempting another cell. The failure event records
the exit, not an invented provider outcome or zero-cost assumption.

Two synthetic offline regressions model exit with no trace and with malformed
retained trace bytes; they assert the failed attempt ledger and distinguish
verifiable-zero retained spend from unverified spend. No agent providers,
historical treatments, evaluator runs, or human ratings are invoked. This is
not a crash-/SIGKILL-proof transaction log or independent proof of model
billing, original artifact custody or prospective preregistration. The pilot
remains diagnostic, frozen automated comparisons retain post-collection,
fixed-order and evaluator-policy limitations, retrospective sensitivities
remain exploratory, and human validation is pending.
