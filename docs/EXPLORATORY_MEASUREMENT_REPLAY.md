# Offline CI escrow for two exploratory measurement diagnostics

**Scope:** reproducible **post-hoc descriptive** checks, not new confirmatory
analysis, provider-trace authentication, or human validation.

The research branch's `.github/workflows/exploratory-measurement-replay.yml`
runs two already-implemented read-only diagnostics against the *exact* published
main-study treatment/evaluator CSVs: realized retrieval exposure and
checked-claim denominator sensitivity. Each producer first verifies the frozen
source fingerprints, full 40-cell task matrix, and summary-input integrity.
The workflow then runs a distinct verifier for **each** saved JSON: the
verifiers recompute the reported arithmetic from the pinned CSVs, without
importing the corresponding exploratory producer. Both check all 40 cells and
30 paired task rows. The workflow aborts before publication if a source
fingerprint, result, scientific-scope declaration, or verifier receipt differs.

A successful run retains **five** files together: two generated diagnostics,
two independent verification receipts, and `artifact_index.json`. The index
records the exact GitHub checkout commit and run ID plus SHA-256 hashes for the
other four files. Retention is **90 days**; export those exact bytes and the
GitHub run link into an independently controlled archive if durable external
custody is required. CI artifacts alone are not independent historical
authentication, nor do they recover any missing original report or trace.

The workflow is triggered by relevant edits on
`research-paper-eval-2027`, qualifying PR changes, or manual dispatch. It
uses read-only repository permissions, a pinned Python interpreter, and
minimal version-pinned parser dependencies. No treatment execution, model or
evaluator requests, human scoring, confirmatory inference, or outcome-based
selection is performed. The generated diagnostics remain exploratory even if
every CI check succeeds.

To replay on a research checkout without relying on the CI service:

```bash
python -m scripts.analyze_main_study_retrieval_exposure > exposure.json
python -m scripts.verify_main_study_retrieval_exposure_artifact --artifact exposure.json
python -m scripts.analyze_main_study_claim_denominators > denominators.json
python -m scripts.verify_main_study_claim_denominator_artifact --artifact denominators.json
```

The frozen **equal-report** confirmatory support estimand, original confidence
intervals and multiple-comparison corrections are untouched. Diagnostic pilot
observations must not be conflated with the frozen main-study inference or the
new descriptive comparisons. The original treatment reports/traces remain
unauthenticated independently, historical fixed-order temporal confounding
remains unresolved, and blinded human validation still requires original
source custody plus two eligible, independent annotators and real ratings.
