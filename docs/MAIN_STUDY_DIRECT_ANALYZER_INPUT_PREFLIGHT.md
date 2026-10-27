# Frozen main-study analyzer: validated local diagnostic entrypoint

The historical analyzer `scripts/analyze_main_study.py` is **byte-pinned**
in the published canonical analysis provenance receipt. Editing it would break
independent verification of preserved results, so the original implementation
is intentionally retained byte-for-byte.

## Previously uncovered local misuse path

The historical command-line analyzer can also be invoked directly, outside
`scripts/run_verified_main_study_analysis.py`. In that unguarded mode its
permissive CSV parser and float-rounded claim counts can accept coherently
relabeled but scientifically invalid exports (for example, altered frozen task
IDs or browse budgets). That would yield numbers which look like preregistered
inference even though the canonical scientific contract was not satisfied.

## Optional local diagnostic command

```bash
mkdir -p outputs/diagnostics
python -m scripts.analyze_main_study_with_preflight \
  --output-dir outputs/diagnostics/local-check-001
# Or, from the repository root:
python scripts/analyze_main_study_with_preflight.py \
  --output-dir outputs/diagnostics/local-check-002
```

This **new** wrapper uses the existing strict canonical CSV reader and
`validate_rows(..., require_canonical_matrix=True)` on the exact in-memory
records that the byte-identical historical analyzer subsequently consumes.
It rejects malformed CSV structure, inconsistent evaluator mirrors, invalid
counts or resource measures, altered task identities, frozen budgets, claim
caps, pricing-source relabeling, and cost/accounting contradictions before
analysis output publication. No treatment, bootstrap rule, contrast, seed,
canonical result, or original pinned analyzer byte is changed.

A synthetic 40-cell control reproduces successful local inference; negative
regressions cover representative scientific contract violations and require
fail-closed behavior before result files appear.

### Isolated create-only diagnostic results

The wrapper requires an explicit `--output-dir` whose parent already exists and
whose final directory **does not exist**. It is an error to reuse a destination.
The unchanged analyzer runs with its result paths temporarily redirected to a
private sibling scratch directory. Only after validation and successful JSON and Markdown rendering are five
files published under the new destination: the two inference outputs, exact
retained treatment/evaluator input CSVs, and a deterministic byte receipt
(described below). The inference files remain:

- `main_study_diagnostic_inference.json`
- `main_study_diagnostic_inference.md`

The canonical analyzer defaults (`outputs/main_study_inference.json` and
`paper/MAIN_STUDY_INFERENCE.md`) are never written by this wrapper, even if
they already contain preserved results. Failed validation or rendering does not
publish a diagnostic directory. Same-filesystem create-only linking prevents
overwriting a previously published file in the new directory; publication of
the **five-file bundle** is not an atomic transaction under abrupt process termination,
so an incomplete directory must not be treated as a valid receipt. The
temporary analyzer globals are restored after both success and failure; do
not run this global-patching helper concurrently in a shared process.

This safeguards local exploratory/diagnostic outputs from accidental
canonical-result replacement. It does **not** cryptographically authenticate
input origin, preserve an immutable filesystem, or authorize any change to
frozen confirmatory reports.

## Critical provenance and research boundaries

This convenience command is **not** a manifest-pinned proof of canonical
artifact origin. It cannot authenticate the original input CSVs or protect
against every concurrent source-file edit while reading. It uses a temporary
module-level reader binding and should not be invoked concurrently from a
shared notebook/kernel. For manuscript-facing canonical inference **always
use the existing independently SHA-256-pinned verified runner**, which
snapshots and verifies the source artifacts and outputs.

The diagnostic pilot, frozen confirmatory study, post-hoc exploratory
analyses, and pending blinded human validation are separate. Synthetic tests
do not constitute experiments or human ratings.

## Diagnostic destination namespace integrity

The local diagnostic publisher now retains POSIX directory descriptors for the
private staging directory, the requested destination parent and the newly
created output directory. It creates both files using descriptor-relative,
create-only hard links, syncs the output directory entries, and verifies
source, parent and destination directory identities before reporting success.
A destination symlink swap or same-name directory replacement during
publication is rejected without writing into the replacement. Regression tests
cover these races, descriptor-bound links and symlinked parent rejection.

These checks reduce path-redirection risk for **local diagnostic output only**;
they do not turn the diagnostic into a canonical SHA-pinned analysis, prevent
post-return filesystem mutation, or make a two-file publication atomic during
abrupt termination. The frozen historical analyzer and its analysis receipts
remain unchanged. POSIX `dir_fd`, `O_DIRECTORY`, and `O_NOFOLLOW` support
is required.

## Staged-output byte continuity during diagnostic publication

A destination hard link shares a mutable inode with its stage file. Therefore
directory and inode identity alone do **not** establish that the two published
inference files still contain the numbers rendered by the analyzer. The optional
diagnostic publisher now captures bounded SHA-256 fingerprints of both generated
stage files before it creates a destination. It refuses symbolic links,
non-regular files and files larger than 16 MiB. Its descriptor-relative reads
check for observable modification or replacement while hashing; publication
rechecks both stage and published names against the initial inode, size,
modification time and byte digests before reporting success.

Synthetic adversarial regressions change a staged JSON result after the first
link, replace an unlinked Markdown result with byte-identical new inode content,
and change a published result after linking. Each must fail closed and remove
the original newly created output directory without touching unrelated paths.
Positive control demonstrates exact-byte publication. Oversized and symlinked
stage-file controls fail before any output directory is created.

These are **observational checks over one publication window**, not a transaction,
immutable escrow, externally pinned artifact, prevention of post-return edits, or
historical proof of the canonical results. SHA-256 establishes only byte identity.
For manuscript-facing inference use the existing verified canonical runner;
the original frozen analyzer and all confirmatory artifacts remain unchanged.


## Retained exact-byte diagnostic inputs and independent byte verification

The optional local diagnostic command now captures a bounded exact-byte
snapshot of each CSV *before validation*. It validates private copies of
precisely those bytes and supplies the same validated rows to the unchanged
historical analyzer. Five files are published under the new, create-only
diagnostic directory: two inference results, two retained input CSVs, and a
deterministic local provenance JSON receipt.

Retained input files are named main_study_diagnostic_treatment_input.csv and
main_study_diagnostic_evaluator_input.csv. The receipt is named
main_study_diagnostic_provenance.json. It records exact byte counts and SHA-256
for both inputs and results, the analyzer, diagnostic wrapper, preflight validator
and numeric-validator source files,
and the bootstrap configuration. Each source CSV is limited to 8 MiB and must
be a stable regular file, not a leaf symlink. Observable mutation/replacement
during capture fails closed; later changes to the original CSV path cannot
silently affect inference computed from the preserved snapshot.

The existing descriptor-bound publication mechanism now includes all five
files. The original byte-pinned analyzer and canonical results remain
unchanged. For independent *local* byte-consistency checking, execute:

    python -m scripts.verify_main_study_diagnostic outputs/diagnostics/local-check-001

This read-only verifier checks the exact file set, fingerprints, current script
fingerprints, analysis configuration and full frozen 40-cell scientific input
preflight against its copied, retained bytes. It does not rerun treatments or
the statistics, and requires no provider API credits.

**Important boundary:** a self-contained receipt is not an externally pinned
provenance proof. A party able to edit both the local archive and its receipt
can forge internal consistency. SHA-256 proves observed byte identity only, and
a different analyzer version/configuration requires explicit verification.
This optional local diagnostic remains distinct from the existing
manifest-pinned canonical main-study analysis, exploratory work, pilot
observations and pending blinded human validation. A separate trusted archive
digest is required for independent chain-of-custody attestation.


## Optional offline recomputation of archived local diagnostic inference

A self-consistent local hash receipt does **not** establish that the archived
inference actually follows from its retained CSV inputs. Both a result and its
self-reported SHA-256 can be rewritten together. The read-only verifier therefore
offers an **opt-in** same-code consistency check:

    python -m scripts.verify_main_study_diagnostic outputs/diagnostics/local-check-001 --recompute

The command first performs the original strict five-file receipt, current-code
fingerprint, and 40-cell input validation. It then feeds only those already
captured/validated rows to the **unchanged historical analyzer** with its
input reader and output paths temporarily redirected. JSON and Markdown are
rendered in a private temporary directory and compared **byte-for-byte** to
both archived inference outputs. Mismatches fail closed even when the local
manifest has been edited to match altered output bytes. The verifier restores
the historical analyzer's temporary bindings on success and failure and
does not touch the canonical output files. No treatment generation, model
calls, common-evaluator runs, or human annotations are performed.

This invokes **the same original statistical implementation**, not an
independent estimator, so shared code defects may be reproduced. The mode is
synchronous and temporarily patches module-level globals: do not run it
concurrently with other uses of the analyzer in one Python process. It does
not establish trusted origin, immutable storage, protection against all
concurrent mutations, or any canonical manuscript-facing verification.
Omitting `--recompute` retains the existing inexpensive byte-only verifier
behavior. Frozen confirmatory results, exploratory diagnostics, pilot
observations and pending blinded human validation remain distinct.
