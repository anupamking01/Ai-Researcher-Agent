# Offline full-CI completion triage (not research-result verification)

GitHub Actions can show a successful pytest transcript while the **job** is subsequently cancelled and the exact-run replay gate is skipped. A passing test transcript does not establish that its source-bound receipt was retained or all sixteen shards passed. Do not mix successes across run IDs, attempts, or commit SHAs.

`scripts/audit_full_ci_job_completion.py` performs offline, read-only triage of a complete GitHub Actions 17-job inventory (16 shards and one replay). It enforces a single run ID, attempt, and SHA; rejects duplicate jobs, unexpected job names, inconsistent pagination counts, and malformed statuses; and separates successful, cancelled, failed, pending, and missing shards.

**Evidence boundary:** This tool audits provided metadata only. It never independently authenticates the GitHub API snapshot or verifies retained test artifacts. The existing `verify_full_ci_shard_set` source-bound receipt replay remains necessary for independently verified sixteen-shard certification.

Obtain original JSON via [GitHub's jobs API](https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run) with sufficient page size and no edits:

```bash
python -m scripts.audit_full_ci_job_completion \
  --jobs-json /path/to/original-run-jobs.json \
  --run-id 45089271290 --run-attempt 1 \
  --commit ada5a719ae9692ef2d69599e8f87bda57b0d7ddf
```

Exit code 0 means every shard job and the full replay job report success; 1 means valid metadata but an incomplete/failed job gate; 2 means invalid/inconsistent input. Exit 0 does **not** independently attest to the evidence archive.

The previously inspected [run 45089271290](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45089271290) recorded nine successful shards, seven cancelled shards and a skipped full-set replay. Some cancelled jobs printed passing pytest summaries before cancellation; those are **not** certified shard successes.

The five-task pilot remains diagnostic. Frozen automated results retain post-collection statistical-plan timing, fixed-order and evaluator-policy limitations. Retrospective sensitivity analyses remain exploratory, not prospective confirmation. Independent source authentication of original report/trace files and genuine human validation remain pending. This tool runs no treatments, evaluators, or human ratings.
