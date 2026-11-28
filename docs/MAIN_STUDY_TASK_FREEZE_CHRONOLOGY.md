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

## Temporal eligibility of retrieved evidence (26 November 2026)

The manifest freeze is a freeze of **questions**, not of the web corpus or
the dates of evidence available to the agent. The ten manifest category
labels are all distinct (one question per label); they are not replicated
benchmark strata. In particular, `main-09` (passkey adoption) explicitly
asks for information available no later than **September 1, 2026**.
The planned four treatments for this question ran in the September 11
live-web study, ten calendar days after that cutoff. The category label
`fixed_cutoff_current_information` is a question descriptor, not a
certification of temporal eligibility.

The following source inspection uses the immutable September 11 launch
revision `c3c15e46a8eec3a8bbc24c968eedc0548172a897`, not the current
pipeline or current search results.

| Stage | Historical source contract | Temporal limitation |
| --- | --- | --- |
| Task handoff | [Runner](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/scripts/run_budget_main_study.py) passes the question text and task ID, not a structured as-of date. | The cutoff is present in the natural-language question. |
| Query construction | [Research agent](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/logic/research_agent.py) uses the full question in direct mode; planner mode requires four nonempty query strings. | The planner is not required by the parser to retain the cutoff in every query. |
| Search | [DDGS adapter](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/scrape/web_search.py) passes query, region, safesearch, result count and backend pool. | No structured upper-date restriction or publication-date eligibility check is applied by this adapter. The agent schedules URLs, not dated document versions. |
| Page capture | [Selenium scraper](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/scrape/web_scrape.py) calls `driver.get(url)` and extracts rendered headings/paragraphs. | Live page contents are not a frozen as-of-September-1 snapshot. |
| Source condensation | [Text preprocessing](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/text_preprocess/text.py) requests preservation of dates and relevant facts from a bounded page sample, using the retrieval query. | This is a model instruction, not a deterministic date gate; planner queries may differ from the original question. |
| Report and support judgment | [Prompts](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/logic/prompts.py) include the original question in report generation and verification; the verifier compares claims to retrieved evidence. | Neither prompt independently establishes when a cited fact or page version first became available. Evidence support is not a separate temporal-validity verdict. |

Thus a report could receive strict-support credit for evidence that was
available at retrieval time but not at the question's cutoff. Conversely,
the agent could have respected the cutoff using appropriate dated sources.
Neither event is established for any actual report: original report, query
and trace custody remains unresolved. The difference between direct and
planner query handling is a possible mechanism, not evidence that either
arm violated the cutoff more frequently.

For a future authorized evidence review, preserve all four original
`main-09` reports, queries and source summaries unchanged. Distinguish
(1) dated evidence demonstrably available by the requested cutoff, (2)
evidence demonstrably first available after it, and (3) unknown availability.
A page's current timestamp or a later update date alone is not proof of
when a particular claim first became public. Recovered summaries may be
insufficient for this distinction; report that limitation rather than
substituting freshly retrieved pages or using today's web as historical
ground truth. Any additional claim-level temporal assessment must be a
separate, explicitly exploratory, independently documented analysis, not
an alteration of the frozen strict-support endpoint or the frozen human
rubric. Do not disclose this coordinator-facing discussion to blinded
annotators.

For manuscript reporting, identify the original selected live-web task
set, its one-question-per-category coverage and the lack of independently
verified cutoff compliance. Do not claim temporal benchmark performance
or per-category generalization. Do not remove or replace `main-09` based
on this source inspection. All ten task pairs remain in the original
analysis. The five-task pilot remains diagnostic, designated-primary
automated results remain post-collection and qualified, later assessments
are exploratory, and genuine independent human ratings remain pending.
