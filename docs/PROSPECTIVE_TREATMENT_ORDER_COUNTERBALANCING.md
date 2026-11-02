# Prospective treatment-order counterbalancing (design-only)

**Status: optional future-study design tool, not a historical repair, not a registered replication, and not a result.** No treatment, common evaluator, statistical inference, or human annotation is executed by this tool.

## Problem addressed

The frozen September 2026 ten-task VERA main study ran each task's variants in the fixed sequence **D3 → D6 → P6 → P6V**. Retrieval and provider conditions could change between calls. Paired-by-task inference does not remove this treatment-versus-time confounding; exact paired sign-flip inference should not be described as randomization in the original study. See MAIN_STUDY_EXECUTION_ORDER_VALIDITY.md and paper/ANALYSIS_PLAN.md.

To remove *systematic* treatment/position coupling in a **separately defined, prospective** ten-task replication, the new offline helper **scripts/plan_counterbalanced_replication.py** creates a reproducible ten-row ordering plan. It is intentionally **not wired into** the original runner or its Actions workflow. Its output cannot replace or repair the historical 40 treatments, and its source manifest must be a *new* independently selected task set fixed before the proposed replication begins.

## Pre-execution design contract

The helper accepts exactly ten distinct new task IDs and questions in a bounded UTF-8 JSON file using **only** these fields:

~~~json
{
  "schema_version": 1,
  "task_set_id": "new-independent-task-set-identifier",
  "frozen_before_execution": true,
  "tasks": [
    {"id": "new-01", "category": "research", "question": "A new research question"},
    {"id": "new-02", "category": "research", "question": "A different question"}
  ]
}
~~~

This is a **schema illustration, not a valid runnable manifest**: the actual file must contain ten distinct entries; do not pad the manifest with historical tasks or select tasks based on the original result directions.

Run in an offline checkout after an independently selected future task set is frozen:

~~~bash
python -m scripts.plan_counterbalanced_replication --task-manifest /path/to/new_frozen_ten_tasks.json > /path/to/proposed_order_receipt.json
~~~

The helper itself writes **only to stdout**. It refuses the original historical task-set ID, the ten reserved original task IDs (`main-01` through `main-10`), verbatim reuse of any of the ten frozen original questions even under case changes, Unicode NFKC variants, or whitespace-only changes, unknown or outcome-bearing JSON fields, duplicate keys, IDs or questions, non-finite JSON, missing freeze flag, ambiguous source types, symlinks, oversized inputs (>256 KiB), and an incomplete matrix. These historical-question fingerprints are checked against the byte-pinned September 2026 original source manifest (`experiments/main_budget_tasks.json`) by offline regression tests; they are not derived from measured outcomes or from recovered report artifacts. This **does not** detect paraphrases, substantial rewrites, near-duplicate tasks, conceptual overlap, or deliberate evasions. A coordinator must still independently document task selection, genuine independence, pre-execution timestamp, and integrity, and ensure there is no treatment outcome feedback into selecting or rewording tasks.

The printed receipt includes both the exact SHA-256 of the source manifest bytes and a separate canonical-semantic task-manifest SHA-256 used to assign slots, plus a deterministic design-version identifier, ordered treatment IDs by task, positional counts, pairwise precedence counts, and a SHA-256 of the canonical receipt fields. Reformatting JSON or changing key order does **not** change arm assignment, but does change the source-byte custody hash and full receipt hash. The receipt hash is **not** an external timestamp or independent pre-registration attestation. Preserve the actual manifest and the receipt in a separately reviewable pre-execution location before authorizing future work.

## Design guarantees

The fixed even-order four-treatment Williams Latin square has rows (using the arm index order D3, D6, P6, P6V):

- D3, D6, P6V, P6
- D6, P6, D3, P6V
- P6, P6V, D6, D3
- P6V, D3, P6, D6

Two copies cover eight tasks; the final two schedules are D3, D6, P6, P6V and its reversal. A deterministic SHA-256-based, canonical-task-manifest-bound slot permutation assigns the ten rows to the ten new task IDs. No treatment measurements or adjustable outcome-tuning seed enter the schedule.

For **each** of the six unordered treatment pairs, each member precedes the other on exactly **5 of 10 tasks**. Each variant occurs at every within-task position either **2 or 3 times** across ten tasks—the mathematically closest possible balance because ten is not divisible by four. Every task receives all four conditions exactly once, for **40 planned cells**. Offline regression tests verify these invariants and the receipt digest.

This balances *position* and *pairwise ordering*, **not** total tokens, latency, dollar budget, or time-varying web content. It does not guarantee independence, remove across-task temporal drift, or imply random assignment in the original study. There is no claim of a causal effect or inference validity from a schedule alone. An actual future independent replication would need its own ethics/provenance, predeclared budget and inference decisions, clean source custody, and separate human validation.

## Historical task-set leakage guard (prospective only)

The prospectively selected task manifest must not quietly recycle previously evaluated questions under fresh IDs: this would invalidate an assertion that the new ten-task replication is independent of the historical main study. The planner now compares SHA-256 of each question after Unicode NFKC normalization, casefolding, and collapsing whitespace against ten source-anchored frozen original-question fingerprints. It also reserves the ten original task IDs. This rejects **normalized exact reuse** only; it is not a semantic similarity filter and does not establish novelty or task-selection blinding. A test checks that the ten stored fingerprints correspond to the full, byte-pinned historical task source; unexpected changes fail closed in CI. The guard performs no treatment, evaluator, or human-annotation execution.

## Within-manifest task uniqueness (prospective only)

A ten-row schedule does not yield ten independent research questions if two task
IDs contain the same question written with different capitalization, spacing,
or Unicode compatibility characters. The initial planner rejected only
`question.strip()`-identical strings, so the same question could enter twice
under distinct task IDs and inflate the apparent number of independent task
units in a future paired analysis.

The planner now checks **within the new manifest** for collisions of
NFKC/whitespace/casefold-normalized question fingerprints, using the same
normalization as the historical-task leakage guard. It fails closed before
assigning any treatments; the independent verifier also rejects an invalid
manifest rather than accepting a self-consistent schedule. Offline synthetic
tests cover case, whitespace, Unicode-width, and casefold-equivalent duplicates.
Task IDs must separately remain unique.

This is a **normalized-exact duplication check**, not a semantic-overlap test:
paraphrases, closely related tasks, and shared source dependencies can still
reduce effective task independence. An independent coordinator must review and
document those risks *before* freezing any future manifest. No historical
tasks, automated measurements, confirmatory results, exploratory findings, or
human-evaluation outcomes are changed by this prospective-only guard.

## Research claim separation

- **Original pilot:** diagnostic operational evidence only.
- **Original 2026 confirmatory analysis:** frozen paired automated measurements from the historical fixed-order main study; unchanged by this design.
- **Exploratory robustness checks:** retain exploratory status and cannot choose a favorable future schedule from observed results.
- **Human validation:** still pending two eligible blinded annotators and authenticated original reports; this prospective schedule produces none.

This work neither recovers the absent original treatment/recovery artifact listings nor resolves the historical source-to-evaluation custody gate. Do not distribute human packets or represent VERA as fully validated on the strength of this planning tool.


## Independent pre-execution receipt verification

A prospective design receipt is not self-authenticating: a coordinator could edit its task-to-order mappings after creation, keep the aggregate order counts unchanged, and recompute its self-hash. Before using **any future** receipt for execution planning, independently reconstruct and compare every field against the retained exact manifest bytes:

~~~bash
python -m scripts.verify_counterbalanced_replication_plan --task-manifest /path/to/new_frozen_ten_tasks.json --plan-file /path/to/proposed_order_receipt.json
~~~

The verifier is offline, read-only, and no-model-call. It requires a bounded regular no-follow task manifest and receipt; rejects duplicate/nonstandard JSON, unexpected fields, altered assignment even if all aggregate balance counts still match, source-manifest changes, wrong data types and mismatched SHA-256 hashes; and prints only a compact audit receipt. Whitespace in the plan receipt may differ if there is **no external byte pin**, because it compares canonical JSON fields rather than text formatting. The exact input manifest byte digest, not merely semantic task content, must match.

For stronger custody, retain the **SHA-256 of the exact plan file** with an independent pre-execution timestamped record, and verify it with `--expected-plan-file-sha256 <64-lowercase-hex>`. This option checks a coordinator-*supplied* digest; it does **not** attest its independence, publication time, authorization, or the originally frozen task-selection process. A verifier pass without this pin means **internal consistency only**; with a matching pin, it means consistency with the supplied prior value, **not** independent registration proof. Coordinators should preserve the original manifest, plan file, digest, and an externally reviewable timestamp before work begins. This does not modify the original 2026 treatment data or resolve their source-custody and human-rating gates.


## Independently retained task-source pin (prospective-only)

The plan verifier recomputes every assignment from the **supplied** manifest,
but an attacker or accidental edit can rewrite both the manifest and plan and
still produce a self-consistent receipt. When the coordinator has separately
preserved a SHA-256 fingerprint of the **original task-manifest bytes before
execution**, verify those exact bytes independently:

~~~bash
python -m scripts.verify_counterbalanced_replication_plan \
  --task-manifest /path/to/new_frozen_ten_tasks.json \
  --plan-file /path/to/proposed_order_receipt.json \
  --expected-task-manifest-sha256 <independently-retained-prerun-source-sha256>
~~~

The result includes `supplied_task_manifest_pin_matched`. This optional pin
is distinct from the existing plan-file pin; both can be supplied together.
It rejects even formatting-only source changes, although those need not alter
the Williams assignment. A matching self-computed digest is *not* proof of
independent retention, preregistration, task independence or execution. The
pilot, historical automated confirmatory findings, exploratory analyses,
future design and pending human ratings remain separate.

## Invisible-character task-source integrity (prospective-only)

The offline plan now **rejects** hidden Unicode formatting and control characters
in the proposed new task's \`question\` or \`category\` before computing its
manifest-bound schedule. Previously, a zero-width character, bidirectional
override/isolate, grapheme joiner, or variation selector could change the
original task bytes **and** the assignment digest while leaving the task
visually indistinguishable. It could also make an otherwise identical
historical or within-manifest question evade normalized-exact duplicate
checks, undermining the independence claim for ten future task units.

The validator refuses Unicode format characters (\`Cf\`), C0/C1/DEL controls
other than ordinary tab/newline/carriage-return formatting, U+034F,
Mongolian variation selectors, and standard/supplementary variation
selectors. It **does not rewrite** submitted task text; accented characters,
ordinary combining diacritics, line breaks, and printable multilingual text
remain accepted. The independent receipt verifier rebuilds the plan through
this same validation and rejects coherently rehashed invalid input.

This is a conservative pre-execution validity rule: some languages and emoji
uses intentionally rely on format characters or variation selectors. Those
future task designs require an explicit, separately reviewed/versioned rule
rather than silently stripping characters before giving the prompt to a model.
The guard cannot detect visually confusable letters, paraphrases, conceptual
overlap, biased task selection, or results-based schedule selection through
ordinary visible edits. Independent pre-execution registration is still
required. No original pilot/confirmatory/exploratory results, treatment runs,
or human evaluations are changed.

