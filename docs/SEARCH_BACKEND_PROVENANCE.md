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

## Prospective candidate URL admission (21 November 2026)

Search result URLs now have an explicit **pre-browse, fail-closed** admission
contract: each returned `href` must be an absolute HTTP(S) URL with a host,
no embedded credentials or whitespace/control characters, and a usable port.
Known localhost/local-name suffixes, non-global IP literals and browser-style
abbreviated or hexadecimal numeric IPv4 authorities are rejected. IDNA
normalization is used only to evaluate host safety (for example visually
encoded localhost); accepted URLs are recorded **byte-for-byte**, without
rewriting query parameters, fragments, ordering, duplicates or selection.
A mixed valid/invalid result array raises a validation error rather than
quietly removing candidates, shifting budgets, or choosing replacement
sources. Both direct and planner query paths use this parser before scheduling
Selenium browsing. This protects prospective retrieval from plainly
non-web/local targets and prevents malformed provider result URLs from
masquerading as valid scheduled sources.

This check is **not** DNS-resolution verification, redirect policing,
revalidation of in-page navigation, or an egress firewall; a public-looking
hostname can still resolve privately and a website can redirect. It also
cannot authenticate search results or missing historical page content.
Synthetic tests exercise externally shaped IPv4/IPv6/Unicode URLs,
local/private and ambiguous numeric hosts, dangerous schemes, credentials,
control characters and batch failure. No historical treatments or evaluator
calls were rerun; frozen automated estimates and exploratory/human-validation
claims remain unchanged.
