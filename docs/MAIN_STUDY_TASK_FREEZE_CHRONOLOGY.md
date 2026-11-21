# Original ten-task source freeze: a distinct historical research gate

**Status: read-only retrospective provenance, not independent preregistration.**

The ten-task manifest entered Git as [commit b1fe8e15](https://github.com/anupamking01/Ai-Researcher-Agent/commit/b1fe8e15ed4daa98b6539616dfb735cf40f49b6b)
at 2026-09-11 16:11:01 UTC. The original [runner-launch commit c3c15e46](https://github.com/anupamking01/Ai-Researcher-Agent/commit/c3c15e46a8eec3a8bbc24c968eedc0548172a897)
has Git timestamp 16:15:12 UTC; the [treatment workflow](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34620917346)
was created at 16:15:15 UTC. The manifest commit is an ancestor of the
launch commit; both store the exact same Git blob, SHA-1
68316fdb00631856006119370f9f549b23d1bee3, for the manifest path.

Use a non-shallow, full-history checkout:

    python -m scripts.audit_historical_task_freeze

The script checks both immutable commit objects and their ancestry, the pinned
blob at *each* commit, unique JSON keys, the original ten task IDs and
the source's freeze declaration. It records the exact source SHA-256 and
explicit non-claims. The historical-design-source CI workflow runs it
alongside the exact-rank source audit and retains separate read-only receipts.
The offline synthetic tests reject changed/missing sources and chronology.

**What this does not prove:** Git commit timestamps are not independent
registration timestamps, and a self-declared freeze flag cannot establish
outcome blindness or that no draft task alternatives existed. The ten tasks
are not established as statistically independent or population-representative.
The missing original treatment reports and traces remain unauthenticated.

This source freeze is separate from the exact statistical-analysis plan,
which was committed on September 14, after original treatment collection
and evaluator recovery. See [analysis freeze chronology](MAIN_STUDY_ANALYSIS_FREEZE_CHRONOLOGY.md).
The pilot remains diagnostic; the frozen main-study automated analysis
retains its post-collection plan qualification; later analyses remain
exploratory; human validation remains pending. No treatment, evaluator,
or human rating is rerun or created by this audit.
