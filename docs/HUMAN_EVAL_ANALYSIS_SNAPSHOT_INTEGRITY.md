# Human-evaluation analysis snapshot integrity

`scripts/human_eval_analysis_core.py` now binds verification and analysis to the
same captured bytes.

Before any treatment identity is opened, the analyzer snapshots the archived raw
rating inputs, blinded packet, frozen ratings, agreement artifact, freeze
manifest, protocol, assignment plan, and human-analysis plan into private
temporary scratch space. The pre-unblinding freeze verifier runs against those
snapshots. If that gate passes and the frozen two-rater requirement is satisfied,
the analyzer then reads the coordinator-only mapping artifacts.

The packet manifest, blinding key, ratings template, and frozen task manifest are
captured only after the blinded gate. The packet verifier runs against that
second snapshot, using the already captured blinded packet. All report-level
aggregation, treatment mapping, agreement inclusion, and provenance hashes are
computed from the verified snapshots rather than reopening the live source paths.

This closes a time-of-check/time-of-use gap where an editor save after a verifier
returned could previously change the scores, task universe, treatment mapping,
agreement payload, or provenance that the analysis actually consumed.

The scratch copies are ephemeral and are deleted when analysis exits. They are
not a replacement for retaining the original archived ratings, packet bundle,
freeze bundle, or Git-tracked analysis plan. Source trace and report provenance
continues to be checked by the packet verifier against the repository; treatment
and evaluator runs are not regenerated.
