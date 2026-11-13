# Evaluation Methodology

This repository treats evaluation as part of the research system rather than as a post-hoc demo score. The current experimental program asks a focused systems question:

> **Where should a web-research agent spend limited retrieval and inference budget: deeper retrieval, explicit planning, or verification?**

The project has progressed beyond the original proposed-study document. Pilot infrastructure, D3/D6/P6/P6V treatments, persisted traces, a common post-hoc support evaluator, cost accounting, a frozen paired analysis plan, evaluator-only recovery, and secret-seeded, replay-verifiable human-evaluation packet generation are implemented on the research branch.

Human quality ratings are **not yet results**. They remain pending and must be collected under `paper/HUMAN_EVAL_PROTOCOL.md` before any human-quality claim is made.


### Shared diagnostic bootstrap-configuration contract (prospective only)

Both the reusable `bootstrap_confidence_interval` and the complete-task
`paired_bootstrap_confidence_interval_by_task` now call one shared parameter
validator **before reading samples or resampling**. A confidence level must be
an explicit built-in finite numeric value strictly between zero and one;
`n_resamples` must be an exact integer of at least two, and `seed` must be
an exact integer (including valid negative integer seeds). Strings, Booleans,
non-finite values, single-draw pseudo-intervals, and otherwise invalid
configurations raise `ValueError` rather than being coerced, reaching an
unhandled RNG error, or emitting a misleading degenerate percentile interval.
The existing empty-sample convention and all valid seeded percentile
estimates remain unchanged. Synthetic regression tests cover malformed
parameters, the before-consumption boundary, seeded reproduction, and
valid empty-input behavior.

This is a **prospective diagnostic input-integrity improvement**, not a
recalculation of frozen automated results or a new inferential claim. The
five-task pilot remains diagnostic, retrospective analyses remain exploratory,
the designated-primary automated study retains its post-collection-plan and
fixed-order qualifications, and original-report custody plus genuinely
independent blinded human validation remain outstanding.

### Complete-task paired bootstrap for prospective diagnostics

`logic.evaluation.paired_bootstrap_confidence_interval_by_task` is an opt-in
offline descriptive helper for *new* task-level measurements. It requires an
independently specified nonempty expected task-ID set, exactly one numeric
observation per task in each arm, and explicit finite confidence, integer
resample count (at least two) and integer seed. It rejects duplicate, omitted,
substituted, malformed or nonfinite task measurements **before drawing samples**.
It sorts the checked task IDs, computes candidate-minus-baseline differences,
then resamples those **paired differences**, rather than independently
resampling the two treatment arms. Consequently one-pass input generators and
different input row orders yield the same seeded result. The return includes
the paired descriptive summary, ordered task IDs, a method label and a
deterministic percentile interval for the *mean paired difference*.

A confidence interval produced by this helper is not an independently
preregistered confirmatory test, and the caller's task manifest still requires
separate provenance authentication. The helper is not used to recompute or
replace the historically frozen designated-primary automated contrasts; the
five-task pilot remains diagnostic, later retrospective sensitivities remain
exploratory, and real blinded human ratings are not yet collected. Synthetic
regression tests protect paired (not arm-independent) resampling, complete
task coverage, deterministic ordering, and fail-closed configuration.

### Diagnostic derived-summary finiteness (prospective only)

The general `logic.evaluation.aggregate_runs` summary and its complete-task
wrapper `aggregate_runs_by_task` reject derived non-finite output values
rather than publishing `Infinity` or `NaN` as descriptive statistics.
Valid nonnegative raw `RunTrace` counts may still exceed floating-point
representation during integer-to-float conversion; these invalid summaries
raise `ValueError` rather than silently publishing `Infinity` or `NaN`.

Population standard deviation centers and squares scale-normalized values
before restoring the original units. Means now use precision-preserving
summation and, only if the intermediate sum overflows, accumulate observations
divided by their count. Even-sized medians similarly halve the operands only
when their finite midpoint sum would overflow. Thus `[1e308, 1e308]`
has a representable mean **and** median of `1e308`, not an invalid
summary. Subnormal precision is retained in the ordinary path. Regression
tests cover aggregates, task-keyed summaries, paired diagnostic differences,
and the reusable descriptive bootstrap. Unrepresentable paired differences
and oversized integer counters still fail closed; estimator definitions and
uncertainty interpretation are unchanged.

This is **numerical integrity for prospective diagnostics**, not a new
statistical estimator, a correction
of historical telemetry, or an attestation of source custody. It applies only
to new in-memory diagnostic summaries. The original 40 treatment outcomes,
frozen automated inference, exploratory sensitivity checks, and pending real
human ratings remain separate and unchanged.

### Diagnostic bootstrap percentile underflow (prospective only)

The reusable offline `bootstrap_confidence_interval` previously interpolated
percentiles by separately multiplying both endpoint values by their weights.
For two identical smallest positive subnormal floats (`5e-324`), a half-way
quantile incorrectly became **zero**: each half underflowed before addition.
This could produce a zero-valued interval around a nonzero constant statistic
for supported draw counts (for example, 101 draws with the default 95%
confidence). Negative subnormal effects were equally vulnerable.

The interpolation now preserves equal endpoints exactly, calculates
same-sign interpolation from one endpoint and its finite difference, and
retains the weighted form for opposite-sign extremes where subtracting the
endpoints could overflow. Synthetic cases pin constant signed subnormal
intervals, bounded nonconstant subnormal percentiles, and the existing
opposite-sign extreme behavior. The percentile definition, resampling seed,
draw count, estimator, and ordinary finite results are unchanged. This
prospective numerical-integrity safeguard neither revises historical
automated/pilot/exploratory results nor establishes human validation or
original-report custody.

### Direct descriptive metric-input integrity (prospective only)

The shared `logic.evaluation._finite_float` boundary for the reusable
positional paired comparison and descriptive bootstrap now requires exact
built-in integer or floating-point *observations*. Previously, strings such
as `"1.0"` and Boolean statuses such as `True` were silently converted into
numeric measurements; a sufficiently large integer could instead escape as
an unhandled Python overflow. The same fail-closed contract now covers raw
baseline/candidate samples, bootstrap samples, and custom bootstrap
statistic returns. Negative and zero numeric observations remain valid for
these generic difference/statistic APIs; non-finite values still fail.
This aligns the positional boundary with the existing task-keyed metric
validation without changing the descriptive estimator, resampling method,
legacy empty-input convention, or any preserved experiment outcomes.

The fix concerns **prospective in-memory diagnostics** only. It does not
authenticate the original reports/traces, alter frozen designated-primary
automated inference, promote pilot or exploratory observations into
confirmatory evidence, or manufacture pending human validation.

### Diagnostic completion-status integrity (prospective only)

`RunTrace` requires `completed` to be an **exact Boolean** at construction.
Python treats nonempty strings such as `"False"` and nonzero integers as truthy;
previously, generic `aggregate_runs` could count such malformed statuses as
successful runs, distorting the descriptive completion rate. Strings, numbers,
`None`, and container placeholders now fail closed before either generic or
task-keyed aggregation. Valid failed and completed observations remain in
their original denominator. This is prospective in-memory diagnostic
validation, not retrospective authentication or revision of the frozen
40-cell treatment data, the post-collection designated-primary automated
analysis, exploratory sensitivity checks, or pending human ratings.

### Diagnostic resource-telemetry validation (prospective, not archival)

The generic, dependency-free `logic.evaluation.RunTrace` constructor rejects malformed
resource counters (`prompt_tokens`, `completion_tokens`, `source_budget`,
`query_count`, `search_call_count`, `model_call_count`, and
`unavailable_usage_call_count`). Each must be an exact nonnegative integer,
not a Boolean, fractional number, or coerced string. Unavailable-usage calls
cannot exceed total model calls. Diagnostic `latency_seconds`,
`estimated_cost_usd`, and the recorded sampling `temperature` must be finite
nonnegative built-in numeric values; NaN, infinity, negative values, Booleans,
text, and nonnumeric placeholders are rejected at trace construction. This
also prevents malformed sampling configuration from entering the trace JSON
and masquerading as reproducible provenance. No arbitrary upper temperature
bound is imposed because allowable values depend on the model/API; this is
numeric integrity, not verification that a provider actually used the setting.
Synthetic tests cover invalid values, legitimate zero and finite positive
configuration, and strict JSON serialization. This strengthens **new in-memory diagnostic telemetry**; it does
not revalidate or rewrite frozen September treatment files, independently
authenticate historical provider usage, change historical cost estimates, or
establish a human-evaluation result. The separate published-input and
original-report custody requirements still apply.

### Task-keyed completeness gate for new descriptive paired comparisons

For **new diagnostic** comparisons, `logic.evaluation.paired_metric_comparison_by_task`
accepts baseline and candidate `(task_id, metric)` records and an **explicit,
independently specified** `expected_task_ids` collection. It fails closed
on duplicate, empty, padded, substituted, or missing task identifiers,
including when **both** arms silently omit the same difficult task.
It validates finite numeric observations, rejects malformed records, and
sorts validated IDs before computing the same descriptive deltas and
win/tie/loss summary as `paired_metric_comparison`. The return includes
the exact sorted task identifiers for a checkable pairing receipt.

Positional `paired_metric_comparison` remains for backward compatibility;
its inputs must already be aligned by the caller. This stricter, opt-in
helper does **not** authenticate the expected task manifest, establish that
an evaluator measured the right report, or repair past experiments. The
frozen main-study inference and its separately pinned input-integrity
audits remain unchanged. Neither descriptive summary establishes a
prospectively preregistered confirmatory effect or human-validation result.

### Complete-arm task-keyed diagnostic aggregation (prospective only)

For **new descriptive analyses**, `logic.evaluation.aggregate_runs_by_task`
accepts one `RunTrace` per expected task, together with explicit
`variant_id`, `task_set_id`, and independently provided
`expected_task_ids`. It rejects omitted or substituted tasks, duplicate
task/run IDs, cross-variant or cross-task-set records, malformed identity
fields, and non-Boolean completion status. The function retains failed and
zero-source runs in the denominator rather than selecting only completed
cases; it sorts by task identifier before reusing the existing
`aggregate_runs` descriptive statistics, so row order cannot change the
accumulation order. The returned summary includes the exact task IDs and
treatment/task-set identity to support a checkable descriptive coverage claim.

For an additional prospective **task-text identity** check, callers can
supply `expected_questions_by_task` as an independent mapping from the frozen
task manifest (in addition to `expected_task_ids`). The optional gate requires
exactly the expected IDs, nonempty string question texts, and an **exact match**
between each observed `RunTrace.question` and the frozen text for that task.
It catches mislabeled or cross-task-swapped questions even when all task IDs,
variant IDs, and run counts remain valid. This check occurs before any
descriptive summary and includes failed and zero-source tasks; input ordering
cannot change its result. It does not normalize whitespace or silently
substitute the observed question for the reference. Omitting the new argument
preserves the previous API behavior for legacy traces that lack question text.

Example (the caller must source this mapping independently of the runs):

```python
summary = aggregate_runs_by_task(
    traces,
    variant_id="D3",
    task_set_id="prospective-v1",
    expected_task_ids=["task-a", "task-b"],
    expected_questions_by_task={
        "task-a": "First frozen research question?",
        "task-b": "Second frozen research question?",
    },
)
```

This opt-in binding is **not** a cryptographic source custody check: a
mislabeled trace can also carry an altered question, and an in-memory mapping
is only as trustworthy as the independently obtained manifest. It neither
authenticates original historical reports/traces nor changes any frozen
treatment, evaluator, or automated analysis result. The pilot remains
diagnostic, historical designated-primary automated inference remains
qualified by post-collection planning and fixed order, retrospective
sensitivities remain exploratory, and blinded human validation is pending.

This is an **opt-in fail-closed wrapper**: the generic `aggregate_runs`
remains unchanged for legacy callers. The expected task list must come from
an independent frozen manifest; the helper does not authenticate that
manifest or the input traces, verify evaluator provenance, or permit
multiple attempts per task. It does not rerun, reinterpret, or alter the
frozen 40-cell automated analysis; pilot evidence stays diagnostic, later
retrospective checks stay exploratory, and blinded human validation remains
pending.

## 1. Research questions

The main study is organized around three primary stage-wise questions plus a broader systems question:

- **Retrieval depth:** What changes when the direct-retrieval treatment receives six scheduled browse opportunities rather than three (`D6 - D3`)?
- **Planning:** At the same six-source browse budget, what is the marginal effect of explicit query decomposition (`P6 - D6`)?
- **Verification:** What is the marginal effect and cost of treatment-time verification (`P6V - P6`)?
- **Quality–cost trade-off:** Do improvements in evidence support justify additional model tokens, model calls, latency, and estimated dollar cost?

The broader research protocol and hypotheses are documented in `paper/RESEARCH_PROTOCOL.md`.

## 2. Study layers

The project deliberately separates four layers that should not be conflated.

### Layer A — Treatment execution

Each experimental variant generates a report under a defined planning/retrieval/verification configuration. The treatment itself records provenance, usage, costs, source outcomes, and final report artifacts.

### Layer B — Common automated measurement

A fixed post-hoc evaluator is applied to all treatment variants so that support labels are not available only for the verifier-enabled treatment. The evaluator is measurement-only and is kept separate from treatment generation.

### Layer C — Offline statistical analysis

Saved traces/evaluator records are summarized with a frozen paired analysis plan. Analysis operates on persisted artifacts; it does not rerun treatments merely because an observed result is inconvenient.

### Independent frozen-summary CSV preflight (offline, read-only)

The separately invocable offline command

    python -m scripts.audit_frozen_analysis_csv_inputs

audits the existing 40-cell treatment and common-evaluator **summary CSV
bytes**, without calling models or rerunning experiments. It fails closed
on ambiguous CSV rows/columns, incomplete or unbalanced task matrices,
fractional or nonfinite counts, negative usage/cost/latency measurements,
impossible evaluator count partitions, source-budget violations, and
disagreements between the evaluator's reported rates/costs and their
mirrored treatment-summary fields. For the frozen evidence-only rubric,
a cell recording zero successful sources must carry the explicit
`zero_successful_sources` evaluator sentinel and classify every checked
claim as unsupported. A sentinel with nonzero sources, or an internally
consistent but nonzero support/partial-support/contradiction count with
zero retrieved sources, fails the audit. Historical nonzero-source
cells may legitimately have an empty evidence-status field.
Count integrality is checked from decimal text before any float rounding.
The independent auditor now also applies the canonical CSV lexical rules to
its exact descriptor-captured byte snapshot before parsing or hashing: every
physical line must be one complete record; blank lines, quoted fields that
span lines, quotes inside unquoted fields, and text after closing quotes are
rejected. `csv.DictReader` would otherwise silently discard or normalize
some of these records while a SHA-256 fingerprint still describes their raw
bytes. This is internal input-interpretation integrity, not authentication of
unavailable treatment traces or a change to frozen statistical analysis.
The production/default audit now also verifies the exact original-run
`experiments/main_budget_tasks.json` source SHA-256 through
`scripts.verify_frozen_main_study_tasks` and requires all ten summary task
IDs to match the pinned original `main-01` through `main-10` set.
Previously, a coordinated replacement of all task IDs in both CSVs could pass
the balanced-pair checks as if it were the original study. This binding cannot
verify the questions or reports behind those IDs; recovering the unchanged
original traces and reports remains a separate mandatory gate.

The standalone production audit additionally compares the **captured exact
bytes of both CSVs** with fixed published SHA-256 inputs recorded in
`outputs/main_study_analysis_inputs_manifest.json` (aggregate
`4e94308472e87cc14b85e5911c40b5f72c63225862a347e624fc0725afd632aa`).
A coherently rewritten 40-cell table can satisfy pairing, source budgets and
support-rate arithmetic while changing scientific outcomes; it must **not**
receive a pass receipt claiming to audit the frozen published data. The
frozen byte fingerprints are pinned in the separate auditor implementation,
rather than loaded as mutable expected values from the same input bundle.
Only synthetic Python fixtures may explicitly disable this check with
`require_published_input_bytes=False`, in which case the receipt marks the
published-byte identity **unchecked**, not passed; CLI always enforces it.
This is a Git-recorded published-summary identity safeguard, not independent
authentication of original treatment traces, reports, or historical custody.

Input capture now rejects symlinked CSV files and parent directories,
non-regular files (including FIFOs), oversized inputs, and observed concurrent
rewrites or pathname replacements. Each CSV is read through one bounded,
regular-file descriptor (256 KiB plus one overflow byte) with before/after
identity, size, mtime and ctime checks; those exact bytes are both parsed and
SHA-256 hashed. This is a local snapshot-integrity guard, **not** independent
authentication of the historical experiment. An unobserved write-and-restore
between filesystem checks is outside the guarantee.

A compact receipt includes both summary-file SHA-256 values, the original
task-manifest source SHA-256, and whether original task-ID matching was
enforced, without scientific measurements or report text. Production CLI
audits always enforce this source identity. Only synthetic callers of the
Python API may explicitly pass `require_original_task_set=False`; the
receipt then marks the original task identity **unchecked**, not passed.
The source pin refers to the historical Git revision, **not** an independently
authenticated archive of the original executed reports. Synthetic regression
tests cover coherent task substitution and missing or rewritten source pins.

**The canonical inference script scripts/analyze_main_study.py remains
byte-for-byte unchanged.** Its historical SHA-256 is pinned in immutable
analysis provenance and must not be edited merely to add checks; editing
it invalidates independently reproducible historical-receipt verification.

### Independent mathematical regression anchors for frozen inference

`tests/test_main_study_inference_reference_cases.py` guards the unchanged,
source-pinned inference implementation with **synthetic, hand-checkable**
10-task sign-flip reference cases. The complete randomized-sign universe
contains `2^10 = 1,024` assignments, including zero-difference tasks.
For ten same-direction nonzero differences, the exact two-sided p-value
must be `2/1024`; for all-zero differences or one nonzero difference
with nine ties it must be `1`; for two same-direction differences with
eight ties it must be `1/2`. Task permutation and contrast reversal
must not change the exact sign-flip p-value.

Additional tests pin the predeclared three-contrast Holm family, bootstrap
seed/draw count, contrast definitions, constant-effect paired CI and direction,
and the all-tied undefined standardized effect. They protect inferential
interpretation against future regressions without altering
`scripts/analyze_main_study.py`, the preregistered analysis plan, or any
historical result. These are **mathematical test fixtures**, not pilot,
confirmatory, exploratory, or human-evaluation measurements.

This optional new audit neither changes the preregistered estimands nor
reclassifies original outputs; it does not authenticate missing
source traces/reports, prove experimental execution, or establish human
validation. Any discrepancy warrants investigation and a documented
protocol deviation, not silent alteration or selective treatment reruns.

### Layer D — Blinded human validation

An offline packet builder with a coordinator-secret shuffle seed hides variant identity and prepares the same reports for rubric-based human evaluation. Human annotations are a complementary measure of overall quality and usefulness, not a synthetic replacement for the automated support metric.

The first two eligible annotators receive source-bound bundles containing the
same blinded reports in canonical and exact reverse order. Section 11 records
this prospective, pre-collection operational control separately from the
frozen rubric, assignment, and analysis rules.

## 3. Frozen main-study treatment matrix

The current main-study analysis focuses on the following four conditions over the same frozen task set:

| Variant | Planning | Scheduled browse budget | Treatment verification | Main contrast role |
|---|---|---:|---|---|
| `D3` | Direct | 3 | No | Retrieval-depth baseline |
| `D6` | Direct | 6 | No | Retrieval-depth comparison / planning baseline |
| `P6` | Planner | 6 | No | Planning comparison / verification baseline |
| `P6V` | Planner | 6 | Yes | Verification comparison |

The full research protocol discusses additional possible retrieval levels, but those should not be silently mixed into the frozen confirmatory analysis unless a new study version explicitly declares them.

## 4. Task design

The study uses a versioned, frozen task set. The intended task mixture includes:

- multi-source factual synthesis;
- comparative research;
- questions where primary sources are preferable;
- conflicting-source questions;
- time-sensitive research;
- long-form synthesis prompts.

Tasks must not be edited after outcomes are observed and still be described as the same study version. New or corrected task sets require a new manifest/version and should be analyzed separately.

## 5. Primary automated outcome

The main automated outcome is **strict evidence support rate** from the common post-hoc evaluator:

`supported claims / claims checked`

The evaluator samples/checks a bounded number of factual claims and classifies support using evidence retrieved by the corresponding treatment. The analysis plan distinguishes strict support from broader support and explicitly avoids calling citation support equivalent to universal factual accuracy.

The automated evaluator should not be described as an unbiased human judge. It is a reproducible measurement instrument with its own model and prompt limitations.

## 6. Secondary outcomes

Secondary measurements include:

- broad support rate: `(supported + partially_supported) / claims_checked`;
- unsupported-or-contradicted rate;
- successful retrieved sources;
- scheduled/attempted source counts where available;
- prompt, completion, and total model tokens;
- model-call count;
- treatment latency;
- treatment-model estimated USD cost;
- report word count;
- completion/failure status;
- failure/provenance diagnostics.

Evaluator usage and evaluator cost are research-measurement overhead. They must not be mixed into the treatment/deployment cost comparison.

### General diagnostic RunTrace source-accounting guard (12 November 2026)

The dependency-free `logic.evaluation.RunTrace` helper now rejects non-integer
(including Boolean), negative or impossible source-attempt and failed-source
counts at object construction. A report with more failures than scheduled
attempts previously returned a silently clamped zero successful sources,
making invalid diagnostic telemetry appear to be a genuine zero-success
observation. Valid counts now satisfy `successful + failed = attempted`
without clamping; empty-attempt runs retain a defined zero success rate.
Offline synthetic tests cover both valid boundaries and invalid inputs.

This protects **new in-memory diagnostic summaries only**. It neither
retroactively reinterprets the frozen pilot, alters the independently
byte-pinned 40-cell automated study or its source-specific CSV audits,
authenticates missing treatment reports/traces, nor supplies human ratings.
It does not establish prospectively preregistered confirmation; exploratory
and human-validation claims retain their separate qualifications.

## 7. Budget accounting

A central integrity rule is that additional planning or verification computation cannot be described as “free.” Every relevant treatment run should retain enough metadata to reconstruct resource use, including:

- model/provider identifier;
- prompt/completion token usage;
- number of model calls;
- retrieval/search/browse activity;
- latency;
- configured browse budget;
- estimated cost under a frozen pricing snapshot.

When total compute differs across variants, the project uses a **quality–cost/Pareto interpretation** rather than falsely describing the variants as equal-total-budget systems.

For any future execution of `scripts/run_budget_main_study.py`, the create-only
study manifest also records the exact Python implementation/version, operating
platform string, and a sorted PEP-503-normalized inventory of every installed
Python distribution and version. This describes the environment that actually
loaded the treatment code, including transitive dependencies, rather than only
the intended top-level requirements. The inventory is captured before treatment
model code is imported or any treatment call begins. The runner reads the
version-controlled `.python-version` pin, records it alongside the exact runtime
patch version, and refuses a runtime outside that pinned major/minor (or exact
patch, when the repository pin includes one) before treatment imports or calls.
It also requires both `requirements.txt` and `requirements-ci.lock` to be
tracked regular files whose exact bytes match their recorded `HEAD` blobs. It
hashes and records each lock separately, requires every non-comment entry in
each file to be an unambiguous exact `name==version` pin, rejects duplicate
normalized names across the two locks, and fails before treatment imports or
calls when any locked distribution is missing or an installed version differs.
The manifest records the combined validated requirement set as well as the
complete installed-distribution inventory, so a recorded environment cannot
silently omit or misstate the workflow-environment supplement that constructed
it. Extra installed distributions remain visible in the inventory without being
treated as part of either reviewed lock.

All repository workflows install requirements through `python -m pip`, binding
the installation to the exact interpreter selected by `setup-python`. Runtime
packages come from the exact pins in `requirements.txt`; pytest and workflow
environment supplements that pip previously resolved transitively come from
`requirements-ci.lock`. Both files are installed with `--no-deps`, so pip
cannot silently resolve a newer transitive package outside the reviewed locks.
The subsequent `python -m pip check` is the closure check: a missing or
inconsistent dependency fails before offline tests, analysis, evaluator
recovery, or any live research step. This is a prospective execution safeguard;
it does not alter or reinterpret the preserved pilot or canonical main-study
artifacts.

The same prospective preflight requires a clean Git checkout and records both
the exact commit object and its tree object. The source state is checked again
after treatment modules load and before the create-only manifest is written. A
missing repository, tracked or non-ignored untracked worktree change, or
commit/tree drift therefore aborts before any treatment call instead of allowing
locally modified code to masquerade as the recorded commit. The check also
requires Git's top-level directory to be the project root and rejects
`assume-unchanged` or `skip-worktree` index flags, closing Git states that could
otherwise hide modified treatment source. Repository-discovery and object/index
overrides from inherited `GIT_*` environment variables are removed from these
read-only probes, so an external repository cannot supply the recorded commit,
tree, status, or index state for the project working tree. Finally, every
tracked `HEAD` entry must be a regular blob, and the runner computes each
working-tree file's raw Git object hash without clean/smudge filters and compares
it with the committed blob ID. Committed symlinks, submodules, filters, or other
states that make executed bytes differ while `git status` remains clean therefore
fail before treatment imports or calls. Before those imports, Python bytecode
lookup is also redirected to a newly created private empty cache and cache writes
are disabled. Treatment modules therefore compile from the attested source rather
than loading ignored adjacent bytecode, including unchecked-hash `.pyc` files.
The attested repository is placed first on Python's import path, inherited
`PYTHONPATH` roots are removed, and the two treatment entry modules must report
their exact repository source paths before any treatment call can begin.

These fields are prospective provenance. They do not retroactively add environment
metadata to the already-completed canonical treatment artifact and are not a
reason to rerun or replace those outcomes. The canonical run retains its
original GitHub Actions workflow, Git commit, dependency files, and logs; their
environment-recording limits remain a threat to exact replication.

### In-memory diagnostic claim-count validation

`logic.evaluation.RunTrace` now rejects negative, fractional, Boolean, and
text-valued source **and claim-classification counts** before calculating
diagnostic rates or exporting a run summary. The five classification fields
(`supported_claim_count`, `partially_supported_claim_count`,
`unsupported_claim_count`, `contradicted_claim_count`, and the legacy
`citation_count`) must be exact nonnegative integers; zero counts remain
valid. This prevents impossible count telemetry from producing a negative
citation proxy or an out-of-range strict claim-support rate. Citation
occurrences and verified claim labels are not generally the same unit, so
the generic helper does **not** require `citation_count` to equal the sum
of claim labels. This checks future in-memory diagnostic inputs only; it
does not authenticate or revise the frozen treatment traces, evaluator
recovery, primary automated estimates, exploratory analyses, or pending
human ratings.

## 8. Failure handling and provenance

A failed source fetch is not equivalent to a missing experiment. Likewise, zero successful evidence can be a valid treatment outcome rather than a reason to discard the run.

Important rules:

- zero retrieved evidence remains an observable outcome;
- under the frozen evidence-only post-hoc rubric, a zero-source sentinel
  cannot support, partially support, or contradict a factual claim; all
  checked claims must be labeled unsupported. Fresh results, retained caches,
  and canonical CSV inference fail closed on that inconsistency. This
  measures absence of *retrieved support*, not whether the report is false;
- treatment failures/timeouts are preserved rather than silently rerun until success;
- duplicate treatment executions are not substituted because their outcomes look better;
- if treatment execution is complete but measurement is interrupted, evaluator-only recovery may fill missing evaluator records without replacing the original treatment output;
- saved evidence and trace provenance must agree before an evaluation cell is considered valid;
- exclusions require an explicit pre-existing validity rule and must be reported.

New post-hoc evaluator caches use schema version 2. Each cache binds the exact
UTF-8 question, report, retrieved-evidence context, and final evaluator prompt
with SHA-256 and byte-size fingerprints. Evaluator-only resume recomputes these
fingerprints before any model call and rejects a stale schema-v2 cache if any
prompt input changed. The already-frozen canonical recovery caches predate this
field and remain readable as schema version 1 for historical reproducibility;
their cell identity and accounting are validated, but they must not be described
as carrying the newer byte-level evaluator-input binding.

Evaluator resume and offline summary generation also load the frozen task file
and require every treatment trace to carry its exact task-set ID and question
text. A trace whose task ID is absent from the frozen task set, whose task-set
metadata drifts, or whose recorded question differs from the frozen definition
is rejected before any evaluator model import/call and before summary outputs
are published. This prevents a correctly shaped treatment/evaluator cell from
being silently attributed to a changed research question.

The common evaluator configuration is also an explicit frozen contract:
`gpt-5.6-terra` at temperature `1.0`. Evaluator recovery rejects different
runtime settings before importing or calling the model client, and offline
summary generation validates every cache against those fixed values rather
than inferring the expected configuration from the first cache. This prevents
a coherently replaced cache set from silently redefining the measurement
instrument.

The evaluator renders both canonical aggregate artifacts completely before it
publishes either one. Each staged file is flushed and synchronized, then moved
over its destination with an atomic replacement; the output directory is
synchronized after both replacements. A failure while rendering or staging
therefore leaves the previous JSON summary and run-level CSV untouched and
removes temporary files. The two final path replacements cannot form one
filesystem transaction, so an interruption between them may leave generations
temporarily mismatched. To make that state detectable, the JSON summary binds
the exact run-level CSV bytes with SHA-256; the evaluator verifies that binding
after publication, and the downstream offline summarizer rejects a missing or
mismatched binding before it writes study-summary outputs.

Representative operational failure categories include:

- `planning_error`
- `search_failure`
- `browse_failure`
- `irrelevant_retrieval`
- `insufficient_evidence`
- `synthesis_error`
- `unsupported_claim`
- `citation_mismatch`
- `provider_error`
- `timeout_or_budget`

## 9. Frozen paired statistical analysis

The confirmatory automated analysis is specified in `paper/ANALYSIS_PLAN.md` and was frozen before inspecting main-study outcome summaries.

Primary paired contrasts are:

1. `D6 - D3` — retrieval depth;
2. `P6 - D6` — planning;
3. `P6V - P6` — verification.

For the primary strict-support outcome, the analysis reports:

- paired mean difference;
- paired median difference;
- deterministic paired bootstrap 95% percentile confidence interval for the mean difference;
- exact two-sided sign-flip/randomization p-value when all paired cells are present;
- paired standardized mean difference (`d_z`) when defined;
- counts of positive, negative, and tied task-level effects.

The three confirmatory p-values are adjusted together with the Holm step-down procedure. Because the frozen task set is small, effect size, uncertainty, and task-level consistency should be emphasized over binary significance language.

Additional metrics and contrasts are exploratory unless separately preregistered.

The manuscript-facing entry point, `scripts/run_verified_main_study_analysis.py`,
does not analyze live CSV paths after merely checking them. It captures both
canonical CSV inputs, re-checks the captured byte counts and SHA-256 digests
against the recorded manifest, validates that snapshot, and points the frozen
analyzer at the same snapshot. A concurrent edit therefore cannot make a
successful provenance receipt describe different bytes from those analyzed.
Before numeric or inferential validation, the shared study-input reader also
requires an unambiguous CSV table: headers must exist, be nonblank, and be
unique; every row must have exactly the declared number of fields; and malformed
CSV quoting is rejected. Canonical inputs are restricted to one CSV record per
physical line, and blank physical records are errors rather than silently
ignored data. The standalone preflight and verified snapshot gate use this same
reader, so a byte-fingerprinted but ambiguously parsed artifact cannot proceed
through the manuscript-facing analysis entry point.
New execution receipts bind the exact shared input-validator source alongside
the verified runner and independent execution verifier. The runner fingerprints
the validator source before validation, executes that exact captured byte stream
rather than a previously cached import, rechecks the canonical source after
analysis, and records the captured digest. This makes validator drift during or
after a run detectable without altering the frozen analyzer used by the
preserved legacy receipt.
The final success receipt is serialized completely into a same-directory
staging file, flushed, and synchronized before an atomic no-replace link makes
it visible. The receipt parent is opened without following a leaf symlink and
its inode is rechecked during invalidation and publication. A concurrent
publisher is therefore preserved and reported rather than overwritten, while
an interruption before the publication boundary cannot expose truncated JSON
at the canonical receipt path.
The analyzer runs in an isolated subprocess so concurrent in-process callers
cannot redirect one another through module-global paths. Future receipts emitted
by this updated entry point also bind the exact runner and independent
`scripts/verify_main_study_execution.py` source bytes. The preserved canonical
receipt predates that added execution-layer field and remains governed by
`scripts/verify_analysis_provenance.py`; it is not retroactively relabeled.
Downstream reconciliation permits that compatibility path only for the exact
pinned SHA-256 of the preserved receipt, so stripping `verified_execution` from
a future receipt cannot downgrade it to legacy verification.

## 10. Pilot vs. main study

The repository keeps pilot evidence distinct from the main study.

### Pilot

`paper/PILOT_RESULTS.md` documents the completed diagnostic pilot. It was used to validate instrumentation and expose reliability/accounting issues. It should not be promoted into a universal benchmark claim.

### Main-study infrastructure

The research branch implements:

- D3/D6/P6/P6V treatments;
- versioned run metadata and trace persistence;
- treatment usage/cost accounting;
- common post-hoc support evaluation;
- workflow validation and evaluator-only recovery;
- offline summary generation;
- a frozen paired inference script/analysis plan;
- deterministic human-evaluation packet generation.

A workflow or recovery run failing operationally must not be rewritten in documentation as a successful end-to-end execution. Final numerical claims should cite the exact canonical artifact set and execution provenance used for analysis.

## 11. Blinded human evaluation

Human evaluation is designed to answer questions the support evaluator does not fully capture.

The frozen rubric scores five dimensions from 1–5:

- correctness;
- completeness;
- source quality;
- synthesis/reasoning;
- clarity.

Build a packet from completed experiment traces with:

```bash
python scripts/build_human_eval_packet.py
```

The script creates:

- `outputs/human_eval/packet.jsonl` — blinded reports and research questions;
- `outputs/human_eval/ratings_template.csv` — blinded rating sheet;
- `outputs/human_eval/blinding_key.csv` — coordinator-only treatment mapping;
- `outputs/human_eval/manifest.json` — packet metadata.

The packet is deterministic given the **coordinator-only 256-bit seed** generated afresh by the production CLI (not the former public fixed default). The seed is retained in the restricted packet manifest for exact replay, but is excluded from CLI stdout and annotator distribution; otherwise public task/variant ordering makes blind IDs predictable. Existing fixed-seed packets must not be used for genuine blinded human scoring. The [pre-annotation blinding security addendum](../paper/HUMAN_EVAL_BLINDING_SEED_ADDENDUM.md) supersedes the historical fixed-seed sentence in the byte-pinned protocol without changing the frozen rubric or planned analyses. The builder fails closed on duplicate treatment/task cells, incomplete runs, missing Markdown reports, unexpected variants, or incomplete task matrices. The annotator-facing leakage audit covers rendered text and recursively percent-decoded Markdown URL metadata so encoded treatment labels cannot be hidden in link destinations; metadata exceeding the bounded decoding depth is rejected instead of bypassing or exhausting the audit, and opaque `data:` destinations are not permitted. Annotator-facing reports are text-and-links only: all Markdown image nodes are rejected because externally fetched or inline pixels can reveal treatment identity or change after the packet is frozen. Only canonical schema-version-2 treatment traces with object-valued experiment and trace sections can enter or later verify against the packet. When a persisted trace carries task-set identity in both its experiment configuration and run-trace payload, those copies must agree and match the frozen task manifest; neither packet generation nor later packet verification silently prefers one conflicting identity.

Before report access, export the first eligible annotator's source-bound bundle
in canonical order and the second's in exact reverse order:

```bash
python scripts/export_human_eval_annotator_bundle.py \
  --output-root outputs/human_eval/annotator-bundle-canonical-v2 \
  --presentation-order canonical

python scripts/export_human_eval_annotator_bundle.py \
  --output-root outputs/human_eval/annotator-bundle-reverse-v2 \
  --presentation-order reverse
```

Each schema-version-2 annotator manifest declares the order and fingerprints
the reordered packet and blank ratings template. Source-bound verification
derives that declared order from the verified coordinator packet, so relabeling
or coherently rehashing a different order fails closed. The two bundles retain
the same reports, blind IDs, rubric, and rating rows; only their presentation
sequence differs. For the required two-rater design, canonical plus exact
reverse pairs position `p` with position `41 - p`, balancing every report's
mean position at 20.5. This is an operational distribution control selected
before access to reports or ratings; it does not revise the frozen rubric,
eligibility/exclusion rules, estimands, missingness rules, or analysis plan.

Before accepting a completed blinded CSV, the coordinator can validate it
against the annotator's exact distribution bundle and retain an immutable
receipt:

```bash
python scripts/freeze_human_eval_ratings.py completed-ratings.csv \
  --preflight-bundle outputs/human_eval/annotator-bundle-canonical-v2 \
  --preflight-receipt-root outputs/human_eval/preflight-receipts/annotator-01
```

The optional receipt directory is published atomically and create-only. Its
schema-version-2 JSON binds the exact submission bytes to the verified bundle
manifest, packet, blank ratings template, annotator guide, and declared
presentation order. This preserves treatment-blind intake evidence before the
multi-annotator freeze; it neither reads the coordinator blinding key nor proves
annotator identity, independence, or real-world compliance. Those claims remain
subject to the separate attestations and frozen human-evaluation gates below.

The publishing command independently reads the visible receipt back and
recomputes the blinded submission-to-bundle binding before reporting success.
The same check can be repeated later without coordinator-only data:

```bash
python scripts/verify_human_eval_submission_preflight.py \
  --receipt-root outputs/human_eval/preflight-receipts/annotator-01 \
  --ratings completed-ratings.csv \
  --preflight-bundle outputs/human_eval/annotator-bundle-canonical-v2
```

Verification requires the receipt directory to contain exactly the canonical
JSON artifact, rejects symlinked roots and files, duplicate JSON keys, schema
type confusion, receipt tampering, and submission or bundle substitution. The
ratings and bundle remain blinded throughout this check.

Bind those intake checks into the final blinded freeze by supplying one
receipt/bundle pair for each ratings argument, in the same order:

```bash
python scripts/freeze_human_eval_ratings.py \
  outputs/human_eval/annotator-a.csv \
  outputs/human_eval/annotator-b.csv \
  --annotator-attestations outputs/human_eval/annotator_attestations.csv \
  --submission-preflight outputs/human_eval/preflight-receipts/annotator-a \
    outputs/human_eval/annotator-bundle-canonical-v2 \
  --submission-preflight outputs/human_eval/preflight-receipts/annotator-b \
    outputs/human_eval/annotator-bundle-reverse-v2 \
  --output-root outputs/human_eval/frozen-v1
```

This evidence-bound path independently replays every receipt against the exact
captured submission, requires the distributed packet to equal the final frozen
packet in the receipt's declared canonical or reverse order, and rejects
missing, duplicate, substituted, or reordered evidence. It archives a
filename-neutralized replay receipt and the treatment-blind distribution bundle
under neutral ordinal paths inside the create-only freeze; the original receipt
is verified but its caller-controlled submission filename is not copied into
the shareable snapshot. The independent freeze verifier replays the same chain
from those retained artifacts. A legacy-compatible freeze without
`submission_preflights` does not establish this intake-to-freeze chain and
must not be used as the planned human-validation evidence bundle.

Both this single-submission preflight and the later multi-annotator freeze
capture every submitted ratings CSV through a non-symlink regular-file
descriptor under a bound regular parent directory. The final freeze applies
the same boundary to its blinded packet, frozen protocol, assignment plan,
annotator guide, coordinator attestations, and archived producer/validator
sources. Non-regular inputs and file or parent replacement during capture are
rejected; parsing, hashing, and archival all consume the same captured bytes.

Annotators must not receive `blinding_key.csv` until ratings are frozen. The
entire 40-report packet must be independently double-scored and inter-annotator
agreement reported before adjudication. The coordinator must provide a
pseudonymous attestation CSV declaring, for exactly the submitted annotator IDs,
pre-report eligibility, treatment blinding, independent human-only scoring, and
no role in generating or selecting the rated reports. The create-only freeze
retains the exact attestation bytes and the independent verifier reparses them;
the declaration is auditable provenance, not independent proof of identity or
conduct.

After real ratings are frozen, the complementary human-analysis command writes
a create-only result bundle whose manifest binds the exact analysis and verifier
sources, both `requirements.txt` and `requirements-ci.lock`, `.python-version`,
and the Python implementation, version, and standard-library PRNG state contract
that produced the numeric outputs. Independent verification rejects source,
pinned-environment, or runtime drift before recomputing the analysis. Before
either blinded verification or unblinding, every analysis input is copied from
an open regular-file descriptor under a non-symlink parent and checked for stable
path, inode, metadata, and byte identity. Redirected parents and same-byte path
replacement therefore fail
closed instead of being laundered into the retained analysis snapshot. This
snapshot now also carries the complete retained `submission_preflights/` tree,
including each neutralized receipt and treatment-blind distribution bundle, so
the independent freeze verifier can replay the intake-to-freeze chain before
the coordinator mapping is opened. Every directory is held by descriptor while
its entry inventory is copied and rescanned; entry replacement, late additions,
symlinks, and non-regular entries fail closed. The freeze-root inventory is
similarly bound across the optional-archive decision, so a late archive cannot
be silently omitted by selective copying. Directory enumeration is also bounded
*at the scan*, not only after a full listing is sorted: each source directory
aborts at its first excess entry, and post-capture rescans stop at the first
addition beyond the original cardinality. This limits malicious or damaged
freeze-tree resource exhaustion without changing ratings, analysis outcomes,
or the predeclared statistical plan. These controls
record reproducibility metadata; they do not create ratings or convert pending
human validation into a result.

The downstream descriptive reconciliation bundle applies the same fail-closed
environment binding and additionally proves that both dependency locks and the
Python-version pin are the exact bytes recorded in its producing Git commit. This
remains a provenance check, not an inferential extension or a substitute for real
blinded ratings. Its manifest is a closed schema: undeclared fields, an altered
integrity statement, extra fingerprint members, and non-integer byte counts are
rejected rather than being accepted through permissive JSON or numeric equality.
The bundle directory is also closed to exactly the canonical JSON, deterministic
Markdown, and manifest; undeclared files or directories are rejected, including
entries added while the verifier captures the declared artifacts.
Before the no-replace rename, the publisher synchronizes every artifact and
the candidate/source directories; after the rename it synchronizes both source
and destination parents. A successful command therefore attests to durable
publication rather than only process-visible atomicity.

The reconciliation readiness gate holds every contract, automated-analysis,
provenance, human-analysis, and human-manifest input open by descriptor for the
full verification phase. It rejects symlinked input parents and detects entry,
inode, metadata, or byte changes before emitting a readiness receipt. The
reconciler repeats that descriptor-bound capture while consuming the verified
analysis inputs, closing the gap between readiness and result computation.
Before reconciliation, it also validates the mathematical support of the
pre-frozen measures: strict-support-rate task contrasts must be in `[-1, 1]`,
1–5 rubric task contrasts must be in `[-4, 4]`, and all declared task/pair/sign
counts must be non-negative integers. Impossible values and JSON booleans that
would otherwise compare equal to `0` or `1` fail closed.

Full instructions are in `paper/HUMAN_EVAL_PROTOCOL.md`.

## 12. Reproducibility map

Key research artifacts:

| Artifact | Purpose |
|---|---|
| `paper/RESEARCH_PROTOCOL.md` | Research question, hypotheses, experimental principles |
| `paper/PILOT_RESULTS.md` | Canonical pilot evidence and caveats |
| `paper/ANALYSIS_PLAN.md` | Frozen main-study confirmatory analysis |
| `paper/HUMAN_EVAL_PROTOCOL.md` | Blinded human-quality scoring protocol |
| `logic/experiment.py` | Experimental configuration/provenance structures |
| `scripts/run_budget_main_study.py` | Main-study treatment/evaluation orchestration |
| `scripts/summarize_budget_main_study.py` | Offline aggregation/validation |
| `scripts/analyze_main_study.py` | Paired preregistered inference |
| `scripts/build_human_eval_packet.py` | Deterministic blinded human-evaluation packet |
| `tests/` | Offline invariants and regression tests |
| `.github/workflows/` | CI and manual research workflows |

## 13. Offline verification

Install test dependencies and run:

```bash
python -m pip install --no-deps -r requirements.txt
python -m pip install --no-deps -r requirements-ci.lock
python -m pip check
python -m pytest -q
```

The ordinary unit-test suite is designed to run without making live LLM or web calls.

The human-evaluation packet builder is also offline; it consumes only persisted traces and Markdown reports.

## 14. Reporting rules

Research-facing documentation should follow these rules:

- do not convert `TBD`, pending annotations, or incomplete workflow artifacts into numerical claims;
- do not call support scoring “factual accuracy” unless truth is independently verified;
- do not call variants equal-budget when total compute differs;
- separate treatment cost from evaluator overhead;
- tie every reported number to a study/task version, commit/workflow provenance, model configuration, and analysis script;
- report failed runs and protocol deviations;
- distinguish pilot, confirmatory main-study, exploratory, and human-validation findings;
- avoid state-of-the-art or universal-superiority claims without a fair external benchmark.

## 15. Current status

The repository now has a reproducible evaluation architecture and a frozen human-evaluation protocol. The remaining research step is not to invent another metric: it is to collect real blinded annotations, validate the canonical main-study artifact set, run the predeclared analysis against that set, and write conclusions that stay within the measured evidence.


## Source-identified task-paired diagnostic bootstrap (prospective only)

The lower-level `paired_bootstrap_confidence_interval_by_task` receives
`(task_id, metric)` observations and cannot detect an accidentally mixed
treatment variant, altered research question, or reused run ID across arms.
`paired_run_trace_bootstrap_by_task` closes that metadata gap for future
`RunTrace` comparisons. It requires two **distinct** declared variants, one
task set, a complete independent task-ID set, and an independently obtained
**exact** task-ID-to-question mapping. Both treatment arms are validated
against the same reference before deriving any metric or drawing samples.
It also refuses any run ID appearing in both arms, preventing one run from
being accidentally treated as two independent treatment outputs.

For example, with the manifest sourced separately from the observed traces:

```python
from logic.evaluation import paired_run_trace_bootstrap_by_task

comparison = paired_run_trace_bootstrap_by_task(
    baseline_traces, candidate_traces,
    baseline_variant_id="D3",
    candidate_variant_id="D6",
    task_set_id="prospective-v1",
    expected_task_ids=["task-a", "task-b"],
    expected_questions_by_task={
        "task-a": "First frozen research question?",
        "task-b": "Second frozen research question?",
    },
    metric="claim_support_rate",
    seed=23,
)
```

The supported higher-is-better rates are `claim_support_rate`,
`source_success_rate`, and the **legacy**
`citation_precision_proxy` (not an independently verified citation-accuracy
measure). Failed and zero-source tasks remain present, including their zero
rates; no favorable-only filtering occurs. After identity validation, the
existing seeded, sorted-task **within-pair** percentile bootstrap estimates
candidate minus baseline; no new hypothesis test or significance claim is
introduced. One-pass trace/task iterables work, and input order does not alter
the seeded output.

This adapter checks **in-memory identity consistency only**. The independent
task/question reference must itself be authenticated elsewhere; matching
`RunTrace` metadata is not proof of report/trace source custody, treatment
independence, human scoring, or causal inference. Do not apply it as a
replacement for the frozen ten-task designated-primary automated procedure:
that plan was committed after the original collection, fixed treatment order
remains confounded, and source/evaluator comparability limits still apply.
The five-task pilot is diagnostic, retrospective measurement checks are
exploratory, and genuine blinded human evaluation remains pending. No
historical result is re-estimated or changed by this optional helper.


## Prospective treatment-setting fidelity check (optional)

A correct variant ID, task ID, and frozen research-question match can still
mask an observation recorded under the wrong treatment settings. Future
diagnostic callers can supply an independently pinned six-field configuration
to `aggregate_runs_by_task(expected_treatment_settings=...)`, or a
variant-keyed pair of configurations to
`paired_run_trace_bootstrap_by_task(expected_treatment_settings_by_variant=...)`.

Each configuration must declare exactly `planning_mode`,
`verification_mode`, `source_budget`, `smart_model`, `fast_model`, and
`temperature`. The input contract validates text, nonnegative integer
budget, and finite nonnegative numeric temperature. Every field is compared
exactly to every observed run (including failed and zero-source tasks).
Both plans are validated **before** reading either paired treatment-arm
iterator. A missing, additional, malformed, or drifted setting fails closed.
Omitting this opt-in contract keeps existing callers and estimates unchanged.

A synthetic illustration (these are not assertions about historical settings):

```python
planned = {
    "D3": {"planning_mode": "direct", "verification_mode": "off",
           "source_budget": 3, "smart_model": "smart-v1",
           "fast_model": "fast-v1", "temperature": 0.0},
    "D6": {"planning_mode": "direct", "verification_mode": "off",
           "source_budget": 6, "smart_model": "smart-v1",
           "fast_model": "fast-v1", "temperature": 0.0},
}
paired_run_trace_bootstrap_by_task(
    baseline_traces, candidate_traces,
    baseline_variant_id="D3", candidate_variant_id="D6",
    task_set_id="prospective-v1", expected_task_ids=["task-a", "task-b"],
    expected_questions_by_task=independently_pinned_questions,
    expected_treatment_settings_by_variant=planned, seed=23,
)
```

Source the plan **independently of the observed traces**. Matching recorded
configuration does not prove the provider actually honored it, authenticate
original trace/report custody, eliminate fixed-order confounding, or correct
historical evaluator-policy differences. No pilot, frozen designated-primary
automated, exploratory, or human-validation result is changed or promoted
by this prospective diagnostic guard. Blinded human validation remains pending.
