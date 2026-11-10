# Counterbalanced pair-to-blinded-freeze continuity

Status: optional, read-only coordinator provenance audit. All regression evidence is synthetic. No actual human ratings, agreements, recruitment or validation results are claimed.

## Gap closed

The existing counterbalanced submission-pair verifier checks two real future rating files against their distinct source-bound canonical and reverse distribution bundles and independently pinned coordinator manifest. The independent blinded-freeze verifier separately validates the archived original files, scores, agreement and protocol. Before this addition no post-freeze gate required the exact pair-verified submitted bytes and presentation orders to match the two actual archived originals.

This matters because a freeze can be individually valid while being built from different submitted files or without demonstrating that the intended pair of opposing presentation orders was preserved. This is evidence continuity, not a new exclusion criterion or a statistical estimate.

## Coordinator procedure

Only after obtaining genuine, eligible independent human ratings under the frozen assignment plan:

1. Run the existing counterbalanced submission-pair pre-freeze verification and save its exact JSON output. Independently record SHA-256 of those exact bytes before freezing; an editable colocated hash file is not an independent pin.
2. Freeze exactly the same two submitted original CSVs with each associated retained preflight receipt and distribution bundle using the existing create-only freeze tool. Include the mandatory separate pseudonymous eligibility attestations.
3. Before unblinding, execute:

    python -m scripts.verify_human_eval_counterbalanced_freeze_link --freeze-root outputs/human_eval/frozen-v1 --pair-receipt path/to/paired-proof.json --pair-receipt-sha256 INDEPENDENT_SHA256 --expected-n-reports 40

The command requires the **version-2** pair receipt with both original
preflight-receipt SHA-256 fields, rejecting older or incomplete pair receipts.
It validates those digests' syntax but does **not** compare them directly with
the freeze's archived receipts: freezing deliberately neutralizes sensitive
source filenames in retained receipt copies, so their raw JSON bytes can differ.
The original pre-freeze receipt files and their byte hashes must be retained
separately. The command independently verifies the retained blinded freeze first. It then links the archived rating-input SHA-256 values to the pinned pre-freeze pair by canonical/reverse order, verifies archived preflight source-bundle fingerprints and missingness counts, requires one of each order, and checks the canonical packet fingerprint against the governing frozen packet. No originals are mutated, and the coordinator-only blinding key is not read.

## Limitations

SHA-256 and file consistency do not prove human identity, independent authorship, eligibility, consent, validity of declarations, statistical agreement, or treatment effects. This is observational verification, not an atomic filesystem transaction. Independently retain the original pre-freeze pair receipt and its digest outside the mutable archive. With additional raters this exact-two-submission gate is not the applicable protocol mechanism; use the frozen assignment/deviation plan. Pilot, confirmatory automated, exploratory, and pending human validation claims remain separate.


## Bounded pair-receipt capture

The optional pair-to-freeze link consumes a small independently pinned JSON
provenance receipt, not a full annotation CSV. That receipt has a **64-KiB**
limit. Its source capture enforces this limit **at the opened file descriptor,
before reading any payload**, rather than first allowing the shared 64-MiB
human-rating input limit and only rejecting the oversized bytes afterward.
Both the initial independently pinned read **and the final end-of-audit
recheck** enforce the same 64-KiB bound before consuming the receipt. This
prevents a replaced or expanded receipt from reverting to the broader CSV input
limit during the final continuity check. Excessive JSON nesting in an otherwise
size-bounded, independently pinned receipt also fails with a controlled
verification error instead of an uncaught parser recursion exception.
The same file-identity, append-growth, symlink and replacement checks remain in
force. The default source-capture contract for genuine rating/packet inputs
is unchanged. Synthetic regression coverage checks oversized pre-read refusal,
the exact size boundary, concurrent growth and invalid caller limits.

This is a resource-safety and integrity safeguard on a future coordinator
receipt, not evidence that human ratings were collected or that historical
treatment reports were authenticated.

## Optional exact original preflight-receipt custody

The version-2 pair receipt binds SHA-256 hashes of **both original pre-freeze
preflight receipt JSON files**, but the frozen archive intentionally stores
filename-neutralized copies. A matching archived receipt alone cannot prove
the exact original JSON bytes without examining those retained source files.

When both original receipts are available, run the ordinary freeze-link command
with the two additional options:

~~~bash
  --canonical-original-preflight-receipt /retained/canonical/preflight_receipt.json \
  --reverse-original-preflight-receipt /retained/reverse/preflight_receipt.json
~~~

Both paths must be supplied together. The audit captures each original under
a 64-KiB regular-file limit, checks its **exact byte hash** against the
independently pinned pair receipt, and requires all original receipt fields
to match the archived counterpart after **only** replacing the intentionally
neutralized submission filename (e.g., `0001.csv`). A final recheck detects
observable mutations during the intervening archive verification window.
The returned `original_preflight_receipts_byte_verified` is `true` only for
two successfully verified originals; when not supplied it is explicitly
`false`. The original source receipts are neither rewritten nor distributed.

This closes a previously optional/unverified byte-continuity link, but it
does not establish independent human identity, submission timestamps,
eligibility, rating independence, or authentic custody of historical treatment
reports and traces. Source fingerprints do not prevent transient changes
fully reversed between observations, and caller-supplied evidence is not
an external timestamp. All tests for this feature are synthetic.

## Receipt source identity across the verification window

When the optional original preflight receipts are supplied, the link now
preserves **both their exact bytes and their observed file/parent-directory
identities** from first capture through final recheck. The independently
pinned pair receipt receives the same protection even when original receipts
are not supplied. Byte equality alone was insufficient: replacing a receipt
with a distinct inode containing identical JSON during the blinded-freeze
audit previously passed both hash and end-of-window byte checks.

The bounded 64-KiB descriptor-based capture now also observes the immediate
parent directory device/inode and each receipt's device/inode, size, mtime
and ctime, checking that observation on both sides of each capture and again
at the end of verification. A visible same-byte file replacement, parent
replacement or metadata rewrite therefore fails closed. The historical
pair schema, optional original-receipt behavior, rating values, statistical
methods and published results are unchanged. Synthetic tests exercise
byte-identical pair/canonical/reverse replacements and a same-byte metadata
rewrite. This is an **observational** custody check, not a filesystem lock,
external timestamp, proof of annotator identity or independent source archive;
changes completely reversed between observations may escape detection.
