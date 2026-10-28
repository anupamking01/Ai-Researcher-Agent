# Recover the original automated-to-human VERA evidence (no outcome reruns)

**Status (2026-10-27): blocked on original report and handoff custody.**
This is an operational inventory and recovery plan, not an experiment or human-evaluation result.

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
