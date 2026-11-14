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

## Reviewed reporting-cover integrity

The mandatory [reporting cover](../paper/MAIN_STUDY_REPORTING_COVER.md) is now
checked against its **complete reviewed SHA-256**, not just a list of phrases.
The reviewed 7 November cover bytes hash to
`a1705941a5834ab391a75f063e5ce10c08617ae2e040cfa90292b4df6b248b2e`.
This prevents a changed cover containing contradictory visible assertions or
caveats concealed in an HTML comment from passing merely by preserving the
required phrase strings. A substantive future revision of the *noncanonical*
cover remains possible, but requires full scientific review and an explicit
matching update to the digest and tests; silently changing the wording fails
closed. This is **checkout-local integrity**, not an externally timestamped
signature, independent original-report custody, or human validation.

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


## Verified CI distribution of the qualified reading copy

The `qualified-main-study-report` workflow executes the actual offline exporter
on changes to the frozen data, rendering dependencies, reviewed cover, or
verification code. It independently checks the *produced file* byte-for-byte
against a newly source-verified assembly and retains two files together in a
90-day GitHub Actions artifact:

- `qualified_main_study.md`: a **noncanonical** manuscript reading copy,
  with the mandatory caveats before the historically unchanged results.
- `verification_receipt.json`: SHA-256 and byte length of that exact copy,
  published frozen-input aggregate, frozen JSON/Markdown pins, reviewed-cover
  pin, and explicit false flags for independent original-report custody,
  prospective preregistration, randomized causal identification, and human
  validation.

The workflow has read-only repository permissions, pinned checkout/Python/
artifact-upload actions, and no model-provider credentials. It performs no
treatment, evaluator, inference, or human-rating run. A successful unit test
alone is not substituted for actually exporting and verifying the distributable
report. Reproduce the receipt locally after generating the report:

~~~bash
python -m scripts.assemble_qualified_main_study_report > qualified_main_study.md
python -m scripts.verify_qualified_reporting_copy \
  --report qualified_main_study.md --receipt qualified_receipt.json
~~~

Receipt creation is **create-only**; do not overwrite an earlier receipt. Each
retained CI artifact is a same-provider, time-limited *checkout-local* record,
not an independently signed attestation or source for the missing 40 original
reports/traces. Distribution to human raters remains blocked pending separately
authenticated source recovery, verified blinding, and genuine independent ratings.

## Verify the retained report and receipt after download

The receipt generator verifies a report *while writing* its companion receipt.
Consumers also need to check the **existing** two-file pair after transfer:
a valid Markdown file accompanied by a rewritten JSON receipt must not be
accepted as the verified CI output. From a checkout containing the pinned
historical CSV and inference evidence, run:

~~~bash
python -m scripts.verify_qualified_reporting_artifact \
  --report /path/to/downloaded/qualified_main_study.md \
  --receipt /path/to/downloaded/verification_receipt.json
~~~

The read-only consumer verifier reassembles and checks the historical sources,
compares the downloaded Markdown byte for byte, and requires the downloaded
receipt to equal the producer's **exact canonical serialized JSON**. A changed
scientific limitation, unrecorded extra claim, duplicate JSON key, altered
boolean or number type, whitespace-only receipt rewrite, missing final LF,
symlink, or substituted file fails closed. It does not rewrite either input,
generate ratings, or run experiments/statistical inference. CI now verifies this
existing pair immediately before upload, rather than testing only the receipt
producer. Changes to the consumer verifier/tests trigger this workflow.

This is **checkout-local same-provider consistency**, not an independently
signed or timestamped GitHub artifact attestation, a guarantee of atomic
filesystem snapshots, or a substitute for archived original treatment reports,
traces, and source-verified human-evaluation handoff. For external audit,
preserve the downloaded original artifact ZIP and an independently retained
checksum/custody record; do not treat a self-consistent regenerated pair as
proof of original report provenance or human validation.


## Verify a downloaded Actions ZIP *before* unpacking

The existing pair verifier checks two files after extraction, but a downloaded
GitHub Actions ZIP can itself contain ambiguous or hazardous member paths,
unexpected files, duplicate entries, or a replaced archive generation. Use the
dedicated offline ZIP consumer from the repository checkout instead:

~~~bash
python -m scripts.verify_qualified_reporting_zip \
  --zip /path/to/vera-qualified-report-<run-id>-<attempt>.zip
~~~

The command reuses the recovered-archive structural preflight to inspect
the complete ZIP (without extraction), bounds its compressed size to 1 MiB,
requires precisely the two published report/receipt member names with no
extra directories, checks member CRCs/hashes and ZIP-generation continuity,
then invokes the existing source-bound report-and-receipt verifier using only
fixed filenames in a deleted private temporary directory. It prints the
observed ZIP SHA-256 for an **independently retained** custody log; that digest
is computed **now**, not a historical external fingerprint. The original ZIP,
repository sources, and preserved analyses are never modified.

For local regression without any API/model or human-evaluation calls:

~~~bash
python -m pytest -q tests/test_qualified_reporting_zip.py
~~~

A PASS means the *present* downloaded ZIP contains the expected checkout-local
noncanonical reporting pair. It does **not** establish that these were the ZIP
bytes originally uploaded by GitHub, supply an independently signed timestamp,
authenticate original treatment reports/traces, or authorize blinded ratings.
Preserve an out-of-band checksum and original archive when independent
distribution custody is needed. Do not substitute this reporting ZIP for
the unavailable historical experimental archives.
