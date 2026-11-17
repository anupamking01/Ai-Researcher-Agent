# Local diagnostic bundle verification: bound five-file custody

The optional `scripts.verify_main_study_diagnostic` checks **local, noncanonical**
diagnostic outputs, not September's archived automated measurements. The prior
reader rejected symlinked leaf files and checked each file during its read,
but could follow a symlinked ancestor, accept a directory substituted between
reads, or accept an identical-byte replacement of a previously read member.

The verifier now holds no-follow descriptors for the entire input directory
chain, pins the starting identity/write generation of **all five** permitted
bundle members, opens each file relative to the retained directory, then
rechecks every member, directory component, and the exact file inventory
after validation (including optional offline inference recomputation).
Explicit `..` traversal and redirected ancestors fail closed. Source-code
fingerprints and the unchanged historical analyzer remain checked separately.

Run the synthetic offline regressions with:

```bash
python -m pytest -q tests/test_main_study_diagnostic_input_receipt.py
```

The new cases exercise symlinked ancestors, parent traversal, directory
substitution after manifest capture, and identical-byte replacement of an
already read CSV after later files were captured. There are no network,
model, evaluator, treatment or human-rating calls.

These safeguards establish *observed local pathname and byte continuity*,
not an atomic filesystem snapshot; transient changes fully reversed between
observations remain outside this guarantee. Neither a locally coherent
manifest nor these checks independently authenticate unavailable original
September reports/traces, their historical custody, or provider actions.
The five-task pilot remains diagnostic. Frozen automated findings remain
qualified by post-collection analysis-plan chronology, fixed treatment
order and evaluator comparability. Retrospective sensitivities are exploratory,
not prospective confirmatory findings. Human validation is still blocked
pending source-authenticated handoff and genuine independent annotators.

## Bounded diagnostic bundle inventory checks

The five-file verification now uses descriptor-relative `os.scandir` and a
fixed membership check **both before reading and after recomputation**, instead
of `set(os.listdir(...))`. The previous implementation materialized every
entry in an untrusted directory before determining whether it contained the
five permitted names. A directory with very many undeclared entries could
therefore consume unbounded verification time and memory before failing.

The verifier now retains only permitted names (at most five) and rejects the
first unexpected or repeated name immediately. A synthetic iterator regression
fails if it is consumed past that first unknown entry; another test adds an
undeclared file after retained-byte verification and checks the final inventory
gate. Existing tests cover valid five-file bundles, initial extras, file
identity substitutions and symlinked ancestors.

This is a local resource-safety and inventory-consistency improvement, **not**
an atomic snapshot, historical report/trace authentication, or evidence that
human ratings were collected. Pilot, qualified frozen automated, exploratory
and pending human-evaluation claims are unchanged.

## Exact JSON-number types in diagnostic provenance

The locally retained manifest is untrusted metadata, even when its declared
hashes agree with the files. Its analysis configuration must contain precisely
the expected integer fields, and each declared source/artifact fingerprint must
contain exactly one positive **integer** `bytes` and one string `sha256`.
JSON floating-point numbers are rejected even when they compare equal to
integers in Python (for example, `8.0 == 8`). Unexpected fingerprint members
are also rejected. Synthetic regression tests prove that these otherwise
numerically equal rewrites cannot be accepted as the original schema.

This verifies schema fidelity, not independent provenance: an adversary can
still rewrite local evidence and self-consistently recalculate its digest.
The optional offline recomputation checks inference consistency, not source
custody. The September original artifacts and human ratings remain unverified
or unavailable, and no pilot, frozen automated or exploratory outcome changes.

## Optional independently retained diagnostic manifest pin

A local diagnostic receipt can be rewritten together with a result file, so
self-consistent local hashes alone do **not** establish that a previously
inspected diagnostic has remained unchanged. The verifier now accepts an
optional `--expected-manifest-sha256` pin for the **exact manifest file
bytes**. The pin must be a 64-character lowercase SHA-256 hex digest, retained
outside the editable bundle **before** a possible revision. It is checked
before trusting any of the manifest's self-declared source/artifact hashes:

```bash
python -m scripts.verify_main_study_diagnostic LOCAL_BUNDLE_DIR \\
  --expected-manifest-sha256 PREVIOUSLY_RETAINED_LOWERCASE_SHA256
```

The JSON result reports `supplied_manifest_pin_matched` (true only after a
supplied pin matches); the unchanged status still describes **local,
noncanonical** diagnostics. The comparison uses exact captured bytes, not a
canonicalized JSON object: even semantically identical reformatting must
fail against a previously retained fingerprint. Without a pin, existing
offline checks remain usable but cannot detect a fully self-consistent rewrite
of the bundle and its manifest. A pin calculated from an already rewritten
local file does **not** establish independent custody or when the evidence
was created. This feature neither authenticates the missing September 2026
source archive nor permits human-evaluation distribution; it does not turn
pilot or retrospective exploratory results into prospective confirmatory or
human-validation results.

Synthetic regressions cover valid and malformed pins, exact-byte formatting
changes, locally rehashed output forgery, and CLI pin forwarding. No model,
evaluator, treatment, or human-scoring calls are needed.

## Analysis-source ancestor and generation continuity

The four source-code fingerprints are now captured using held, no-follow
directory descriptors rather than a fresh pathname read at verification time.
The verifier retains the identities of all four source files and their
ancestor directories throughout the five-file validation and optional offline
recomputation. It rejects a source path reached through a symlinked ancestor
and a byte-identical source replacement after fingerprint capture. Synthetic
tests cover both cases without touching the actual research source or
historical artifacts.

These are local continuity checks, **not** proof of which Python bytecode was
originally executed, an atomic snapshot, independently archived code custody,
or authentication of the missing original September treatment reports. A
change fully reversed between observations is not detectable. The existing
pilot, frozen automated, exploratory, and pending human-validation claim
boundaries remain unchanged.
