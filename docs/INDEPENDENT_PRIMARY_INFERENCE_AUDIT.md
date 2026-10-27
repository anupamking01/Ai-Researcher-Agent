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

It checks: frozen task order and configuration, report-level strict-support
fractions, four variant mean strict-support rates, the three preregistered
left/right paired means and mean/median contrasts, all ten task differences per
contrast, sign counts, paired standardized effects, exact two-sided sign-flip
p-values across 2^10 assignments, and the three-test Holm family. A mismatch
fails closed. No model/provider access, experimental execution, evaluator
recovery, or human-rating input is involved.

The implementation intentionally does **not** import the historical analyzer's
math helpers. Arithmetic consistency is independent of the frozen inference
implementation, but the auditor shares the existing scientific input preflight;
it is not an independently developed validation of that entire input schema.

**Scope limitations:** Bootstrap confidence interval draws, secondary paired
descriptives, cost-quality Pareto summaries, and report rendering are *not*
independently recomputed here. They remain covered by the existing frozen
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
