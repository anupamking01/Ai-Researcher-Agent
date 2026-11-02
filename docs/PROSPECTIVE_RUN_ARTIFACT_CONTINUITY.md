# Prospective VERA run artifact continuity (offline, recorded evidence only)

**Scope: a separately designed future counterbalanced replication, never the historical September 2026 pilot or fixed-order main study.** This optional offline verification layer does not execute agents, call evaluators, compute scientific effects, score reports, create human ratings, or recover lost historical evidence.

## Gap and interpretation

The existing schedule verifier reconstructs the ten-task treatment order from a prospective manifest. The chronology verifier checks that a **self-reported** forty-cell execution ledger follows this order, including failed, timed-out, cancelled, and unattempted cells. Neither verifies that the recorded run identifiers have corresponding local traces and reports. A coherent execution log could pass even when its purported output files are absent, replaced, or assigned to different run IDs.

The new read-only scripts/verify_prospective_run_artifacts.py gate independently recomputes both prior checks, then verifies candidate **local artifact bytes** against an exact forty-cell inventory. Each attempted run must have a nonempty UTF-8 JSON trace; every completed run must also have a nonempty, nonblank UTF-8 Markdown report. Failed, cancelled and timed-out runs must retain a trace but may have no report. Unattempted suffix cells must declare null for run ID, trace and report. Nothing is silently removed from the denominator.

A pass establishes *internal agreement* between the supplied prospective manifest, plan, recorded chronology, inventory fingerprints, trace identity, **exact task-question fingerprint**, **self-reported intervention controls**, UTC interval fields, and local report bytes. A trace with a valid run ID but a fingerprint for a different research question now fails, even when the candidate inventory has been rehashed. This guards against a ledger with rewritten start/end times being paired with retained traces that still record the original interval. These clock claims remain self-reported; equal strings do not prove provider execution or trustworthy real-world timing. It **does not** prove that the trace reflects an actual model call, the provider supplied its contents, sources were fetched, a report is correct, or an experiment or human validation was independently authenticated. A coordinator can rewrite all candidate files consistently. Independently retained pre-run/post-run digests are needed for stronger custody, and additional provider-bound evidence is needed for independent execution authentication. Do not use a passing receipt to promote pilot observations to confirmatory findings or to publish claims of completed replication.

## Evidence index schema v1

Keep the exact original prospective task manifest, its originally frozen schedule receipt, unchanged execution ledger, candidate artifact directory, and index JSON. The index is a UTF-8 JSON object with exactly schema_version (integer 1), classification (the exact literal shown below), task_set_id, execution_log_sha256 (SHA-256 of exact execution-ledger bytes), and cells (exactly forty entries in execution order).

Illustrative first cell only (the complete index **must** include all forty cells):

    {
      "schema_version": 1,
      "classification": "prospective_replication_local_artifact_continuity_only",
      "task_set_id": "new-independent-2027",
      "execution_log_sha256": "<sha256 of original execution log bytes>",
      "cells": [
        {
          "task_id": "<first task ID from the frozen plan>",
          "variant": "<first assigned arm>",
          "run_id": "run-00",
          "status": "completed",
          "trace": {
            "path": "traces/run-00.json",
            "size_bytes": 248,
            "sha256": "<sha256 of trace bytes>"
          },
          "report": {
            "path": "reports/run-00.md",
            "size_bytes": 4096,
            "sha256": "<sha256 of report bytes>"
          }
        }
      ]
    }

Each inventory row has exactly task_id, variant, run_id, status, trace, report. The first four fields must match the corresponding independently verified chronology row **with identical JSON types**; for unattempted cells the run ID, trace and report must all be JSON null. File fingerprints use exactly path, size_bytes (positive JSON integer), and lowercase SHA-256. Paths are safe relative paths beneath the nominated artifact root with no traversal, aliases, symbolic links or hardlinks; distinct artifacts cannot reuse a path or underlying inode. The verifier holds one descriptor for the root directory across all reads and fails if the root directory metadata or the pathname's underlying inode changes before completion. After scanning all cells, it reopens **every** referenced file beneath that pinned root and requires the same inode, size and SHA-256 as at its first verification. This catches an earlier trace/report that was edited, replaced with identical bytes under a new inode, or removed while later cells were being audited—even if only a nested directory changed and the root metadata stayed constant. The final verification rereads at most the already bounded 16 MiB of indexed evidence. It is **not** an atomic filesystem snapshot: concurrent mutation after or between checks is still possible, and it does not independently authenticate source files. Each file is limited to 2 MiB; all referenced artifacts together are limited to 16 MiB. The index itself is limited to 256 KiB.

**Exclusive evidence-root inventory and nonselection gate:** The nominated artifact root is now a **dedicated directory containing only the referenced prospective trace and report files** and any necessary parent directories. In addition to validating every submitted cell, the verifier enumerates the local directory tree both before and after inspecting all indexed evidence. Every retained regular file must be referenced exactly once by an attempted treatment cell; an extra trace, report, nested alternative attempt, or leftover file for an `not_started` cell causes failure. The bounded inventory rejects symlinks, hardlinks, device files, unsafe names, excessive nesting (more than 16 levels) or more than 256 entries. All files must fit the same safe relative path limit (384 characters). This is a *local completeness/anti-selection check*, not a proof of all historical attempts: it cannot detect evidence removed before inventory, files kept outside the nominated root, or transient changes missed by two non-atomic scans. To avoid false claims, the receipt explicitly reports inventory agreement as **local only**. Store manifests, execution logs, receipts, and unrelated working files **outside** the dedicated evidence root. Do not copy an unattempted cell's placeholder files into the root. If an extra genuine attempt is found, preserve it separately for investigation and document the protocol deviation rather than deleting it to obtain a passing receipt.

**Human-readable report envelope:** Every indexed report, including an optional report from a failed, timed-out or cancelled attempt, must use a relative path ending in `.md`, decode as strict UTF-8, contain non-whitespace text after an optional leading UTF-8 byte-order mark, and contain no NUL characters. Merely providing a matching SHA-256 and a nonzero byte length is insufficient: a PDF, arbitrary binary, empty/BOM-only or whitespace-only file cannot serve as Markdown evidence for later blinded human review. These checks apply to synthetic prospective v1 artifacts only and never reinterpret or overwrite the historical 2026 reports. They establish textual inspectability, **not** research correctness, source authenticity, Markdown safety for distribution, or human-validation eligibility; the separate content-leakage and original-evidence gates remain mandatory.

**Rendered-text integrity for future blinded review:** The report envelope also rejects nonprinting C0 characters (except tab, line feed, and carriage return), DEL/C1 controls (U+007F–U+009F), and explicit Unicode bidirectional embedding/override and isolate controls (U+202A–U+202E, U+2066–U+2069). These can manipulate terminal, Markdown, or text-review presentation without changing the visible prose. Ordinary Unicode text, including non-Latin scripts, and normal line formatting remain allowed. This is an intentionally narrow **prospective-only display-integrity check**, not a guarantee of safe Markdown rendering, absence of treatment-label leakage, content authenticity, or human-review eligibility. Preserve any rejected original unchanged and document a protocol deviation; do not silently sanitize or rewrite research reports to obtain a passing audit.

A prospective trace JSON object must include at least these exact, correctly typed event-identifying keys, matching the original ledger: task_id, variant, run_id, status, started_at_utc and finished_at_utc. Both UTC timestamp fields must be strings exactly equal to the verified execution ledger's corresponding event timestamps, including their original UTC representation. An attempted trace lacking either clock field, or giving conflicting clocks even with otherwise matching run identity and valid artifact hashes, fails closed. It must also contain **task_question_sha256**, the lowercase SHA-256 of the exact UTF-8 bytes of its task's original question string from the frozen prospective manifest, plus report_sha256, whose value is the lowercase SHA-256 of the corresponding indexed report or JSON null when no report is indexed. Do not normalize or paraphrase the question before hashing it. Missing, non-string, or mismatched question fingerprints fail even when the trace and inventory are consistently rehashed. This is a **self-reported source-question binding**: it cannot prove which prompt was actually sent to any model or independently authenticate an execution. Each attempted trace must also include an exact **treatment_controls** JSON object with exactly three factors: planning_mode (string), source_budget (integer, not boolean/float), and verification_mode (string). Their values are checked against the frozen prospective intervention contract in scripts/plan_counterbalanced_replication.py:

| Arm | planning_mode | source_budget | verification_mode |
| --- | --- | ---: | --- |
| D3 | direct | 3 | none |
| D6 | direct | 6 | none |
| P6 | planner | 6 | none |
| P6V | planner | 6 | verify |

An otherwise correctly indexed P6V trace claiming verification_mode=none, or a P6 trace claiming direct planning, fails even when its source bytes and index hash have been rewritten consistently. Regression tests cross-check the frozen values with logic.experiment.ExperimentConfig.from_variant. These are **self-reported control settings only**: the checker cannot prove which settings actually ran. It does not attest other parameters such as model versions, prompt revisions, timeouts, concurrency, or search multipliers, which must be retained separately before making any intervention-fidelity claim. Historical trace formats are unchanged.

Other trace fields may hold legitimate provenance or failure details and are not used for outcome scoring. Duplicate JSON keys, malformed UTF-8 and nonstandard numeric constants are rejected. This is a **new prospective trace envelope contract**; historical VERA traces must not be silently reclassified to satisfy it.

For a recorded failure, timeout or cancellation, require the trace even when no report exists. A failed attempt that genuinely produced no trace cannot pass this stronger artifact-custody check: preserve the incomplete ledger and explicitly report the provenance gap, rather than fabricate a trace. For an unattempted cell, never create a fake run ID or placeholder trace. A full forty-cell confirmatory dataset cannot be inferred from a partial or failed ledger.

## Read-only verification

    python -m scripts.verify_prospective_run_artifacts \
      --task-manifest /path/to/frozen-future-tasks.json \
      --plan-file /path/to/original-future-plan.json \
      --execution-log /path/to/original-execution-log.json \
      --evidence-index /path/to/recorded-local-index.json \
      --artifact-root /path/to/candidate-original-traces-and-reports \
      --expected-task-manifest-sha256 <independently-retained-prerun-value> \
      --expected-plan-file-sha256 <independently-retained-prerun-value> \
      --expected-execution-log-sha256 <independently-retained-postrun-value> \
      --expected-evidence-index-sha256 <independently-retained-postrun-value> \
      --expected-runtime-context-sha256 <independently-retained-prerun-value>

All four expected SHA-256 options are optional. The verifier reports separately which were provided and matched. Self-computed values from the candidate files must **not** be called independently preserved. Successful checks print only a compact status/digest/count receipt, including the count of artifact paths rechecked after the full scan and an explicitly local final-recheck stability flag; no report text, token content, source URLs, annotator identities or experimental measurements are printed or written. An invalid candidate fails closed. There are no model/network calls, and the verifier never mutates the source files.

For stronger external trust, independently preserve the prospective manifest and plan hashes **before** execution and execution-log and index hashes **after** each finalized capture. These timestamps and custodian identities must be established outside this script. Verify provider-bound run receipts, original retrieval provenance and model/experiment traces separately before treating any candidate artifacts as authenticated science.

## Research gate separation

The **diagnostic pilot** remains diagnostic, the original **frozen automated confirmatory** analysis remains tied to its historical outputs and original fixed execution order, and any **exploratory** sensitivity or cost-quality investigations remain exploratory. The new prospective plan and this artifact auditor are **methodology only**, with no future measurements generated. Authentic **human validation** is still blocked until the original treatment traces/reports are independently recovered and two eligible blinded annotators are selected.

As of the audit performed for this change, the historical treatment and evaluator-recovery workflows continue to expose zero downloadable GitHub Actions artifacts, although the separately preserved canonical automated-analysis ZIP remains available. This prospective continuity check does **not** repair that source-custody break or retroactively remove the 2026 time-order confound.

## Prospective source-budget ledger fidelity (self-reported only)

Each **attempted** prospective trace must additionally retain six source-use
fields: `source_count`, `successful_source_count`, `failed_source_count`
(nonnegative JSON integers, never booleans/floats), and `scheduled_urls`,
`successful_urls`, `failed_urls` (JSON arrays of distinct, nonempty, trimmed
URL strings). `source_count` must not exceed the frozen assigned arm's
`source_budget` (D3 = 3; D6/P6/P6V = 6). All URL counts must match their
corresponding arrays; successful and failed URL sets must be disjoint and
partition exactly the scheduled set **by canonical HTTP fetch identity** (rather
than by byte-identical URL spelling). An attempted failed/cancelled/timed-out
cell can legitimately declare zero sources, but still must retain the ledger.
An unattempted cell retains no trace and therefore makes no invented source
claim. A rehashed trace and evidence index cannot excuse a budget violation
or fabricated, overlapping or unaccounted URL outcomes.

This checks **consistency of recorded source-use metadata**, which is central
to the treatment's retrieval-budget contrast. It does **not** authenticate web
retrievals, browser/provider activity, external timestamps, source relevance
or whether the treatment actually executed with its declared settings. Do not
interpret a passing ledger as independently measured retrieval use. This
prospective-only trace envelope does not retroactively alter or reclassify
the frozen September 2026 experiment, its automated confirmatory analysis,
diagnostic pilot, exploratory work or pending blinded human validation.


## Prospective source URL validity and fetch-identity nonduplication

The six-field prospective source ledger additionally requires each recorded
source identifier to be an **absolute HTTP(S) URL**, at most 2,048 characters,
with a nonempty host and an optional valid, nonzero network port. Non-web
schemes, local paths, embedded credentials, whitespace, control/format
characters, backslashes and malformed authorities fail closed. IDN domains,
IPv6 hosts, URL queries and ordinary fragment references remain eligible.

**One fetchable HTTP resource cannot count multiple times** within an
individual scheduled/successful/failed URL list simply through spelling
changes: the offline auditor compares scheme/host case-insensitively,
normalizes default HTTP/HTTPS ports and an empty path to "/", and ignores
fragments (which the browser does not send to an HTTP server). Equivalent compressed and expanded bracketed IPv6 address spellings (including
IPv4-mapped IPv6 literal forms) are treated as one network address, not
separate sources. Link-local interface-zone suffixes such as
`[fe80::1%25eth0]` are rejected as nonportable source identifiers rather
than silently folded into a different fetch target. Distinct IP addresses
and distinct query strings remain distinct.
The query
string remains significant. The outcome sets must partition the scheduled **fetch identities**.
A reported outcome may have a different URL fragment, host capitalization,
explicit default port or empty-path spelling without becoming a different
HTTP request. A different scheme, path or query still denotes a distinct
resource and cannot satisfy a scheduled source claim. All original URL strings
remain unchanged in the trace, and duplicate fetch identities inside any
individual ledger list or across success/failure outcomes are rejected.
This prevents rejecting faithful source accounting when the same resource
is represented by slightly different URLs, while still detecting missing,
invented or overlapping outcomes. The success receipt explicitly marks
the syntactic URL/fetch-identity gate.

This is a conservative **prospective, self-reported non-overcounting rule**,
not proof that a network request occurred, the URL resolved, the server
returned particular evidence, or that distinct URLs had distinct contents.
Redirects, percent-encoding equivalences and near-duplicate pages are not
deduplicated. Preserve any source trace rejected by the rule unchanged as
a documented protocol deviation; do not select or rerun results to pass.
The historical pilot, frozen automated confirmatory analysis, exploratory
results, and pending human validation remain untouched.

## Prospective common non-treatment runtime context (self-reported only)

A future counterbalanced replication's retrieval and planning contrasts are
confounded if its **model selection, search backend, code revision, dependency
lock or non-treatment resource guardrails** silently change between the
D3/D6/P6/P6V arms. The optional prospective verifier therefore requires an
exact `runtime_context` JSON object inside **every attempted trace**,
including failed, timed-out and cancelled attempts. The ten fields are:

- `runner_commit`: lowercase 40- or 64-hex Git commit identifier for the
  code actually intended to execute (the verifier does **not** inspect a
  checkout or Git tree);
- `requirements_sha256`: lowercase SHA-256 fingerprint of the intended
  pinned dependency lock (not independently read by this verifier);
- `smart_model_id`, `fast_model_id`, `search_provider_id`: nonempty,
  bounded, visible ASCII identifiers, at most 128 characters, representing
  the declared model/provider configuration;
- `generation_temperature`: finite JSON number in [0, 2], not boolean;
- `search_candidate_multiplier` and `max_concurrent_browses`: integers
  from 1 to 64, not booleans;
- `browse_timeout_seconds` and `run_timeout_seconds`: finite positive JSON
  numbers at most 86,400 seconds, not booleans.

These values describe **common non-treatment configuration**, not the
arm-specific `treatment_controls` (which remain separately fixed by D3/D6/P6/P6V).
Their exact JSON schema and canonical JSON SHA-256 must be identical across
every attempted trace. A valid-looking second arm changing its recorded
model, Git revision or timeout fails even when its trace and inventory
hashes are consistently recomputed. The checker emits one digest of the
common context, never model names, source URLs or secret values.

Before future execution, coordinators can independently precommit the
SHA-256 of `json.dumps(runtime_context, sort_keys=True,
separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")`
and supply it through `--expected-runtime-context-sha256`. Only a
matching **independently retained pre-run** digest may be described as
externally pinned; merely calculating that value from candidate evidence
does not establish preregistration. The receipt records the separately
reported pin match and **always** states that actual runtime configuration
was not independently authenticated. Preserve any drift or incomplete
trace as a protocol deviation rather than rewriting historical outputs
or selecting better experimental runs.

This is prospective-only methodological reproducibility protection. It
does not certify installed dependencies, actual provider model versions,
true browsing, historical 2026 treatment authenticity, confirmatory
replication, or human validation. Pilot, frozen automated main-study,
exploratory and pending human assessments remain separate.

## Prospective source-use exposure receipt (no new measurements)

A valid recorded source ledger may use **fewer** sources than the assigned
D3/D6/P6/P6V upper budget. The within-cap verification alone must not be
reported as evidence that higher-budget arms actually scheduled more
retrievals. To make this distinction reviewable, the local audit receipt now
includes `self_reported_source_usage_by_variant` with all four arms, even
when a study stops partway through the 40-cell schedule.

Each arm contains integer `attempted_cells` and `completed_cells`
denominators, `scheduled_source_claims`, `successful_source_claims`,
`failed_source_claims`, `at_budget_attempted_cells`,
`zero_scheduled_source_attempts` and
`zero_successful_source_attempts`. Unattempted cells contribute nothing;
failed, timed-out and cancelled **attempted** cells remain in the denominator.
Counts are summed from the same trace fields that were checked against the
frozen browse cap and URL outcome partition. The receipt never includes
individual URLs, questions, reports, or human ratings.

These are **unverified, self-reported exposure diagnostics**, not a fourth
outcome measure, a treatment-compliance exclusion criterion, or evidence of
actual HTTP requests. In particular, a completed D6 cell with zero scheduled
sources remains visible as such rather than being silently treated as having
used its six-source allowance. Do not remove, rerun, or reclassify cells
based on these counts. Any interpretation of achieved retrieval exposure
is descriptive and prospective; it does not change the frozen 2026 pilot,
confirmatory automated results, exploratory results, or pending human
validation.



## Paired source-exposure contrast diagnostic (prospective, descriptive)

The four arm-wide source totals cannot establish whether the **same task**
received more recorded retrieval exposure under a higher-budget treatment.
A task-pooled total can obscure unequal within-task exposure, which matters
when interpreting the three frozen *task-paired* contrasts. The prospective
artifact verifier therefore also emits
`self_reported_paired_source_exposure_by_contrast` for **D6 - D3**,
**P6 - D6** and **P6V - P6**, without reading or generating outcomes.

For each contrast, `both_attempted_tasks` counts only tasks with a trace
for **both** arms, and `both_completed_tasks` separately counts pairs
whose two recorded statuses are `completed`. Failed/timed-out/cancelled
attempts are kept in the first denominator; unattempted arms are **not**
imputed to have zero retrieval. Among both-attempted pairs, signed
`scheduled` and `successful` source-count differences (later arm
minus earlier arm) are summarized as `*_delta_positive`,
`*_delta_zero`, `*_delta_negative` and integer `*_delta_sum`.
The three direction counts must sum to `both_attempted_tasks`; no
per-task IDs, source URLs, generated text or individual outcome scores are
emitted. All completed forty-cell matrices have ten task pairs per contrast,
but this should never be inferred for an interrupted replication.

These are **self-reported, within-task exposure descriptions**, not
independent proof of requests or evidence quality, a manipulation-success
test, a new preregistered endpoint, or a reason to rerun/omit a task.
Differences can be negative even in higher-budget arms, because a
configured cap is not guaranteed usage. They cannot authenticate the missing
2026 source evidence, change the frozen confirmatory analysis, or substitute
for real blinded human ratings. Keep pilot, confirmatory automated,
exploratory and pending human-validation claims separate.
