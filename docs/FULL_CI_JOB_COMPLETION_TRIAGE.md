# Offline full-CI completion triage (not research-result verification)

GitHub Actions can show a successful pytest transcript while the **job** is subsequently cancelled and the exact-run replay gate is skipped. A passing test transcript does not establish that its source-bound receipt was retained or all sixteen shards passed. Do not mix successes across run IDs, attempts, or commit SHAs.

`scripts/audit_full_ci_job_completion.py` performs offline, read-only triage of a complete GitHub Actions 17-job inventory (16 shards and one replay), cross-checked against the original matching workflow-run response. It enforces a single run ID, attempt, and SHA; rejects duplicate jobs, unexpected job names, inconsistent pagination counts, and malformed statuses; and separates successful, cancelled, failed, pending, and missing shards. For each successful shard it additionally checks that the provider job-step inventory reports successful offline tests, checkout verification, receipt replay and artifact retention. A successful full-set replay job must report successful evidence downloads, staging, sixteen-shard replay and retained replay upload. All **21 unconditional shard steps** and **12 unconditional aggregate-replay steps** must report completed/success—including checkout, pinned runtime, dependency installation/verification, compilation, evidence gates and post-test integrity checks. The single failure-only diagnostic upload is optional and may be skipped in a successful job. A skipped, missing, failed or duplicate mandatory step fails closed despite a successful job conclusion. The job-step inventory must also carry strictly increasing positive integer step numbers, and the required test, receipt, replay and retention gates must appear in the exact declared execution order. Otherwise a superficially green inventory could place evidence retention before the evidence it is supposed to certify. A green job must also contain **no undeclared extra execution steps**: only the reviewed mandatory workflow steps, the shard's known failure-only diagnostic upload, and explicit GitHub-managed setup/post/complete labels are permitted. An unknown extra step fails closed even when every required test and evidence step reports success. For successful shard jobs, the conditional failure-only diagnostic upload must be reported as **completed/skipped**, never as executed; any provider-managed setup/post/complete housekeeping step included in a successful job must be **completed/success**. The same housekeeping requirement applies to the successful aggregate replay. A superficially green job with failed, pending, or skipped provider housekeeping or an executed failure-only diagnostic is rejected as contradictory metadata. These checks do not prove execution authenticity or archive integrity. Cancelled jobs remain classifiable without complete step inventories.

**Evidence boundary:** These are same-provider **job-step conclusions**, not independently verified execution or archive bytes. This tool audits provided metadata only. It never independently authenticates the GitHub API snapshot, the executable workflow definition, or retained test artifacts. Required step names **and order** are intentionally coupled to `tests.yml`: legitimate renames or reordered gates require matching auditor and synthetic-test updates. The ordering and extra-step checks are metadata-consistency safeguards, not independent attestation of which commands actually executed. Provider housekeeping labels are an explicit compatibility allowlist; new legitimate provider labels require a reviewed update rather than an implicit wildcard. A claimed **fully successful** seventeen-job inventory now also requires valid UTC `started_at`/`completed_at` job windows: each successful job must finish no earlier than it starts, and the full-set replay may not start before the last of the sixteen shard jobs has completed. This checks the cross-job dependency ordering implied by `replay-complete-shard-set: needs: unit-tests`, so internally green jobs cannot certify an impossible replay chronology. For a complete-success claim, every mandatory step must additionally have a valid UTC start/end interval wholly inside its parent job's window. Mandatory steps must not overlap or run backwards relative to their declared order. This prevents a green receipt/upload inventory from certifying contradictory step chronology even when its step numbers and job windows look correct. Optional provider housekeeping and skipped failure-only steps are not subject to this extra timestamp check. GitHub timestamps have whole-second resolution; equal-second boundaries are permitted. Missing or malformed times invalidate **only a claim of complete success**; cancelled/incomplete runs can still be triaged without their complete timestamp inventories. This is a same-provider metadata consistency test, **not** evidence that the artifact bytes were retrieved or independently authenticated. The loader also bounds supplied JSON to 2 MiB and 32 container levels. Quote-aware scanning before decoding rejects pathological nesting or malformed container boundaries with a controlled invalid-input verdict without mistaking bracket characters inside quoted job metadata for nesting. A defensive decoder recursion fallback is also treated as invalid input. These resource safeguards do **not** authenticate job metadata. The existing `verify_full_ci_shard_set` source-bound receipt replay remains necessary for independently verified sixteen-shard certification.

Obtain original JSON via [GitHub's jobs API](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run) with sufficient page size and no edits:

```bash
python -m scripts.audit_full_ci_job_completion \
  --jobs-json /path/to/original-run-jobs.json \
  --run-json /path/to/original-workflow-run.json \
  --run-id 45089271290 --run-attempt 1 \
  --commit ada5a719ae9692ef2d69599e8f87bda57b0d7ddf
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
`GET /repos/{owner}/{repo}/actions/runs/{run_id}`, and the original jobs
inventory from `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100`.
The CLI requires both snapshots: it binds the run ID, attempt, tested commit SHA,
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
