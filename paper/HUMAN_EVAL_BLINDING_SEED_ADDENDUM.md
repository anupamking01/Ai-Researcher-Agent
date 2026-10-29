# Human-evaluation blinding seed: pre-annotation security addendum

**Status: prospective operational blinding correction; 2026-10-29. No human
ratings have been collected or unblinded.** This document does not change
VERA's diagnostic pilot, frozen automated confirmatory analysis, exploratory
findings, human rubric, assignment/coverage, missingness, agreement measures,
or human-analysis estimands.

## Vulnerability in the historical packet recipe

The frozen `paper/HUMAN_EVAL_PROTOCOL.md` documents an earlier fixed seed
(`20260915`). Given exactly one record per public (task, treatment) cell,
the packet builder's public sort order and that known seed completely determine
the permutation of the blind IDs. An annotator could recover the treatment
mapping without seeing `blinding_key.csv`. Omitting the seed from an annotator
manifest was not sufficient when the default was publicly predictable.

**Do not distribute an old fixed-seed packet for genuine blinded scoring.**
Retain any such packet unchanged as provenance; it cannot be retroactively
certified as blinded by hiding its coordinator key.

## Prospective correction

`scripts/build_human_eval_packet.py` now uses a fresh 256-bit seed from
`secrets.randbits` on every production CLI invocation. The CLI does **not**
accept a `--seed` option and prints only a seed-free creation receipt. The
coordinator-only `manifest.json` retains the actual seed so
`scripts/verify_human_eval_packet.py` can independently replay and verify
the precise treatment-to-blind-ID permutation. The separate
`blinding_key.csv` remains coordinator-only.

Explicit seeds in the Python `build_packet()` API are retained solely to
make synthetic unit-test fixtures reproducible. They must not be supplied for
a live human-rating packet. A newly generated packet is deterministic
**conditional on its securely retained seed**, not predictably identical
across separate runs.

Keep both coordinator artifacts and the full manifest JSON private during
scoring, including in logs, repository commits, and annotator-facing
distributions. The exporter continues to distribute only the verified,
seed-free annotator bundle.

## Recovery and collection gate

Original treatment traces and Markdown reports are still unavailable from the
historical Actions artifacts. Independently recover and authenticate those
original sources first. Only then, and **before any report is shown to an
annotator**, create a fresh, versioned coordinator packet with the default CLI,
verify it, and export separately verified seed-free annotator bundles.
Do not regenerate treatment outputs or rerun an evaluator to repair an exposed
packet. Record any previous fixed-seed packet and the reason it was replaced.

This addendum is a prospective procedural security amendment. The original
`paper/HUMAN_EVAL_PROTOCOL.md` is deliberately left **byte-for-byte unchanged**
because other research validation gates pin its historical SHA-256. Its earlier
fixed-seed implementation sentence is superseded only for *future packet
construction*. No historical protocol fingerprint has been silently re-pinned
or rewritten, and no empirical or human-validation claims are added.
