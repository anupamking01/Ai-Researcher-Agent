# Verifying a retained canonical-analysis ZIP against the published checkout

The only GitHub Actions artifact still listed for VERA's three historical
runs as of **2026-10-29** is `canonical-main-study-analysis-36070798723`
(artifact ID `10837878458`; expiry **2026-12-23T23:03:46Z**).
The original treatment run `34620917346` and evaluator-recovery run
`34783525480` have no listed downloadable artifacts. Recheck the run-scoped
API before relying on this dated observation.

If an authorized copy of the canonical-analysis artifact is obtained, run
this entirely offline, from the exact published research checkout:

```bash
python -m scripts.verify_canonical_archive_checkout \
  /path/to/canonical-main-study-analysis-36070798723.zip \
  --root /path/to/Ai-Researcher-Agent
```

If a trustworthy **pre-existing, independently retained ZIP-byte** SHA-256
is available, add `--expected-archive-sha256 <64-lowercase-hex>`. Do not
compute a fresh digest from an untrusted ZIP and describe it as historical
custody evidence.

The verifier first runs the existing independent canonical provenance and
execution-recomputation gate on the checkout. It then invokes the extraction-free,
bounded ZIP structural/CRC preflight, requires **exactly these seven** paths,
and compares every uncompressed member's byte count and SHA-256 to the
provenance-verified published checkout:

- `outputs/canonical_analysis_source.json`
- `outputs/main_study_analysis_inputs_manifest.json`
- `outputs/main_study_analysis_provenance.json`
- `outputs/main_study_inference.json`
- `outputs/main_study_runs.csv`
- `outputs/posthoc_support_runs.csv`
- `paper/MAIN_STUDY_INFERENCE.md`

The path set comes from the canonical-analysis workflow's upload step, **not**
from filenames provided by an unauthenticated candidate archive. Missing,
additional, renamed, or byte-changed files block concordance. Read-only
pre/post checkout captures reject observable source changes during verification.
The comparison does not rewrite the checkout or ZIP, extract files, rerun
treatments or evaluators, or generate human annotations. Synthetic regression
tests cover matching members, altered contents, replacement members, missing
and additional paths, an incorrect independently supplied ZIP pin, provenance
gate failure, symlinks, and source mutations during inspection.

**Scientific interpretation:** PASS means a *presently inspected candidate
canonical-analysis ZIP* is structurally safe and contains bytes matching the
published provenance-verified analysis checkout. It does **not** prove the
ZIP is the historical GitHub artifact, establish independent historical
custody, authenticate original treatment traces/reports, or imply human
validation. An ordinary checked-out tree may change between observations;
the read-only comparisons are not an atomic filesystem snapshot.

The original **40 experiment traces and matching Markdown reports** plus
independently retained archival fingerprints remain the blocker for
source-authenticated human-evaluation preparation. The canonical analysis
ZIP cannot replace them. Keep diagnostic pilot, automated confirmatory,
post-hoc exploratory and pending human-validation claims separate.
