# Bounded inputs at the automated–human reconciliation readiness gate

`scripts/verify_human_reconciliation_readiness.py` verifies previously captured
automated and human analysis before descriptive reconciliation. These are
**metadata receipts, predeclared contract text, and analysis summaries** for a
frozen 10-task design—not arbitrary-size experiment datasets.

## Input capture rule

The readiness gate now applies a **16 MiB per-file byte bound** to every
descriptor-captured input: frozen reconciliation contract, automated analysis
and provenance, human analysis, and human analysis manifest. Before reading,
it requires a regular file and rejects an oversized `fstat` size. Each
`pread` request is limited to the remaining budget plus one detection byte;
the extra byte detects growth when a file becomes too large after the initial
file-size check. A second size check, before/after descriptor identity and
timestamp comparison, and the existing closing path/descriptor recheck remain
mandatory. Exceeding the bound fails closed without a success receipt.

This closes an independent resource-exhaustion path in the **human-validation
readiness step**: a sparse oversized receipt previously reached an unbounded
read, and a concurrently growing regular file could consume unpredictable
memory. It does not change research inputs, canonical measurements, frozen
inference, human rubrics, eligibility, or descriptive reconciliation equations.

## Evidence and limitations

Synthetic offline tests in
`tests/test_human_reconciliation_readiness_input_bounds.py` cover ordinary
small inputs, the exact limit, fail-before-read on a large sparse file,
growth during reading, contract-precedence validation, and mutation between
first capture and final recheck. All are synthetic safety controls; no actual
human submissions are created by these tests.

This is a **per-file resource limit and observable consistency check**, not an
atomic multi-file snapshot, immutable source store, signature, or provenance
authentication. A 16 MiB analysis receipt should be reviewed rather than
silently accepted with an increased limit; any change to the limit must be
separately justified and regression-tested. No result about inter-annotator
agreement or automated–human alignment is implied while real blinded ratings
remain outstanding.

## Strict finite JSON-number decoding at reconciliation preflight

The independent reconciliation-readiness reader rejects nonstandard JSON
numeric constants (`NaN`, `Infinity`, and `-Infinity`) and decimal
exponents that overflow to nonfinite Python floats (for example, `1e999`).
It also rejects integer tokens exceeding **128 decimal digits** before
converting them, keeping even a file below the 16 MiB byte bound from
carrying an unreasonably large integer token. Numeric validation converts
ordinary Python integers through a guarded finite-float conversion so that
injected extreme values fail as `ValueError`, not an uncaught
`OverflowError`. JSON `null`, booleans, ordinary finite fractions, and
string literals containing these words remain valid at the decoder boundary.

These are *readiness-layer* checks on already collected automated and human
analysis receipts, complementary to upstream independent output verification;
they neither authenticate original missing treatment reports nor change
the frozen analysis. Synthetic tests in
`tests/test_human_reconciliation_readiness_json_numbers.py` cover illegal
constants, exponent overflow, integer-token limits, nested values, valid
boundary values, the preserved automated snapshot, and direct numeric
overflow. No treatments, evaluations, analyses, or human ratings were rerun
or generated. Pilot observations remain diagnostic, frozen automated
designated-primary findings retain post-collection plan-timing qualifications,
retrospective sensitivity findings remain exploratory, and human validation
is pending original-source recovery and eligible annotators.


## JSON structural and float-token resource bounds

The same independent readiness reader now rejects JSON nested more than
**64 array/object levels** and decimal/exponent number tokens longer than
**128 characters**. This complements the existing 128-decimal-digit integer
limit and 16 MiB per-input bound: a file below the byte cap can still contain
pathologically deep JSON or a very long but numerically finite float token.
Depth is checked with a linear preflight that ignores braces/brackets inside
quoted strings, including escaped quotes and backslashes. Python's JSON
decoder still performs the complete syntax and duplicate-key validation;
malformed/deep structures fail with controlled errors rather than uncaught
recursion errors. Exactly bounded finite numbers and normal nested receipts
remain accepted. No historical observation, human score, or inference method
was changed.

`tests/test_human_reconciliation_readiness_json_structure_bounds.py` exercises
depth-limit boundaries for arrays and objects, escaped quoted punctuation,
floating-point token limits, normal syntax failures, and the preserved
automated-analysis receipt. These tests use synthetic documents and retained
automated bytes only; they are not new treatment, confirmatory, exploratory,
or human-validation results.


## Malformed nested analysis containers fail before reconciliation

The readiness validator now requires the two parsed analysis payloads and
every designated automated contrast and human contrast/dimension block to
be JSON objects before accessing their fields. Included/missing human task
identifiers must be strings from the same frozen ten-task universe before
they are converted to sets. This prevents a malformed retained analysis
(such as a nested JSON list in place of a contrast, or an object inside a
task-ID list) from escaping with a Python `AttributeError` or `TypeError`
instead of a controlled, descriptive readiness validation failure.

The changes are schema-hardening only; they do not modify, synthesize,
impute, or rerun automated measurements or human ratings. Synthetic
regressions in `tests/test_human_reconciliation_readiness.py` exercise
malformed top-level and nested containers, unhashable/unknown task IDs,
and the unchanged well-formed path. A passed readiness check still requires
independent source verification; it does not establish original-report
custody or human validation without genuine retained blinded submissions.


## Reconciliation readiness single-link and full-generation custody

The *downstream* readiness preflight now refuses every pre-existing hardlink to
its captured automated analysis, automated provenance, human analysis,
human-analysis manifest, or frozen reconciliation contract. It requires one
filesystem link before reading, then binds device, inode, byte count, mtime,
ctime, file mode and link count during the descriptor read and at the final
pathname recheck. Earlier checks held content, size, mtime, ctime and inode,
but accepted a pre-existing alternate hardlink and compared only device/inode
at the final pathname check. The final check now also catches a mode or
metadata change between the final descriptor check and the visible path check.

Synthetic, offline regressions in
`tests/test_human_reconciliation_readiness_file_identity.py` cover an
ordinary single-link control, pre-existing aliases for both automated and human
inputs, an alias created within the verification window, and an instrumented
late pathname metadata change. They do not modify any genuine rating or
automated measurement.

This closes an observable local alias and same-inode mutation route before a
descriptive automated-to-human readiness receipt can be issued. It does not
authenticate original archived reports and traces, prohibit copies made
elsewhere, guarantee atomic filesystem snapshots, prove annotator independence,
or create human-validation results. The diagnostic pilot remains diagnostic,
frozen designated-primary automated findings are post-collection rather than
established prospective preregistration, exploratory analyses remain
exploratory, and actual blinded human ratings are still pending.
