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

The direct replay now also performs a **closed-world trace-directory
inventory** before loading treatment JSON. Every immediate entry under the
dedicated trace root must be one of the four frozen variant directories; each
variant directory may contain only regular, non-symlink `.json` trace files,
with no nested directories, hidden backup files, alternate variants, or
misnamed traces. The scan stops after five root entries or eleven entries
inside any arm, rather than sorting an unbounded untrusted directory. A
missing variant directory is left to the existing complete-40-cell gate to
reject. This prevents a valid selected matrix from masking additional
unselected treatment evidence. It does not inspect ancestor symlinks, make
the directory tree an atomic snapshot, or authenticate the original reports.

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

## Strict numeric integrity for local replay JSON

Treatment traces and cached evaluator records are **untrusted local JSON inputs**.
The common decoder now rejects `NaN`, `Infinity`, `-Infinity`, exponent
overflow (for example, `1e400`), numeric tokens longer than 128 characters,
and structures beyond the JSON parser nesting limit. Checks apply recursively,
including unconsumed metadata; ordinary finite integers and floats are retained.
Duplicate-key rejection remains in effect. Malformed local trace/cache JSON
fails before importing the model client or generating additional measurements.

This safeguard does not authenticate the lost historical sources or authorize
a treatment/evaluator rerun. It does not change the frozen pilot, confirmatory
or exploratory analyses, and real blinded human evaluation remains pending.

## Closed-world cached-measurement inventory

The direct noncanonical evaluator previously used `*/*.json` globbing for
cache preflight and existing-spend accounting. That selected only JSON files
under immediate directories and silently omitted differently named backups,
nested folders, alternate variant directories, and non-JSON leftovers. A
seemingly complete set of selected cached scores could therefore mask other
local evaluation records, while the spend helper did not account for them.

Both the resume preflight and historical-cache spend helper now use the same
bounded, closed-world cache inventory. The absent cache root is permitted
(no measurements yet). An existing root must be a regular, non-symlink
directory; its immediate children must be D3, D6, P6, or P6V directories,
and each arm may contain at most ten regular, non-symlink `.json` files
with no nested directories or extra backup files. Unexpected JSON cache
cells still fail the separate expected-path check. All checks happen before
a new model call, without deleting, selecting, or recomputing any results.

The guard is **not** an independent authentication of any cached
measurement, a provider-billing audit, an atomic filesystem snapshot, or
a means to recover expired historical evaluator artifacts. Pilot, frozen
confirmatory, exploratory, and pending human-evaluation evidence retain
their separate classifications. These checks use synthetic offline tests;
the historical 40 treatments, common evaluator, and human raters were
not rerun.

## Closed-world report and retrieved-evidence inventory

The direct noncanonical common evaluator previously selected evidence through
a wildcard query-text glob. Other local files could enter the original
research-agent text loader but be silently omitted from replay; alternate
source backups, nested directories and symlinks could also go unreported.

Before evaluator prompt preparation or any provider call, the new bounded
inventory checks all immediate entries in each selected treatment run folder.
It permits only the frozen writer's research-query-01.txt through
research-query-04.txt, research_report.md, optional research_report.pdf and
optional verification.json. It rejects unexpected files, nested paths,
symlinks, alternative query-file names, and gaps in the numbered query
sequence. Enumeration stops after eight entries (one beyond the seven
allowed names), avoiding a full unbounded directory listing. A valid
zero-source treatment can still have no query files; the existing
report-integrity and zero-evidence rubric checks remain in effect.

This is prospective local evidence-selection consistency, not independent
2026 historical-archive authentication or an atomic filesystem snapshot.
It neither authorizes selective reruns nor changes pilot, frozen automated
confirmatory, exploratory, or pending human-validation claims. Regression
tests are synthetic/offline and produce no experimental measurements.
