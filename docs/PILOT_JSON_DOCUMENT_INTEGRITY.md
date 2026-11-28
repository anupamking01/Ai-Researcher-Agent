# Diagnostic pilot JSON document integrity

**Scope:** Offline validation of prospective D6/P6/P6V pilot manifests, progress checkpoints, experiment traces, and summaries. No treatments or evaluators are executed.

## Source-selection risk

Python's permissive JSON decoder accepts duplicate object keys with *last-key-wins* semantics. This means a manifest could include two different `task_set_id` values, a trace two different `variant_id` values, or a summary conflicting counts, while the postrun validator sees only the final value. The decoder also accepts nonstandard `NaN` / `Infinity` tokens and can silently turn very large JSON exponents (for example, `1e309`) into infinity. Since scientific traces and manifest identities are research evidence, ambiguous source documents should not be repaired or implicitly selected.

## Fail-closed contract

`scripts/validate_pilot_artifacts.py` now parses each required JSON source with an object-pairs hook that refuses duplicate keys **at every nested level**, including fields that the downstream validator does not currently inspect. It refuses the nonstandard numeric constants `NaN`, `Infinity`, and `-Infinity`, and refuses JSON floating-point literals that overflow to nonfinite values. Every document must have a JSON object as its top-level value.

Malformed, undecodable, or otherwise nonconforming sources produce an explicit artifact-path validation error rather than a traceback or an implicit last-key-wins source selection. The three metadata documents are checked before comparing the experimental matrix; an invalid individual trace is reported and is not included in the set of validated trace pairs. Identical field names in **different** objects are legal and continue to work. This does not normalize, recover, or impute scientific observations.

## Offline regression

```bash
python -m pytest -q tests/test_pilot_json_document_integrity.py tests/test_pilot_numeric_counter_integrity.py tests/test_pilot_plan_identity.py tests/test_pilot_source_url_accounting.py tests/test_pilot_treatment_factor_identity.py
```

Synthetic cases check duplicate keys at several levels, nonstandard numeric constants, nonfinite float exponents, malformed documents, non-object top-level documents, and pristine valid traces. The contract is forward-looking: it does not reauthenticate already missing original main-study reports/traces, and is **not** a substitute for independent artifact custody or cryptographic provenance.

The historical five-task pilot remains diagnostic; the ten-task frozen automated main-study results remain methodologically qualified (including analysis-plan timing and fixed-order concerns); retrospective sensitivity analyses remain exploratory; and genuine independent blinded human validation is still pending.
