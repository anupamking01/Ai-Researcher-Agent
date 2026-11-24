# Offline full-CI completion triage (not research-result verification)

GitHub Actions can show a successful pytest transcript while the **job** is subsequently cancelled and the exact-run replay gate is skipped. A passing test transcript does not establish that its source-bound receipt was retained or all sixteen shards passed. Do not mix successes across run IDs, attempts, or commit SHAs.

`scripts/audit_full_ci_job_completion.py` performs offline, read-only triage of a complete GitHub Actions 17-job inventory (16 shards and one replay), cross-checked against the original matching workflow-run response. It enforces a single run ID, attempt, and SHA; rejects duplicate jobs, unexpected job names, inconsistent pagination counts, and malformed statuses; and separates successful, cancelled, failed, pending, and missing shards. For each successful shard it additionally checks that the provider job-step inventory reports successful offline tests, checkout verification, receipt replay and artifact retention. A successful full-set replay job must report successful evidence downloads, staging, sixteen-shard replay and retained replay upload. All **21 unconditional shard steps** and **12 unconditional aggregate-replay steps** must report completed/success—including checkout, pinned runtime, dependency installation/verification, compilation, evidence gates and post-test integrity checks. The single failure-only diagnostic upload is optional and may be skipped in a successful job. A skipped, missing, failed or duplicate mandatory step fails closed despite a successful job conclusion. The job-step inventory must also carry strictly increasing positive integer step numbers, and the required test, receipt, replay and retention gates must appear in the exact declared execution order. Otherwise a superficially green inventory could place evidence retention before the evidence it is supposed to certify. A green job must also contain **no undeclared extra execution steps**: only the reviewed mandatory workflow steps, the shard's known failure-only diagnostic upload, and explicit GitHub-managed setup/post/complete labels are permitted. An unknown extra step fails closed even when every required test and evidence step reports success. For successful shard jobs, the conditional failure-only diagnostic upload must be reported as **completed/skipped**, never as executed; any provider-managed setup/post/complete housekeeping step included in a successful job must be **completed/success**. The same housekeeping requirement applies to the successful aggregate replay. A superficially green job with failed, pending, or skipped provider housekeeping or an executed failure-only diagnostic is rejected as contradictory metadata. These checks do not prove execution authenticity or archive integrity. Cancelled jobs remain classifiable without complete step inventories.

**Evidence boundary:** These are same-provider **job-step conclusions**, not independently verified execution or archive bytes. This tool audits provided metadata only. It never independently authenticates the GitHub API snapshot, the executable workflow definition, or retained test artifacts. Required step names **and order** are intentionally coupled to `tests.yml`: legitimate renames or reordered gates require matching auditor and synthetic-test updates. The ordering and extra-step checks are metadata-consistency safeguards, not independent attestation of which commands actually executed. Provider housekeeping labels are an explicit compatibility allowlist; new legitimate provider labels require a reviewed update rather than an implicit wildcard. A claimed **fully successful** seventeen-job inventory now also requires valid UTC `started_at`/`completed_at` job windows: each successful job must finish no earlier than it starts, and the full-set replay may not start before the last of the sixteen shard jobs has completed. This checks the cross-job dependency ordering implied by `replay-complete-shard-set: needs: unit-tests`, so internally green jobs cannot certify an impossible replay chronology. Every successful job, including a green shard in an otherwise incomplete run, must have a valid UTC job window and every mandatory step must have a valid UTC start/end interval wholly inside that window. Mandatory steps must not overlap or run backwards relative to their declared order. This prevents a green receipt/upload inventory from certifying contradictory step chronology even when its step numbers and job windows look correct. Optional provider housekeeping and skipped failure-only steps are not subject to this extra timestamp check. GitHub timestamps have whole-second resolution; equal-second boundaries are permitted. Missing or malformed times invalidate any reported successful job; cancelled, failed, skipped or pending jobs can still be triaged without their own complete timestamp inventories. This is a same-provider metadata consistency test, **not** evidence that the artifact bytes were retrieved or independently authenticated. The loader also bounds supplied JSON to 2 MiB and 32 container levels. Quote-aware scanning before decoding rejects pathological nesting or malformed container boundaries with a controlled invalid-input verdict without mistaking bracket characters inside quoted job metadata for nesting. A defensive decoder recursion fallback is also treated as invalid input. These resource safeguards do **not** authenticate job metadata. The existing `verify_full_ci_shard_set` source-bound receipt replay remains necessary for independently verified sixteen-shard certification.

Obtain original JSON via [GitHub's jobs API](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run) with sufficient page size and no edits:

```bash
python -m scripts.audit_full_ci_job_completion \
  --jobs-json /path/to/original-run-jobs.json \
  --run-json /path/to/original-workflow-run.json \
  --run-id 45089271290 --run-attempt 1 \
  --head-sha ada5a719ae9692ef2d69599e8f87bda57b0d7ddf
```

Exit code 0 requires all seventeen jobs and the matching `tests.yml` workflow to report success; 1 means valid but incomplete/cancelled/failed metadata; 2 means invalid or contradictory input. Exit 0 does **not** independently attest to the evidence archive.

The previously inspected [run 45089271290](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45089271290) recorded nine successful shards, seven cancelled shards and a skipped full-set replay. Some cancelled jobs printed passing pytest summaries before cancellation; those are **not** certified shard successes.

The five-task pilot remains diagnostic. Frozen automated results retain post-collection statistical-plan timing, fixed-order and evaluator-policy limitations. Retrospective sensitivity analyses remain exploratory, not prospective confirmation. Independent source authentication of original report/trace files and genuine human validation remain pending. This tool runs no treatments, evaluators, or human ratings.

## Source-bound fast CI for this metadata auditor

The `full-ci-job-completion-fast-ci` workflow runs the synthetic auditor
regression module plus a separate workflow-contract test in a short, firewalled,
exact-commit GitHub Actions lane. It is triggered by changes to the auditor,
its tests, the workflow under audit, or its source/evidence dependencies.
It checks that the full ordered mandatory-step inventory exactly matches the actual
sixteen-shard workflow and that critical test, replay and artifact-upload
steps still point to their expected implementations. The lane retains a
source-bound test transcript and independently replayed receipt for 90 days.

**Scope limitation:** A green fast lane certifies the *auditor's synthetic
regressions and current source contract*, not completion of the sixteen-shard
workflow, authenticity of the supplied job metadata, verification of actual
retained shard evidence, authentication of original experiment artifacts,
prospective confirmation, or human evaluation. A cancelled full suite remains
uncertified, even when this fast lane passes.

## Cross-endpoint workflow-run completion gate

The GitHub jobs endpoint omits the **overall workflow conclusion**. Obtain
the original run JSON from
`GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}`, and the original jobs
inventory from `GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}/jobs?per_page=100`.
Use attempt-specific endpoints rather than latest-attempt responses when preserving historical evidence.
The CLI requires both snapshots: it binds the run ID, attempt, REST workflow head SHA,
workflow name, exact `tests.yml` path, event, status and conclusion. A
cancelled or unfinished run cannot be certified even if a synthetic jobs
snapshot reports all green. A green workflow envelope contradicting incomplete
jobs fails closed rather than claiming completion.

The original `full_job_gate_completed` field remains the **job-only** check;
the new `full_workflow_job_gate_completed` also requires a completed,
successful workflow-run verdict and determines the CLI exit code. This is a
two-endpoint **metadata-consistency** safeguard, not independent source
authentication or retained-artifact verification. Frozen automated results,
the diagnostic pilot, exploratory sensitivities and pending human validation
are unchanged; no treatments, evaluators or ratings are rerun.


## Exact input snapshot fingerprints

For both complete-success (exit 0) and valid incomplete (exit 1) CLI
receipts, `jobs_json_sha256` and `run_json_sha256` identify the **exact raw
bytes parsed by this invocation** for the jobs inventory and matching
workflow-run envelope, respectively. Preserve both original JSON files
alongside the receipt. Even whitespace-only changes produce a different
fingerprint; JSON is not reserialized or reopened for hashing. The existing
in-memory audit functions do not claim raw-file fingerprints.

A later reviewer can compare the two files' SHA-256 digests to the receipt
and replay the same command. These fingerprints identify captured bytes;
they neither authenticate the GitHub source nor prove that the files still
contain those bytes after the read. They do not certify independently
retained CI artifacts or any experimental or human-evaluation outcome.
Invalid input still produces no success or incomplete receipt.


## Cross-endpoint repository identity

Use the unmodified REST responses, not a reduced connector job list. Every job
(including cancelled jobs) must identify the `tests` workflow and the same
canonical GitHub API `run_url` ending in the requested run ID. Job run IDs and
attempts must be JSON integers, not numeric lookalikes. The run envelope's
`repository.full_name` and `url` must independently agree with the job
inventory URL, and the in-memory job audit must match the requested commit,
run and attempt. The receipt records `jobs_run_url` for both complete and
incomplete classifications. Mixed or missing source identities fail closed.

This catches contradictory source labels, not forged but internally consistent
metadata. It does not authenticate the repository's provider response, prove
artifact custody, or change any frozen scientific outcome. The original
17-job inventory for [run 45289666532](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45289666532)
contains the matching source labels for all jobs (five successful shards,
eleven cancelled, replay skipped); it remains uncertified.


## Malformed metadata field handling

The CLI treats non-string job/workflow status, non-string non-null conclusions,
and non-string workflow events as invalid input (exit 2), including JSON arrays,
objects, numbers and booleans. Missing conclusion keys are not interchangeable
with explicit JSON nulls for pending jobs or workflows. The shard names must use
the exact canonical decimal labels from the declared matrix (0 through 15,
without leading zeros); aliases such as `unit-tests (00)` are invalid rather than
being converted into an index that later fails during replay chronology checks.
Malformed input produces a controlled diagnostic and no receipt, not an
uncaught exception or a valid incomplete classification. These are offline
schema checks, not evidence that the provider snapshot is authentic.


## Distinguish unsettled snapshots from terminal incomplete runs

The receipt's `pending_shards` field lists observed unfinished shard jobs
(explicit null conclusion); `other_incomplete_shards` lists terminal
skipped/neutral shards, not pending jobs. A completed workflow envelope
paired with any unfinished observed shard or replay job is inconsistent and
returns exit 2 without a receipt. Re-capture both original attempt-specific
API responses; do not edit an old snapshot to make its status agree.
Missing shard jobs remain distinguishable from observed unfinished jobs:
an incomplete cancelled attempt can legitimately lack scheduled jobs.
An in-progress workflow with pending jobs remains valid incomplete triage.

The attempt-specific endpoints for [run 45305773051](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45305773051)
reported a completed/cancelled workflow, three successful shards, thirteen
cancelled shards and skipped replay, with no unfinished observed jobs. This
is terminal incomplete metadata, not a full-suite certificate. No cause of
cancellation or authenticity of the retained artifacts follows from these
status fields.


## Workflow head identity is not the tested checkout identity

For a pull-request workflow the REST run/job `head_sha` can identify the PR
branch head even though the runner tests an integration merge commit.
Use `--head-sha` with the original REST `head_sha` for this metadata auditor;
`--commit` remains a legacy alias with identical semantics. Supply only one.
The receipt explicitly records `workflow_head_sha` (the legacy `commit` field
has the same value), `workflow_event`, and
`tested_checkout_sha_verified_by_this_tool: false`. Even exit 0 does not
certify the tested checkout SHA.

For example, the original attempt-1 jobs inventory for
[run 45313095875](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45313095875)
reports PR head `e3eebfe83afa86039812f7a1aff020019055ee8a`. The retained
[shard 12 job log](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45313095875/job/138173345771)
instead reports the merge checkout `03a2a47136a3b0cadda5e0bb50c75966b9606138`
in both the early diagnostic and full-suite transcript. These are distinct
provider-reported identities, not an independently verified source checkout.
That run had seven successful shards, nine cancelled shards, and skipped replay;
it remains uncertified.

Do not pass the REST head SHA automatically to the independent artifact
replayer. Obtain the actual tested checkout identity from independently
retained run/checkout evidence, then follow
[FULL_OFFLINE_CI_SHARD_SET_REPLAY.md](FULL_OFFLINE_CI_SHARD_SET_REPLAY.md).
The metadata auditor does not substitute a current PR merge SHA for a
historical tested commit, infer a checkout from a branch name, or authenticate
the actual source tree or archive. No scientific outcomes are changed.


## Aggregate replay dependency consistency

The `replay-complete-shard-set` job declares `needs: unit-tests` with no
status override. A reported successful aggregate replay is therefore
inconsistent with any missing, unfinished, cancelled or otherwise unsuccessful
shard in the exact-attempt job inventory. Such a snapshot is invalid (exit 2,
no receipt), not valid incomplete triage that can advertise a successful replay.
Re-capture the original attempt-specific job inventory; never combine attempts
or edit job conclusions. Skipped, cancelled or pending aggregate replay remains
triageable as incomplete under the existing snapshot consistency checks.

For comparison, [run 45320219010](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45320219010)
reported eight successful shards, eight cancelled shards and skipped aggregate
replay. Its [shard 6 log](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45320219010/job/138196686038)
printed 364 passing tests before reporting operation cancellation; this is not a
successful shard or proof of the cancellation cause. The metadata dependency
check neither authenticates the provider response nor verifies retained bytes,
scientific provenance, or human validation.


## Cancellation progress, not cancellation cause

For cancelled shards only, the receipt now includes
`cancelled_shard_progress`, sorted by shard index. It reports the last
contiguous mandatory step marked completed/success, the first mandatory step
without that confirmation and its reported conclusion (null if absent or not
settled), and the list of mandatory steps explicitly marked cancelled.
Cleanup and failure-only diagnostic uploads do not advance the mandatory
progress boundary. A missing, malformed or out-of-order step inventory yields
`step_inventory_usable: false` with no progress claim; the job remains
cancelled. A gap in a partial inventory is never bridged by later green steps.
Even when all mandatory steps are reported successful, a cancelled job cannot
count toward full-suite certification.

This is an operational triage aid to locate missing evidence and prioritize
log inspection; neither a first unconfirmed step nor a reported cancelled
step identifies the cancellation cause or independently establishes artifact
retention. For example, [run 45327092483](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45327092483)
reported six successful shards, ten cancelled shards and skipped replay.
Nine cancelled shard inventories explicitly marked `Run offline unit tests`
cancelled; shard 0 last reported success at `Verify installed CI dependencies
before tests`, with no explicit cancelled mandatory step. These observations
are not proof that pytest or dependency installation caused the cancellations.
No scientific outcomes, original evidence authentication, or human-validation
claims change.


## Consistent chronology for successful shards in incomplete attempts — 24 November 2026

A partial-run receipt reports individual successful shards even when the
aggregate replay is skipped. Previously their job and mandatory-step time
windows were only checked if all seventeen jobs succeeded. This allowed a
contradictory green shard to enter an otherwise valid incomplete receipt.
Apply the same successful-job chronology checks to every green shard,
while keeping unsuccessful jobs triageable without timestamps. The
cross-job replay dependency check still applies to full success only.
Six synthetic regressions cover invalid job/step timestamps and the CLI
no-receipt behavior. All six successful shards in attempt 1 of
[run 45341180408](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45341180408)
had consistent mandatory-step timestamps in the attempt-specific REST
metadata at inspection. Ten shards were cancelled and replay was skipped;
this is not full-suite certification or independent evidence authentication.
No treatments, evaluators, frozen outcomes or human ratings are changed.


## Nonregular metadata snapshot inputs — 24 November 2026

Both JSON inputs must be regular files, not directories, symlink leaves or
named pipes. A byte limit alone does not bound a blocking FIFO open. The
auditor now checks the pathname with lstat, opens nonblocking where supported
(and without following a leaf symlink where supported), and verifies the
opened descriptor's regular-file type and device/inode against the preflight
identity before reading. Eight synthetic cases cover both input roles and
replacement between preflight and open. An invalid input produces exit 2
and no receipt. Use saved regular JSON files rather than process substitution
or pipes. This is a local input safety check, not an atomic filesystem
snapshot, a guarantee against concurrent in-place edits, or independent
source authentication. The same parsed bytes remain SHA-256 fingerprinted.
No scientific outcomes or human-validation claims are changed.


## Optional exact-attempt artifact inventory gate — 24 November 2026

Job-step success does not establish that its retained evidence is still
listed. Preserve the complete run-wide response from
`GET /repos/{owner}/{repo}/actions/runs/{run_id}/artifacts?per_page=100`
(with all pages, if necessary), and pass it as `--artifacts-json` alongside
the original attempt-specific jobs and run JSON. The auditor binds its raw
bytes as `artifacts_json_sha256`, checks inventory cardinality, unique IDs,
run/repository/head identity and exact expected artifact names. Names from
earlier attempts and unrelated artifacts cannot fill a current-attempt slot.
Duplicate exact-attempt names and malformed metadata fail closed (exit 2).

The receipt separates listed-unexpired, listed-expired and missing entries
for early diagnostics, offline tests, unverified failure diagnostics and the
aggregate replay. Optional failure diagnostics never substitute for success
evidence. With the extra input, exit 0 additionally requires all 16 early,
16 offline and one aggregate artifact to be listed unexpired; otherwise a
valid but incomplete inventory yields exit 1 even when the separate job gate
is green. Without it the existing job-only exit contract is unchanged.
The endpoint is run-wide: attempt association is inferred from the exact
workflow naming convention, not independently attested by artifact metadata.
Listed-unexpired is a snapshot property, not proof of downloadability,
archive integrity, actual runner checkout or replay. Use the separate
full-set evidence replayer for byte-level verification.

For [run 45357047893](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45357047893),
attempt 1, the 31 listed artifacts comprised 16 early diagnostics, four
offline-test bundles, eleven unverified failure diagnostics and no aggregate
replay. All were reported unexpired. The four offline bundles corresponded
to successful shards 4, 6, 11 and 15; cancelled shard 0 had no listed failure
diagnostic. This is an inventory observation, not certification or proof of
cancellation cause. No treatments, evaluators, frozen results or human ratings
are changed.
