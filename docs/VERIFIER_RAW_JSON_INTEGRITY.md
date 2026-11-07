# Raw verifier-response JSON integrity

## Scientific validity issue

The web-research agent uses a verification-response normalizer both for
treatment-time verification and for the common, measurement-only post-hoc
support evaluator. Python's permissive default JSON decoder accepts repeated
object keys (keeping only the final value) and nonstandard `NaN`/`Infinity`
constants. A model response could therefore have two contradictory
`supported` counts or two conflicting labels for an evidence example yet
still normalize into an apparently self-consistent measurement.

## Fail-closed parsing contract

Before any schema, classification-conservation, or claim-cap checks,
`logic.experiment.normalize_verifier_output` now:

- rejects repeated member names in *every* JSON object, including nested
  objects inside the retained example list;
- rejects nonstandard numeric tokens `NaN`, `Infinity` and `-Infinity`;
- rejects syntactically valid exponent values that overflow finite float
  range (for example `1e309`), including within illustrative examples.

Valid JSON (including the pre-existing optional Markdown `json` fences),
the frozen count/rubric validation, the 12-claim cap for the common evaluator,
and the eight-example retention cap remain unchanged. The common evaluator
wrapper is explicitly covered by a regression test. Parse failures retain
the established ValueError failure path; they are not converted into
unsupported claims, dropped measurements, or automatically retried for a
more favorable answer.

## Interpretation and limits

This is a **prospective input-integrity guard**, not a revision of the
frozen study outcomes or the preregistered statistical plan. It does not
retroactively attest that previously normalized model responses lacked
ambiguous raw members unless their original raw responses were retained and
independently checked. Existing canonical treatments, recovered evaluator
artifacts, costs, p-values, and task inclusion are untouched.

Unit tests use only synthetic response strings and execute offline. This
change does not generate research outcomes, rerun treatments or evaluators,
authenticate model outputs or source evidence, or produce any human ratings.
Diagnostic pilot findings, automated confirmatory estimates, post-hoc
exploration, and pending human validation remain distinct.
