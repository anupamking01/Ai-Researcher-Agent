# Forward-looking search candidate and backend-pool provenance

The metasearch adapter (`scrape/web_search.py`) annotates normalized results
with `_search_backend_pool`, but the research agent previously stored only
candidate and scheduled URL strings in `trace.search_records`. A report's
trace therefore could not distinguish which *configured request pool* was
selected for its retrieval candidates. The adapter's selected pool is **not**
independent proof of the external search engine that served an individual
result or of the original page content.

Prospective traces now add two **ordered, additive** fields for each successful
query: `candidate_sources` (one record per candidate, preserving order
and duplicates) and `scheduled_sources` (the actual selected URLs in
scheduled order, bound to their first matching candidate record). Each record
has `url` and `backend_pool`. Missing pool metadata is
explicit `null`, never guessed. Existing `candidate_urls`,
`scheduled_urls`, query order and retrieval scheduling remain unchanged.
A transient metasearch `RuntimeError` records empty source lists plus
the existing bounded error note.

A malformed return envelope previously could silently yield zero candidates
(for example an object root, non-object list item, or missing `href`).
The new stdlib-only `logic.search_provenance` parser rejects those
noncontract results, ambiguous repeated JSON keys, nonfinite JSON constants,
invalid explicit pool labels, and scheduled URLs absent from returned
candidates, rather than transforming corruption into a valid-looking
zero-source search. The normal normalized list-of-objects search contract
remains compatible with legacy missing pool labels. It neither retries,
filters, ranks, substitutes, nor requests additional search results.

Synthetic offline regression tests cover real/unknown pool attribution,
original candidate order, duplicate candidates, actual scheduling,
malformed or ambiguous JSON, missing URLs, malformed pool labels and
mutable-record isolation. They run in the source-bound,
firewalled main-study runner fast CI lane alongside the unchanged
offline full-suite requirement. No search provider, model or evaluator
was contacted for these tests.

This guard applies only to **future** runs; no historical September
treatment report/trace or frozen automated result was reconstructed,
modified, rerun or reinterpreted. The earlier five-task pilot stays
diagnostic; designated-primary frozen automated inference remains
post-collection with fixed treatment-order and evaluator-policy
limitations; retrospective sensitivities remain exploratory. Original
source custody, eligible annotators and genuine blinded human ratings
remain separate, unmet research gates.
