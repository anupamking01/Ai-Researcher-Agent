# Verifying a retained canonical-analysis ZIP against the published checkout

The only GitHub Actions artifact still listed for VERA's three historical
runs as of **2026-10-29** is `canonical-main-study-analysis-36070798723`
(artifact ID `10837878458`; expiry **2026-12-23T23:03:46Z**).
The original treatment run `34620917346` and evaluator-recovery run
`34783525480` have no listed downloadable artifacts. Recheck the run-scoped
API before relying on this dated observation.

On **2026-10-29** the GitHub Actions API returned the actual retained ZIP
for artifact **10837878458** (10,270 bytes). The downloaded ZIP SHA-256 is
`226f009ba6b158b77fc98f4e56ec96e1943d1749bc818b0876e90f76077de4b5`,
matching the digest reported by GitHub's artifact metadata. This is a
**provider-observed** digest, not an independently retained historical
fingerprint and not evidence of the missing original 40 treatment traces.
The ZIP has exactly the seven named files below.

Run the verifier entirely offline from a provenance-verified current checkout:

```bash
python -m scripts.verify_canonical_archive_checkout \
  /path/to/canonical-main-study-analysis-36070798723.zip \
  --root /path/to/Ai-Researcher-Agent
```

If a trustworthy **pre-existing, independently retained ZIP-byte** SHA-256
is available, add `--expected-archive-sha256 <64-lowercase-hex>`. Do not
compute a fresh digest from an untrusted ZIP and describe it as historical
custody evidence.

The verifier first runs the existing canonical provenance and
execution-recomputation gate on the checkout. It then invokes the extraction-free,
bounded ZIP structural/CRC preflight and requires **exactly these seven** paths.
Six files must match the verified current checkout byte-for-byte. The seventh,
the provenance receipt, may either match the checkout exactly or match an
**exactly pinned historical workflow v1 receipt** (details below):

- `outputs/canonical_analysis_source.json`
- `outputs/main_study_analysis_inputs_manifest.json`
- `outputs/main_study_analysis_provenance.json`
- `outputs/main_study_inference.json`
- `outputs/main_study_runs.csv`
- `outputs/posthoc_support_runs.csv`
- `paper/MAIN_STUDY_INFERENCE.md`

### Historical v1 versus checked-in v2 provenance receipt

Actual inspection on 2026-10-29 showed a **real version difference**:
the ZIP's `outputs/main_study_analysis_provenance.json` is schema **v1**,
2,492 bytes, SHA-256
`73f12a725f3cf4d27748a95e1f380ca5cfcac3b8fdd5adeda7abaa2f3f6e10e0`.
The currently published checkout has a strengthened schema **v2** receipt,
which adds later verification fields and changes implementation hashes.
It is **not byte-identical** to the historical workflow output. The other
six ZIP members are byte-identical to the current research checkout at
`9d163f811444b5e01129d9433395e806b5b9255b`, as checked through their
Git blob hashes and uncompressed bytes.

The old verifier incorrectly required the v1 receipt to equal the later v2
checkout receipt and therefore would reject the actual GitHub archive despite
identical canonical inputs, inference, and manuscript output. The updated
verifier accepts **only** the specific pinned v1 receipt SHA-256 above as an
exception, while requiring a freshly verified current checkout and exact
byte agreement for all six substantive files. Any other changed receipt
still fails closed. The result distinguishes the archived receipt's actual
digest from the current verified checkout receipt digest, and labels the
exception explicitly. The pinned v1 digest comes from **this newly retrieved
GitHub artifact**, not a pre-existing independent historical anchor.

The expected seven-member path set comes from the canonical-analysis
workflow's upload step, **not** from filenames supplied by the candidate ZIP.
Missing, additional, renamed, or byte-changed substantive files block
concordance. Read-only pre/post checkout captures reject observable changes
during verification. The operation does not rewrite the checkout or ZIP,
extract files, rerun treatments or evaluators, or generate human annotations.
Synthetic tests cover identical-current bundles, the pinned historical v1
receipt, unpinned receipt lookalikes, malicious substitutions even alongside
the pinned receipt, wrong independent ZIP pins, provenance-gate failures,
missing/additional paths, symlinks and observable file mutations.

**Scientific interpretation:** PASS means the inspected ZIP passed structural
triage, matched the six current provenance-verified canonical input/output
files byte-for-byte, and had either an identical current provenance receipt or
the exact provider-observed historical v1 receipt. It does **not** establish
independent historical custody, authenticate original treatment reports/traces,
or imply human validation. The ZIP observed in this recovery iteration matched
GitHub's reported byte digest, but that provider metadata is not an
independently retained archival fingerprint. Checkout observations are not an
atomic filesystem snapshot.

The original **40 experiment traces and matching Markdown reports** plus
independently retained archival fingerprints remain the blocker for
source-authenticated human-evaluation preparation. The canonical analysis
ZIP cannot replace them. Keep diagnostic pilot, automated confirmatory,
post-hoc exploratory and pending human-validation claims separate.
