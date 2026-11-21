# Independent arithmetic audit of VERA primary contrasts

Status: **additional prospective verifier, not a new analysis or revised result**.

The canonical analysis provenance verifier already reruns the byte-pinned
historical analyzer and checks exact output bytes. Reusing the same analyzer
cannot independently detect an error in its original primary paired arithmetic.
The optional new auditor `scripts/audit_primary_inference_independently.py`
checks the preserved primary results through a separate, small implementation
using exact rational arithmetic for claim-support fractions and exhaustive
paired sign-flip enumeration.

From the repository root:

```bash
python -m scripts.audit_primary_inference_independently
```

Optional `--main`, `--evaluator`, and `--inference` paths support reviewing
local copies without writing output. The historical SHA-pinned CSV export lacks pricing-metadata fields required by
the newer prospective strict canonical preflight. The auditor therefore runs
the shared row-level scientific input validator and **separately** requires
the exact 40 frozen treatment/task cells, unique identities, matching
treatment/evaluator rows, evaluator count conservation, and published
treatment/evaluator support-count and strict-rate mirrors. This is not a claim
that legacy CSVs satisfy the newer prospective metadata contract. It rejects
duplicate or non-finite inference JSON members.

**Read-only input snapshot integrity (6 November 2026):** The optional
independent auditor captures both CSVs through the existing 256-KiB
descriptor-bound frozen-summary CSV reader, so lexical validation, parsing and
subsequent arithmetic use the *same* captured bytes. The inference JSON is
captured through a bounded 8-MiB regular-file descriptor with source-path,
size, metadata and hardlink checks before/after reading; symlinked ancestors
and observed concurrent rewrites or replacements fail closed. Its fixed-schema
JSON input also rejects nesting beyond 32 containers, numeric tokens beyond
128 characters, and nonfinite numeric values before expensive bootstrap
recomputation. Synthetic-only regression tests cover these failure modes and
quoted bracket escapes. This is an internal current-file consistency guard,
not a new historical SHA pin, independent proof of original experimental
custody, or a change to the preserved inference implementation. Both CSV captures now require a single-link regular file and detect changes
to the inode link count during capture. This rejects hard-link aliases that
can otherwise be rewritten through a second pathname without replacing the
named source. The rule is a local snapshot safeguard, not cryptographic
custody or detection of unobserved changes after a successful read. The summary
CSV reader remains shared with the existing independent CSV preflight; only
the *statistical arithmetic* here is separately implemented.

**Three-source observation window (6 November 2026):** The independent
auditor now retains the initially captured inference-JSON and two CSV byte
sequences and a filesystem generation identity for each source, completes the
statistical arithmetic, and then recaptures all three paths using their
existing bounded descriptor readers. A modified file, an observed same-byte
pathname replacement, or a failed final capture aborts the audit instead of
returning a successful receipt based on inputs that have changed during the
arithmetic. Synthetic regression fixtures exercise changes to all three
sources, same-byte replacement, and an unchanged read-only case. This check
does not lock the files, establish archival custody, guarantee detection of
unobserved transient mutations, or turn the independent arithmetic check into
a new statistical analysis.

It checks: frozen task order and configuration, report-level strict-support
fractions, four variant mean strict-support rates, the three preregistered
left/right paired means and mean/median contrasts, all ten task differences per
contrast, sign counts, paired standardized effects, exact two-sided sign-flip
p-values across 2^10 assignments, the three-test Holm family, **and the three
predeclared 95% paired-bootstrap percentile intervals**. The interval check
recreates the frozen 20,000 within-task-pair resamples for each contrast with
the prespecified seeds 20260914, 20260915, and 20260916. It computes the
resample means and linearly interpolated 2.5%/97.5% quantiles using exact
rational arithmetic rather than the historical analyzer's floating-point
mean and percentile helpers; comparison allows only a 1e-12 absolute
rounding difference. The seeded Python `random.Random.randrange` index
stream is intentionally shared to match the frozen resampling procedure.
A mismatch fails closed. No model/provider access, experimental execution, evaluator
recovery, or human-rating input is involved.

The implementation intentionally does **not** import the historical analyzer's
math helpers. Arithmetic consistency is independent of the frozen inference
implementation, but the auditor shares the existing scientific input preflight;
it is not an independently developed validation of that entire input schema.

**Additional independent exploratory-descriptive check (27 October 2026):**
The same read-only command now independently reconstructs all eight frozen
secondary outcome types (broad support, unsupported/contradicted fraction,
successful sources, tokens, treatment cost, latency, model calls, and report
words) from the preserved treatment/evaluator CSV records. Count ratios use
exact rational arithmetic; treatment measurements are parsed through
`Decimal` to rational values rather than the historical float aggregation.
For each variant it checks all eight means and the zero-evidence report count;
for each of the three frozen contrasts it checks eight task-paired point
descriptives: means, mean/median differences, all task differences, paired
standardized differences, and positive/negative/tie counts. Malformed,
missing, or inconsistent metrics fail closed. This is **not** a new secondary
hypothesis test, primary outcome, or preregistered confirmation. No p-values
are added and no analyses are selected based on favorable effects.

**Independent descriptive Pareto check (27 October 2026):** The same
read-only audit now reconstructs the frozen cost-quality frontier directly
from report-level strict-support counts and treatment-only cost records. It
uses exact fractions for both ten-task means and verifies the complete
ordered dominated-by relation, non-dominated frontier, fixed variant set,
and the historical scope note excluding evaluator measurement overhead.
The strict criterion is no worse on both axes with a strict improvement
on at least one; equal quality *and* equal cost does not imply dominance.
This verifies a descriptive summary only; it does not select a treatment,
alter hypotheses, add a significance test, or establish human quality.

**Independent secondary bootstrap check (27 October 2026):** The offline
auditor now also reconstructs all **24** preserved exploratory paired-bootstrap
95% percentile intervals (three frozen comparisons × eight secondary metrics).
It uses the existing 20,000 with-replacement, task-paired resamples and the
historical seed mapping (20260914 + 100 + 10 × contrast index + metric index).
Inputs are exact fractions derived from the archived CSV rows; bootstrap
resample sums and percentile interpolation use integer-scaled rational
arithmetic, not the historical float summary implementation. Legacy float
percentile rendering is compared within the larger of an absolute 1e-12
tolerance or 16 binary64 units in the last place (ULPs) at the endpoint's
magnitude; this narrow numerical allowance is necessary for token-count
intervals without relaxing report-level support comparisons. The seed's
Python random.Random.randrange index stream is shared by design.
Missing, malformed, non-finite, or altered interval endpoints fail closed.
The verifier does **not** calculate secondary p-values or change the
predeclared three-test Holm family: all secondary outcomes and intervals
remain **exploratory/descriptive**, not confirmatory.

**Scope limitations:** Report rendering is *not* independently recomputed here.
The bootstrap audit verifies the frozen deterministic sample procedure, **not**
the frequentist coverage of its confidence intervals, the representativeness
of the task set, or a separately generated random number stream. They remain covered by the existing frozen
analysis/provenance/output checks, which are not substitutes for an independently
implemented estimator. This is a numerical consistency audit, **not** an
external signature, proof of authentic raw evidence, additional experiment,
new inferential result, or prospective preregistration change. It does not
retroactively authenticate treatment traces and cannot establish human
validation. Historical canonical artifacts, the frozen analysis script, plan,
and hashes are unchanged.

The original diagnostic pilot, frozen automated confirmatory results,
exploratory follow-ups, and still-pending genuine blinded human evaluation
must be reported separately. The auditor does not alter or select outcomes.


**Held-ancestor capture for published CSV preflight (6 November 2026):**
The shared frozen-summary CSV reader now opens and holds each ancestor
directory using `O_DIRECTORY|O_NOFOLLOW` and descriptor-relative access.
It rejects symlinked parents, checks the expected leaf inode and single-link
constraint, and rechecks the held ancestor chain after reading. Previously,
a parent could be replaced after an initial `is_symlink()` inspection while
the CSV was still opened by its full pathname. Synthetic regression tests
cover same-byte directory replacement during capture, symlink injection between
parent inspection and opening, and legitimate nested CSV paths. This applies
to the independent frozen-CSV input preflight and downstream exploratory
denominator inspection as well as the independent inference audit. The
published SHA-256 pins, 40-cell arithmetic checks, frozen statistical
implementation, and confirmatory results are unchanged. This is a *local
path-continuity safeguard*, not proof of original experiment custody, an
atomic filesystem snapshot, or evidence of human-validation readiness.
