# Human reconciliation: checkout-local annotator-guide provenance

Status: offline implementation safeguard; genuine blinded human annotations are
still pending.

## Identified gap

The automated–human reconciliation readiness gate accepts an explicit
`root` for independently checking an alternate checkout. It already routed
the frozen protocol, assignment plan, analysis plan, task manifest, packet and
freeze archive through that selected root. However, it omitted
`annotator_guide_path` when calling
`verify_human_eval_analysis_outputs.verify_bundle_against_inputs`.
That verifier's default came from the checkout where the Python module was
imported, **not necessarily the selected checkout**.

Consequently an alternate checkout with a missing, substituted or stale
annotator guide could be examined using the ambient checkout's guide instead.
An exact SHA-256 check on the wrong path does not prove that the selected
checkout contains the approved governing document.

## Safeguard

`_verify_human_analysis_bundle` now explicitly supplies
`root / "paper" / "HUMAN_EVAL_ANNOTATOR_GUIDE.md"`. All governing
paths for the independent human-analysis recomputation are selected from the
same requested checkout. The existing pinned guide-byte verification remains
in force. No fallback to an ambient checkout is permitted.

Synthetic offline regressions assert the complete path map, demonstrate that
a selected-checkout guide's bytes reach the independently invoked verifier,
and require a missing selected guide to remain missing rather than being
silently substituted with the ambient repository's guide.

## Limits and scientific boundary

This correction is **path/provenance integrity**, not a new rating protocol,
source-signature scheme, immutable archive guarantee, statistical analysis or
evidence of genuine annotations. The frozen human analysis plan, automated
confirmatory outputs, pilot findings, exploratory claims, treatment reports,
and descriptive reconciliation contract remain unchanged. No model, web
retrieval, evaluator or treatment is rerun.
