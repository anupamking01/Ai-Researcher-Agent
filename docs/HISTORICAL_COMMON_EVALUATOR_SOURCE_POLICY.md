# Original versus recovered common-evaluator source-policy comparison

**Status: retrospective source-only evaluation-validity audit; not a new measurement.**

The first historical workflow ran the treatment matrix and attempted the common post-hoc support evaluator. The September 13 evaluator-only recovery resumed using 37 retained evaluator records and required the three missing identities P6V/main-02, P6V/main-08, P6V/main-10. These are *requirements encoded in the historical recovery workflow*, not independently authenticated original archive contents.

The evaluator-recovery source was modified after the original treatment commit. It is therefore important not to assert that the two executable scripts were byte-identical just because both were described as a "common evaluator."

Run in a full-history checkout without credentials or any model/network calls:

    python -m scripts.audit_historical_common_evaluator_policy

The verifier pins Git ancestry and the exact 22 historical Git blobs for the original/recovery evaluator scripts, their launch workflows, prompt generator and normalizer. It parses historical evaluator source as Python AST **without importing or running it**. It checks shared calls to the same prompt generator, the same model-selection expression, the same 120-second request timeout and the same score normalizer, along with the workflow-declared model gpt-5.6-terra, temperature 1 and 12-claim cap. The historical prompt-generator and normalizer blobs are byte-identical across these two revisions.

It additionally checks the **entire source bytes in both historical revisions** for seven execution/accounting dependencies: the OpenAI chat adapter, provider-usage tracker, environment configuration, evaluator-cost estimator, frozen dated pricing table, and both Python requirements files. Both historical workflows must explicitly install those requirements. The independently pinned Git blobs are compared and SHA-256 fingerprints retained; the requirements source pins `openai==0.27.10`. This closes a source-provenance gap: identical top-level evaluator calls alone did not establish whether their transport, usage recording, temperature configuration, or cost-accounting implementations had drifted. These **source dependencies did not drift** in the pinned historical commits; this does **not** establish which wheels were installed, that the provider served an identical model, that any API call executed as declared, or that historical costs were empirically authenticated.

**Material, explicit difference:** The original evaluator rejected empty retrieved-evidence context. The recovery evaluator added a zero-successful-source sentinel that forbids outside knowledge, while continuing to reject missing saved evidence if the trace claimed successful sources. Thus the **input admissibility policy changed**, even though the prompt/normalization components and evaluator-call shape are shared. Without independently authenticated original traces and reports it is not valid to claim which recovered cells took the sentinel path, that the original 37 measurements were all correctly loaded, or that all 40 ran under an entirely identical executable.

The existing full-history historical-source CI records the audit result with explicit false provenance/validation flags. Failure signals a source-interpretation problem, not an invitation to rerun evaluations or change numerical outcomes.

**Scientific boundary:** The five-task pilot is diagnostic. The frozen ten-task automated analysis has a post-collection statistical-plan qualification, unresolved fixed-order treatment/time-position confounding, and missing original report/trace custody. This retrospective source comparison is exploratory provenance documentation, not a new causal or confirmatory analysis. It cannot authenticate provider model behavior, historic execution, report source integrity, common scoring for every cell, or genuine human validation. The frozen automated inputs, original analysis results and human rubric remain unchanged.

## Retained job-log evidence of dependency resolution (26 November 2026)

A separate read-only check of the retained GitHub Actions job logs provides
stronger evidence than the requirements source alone. Both install steps
completed successfully, but the two logs explicitly report different versions
of an unpinned transitive dependency.

| Job-log record (UTC) | Original treatment + evaluator | Evaluator-only recovery |
| --- | --- | --- |
| Run | [34620917346](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34620917346) | [34783525480](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34783525480) |
| Job log | [103334373932](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34620917346/job/103334373932) | [103794737655](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/34783525480/job/103794737655) |
| Main requirements success line | `2026-09-11T16:15:46.4540456Z` | `2026-09-13T21:21:02.6123201Z` |
| Dev requirements success line | `2026-09-11T16:15:47.3444659Z` | `2026-09-13T21:21:03.8525380Z` |
| Package-version tokens reported across both lines | 107 | 107 |
| Tokens identical across jobs | 106 | 106 |
| OpenAI client token | `openai-0.27.10` | `openai-0.27.10` |
| Search dependency token | `ddgs-9.16.0` | `ddgs-9.16.0` |
| Differing transitive dependency token | `primp-2.0.0` | `primp-2.0.1` |

Both logs report `Collecting primp>=1.3.1 (from ddgs==9.16.0->-r requirements.txt (line 18))`.
The observed version difference is consistent with the same requirement source
resolving an unpinned transitive dependency differently. The source audit's
identical-source finding therefore must not be interpreted as an identical
resolved installation. Both logs also report runner image `ubuntu-24.04`
version `20260907.300.1` and a setup-python cache key containing Python
`3.11.16`; the latter is a cache-key observation, not a separate interpreter
measurement.

For reproducibility, the following is the sorted intersection of the exact
package-version tokens on the two timestamped `Successfully installed` lines
per job, excluding the differing `primp` token. It is a sanitized transcription
of installation summaries, **not a complete package inventory or lockfile**.

```text
Brotli-1.1.0 Flask-3.0.3 Jinja2-3.1.4 Markdown-3.6 MarkupSafe-2.1.5 PySocks-1.7.1 PyYAML-6.0.1 Pygments-2.18.0 SQLAlchemy-2.0.30 Werkzeug-3.0.3 aiofiles-23.2.1 aiohttp-3.9.5 aiosignal-1.3.1 anyio-4.4.0 async-timeout-4.0.3 asyncio-3.4.3 attrs-23.2.0 beautifulsoup4-4.12.2 blinker-1.8.2 certifi-2024.6.2 cffi-1.16.0 charset-normalizer-3.3.2 click-8.1.8 colorama-0.4.6 cssselect2-0.7.0 dataclasses-json-0.5.14 ddgs-9.16.0 dnspython-2.6.1 docopt-0.6.2 email_validator-2.1.1 exceptiongroup-1.2.1 fastapi-0.111.0 fastapi-cli-0.0.4 fonttools-4.53.0 frozenlist-1.4.1 greenlet-2.0.2 h11-0.14.0 h2-4.1.0 hpack-4.0.0 html5lib-1.1 httpcore-1.0.5 httptools-0.6.1 httpx-0.27.0 hyperframe-6.0.1 idna-3.7 iniconfig-2.3.0 itsdangerous-2.2.0 langchain-0.0.263 langsmith-0.0.92 lxml-5.2.2 markdown-it-py-3.0.0 markdown2-2.4.13 marshmallow-3.21.3 md2pdf-1.0.1 mdurl-0.1.2 multidict-6.0.5 mypy-extensions-1.0.0 numexpr-2.10.0 numpy-1.26.4 openai-0.27.10 openapi-schema-pydantic-1.2.4 orjson-3.10.3 outcome-1.3.0.post0 packaging-24.0 pillow-10.3.0 playwright-1.36.0 pluggy-1.6.0 pycparser-2.22 pydantic-1.10.15 pydyf-0.10.0 pyee-9.0.4 pyphen-0.15.0 pyreqwest_impersonate-0.4.7 pytest-8.3.2 python-dotenv-1.0.1 python-multipart-0.0.9 requests-2.32.3 rich-13.7.1 selenium-4.11.2 shellingham-1.5.4 six-1.16.0 sniffio-1.3.1 socksio-1.0.0 sortedcontainers-2.4.0 soupsieve-2.5 starlette-0.37.2 tenacity-8.3.0 tinycss2-1.3.0 tqdm-4.66.4 trio-0.25.1 trio-websocket-0.11.1 typer-0.12.3 typing-inspect-0.9.0 typing_extensions-4.12.2 ujson-5.10.0 urllib3-2.2.1 uvicorn-0.30.1 uvloop-0.19.0 watchfiles-0.22.0 weasyprint-62.2 webdriver-manager-4.0.0 webencodings-0.5.1 websockets-12.0 wsproto-1.2.0 yarl-1.9.4 zopfli-0.2.3
```

To reproduce the comparison if the logs remain available, download the two
job logs through the authenticated GitHub Actions job-log endpoint
(`GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs`) into a private working
directory; do not publish raw logs. Select only physical lines beginning with
the UTC timestamp followed by the literal ` Successfully installed `, split
the remainder on whitespace, require two lines and 107 distinct tokens per
job for these historical records, and compare the resulting sets. The two
set differences must be the single version tokens shown above. These checks
were performed against both retained logs on 26 November. They are not
assertions about all preinstalled packages, wheel hashes, actual imports,
or provider execution.

**Interpretation:** this is an observed installation-summary difference, not
evidence that the change affected any score. The recovery workflow was
evaluator-only and read persisted reports and saved query text; it did not
rerun retrieval or generate replacement treatment reports. The logs do not
establish whether the changed dependency was imported or used by the
evaluator. Do not infer a bias direction or magnitude, exclude recovered
cells, or rerun treatments/evaluators from this observation. The original
37 / recovered 3 split, frozen automated outcomes, and pending human
validation are unchanged. Independently authenticated original source custody
and complete runtime attestation remain open.
