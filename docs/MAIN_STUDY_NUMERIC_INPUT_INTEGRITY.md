# Main-study CSV numeric integrity: independent offline preflight

**Scientific status:** Input-consistency audit only. This does not create new
experimental, inferential, exploratory, or human-evaluation outcomes.

The frozen automated inference implementation is SHA-256-bound by the
historical canonical-analysis receipt. **Do not edit or rebind
`scripts/analyze_main_study.py` to add a new input rule.** This verifier
is deliberately separate and read-only, preserving the published result
and its ability to be independently recomputed with the exact historical
implementation. The verifier checks CSV source-internal numeric validity
before a reviewer or later analysis trusts an input table; it is not a new
estimator and does not modify any frozen output.

The preflight rejects nonfinite/negative numeric fields, fractional
integer counts (without rounding them into observations), nonpositive
or over-cap evaluator claim counts, count partitions that do not add up,
missing/duplicate treatment/task cells, and rates inconsistent with
supported/checked counts. It crosschecks the treatment CSV's mirrored
post-hoc claim count, strict rate and evaluator cost with the common
evaluator CSV, and verifies the frozen treatment browse-budget limits.
The source budget applies to **successful plus failed** retrieval slots, not
only successful ones. The recorded treatment `cost_status` must match the
historical summarizer's literal `estimated_from_frozen_uncached_rates` label:
these costs are token-based estimates under frozen uncached rates, **not
provider invoices or observed billing**. Numerically identical costs cannot
be relabeled as billed amounts or as a different pricing methodology while
still receiving an independent consistency receipt. This categorical check
is source-internal and does not authenticate the original pricing source,
provider billing, or missing treatment traces. Each evaluator record must have a nonempty run ID unique
across all 40 cells. A treatment with zero successful sources must carry the
`zero_successful_sources` evaluator sentinel and classify every checked claim
as unsupported, never as supported, partially supported, or contradicted;
nonzero-source cells cannot carry that sentinel. These are source/evaluator
accounting constraints, not claims about the authenticity of original traces.
Small decimal export discrepancies up to absolute `1e-12` are accepted
for rates and cost mirrors. Each observed 10-task × four-arm cell is
included; zero-successful-source treatments remain valid.

The generated receipt contains the original input CSV byte SHA-256
fingerprints and only counts, not scores or new treatment comparisons.
This is **internal consistency**, not proof that the original reports
or traces were authentically archived, nor that automated evaluator policy
was identical across historically recovered cells.

## Offline verification

```bash
python -m scripts.audit_main_study_numeric_inputs
python -m pytest -q tests/test_main_study_numeric_integrity.py
```

These commands make no network/model calls, do not regenerate treatments,
evaluator results or historical statistics, and do not edit canonical
inference artifacts. The dedicated CI workflow runs the same read-only
checks on subsequent source changes. The existing frozen-recomputation
suite independently protects the **original** historical analyzer bytes.

The five-task pilot remains **diagnostic**; the September automated
main-study outcomes retain their post-collection statistical-plan
chronology and fixed-order/evaluator-recovery qualifications; retrospective
sensitivity analyses remain **exploratory**; and human validation remains
pending original-source custody and two independent blinded annotators.


## Local CSV capture and receipt continuity

The read-only numeric preflight now opens each fixed CSV using a held file
descriptor with no-follow directory and file flags. It requires a regular,
single-linked input no larger than 2 MiB, reads only the initially observed
length, detects append-only growth, and checks the opened inode, pathname,
size, link count, and modification/change metadata before accepting bytes.
After semantic validation it independently recaptures both original paths
and refuses to issue the receipt if either content changed. Synthetic
regressions exercise symlinks, hard links, oversized inputs, path replacement,
in-place modification, and post-parse edits; they do **not** use live treatment
or evaluator observations.

This is a **bounded, locally consistent capture**, not an atomic snapshot of
two files, and not proof of historical originality, collision resistance of
filesystem metadata, or protection against an attacker who changes bytes and
restores them between observation points. The auditor reports hashes of the
actual bytes it parsed; it does not revise or authenticate the original 40
reports/traces. The separately frozen September analyzer and all recorded
automated/pilot/exploratory results remain unchanged.


## Bounded numeric conversion

The independent preflight rejects numeric tokens longer than 128 characters,
nonzero decimal measurements whose adjusted base-10 exponent lies outside
[-324, 308] or which overflow or underflow to a nonfinite/zero binary64
value, and integer counts above 2^53−1. These are defensive parsing
bounds, not new scientific thresholds or revised scores. In particular, a
short token such as `1e1000000000` must not allocate a billion-digit integer
when an externally supplied CSV is audited. The count ceiling matches the
separate pinned-input auditor's exact-integer limit; all original CSV values
remain unchanged. Synthetic tests exercise oversized tokens, extreme positive
and negative exponents, nonrepresentable binary64 values, out-of-range
counts, and acceptance of the smallest subnormal value.

This check is independent of, and does not replace, the frozen byte-pinned
analysis-input verifier. It does not establish historical report/trace custody,
preregistered confirmatory status, or human-evaluation results.


## Formula-like CSV cell and row-shape checks

Both frozen automated main-study CSVs are human-readable research exports.
CSV quoting alone does not prevent spreadsheet applications from executing a
cell starting with `=`, `+`, `-`, or `@`. For example, `+1.25`
compares numerically equal to `1.25`, so numeric consistency alone cannot
certify spreadsheet-safe source bytes. The independent verifier now rejects
formula-like prefixes in **every exported cell and header**, including
unconsumed metadata, after leading whitespace, Unicode separator, control,
or format characters. It rejects missing or surplus CSV fields as well.
No inputs are escaped, modified, or re-serialized; rejected exports fail
closed before the verification receipt is issued.

Synthetic, offline reproduction:

```bash
python -m pytest -q tests/test_main_study_csv_export_safety.py
python -m scripts.audit_main_study_numeric_inputs
```

This is spreadsheet-import hygiene, not a guarantee about any particular
spreadsheet engine, and not independent authentication of the original 40
reports/traces. The five-task pilot remains diagnostic, frozen automated
inference remains qualified by its post-collection analysis plan and
recovery-policy differences, retrospective sensitivity remains exploratory,
and actual human validation has not been conducted.


## CI provenance prerequisite for the independent numeric audit

The dedicated `main-study-numeric-input-integrity` workflow now executes the
**existing** `scripts.verify_published_main_study_inputs` verifier before its
source-internal numeric check, in one unconditional fail-closed job. Previously,
the numeric job could pass for two coherently changed CSVs: their local
SHA-256 receipt did not require the originally published fixed input aggregate.
The source verifier instead compares the two frozen CSVs and their saved
manifest with the previously preserved canonical aggregate digest. This
reuses an established guard; it does not mint new historical provenance.

Both push and pull-request path filters now cover the saved manifest and all
static first-party script dependencies of the published-source verifier.
An offline regression checks trigger coverage, read-only permission, and
execution order. To reproduce the same combined gate locally:

```bash
python -m scripts.verify_published_main_study_inputs
python -m scripts.audit_main_study_numeric_inputs
```

Passing establishes checkout-level identity with the preserved *published
CSV input aggregate* and numerical consistency, **not** independent custody
of original treatment traces/reports or uniform historical evaluator policy.
The gate does not prove provider billing, prospective preregistration,
randomization, human ratings, or source-verified human-evaluation readiness.
It changes no canonical measurements, inferential procedures or findings.

## Historical evaluator evidence-status interpretation in the numeric receipt

The independent CSV audit now restricts `evidence_status` to the three
literal forms present in the published frozen evaluator export: blank,
`retrieved_evidence`, and `zero_successful_sources`. Unknown or
relabelled statuses fail validation rather than being silently accepted as
a fourth evidence policy. A blank remains **unspecified**; it is not
converted into `retrieved_evidence` merely because the treatment CSV records
at least one successful source. A zero-source treatment still requires the
explicit sentinel and all claims unsupported, as before.

The read-only numeric receipt counts these *declared labels*, separately
from numeric scores. In the unchanged 40-cell published CSV this is
**37 blank/unspecified, 2 explicitly `retrieved_evidence`, and 1 explicit
`zero_successful_sources`**. These correspond to the source-linked
[historical evaluator measurement partition](HISTORICAL_EVALUATOR_MEASUREMENT_PARTITION.md);
the new counters do not themselves prove which historical provider calls
executed, authenticate original archives, or assert identical evaluator
input-admissibility policies. The receipt explicitly sets
`historical_evaluator_evidence_status_authenticated: false`.

Synthetic offline regressions cover unknown/whitespace-relabelled statuses,
acceptance of true legacy blanks, the distinction between a retrieved-evidence
*declaration* and independent source custody, and the saved 37/2/1 label
partition. No experimental measurements, provenance pins, analysis settings,
or human ratings are changed. The pilot is diagnostic; automated main-study
inference remains frozen but qualified; historical status accounting is
retrospective provenance, not a confirmatory test; human validation is pending.
