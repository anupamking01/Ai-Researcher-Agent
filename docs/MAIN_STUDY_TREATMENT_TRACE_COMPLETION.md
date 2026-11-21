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
