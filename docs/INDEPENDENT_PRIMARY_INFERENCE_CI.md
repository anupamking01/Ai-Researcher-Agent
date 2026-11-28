# Exact-commit CI for independently audited frozen primary arithmetic

The `independent-primary-inference-audit` workflow adds a reliable,
dependency-free GitHub Actions check for an **already implemented but previously
optional** arithmetic verifier. Broad `tests` workflows on recent research
commits ended *cancelled* before their offline pytest step; a successful
standalone published-CSV numeric-input check by itself does not establish
correctness of the frozen paired bootstrap, exact sign-flip, Holm, or
secondary descriptive arithmetic.

The workflow (1) authenticates the Git-published 40-cell CSV pair against
the fixed historical manifest aggregate; (2) executes
`scripts.audit_primary_inference_independently` using rational-count
paired arithmetic, exact sign-flip enumeration, seeded 20,000-draw primary
and secondary bootstrap cross-checks, and descriptive frontier verification;
(3) verifies source bytes remained stable; and (4) retains a 90-day
commit/run-bound JSON receipt. A separate step checks receipt binding to
the exact checkout and source bytes. It does **not** invoke the historical
analyzer as its own arithmetic oracle, edit output, call any provider,
or rerun treatments or post-hoc evaluators.

Local reproduction (offline, Python 3.11):

```bash
python -m unittest discover -s tests -p test_independent_primary_inference_ci_workflow.py -v
python -m scripts.verify_published_main_study_inputs
python -m scripts.audit_primary_inference_independently
```

A passing CI receipt establishes consistency of frozen automated inference
*as recorded in Git* with the separately preserved published CSVs.
It does **not** establish independent authenticity of the lost original
treatment reports/traces, evaluator-policy equivalence, provider invoices,
outcome blinding at freeze, or prospective precollection statistical
preregistration. The five-task pilot remains **diagnostic**; the 10-task
frozen automated designated-primary results retain post-collection plan,
fixed-order and evaluator comparability qualifications; retrospective
sensitivity analyses and cost-quality findings remain **exploratory/
descriptive**; real blinded human validation and reconciliation remain
pending source custody and two independent annotators. No result or
hypothesis family is modified by this CI improvement.
