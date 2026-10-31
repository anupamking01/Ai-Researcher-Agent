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

The command independently verifies the retained blinded freeze first. It then links the archived rating-input SHA-256 values to the pinned pre-freeze pair by canonical/reverse order, verifies archived preflight source-bundle fingerprints and missingness counts, requires one of each order, and checks the canonical packet fingerprint against the governing frozen packet. No originals are mutated, and the coordinator-only blinding key is not read.

## Limitations

SHA-256 and file consistency do not prove human identity, independent authorship, eligibility, consent, validity of declarations, statistical agreement, or treatment effects. This is observational verification, not an atomic filesystem transaction. Independently retain the original pre-freeze pair receipt and its digest outside the mutable archive. With additional raters this exact-two-submission gate is not the applicable protocol mechanism; use the frozen assignment/deviation plan. Pilot, confirmatory automated, exploratory, and pending human validation claims remain separate.
