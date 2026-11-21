# Prospective planner-query contract and treatment fidelity

The P6/P6V planning treatment obtains one JSON list of **exactly four** query
strings before the fixed browse budget is allocated. The earlier runtime
silently cast JSON booleans, numbers, arrays, and objects to strings and dropped
blank entries. That could make an invalid planner response appear to have
satisfied the four-query contract, obscuring the actual generated plan in the
prospective search trace.

`logic.planner_queries.parse_planned_search_queries` now requires the raw
provider response to be JSON text containing a list with precisely four
nonblank string entries. It trims surrounding whitespace as before and keeps
the original order. **Valid duplicates remain valid:** they are evidence of
what the planner generated, not a reason to select a different outcome or
silently repair the plan. An invalid response raises `ValueError` rather than
being recast, pruned, retried, or replaced by preferred output.

Direct D3/D6 treatments still use the original question as their single query.
No retrieval source, provider, treatment, or evaluator is contacted by the
contract tests. Synthetic cases cover valid Unicode/duplicates, malformed JSON,
incorrect cardinality, blank entries, and non-text values. The separate
source-bound main-study runner fast CI lane executes these tests offline, with
the full-suite tests remaining independently required for certification.

**Scope:** This is a forward-looking experiment validity safeguard; it does
not retroactively alter, rerun, or reclassify the frozen September treatment
matrix, evaluator outputs, primary paired analysis, or pilot observations.
It cannot verify source custody, the historical planning outputs, provider
activity, or treatment-order exchangeability. The pilot remains diagnostic;
retrospective measurement sensitivity remains exploratory; the frozen
automated analysis retains its post-collection planning qualification; and
human validation still requires authenticated reports, eligible independent
raters, and genuine blinded ratings.
