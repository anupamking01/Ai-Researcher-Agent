# Original versus recovered common-evaluator source-policy comparison

**Status: retrospective source-only evaluation-validity audit; not a new measurement.**

The first historical workflow ran the treatment matrix and attempted the common post-hoc support evaluator. The September 13 evaluator-only recovery resumed using 37 retained evaluator records and required the three missing identities P6V/main-02, P6V/main-08, P6V/main-10. These are *requirements encoded in the historical recovery workflow*, not independently authenticated original archive contents.

The evaluator-recovery source was modified after the original treatment commit. It is therefore important not to assert that the two executable scripts were byte-identical just because both were described as a "common evaluator."

Run in a full-history checkout without credentials or any model/network calls:

    python -m scripts.audit_historical_common_evaluator_policy

The verifier pins Git ancestry and the exact 30 historical Git blobs for the original/recovery evaluator scripts, their launch workflows, prompt generator and normalizer. It parses historical evaluator source as Python AST **without importing or running it**. It checks shared calls to the same prompt generator, the same model-selection expression, the same 120-second request timeout and the same score normalizer, along with the workflow-declared model gpt-5.6-terra, temperature 1 and 12-claim cap. The historical prompt-generator and normalizer blobs are byte-identical across these two revisions.

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


## Scope of the dependency difference and runner evidence (26 November 2026)

The retained job logs also explicitly report successful CPython setup, rather
than only a Python version embedded in a cache key. Both jobs restored the
same pip cache key and downloaded identical revisions of their three shared
Actions. These observations narrow the known environment differences without
establishing complete runtime identity.

| GitHub log observation | Original job | Recovery job |
| --- | --- | --- |
| Successfully set up CPython | 3.11.16 at 16:15:20.9817666Z (Sep 11) | 3.11.16 at 21:20:38.5843900Z (Sep 13) |
| Runner version | 2.337.0 | 2.337.0 |
| checkout@v4 | `11d5960a326750d5838078e36cf38b85af677262` | same |
| setup-python@v5 | `a26af69be951a213d495a4c3e4e4022e16d87065` | same |
| upload-artifact@v4 | `ea165f8d65b6e75b540449e92b4886f43607fa02` | same |
| download-artifact@v4 | not listed | `d3f86a106a0bac45b974a628896c90dbdf5c8093` |

The cache-restore key in both logs is
`setup-python-Linux-x64-24.04-Ubuntu-python-3.11.16-pip-189282c64ba415190431b8679a96d5304c37404f106891c01c5ba6ea3c75167d`.
The observed primp version difference despite that matching key demonstrates
why a pip download cache hit must not be interpreted as a locked installation.

The source audit now additionally pins four previously uninspected local
package initialization/support files (agent, logic and settings initializers,
and settings/singleton.py) at both historical revisions, and verifies that
scripts had no package initializer. It extracts all explicit Python import
declarations, including imports nested inside functions, from the evaluator
and the ten first-party files reached by its declared imports. Both revisions
have the same inventory: the directly declared external modules are
`openai`, `colorama` and `dotenv`. Neither `ddgs` nor `primp` appears in that
inspected first-party import inventory. The historical retrieval module
`scrape/web_search.py` (blob
`77a96cd160fdd031f22470f2fba01218fa66168d` at both revisions) instead declares
`from ddgs import DDGS`; it is not imported by the inspected evaluator files.

Reproduce the static inventory using the existing offline command above;
inspect the receipt field `historical_explicit_first_party_import_modules`.
This is deliberately not a dependency resolver or runtime import tracer:
third-party internals, runtime import hooks, actual library calls and provider
execution remain unauthenticated. The drift is therefore a documented
installation-level difference associated with the search dependency, not
evidence of a changed evaluator code path or effect on scores. No treatment
or evaluator rerun is warranted; the frozen automated results and pending
human validation remain unchanged.

## Historical raw-response schema and claim-label auditability (27 November 2026)

The historical prompt and normalizer had different enforcement boundaries.
The [original prompt source](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/logic/prompts.py)
requests integer counts summing to the declared checked-claim count, at most
12 selected important claims (as invoked by the common evaluator), and at most
eight illustrative examples. The byte-identical historical
[normalizer](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/logic/experiment.py)
(blob `c98916c4a0aa17a94c38dd981489693bec5b87a7`) instead uses ordinary
`json.loads`, converts each label count with `int(data.get(label, 0))`,
clamps negatives to zero, and recomputes the denominator from the four
normalized counts. Both the [original caller](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/scripts/evaluate_posthoc_support.py)
and [recovery caller](https://github.com/anupamking01/Ai-Researcher-Agent/blob/8733ce492abc74e7b2966ed22ce08d3fddec43ca/scripts/evaluate_posthoc_support.py)
check that the resulting denominator is positive, but do not enforce the
12-claim upper bound on that raw-response path.

The following **synthetic examples, not historical responses**, show why a
valid retained count partition does not establish that the raw model
response satisfied the prompt. Start with a valid one-claim supported
response: all other label counts are zero, claims_checked is 1 and examples
is an empty list. Apply each mutation separately.

| Raw-response mutation | Historical normalized checked / supported |
| --- | --- |
| None (control) | 1 / 1 |
| Declare claims_checked = 9 | 1 / 1 |
| Set unsupported = -1 | 1 / 1 |
| Omit unsupported | 1 / 1 |
| Set supported = 1.9 | 1 / 1 |
| Set supported = true | 1 / 1 |
| Duplicate supported, first 0 then 1 | 1 / 1 |
| Set both claims_checked and supported = 13 | 13 / 13 |

Reproduce offline from a full-history checkout by extracting only the
historical normalizer function (not importing historical modules or calling
a model):

```python
import ast, json, subprocess
from typing import Any

rev = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
src = subprocess.check_output(["git", "show", rev + ":logic/experiment.py"])
node, = [n for n in ast.parse(src).body
         if isinstance(n, ast.FunctionDef)
         and n.name == "normalize_verifier_output"]
scope = {"json": json, "Any": Any}
exec(compile(ast.Module(body=[node], type_ignores=[]), "<historical>", "exec"), scope)
normalizer = scope["normalize_verifier_output"]
base = dict(claims_checked=1, supported=1, partially_supported=0,
            unsupported=0, contradicted=0, examples=[])
cases = [json.dumps(base),
         json.dumps(base | {"claims_checked": 9}),
         json.dumps(base | {"unsupported": -1}),
         json.dumps({k: v for k, v in base.items() if k != "unsupported"}),
         json.dumps(base | {"supported": 1.9}),
         json.dumps(base | {"supported": True}),
         json.dumps(base).replace('"supported": 1',
                                  '"supported": 0, "supported": 1'),
         json.dumps(base | {"claims_checked": 13, "supported": 13})]
for raw, expected in zip(cases, [1]*7 + [13]):
    result = normalizer(raw)
    assert (result["claims_checked"], result["supported"]) == (expected, expected)
```

The [current stricter normalizer](https://github.com/anupamking01/Ai-Researcher-Agent/blob/487840cf2cbccdcde3acba695a15b49f06d449b5/logic/experiment.py)
rejects the seven malformed cases when called with max_claims=12; it does
not retroactively validate the original raw model responses. The
[retained CSV numeric audit](MAIN_STUDY_NUMERIC_INPUT_INTEGRITY.md) separately
checks the published normalized partitions and cap. This is useful arithmetic
and metadata validation, not raw-response validation.

Both historical per-cell JSON writers save normalized counts and up to eight
examples, not the raw response string. Even if those JSON records are recovered,
the examples are illustrative, not a complete claim-level verdict ledger:
a 12-claim record can contain at most eight examples. Neither a matching
archive digest nor a consistent summary establishes raw-response schema
compliance, complete claim segmentation, or per-claim label accuracy.
If independent original raw responses are recovered, retain their bytes
separately and assess schema compliance without replacing the historical
scores; otherwise report raw-response compliance as unknown. Do not infer
that any of the synthetic mutations occurred, or their frequency, direction
of bias, or treatment-specific effect.

This is a retrospective source-policy qualification only. No pilot or
frozen automated outcome is changed; the designated-primary analysis
remains post-collection and qualified, retrospective diagnostics remain
exploratory, and genuine human validation remains pending.

## Requested model versus returned model identity (27 November 2026)

The historical source contract makes a narrower distinction than the field
names alone suggest. In both pinned revisions, the [chat adapter](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/agent/llm_utils.py)
(blob `bbc8daec4ae972f26851195dc59dd0ca1966d865`) passes the **requested**
model argument to both `openai.ChatCompletion.create` and
`usage_tracker.record_response(model, response)`. The byte-identical
[usage tracker](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/logic/usage.py)
(blob `336b7d96967395d368a962a751001f34b4fb8091`) extracts token counters
from the response's usage object but indexes its ledger by the argument
`model`, not by any model identifier in the response.

Both the original and recovery evaluator record writers set
`evaluator_model` from `SMART_LLM_MODEL` and
`provider_usage_by_model` from that tracker. Their shared
[historical cost estimator](https://github.com/anupamking01/Ai-Researcher-Agent/blob/c3c15e46a8eec3a8bbc24c968eedc0548172a897/scripts/summarize_pilot.py)
(blob `08413f9d9ab7748cfed78c30ec1c189610c7fd14`) looks up the frozen
pricing rate by the ledger key. Thus:

| Recorded quantity | What the historical source establishes |
| --- | --- |
| `evaluator_model` | Configured/requested identifier |
| Keys of `provider_usage_by_model` | Requested identifiers associated with reported token counters |
| `estimated_cost_usd` | Estimate at the frozen rates for those ledger keys; not invoiced cost |
| Response model, completion ID, backend fingerprint (if supplied) | Not retained by this adapter/tracker or either historical evaluator record writer |

A matching model name and a nonmissing usage ledger therefore do not
independently demonstrate that both historical jobs received responses
from the same resolved model snapshot or backend. A different returned
model string would not itself prove that a different model served the
request (aliases can resolve to dated identifiers), but the historical
ledger does not even preserve that distinction for later inspection.

### Offline demonstration

The following reproduction loads only the byte-pinned historical usage
module, which uses standard-library imports. All responses and counters
below are **synthetic**, not observations of provider behavior. No provider
call or treatment/evaluator execution is involved.

```python
import hashlib
import subprocess

rev = "c3c15e46a8eec3a8bbc24c968eedc0548172a897"
src = subprocess.check_output(["git", "show", rev + ":logic/usage.py"])
header = f"blob {len(src)}\0".encode()
assert hashlib.sha1(header + src).hexdigest() == (
    "336b7d96967395d368a962a751001f34b4fb8091"
)
scope = {}
exec(compile(src, "<historical usage>", "exec"), scope)
requested = "gpt-5.6-terra"
usage = dict(prompt_tokens=100, completion_tokens=20, total_tokens=120)
metadata = [
    dict(model=requested, id="synthetic-a", system_fingerprint="synthetic-fp-a"),
    dict(model="synthetic-other-model", id="synthetic-b",
         system_fingerprint="synthetic-fp-b"),
    {},
]
snapshots = []
for meta in metadata:
    tracker = scope["UsageTracker"]()
    tracker.record_response(requested, {"usage": usage, **meta})
    snap = tracker.snapshot()
    assert set(snap["by_model"]) == {requested}
    assert snap["unavailable_calls"] == 0 and snap["total_tokens"] == 120
    snapshots.append(snap)
assert snapshots[0] == snapshots[1] == snapshots[2]
```

All three cases produce identical snapshots (one model call, zero
unavailable calls, 120 total tokens under the requested identifier).
This was reproduced offline against a local copy whose Git blob hash
matched the historical source. It demonstrates information loss in
the recording contract, not any actual model substitution or cost error.

For a separately authorized future study, retain per-call requested and
returned identifiers and provider completion ID/backend fingerprint when
available, under the applicable private evidence-retention policy. Record
absent metadata as unknown; preserve raw envelopes independently when
permitted. Do not assume a provider identifier alone authenticates model
weights. If historical provider records are independently recovered,
reconcile them without changing the frozen estimates or selecting cells
by outcome. Until then, resolved-model continuity and actual billing
remain unverified. The diagnostic pilot, qualified post-collection
automated primary analysis, exploratory sensitivity analyses, and pending
human validation remain distinct. No new measurement or rerun is warranted
by this finding.


## Prospective raw evaluator text retention (27 November 2026)

The historical absence of raw model text is irreversible from normalized
counts alone. Newly produced **explicitly noncanonical** evaluator cache
records now retain a `raw_response` object containing the exact returned
text (including surrounding whitespace and any code fences), its UTF-8 byte
length, and SHA-256. This is the text returned by the adapter, not a raw HTTP
response, provider execution identity, billing receipt, or signed timestamp.
The text is bounded to 1 MiB of UTF-8. The existing strict normalizer and
positive-denominator/evidence-only checks still govern publication; a
malformed response does not become a valid measurement.

When a cache includes this object, the offline replay preflight verifies
its fingerprint, re-normalizes the retained text under the current frozen
claim cap and compares all normalized counts and examples against the stored
measurement. The existing schema-2 input-fingerprint contract remains
compatible with older caches. **Absence of this optional extension is not
evidence of raw-response compliance**; the verifier cannot establish that
an older record ever retained this text or that a new cache was not rewritten
coherently before capture. Keep raw evaluator records coordinator-only;
they may contain report or source excerpts and must not enter annotator
bundles. The aggregate CSV continues to contain only the existing selected
fields.

This prospective safeguard does not recover the historical raw responses,
validate individual classification accuracy, or justify a treatment or
evaluator rerun. No historical measurements, frozen plans, or human ratings
are changed. The pilot remains diagnostic, the frozen automated analysis
qualified, retrospective diagnostics exploratory, and human validation
pending.
