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


## Versioned prospective search-trace reconciliation (21 November 2026)

A returned candidate array and run-level browse counts can be individually
well-formed but internally contradictory. Future traces emitted by logic.run
are explicitly stamped with search_provenance_schema 1. The offline
noncanonical treatment runner now validates marked completed traces against
the original ordered query list, per-query candidate and selected-source URL
arrays, backend-pool labels, search error records, unique run-level scheduled
URLs and attempted-browse counts. Any contradiction fails the prospective
trace before it can be accepted as a completed treatment or cost observation.
Order and duplicate candidate entries are retained, not repaired, trimmed,
reranked, or replaced.

Historical September traces and legacy fixtures remain unmarked and readable;
their absence of this marker is not evidence of authentication and they are
not silently retroactively certified. This is internal source-ledger consistency
rather than proof of the external engine, original web pages or missing original
40 report/trace pairs. New offline synthetic and integration tests exercise
both valid and altered ledgers without model, search, evaluator, treatment or
human-annotation calls. Diagnostic pilot, post-collection frozen automated
inference, retrospective exploratory sensitivity and pending human validation
remain separate.


## Prospective browse-outcome ledger reconciliation (21 November 2026)

The versioned search-trace validator now binds **observed successful and failed
browse URLs** back to scheduled attempts, in encounter order, rather than
relying only on unordered set membership and total counts. It checks that
each outcome URL belongs to a scheduled attempt, appears once in exactly one
outcome class, preserves its relative position in the original schedule, and
matches the recorded class count. A completed run must classify every
scheduled browse. The recorded `source_success_rate` must also equal the
observed successful-attempt fraction (or zero when no browsing was scheduled),
with nonfinite and Boolean values rejected. A non-completed run may retain
unclassified attempts instead of inventing a success or failure.

This closes a prospective evidence-integrity gap in which reordered outcome
lists or a stale/forged success ratio could pass set-based source accounting.
The checker does not reorder, repair, recover, or rerun any sources; it fails
inconsistent completed traces before the noncanonical runner accepts them.
Synthetic regression cases include interleaved successes/failures, identity
and count discrepancies, same-set order swaps, unclassified completed
attempts, nonfinite rates, and legitimate partial/zero-attempt traces.
The running agent already records outcomes in scheduling order. The historic
unmarked September traces are neither revalidated nor authenticated by this
forward-looking requirement.

This is local trace consistency, not independent proof of external page
content or the original 40 report/trace pairs. The five-task pilot remains
diagnostic; frozen automated inference remains post-collection with
fixed-order and evaluator-policy comparability qualifications; retrospective
sensitivities are exploratory; and blinded human validation remains pending.


## Prospective requested-candidate receipt reconciliation (21 November 2026)

The previous parser enforced the actual per-query search request at ingestion,
but schema-1 traces recorded the candidates and scheduled sources **without**
the requested count. A trace reviewer could not independently check whether
a seemingly valid candidate array exceeded its request even when no URLs were
scheduled from the excess.

New prospective `search_provenance_schema: 2` traces therefore record the
`requested_candidate_limit` for every attempted search, including provider
outages with zero candidates. The run-level trace also records the configured
`search_candidate_multiplier`. The offline verifier recomputes each request
limit from the persisted source budget, ordered planned query slots, already
scheduled browse attempts, multiplier, and the fixed 20-candidate adapter cap.
It rejects missing/boolean/contradictory request counts, overproduced source
arrays, and searches attributed to zero-budget or exhausted query slots. The
same check applies to successful and search-error records. It does not alter
query allocation, candidate selection, retrieval budgets, or experimental
outcomes.

Legacy schema-1 traces remain verifiable under their earlier reconciliation
contract but **are not retroactively certified** for per-request count
conservation. Schema-2 receipt consistency is not independent authentication
of the provider's actual web request or the original September report/trace
bytes. Synthetic offline cases cover valid duplicate candidates, error
records, forged counts, changed multiplier/budget, overproduction, and
unfunded query slots; no live treatment/evaluator or human ratings are
produced. The pilot remains diagnostic, the frozen automated comparisons
remain post-collection and subject to fixed-order/evaluator-policy
limitations, retrospective sensitivity analyses remain exploratory, and
independent human validation remains pending.


## Prospective funded-query and per-slot browse-accounting gate (21 November 2026)

A schema-2 search receipt previously checked that every *recorded* query had
an allowable candidate-request limit, but it did not require every **funded**
planned query to appear in a completed run. A completed report could omit a
planner query and still preserve internally consistent aggregate counts.
It also checked candidate overproduction without separately limiting how
many URLs were actually scheduled for a single query; the first query could
spend another query's allotted browse attempts while staying under the
run-level total budget.

The completed-trace gate now requires exactly one search record for each
planned query given a positive browse allocation, including explicitly
recorded provider outages (which need not return candidates). A trailing
zero-budget query slot remains legitimately unattempted. Each recorded
query's **scheduled browse attempts** must also fit its own allocated slot
and the remaining global budget. Neither valid duplicates in candidate
results nor source failures are silently removed or replaced, and no
treatment is retried to meet the rule. Legacy schema-1 receipts remain
under their historical, weaker contract; incomplete traces are not
misrepresented as completed research.

Offline regressions exercise omitted funded query attempts, recorded outages,
legitimate unfunded queries, zero-query completed reports and a three-attempt
first query exceeding its two-attempt allocation without exceeding the
global four-attempt budget. This is **internal accounting integrity**, not
proof of external search results or missing historical report custody.
The pilot remains diagnostic, the frozen automated main-study analysis is
post-collection with fixed-order and evaluator-comparability limitations,
retrospective sensitivities remain exploratory, and independent human
validation has not yet been performed. No historical treatment, evaluator,
score or human rating is changed.

## Prospective treatment-to-search-plan binding (21 November 2026)

The completed schema-2 trace verifier reconciled requested candidate counts,
per-query browsing budgets and total search calls, but did not independently
check whether the *planned queries themselves* matched the treatment's
planning mode. A self-consistent two-query planner trace, or a direct-mode
trace that substituted a different question, could pass those accounting
checks even though production planning uses exactly four queries for the
planner treatment and the exact task question for direct retrieval.

New prospective `search_provenance_schema: 3` receipts fail completed traces
unless they record a nonblank original `question`, the proper
`planning_mode`, and either the exact one-query direct plan
`search_queries == [question]` or **exactly four** planner query strings.
Planner-query order and legitimate duplicates are preserved; the validator
does not invent, truncate or replace any queries or search results. These
checks use fields already emitted by the agent. Incomplete/failed traces are
still preserved when planning has not completed, rather than fabricating a
valid plan.

Schemas 1 and 2 retain their original, weaker contracts; this stronger
gate does **not** retroactively certify previously recorded traces.
Offline synthetic tests cover valid direct/planner plans, duplicate planner
queries, missing or changed task identity, altered planner arity, invalid
mode and incomplete-run retention. No live treatment, search, evaluator or
human rating was produced. The pilot remains diagnostic, frozen automated
inference remains post-collection and qualified by fixed-order and evaluator
comparability limitations, retrospective sensitivities are exploratory,
and independent human validation remains pending.


## Prospective frozen-arm treatment-factor custody (21 November 2026)

Schema-3 completed traces could demonstrate that a direct search used its
exact original question, or that a planner emitted four queries, without
independently binding the recorded **variant ID, source budget and
verification mode** to the predeclared D3/D6/P6/P6V treatment assignment.
A locally consistent direct retrieval ledger could thus misstate whether
treatment-time verification was enabled. A separately persisted
`experiment` envelope might also disagree with its own trace.

Schema **4** now fails closed on completed traces unless *both* the trace
and the saved ExperimentConfig envelope agree on the frozen factors:
D3 = direct / 3 attempted browses / no verification;
D6 = direct / 6 / no verification;
P6 = planner / 6 / no verification;
P6V = planner / 6 / verification. Unknown variant identifiers, Boolean
budgets, missing envelopes and any conflicting factor fail validation.
The noncanonical study runner passes the independently persisted
experiment envelope to the validator. Existing query-plan, candidate,
schedule and browse-outcome reconciliation remains in force.

The check does not authenticate the physical execution of a model or
verifier, external search results, or historical source documents.
Previously recorded schemas 1–3 are not retroactively certified for
this new factor-envelope invariant. Incomplete traces remain preservable
without fabricated treatment factors. Offline synthetic cases exercise
all four correct assignments, altered trace/envelope factors, missing
envelopes, and backward compatibility; no treatment, evaluator or human
rating was rerun. The five-task pilot remains diagnostic, frozen
automated findings remain post-collection with fixed-order and
evaluator-policy caveats, retrospective sensitivity analyses stay
exploratory, and genuine blinded human validation remains pending.


## Prospective retained verifier-output custody (22 November 2026)

Schema-4 treatment-factor checks only established that a completed P6V trace
*claimed* verification mode. They did not require a matching
`verification.json` receipt, or cross-check the reported verification status
and claim-category totals against that retained output. A completed trace could
otherwise be accepted with a verification flag but no accompanying verifier
output.

New **schema 5** adds an exact UTF-8 SHA-256 of the verifier's published JSON
bytes to prospective traces. The noncanonical treatment validator requires a
completed P6V trace to report `ok` or explicit `parse_error`, checks bounded
nonnegative claim totals, and reads the expected `outputs/<run-id>/verification.json`
through the existing bounded, no-follow file capture before matching SHA-256,
strict JSON structure, status and all five verifier counters. Non-verification
arms must claim neither a verifier artifact nor verifier counts. An actual
parse error remains a recorded measurement failure with **zero** checked
claims, never silently presented as successful evidence verification.
Incomplete runs remain preservable without inventing a verifier result.

The new contract does **not** establish that the external LLM executed, that
a verifier's judgments were correct, or independent custody of historical
September treatments. Historical schema-1 through schema-4 traces retain their
original contracts and are not retroactively certified. Synthetic offline
tests cover all four arms, successful/parse-error receipts, altered digests,
duplicate JSON keys, forged counts/statuses, missing receipts, and backwards
compatibility. No treatment, evaluator or search is rerun for better outcomes.
The five-task pilot is diagnostic; frozen automated inference retains
post-collection planning, fixed-order and evaluator-policy limitations;
retrospective sensitivity analyses remain exploratory; and blinded human
validation is pending.


## Prospective completed-report byte custody (22 November 2026)

Prior prospective checks required a completed Markdown report with the same
`report_words` count as its treatment trace, but a different report with an
identical word count could still pass. This matters when the retained Markdown
is subsequently considered for blinded human evaluation: verification of the
retrieval ledger or verifier's JSON does not identify which report text was
actually retained.

New **search provenance schema 6** records the SHA-256 digest of the generated
UTF-8 report text for all four arms. The noncanonical study runner independently
reads the bounded, no-follow `outputs/<run-id>/research_report.md` file and
checks its exact bytes against the completed trace after the preexisting report
path, UTF-8, and word-count checks. A missing digest, same-word-count
substitution or byte-level alteration fails before a run can be accepted as
completed evidence. The existing schema-5 verifier JSON continuity check
remains enforced for P6V under schema 6; no-verification arms are also subject
to the new report check. Incomplete traces and historical schema 1–5 records
retain their previous contracts and are **not retroactively authenticated**.

This checks prospective internal trace-to-report custody, **not** independent
proof that the saved bytes came from an external LLM, that the text is correct,
that original 2026 historical treatment reports were recovered, or that blinded
ratings have occurred. Synthetic offline tests cover all four arms, exact byte
matches, same-word-count changes, missing/malformed hashes, oversized bytes and
legacy compatibility. No research treatment, common evaluator or human rater
was rerun; the five-task pilot remains diagnostic, frozen automated findings
retain their post-collection planning, fixed-order and evaluator-policy caveats,
retrospective sensitivity analyses remain exploratory, and genuine blinded
human-validation results remain pending.
