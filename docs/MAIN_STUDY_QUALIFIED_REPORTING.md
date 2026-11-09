# Qualified, source-checked main-study reporting copy

Status: read-only **noncanonical reporting aid**, not a new analysis or human
study. The 24 September 2026 inference artifact remains unchanged.

When quoting VERA main-study strict-support estimates or p-values, use:

~~~bash
python -m scripts.assemble_qualified_main_study_report > qualified_main_study.md
~~~

The command verifies the **historically published frozen CSV aggregate**
using the preserved fingerprint, checks the canonical inference JSON-to-Markdown
rendering using the existing verifier, requires both canonical output SHA-256s
from the retained historical canonical-analysis archive checkout receipt, and assembles a reading copy with the
required reporting cover **before** the unaltered historical inference text.
It fingerprints both Markdown inputs, rechecks the inputs before emitting any
stdout, and fails rather than issuing an unqualified copy if a required
disclosure is removed. It never edits, re-estimates, or replaces the canonical
data, plan, output, treatment/evaluator runs, or human ratings.

The cover explicitly explains why the historical D3/D6/P6/P6V fixed order does
not supply randomized treatment assignment or justify a design-based
causal-randomization interpretation of the exact paired sign-flip p-values.
Any statistical calibration requires unverified symmetry/exchangeability
assumptions; Holm adjustment does not fix the order confounder. The paired
bootstrap conditions on ten selected tasks without a representative
population guarantee. The exact frozen arithmetic remains available for
reproduction but its interpretation is methodologically qualified.

The September 14 exact statistical plan postdated the September 11 treatment
execution and September 13 evaluator recovery; prospective precollection
preregistration and blinding at the freeze are unestablished. Source artifacts
for the original 40 reports/traces remain unauthenticated, and human validation
has not occurred. The five-task pilot is diagnostic, frozen automated findings
are qualified, and later sensitivity checks are exploratory.

The tool provides checkout-level input/output consistency, **not** an
out-of-band signed provenance attestation, an atomic filesystem snapshot, or
independent original-report custody. It is not a replacement for
the separately required independently pinned evidence and blinded human
handoff gates. Output redirects are user-controlled; the tool itself writes
no files. The tool does not rerun a treatment, evaluator, or statistical test.

Offline regression:

~~~bash
python -m pytest -q tests/test_qualified_main_study_report.py
~~~

The two archived output SHA-256s are 9356cbad9711012850baef349c7d16a104d63987e1d7be2e53184456a8cb2f1c
(manuscript Markdown) and bbf439aabf0db38afd5430a885aff107014c6b924c05c62d6d724d16e00f450f
(canonical JSON). They are pre-existing **GitHub-retained, same-provider**
checkout-concordance pins, not independent treatment/report source
authentication. This additional result-byte anchor rejects a coherent,
numerically parseable change to the canonical output that a renderer check
alone would not detect.
