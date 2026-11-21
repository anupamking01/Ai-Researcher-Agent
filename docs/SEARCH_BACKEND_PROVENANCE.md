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

## Bounded untrusted search-result JSON (21 November 2026)

Prospective metasearch result ingestion now applies explicit, fail-closed
resource/number bounds **before candidate selection**: at most
`1,048,576` UTF-8 bytes of JSON, at most `128` returned candidates per
query, and at most `128` characters per JSON numeric token. A finite
JSON floating-point value is required, including for otherwise ignored
metadata (a JSON exponent that overflows to infinity is not silently
accepted). Deeply nested input produces a bounded validation failure rather
than propagating an uncaught Python recursion error; unencodable text is
rejected before JSON parsing.

These ceilings substantially exceed the frozen metasearch adapter's
four-result-per-query contract. Within the limits, original candidate URL
bytes, backend-pool labels, order, duplicates and retrieval budgets are
unchanged. If a response exceeds a limit, the **whole query fails**, rather
than trimming candidates or choosing more favorable sources. The guard
limits malformed-result memory and parsing exposure; it is **not** a cap on
provider execution time, a DNS/redirect security policy, or a verification
of historical evidence.

Offline regression tests cover both ASCII and multibyte UTF-8 wire sizes,
candidate ceilings, abnormal JSON exponent/number tokens, recursive JSON
nesting and valid finite metadata. No live search, treatment, evaluator or
human rating was generated; the five-task pilot remains diagnostic, frozen
automated comparisons retain their post-collection and fixed-order caveats,
retrospective sensitivity remains exploratory, and genuine human validation
is still pending.

## Search-request result-count fidelity (21 November 2026)

The production `web_search(query, num_results=candidate_limit)` adapter
normalizes its result list to **at most** the requested count. Earlier
prospective trace ingestion used only a broad 128-candidate safety ceiling,
so a malformed or substituted result list could exceed the **actual**
per-query request (typically much smaller) and still influence candidate
ordering and scheduled browsing. The agent now passes the exact request bound
to the candidate parser. An overproduced list fails the **entire query**
before any URLs are scheduled or source-budget counters are consumed; no
extra candidates are truncated, reranked, retried, or selected. The broader
128-candidate absolute bound remains in place for callers without a request
limit. Strict positive-integer limit validation rejects Boolean and
noninteger controls instead of silently coercing them.

Offline synthetic regressions verify the exact-boundary behavior, fail-closed
overproduction across small and maximum current request sizes, invalid limit
types, preservation of duplicate/order/pool fields, and the agent-to-parser
wiring. This is prospective search-contract and evidence-selection integrity,
not proof of the underlying external search engine, DNS/redirect safety, or
historical page custody. No treatment/evaluator was rerun; frozen automated
findings retain post-collection, fixed-order and evaluator-policy caveats,
pilot findings remain diagnostic, retrospective analyses exploratory, and
genuine independent human ratings pending.
