# Noncanonical evaluator replay: complete treatment-matrix preflight

The original VERA main study is a frozen 4-variant × 10-task experiment.
Its historical 40 treatment traces and evaluator-recovery outputs must **not**
be regenerated to improve the reported automated outcomes. The direct
post-hoc evaluator now requires explicit noncanonical replay acknowledgment
**and** a complete, uniquely identified treatment matrix before any model
invocation. This supplements the GitHub Actions recovery workflow's historical
cardinality checks for operators invoking the Python script directly.

The offline structural preflight in
`scripts/evaluate_posthoc_support.py` rejects:

- task contracts that do not have exactly `main-01` through `main-10`;
- missing or repeated `(variant, task)` cells among D3, D6, P6, P6V;
- different cells referencing the same run ID (shared report identity);
- incomplete treatment traces, even if a full set of other traces exists;
- JSON trace files under unselected variant directories.

No candidate is selectively dropped to make the available evaluator results
look complete. Missing, failed, or incomplete treatments require provenance
adjudication, **not** a replacement rerun. The original 40-cell evaluation
matrix is unchanged; the evaluator may still resume only missing post-hoc
measurements from a complete and otherwise validated treatment corpus, but
all new measurements remain noncanonical.

The guard operates on selected local trace records and the supplied task
contract. It does **not** authenticate those bytes against independently
retained 2026 archives, prove report/evidence integrity, eliminate fixed-order
temporal confounding, or establish blinded human-evaluation readiness. Existing
frozen automated confirmatory statistics and diagnostic pilot findings are not
recomputed or updated; exploratory analyses and future human judgments remain
separately classified. Synthetic offline tests establish rejection behavior
only, not a scientific result.

**Remaining gate:** the original treatment run 34620917346 and evaluator
recovery run 34783525480 currently have no downloadable Actions artifacts;
an independently authenticated original report/trace archive and two eligible
blinded human annotators are still required for human-validation claims.
