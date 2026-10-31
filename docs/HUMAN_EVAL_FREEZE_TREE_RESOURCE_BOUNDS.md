# Human-evaluation freeze archive capture resource boundaries

The human-analysis pipeline verifies blinded freeze inputs **before** accessing
the coordinator-only treatment mapping. The freeze-root snapshot previously had
a per-file 16 MiB bound, but not a bound on the *number*, *combined size*, or
*nesting depth* of archived files. A malformed freeze tree could therefore
exhaust temporary-storage or recursion resources before independent verification
rejected it.

## Guardrail

`scripts/human_eval_analysis_core.py` now fails closed on freeze-tree
captures exceeding any of these conservative resource ceilings:

- **256 entries**, counting both nested files and directories (excluding the
  root directory itself).
- **64 MiB aggregate regular-file bytes** (in addition to the existing
  16 MiB per-file bound).
- **8 directory levels** below the snapshot root.

The pre-copy inode/metadata inventory and the descriptor-bound copy enforce
the same ceilings independently. A second inventory check still verifies that
the original tree generation did not change during copying. Direct consumers
of the generic recursive-copy helper receive the same bound.

These limits are implementation safety constraints, not a modification to
the frozen rating rubric, sample size, treatment matrix, analysis plan, or
statistical inference. They do not imply an atomic filesystem snapshot and
cannot authenticate source provenance, annotator identity, or genuine ratings.
A metadata-only inventory can still enumerate up to its bounded tree budget;
the limits are not a guarantee against all forms of resource exhaustion.

Regression tests use small, synthetic nested trees and exact-boundary,
over-limit, and pre-copy cases. They do not run treatments, generate ratings,
unblind evidence, or alter canonical frozen results.
