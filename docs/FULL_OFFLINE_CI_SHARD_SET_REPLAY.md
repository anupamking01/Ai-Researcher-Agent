# Replaying the complete sixteen-shard offline CI evidence set

The ordinary offline test workflow partitions every discovered test module into **sixteen** deterministic, firewalled pytest shards. Each job separately runs an early dependency-free unittest gate. One passing shard, a successful fast lane, or a green pytest transcript from a subsequently cancelled job does **not** constitute a successful complete suite.

For one *completed successful* GitHub Actions run and attempt, obtain both kinds of retained artifacts for **every** shard, N=0...15:

- `vera-offline-tests-shard-N-<run-id>-<attempt>`: the exact test log, receipt, and module inventory. Extract as `/trusted-download/pytest/shard-N/` with filenames `vera-offline-tests.log`, `vera-offline-test-receipt.json`, and `vera-offline-test-modules.txt`.
- `vera-stdlib-evaluation-shard-N-<run-id>-<attempt>`: the pre-install diagnostic log and receipt. Extract as `/trusted-download/early/shard-N/` with filenames `vera-stdlib-evaluation.log` and `vera-stdlib-evaluation-receipt.json`.

Use a clean checkout of the **exact tested Git SHA**. For pull-request runs, GitHub Actions may test an integration merge SHA instead of the PR branch head; select `--event pull_request` and use the actual tested checkout SHA. Supply run identity from the independent GitHub run metadata, *never* from a downloaded receipt.

```bash
python -m scripts.verify_full_ci_shard_set \
  --evidence-root /trusted-download/pytest \
  --early-evidence-root /trusted-download/early \
  --checkout-sha <tested-40-hex-sha> \
  --run-id <run-id> --run-attempt <attempt> --event push
```

The verifier requires all sixteen three-file pytest shard bundles and all sixteen two-file pre-install bundles for the same SHA, event, run and attempt. It independently recomputes the retained full-test success receipts and module selections, verifies that their union covers each source test module exactly once, and replays every retained pre-install diagnostic transcript and receipt against the tracked early-gate source bytes. Any missing/extra shard, mixed run/attempt, altered receipt/log, unexpected bundle entry, or symlinked evidence path fails closed. Directory inventory scans and evidence reads are bounded, with descriptor-relative no-follow ancestor custody checks. The GitHub replay job performs the same check on the downloaded artifacts and retains the resulting combined receipt.

The `--early-evidence-root` argument is optional for **legacy pytest-only** review; its output explicitly says `preinstall_diagnostics: not_replayed`, and must not be presented as the complete combined offline evidence replay.

**Scope and limitations:** These are source-bound *local consistency* checks, not independent attestation of runner honesty, network isolation, actual test execution, artifact-service custody or experimental provenance. A cancelled workflow remains cancelled even if its pytest transcript says `passed`; all sixteen job conclusions and the aggregate replay must succeed. Neither replay reruns treatments/evaluators nor fabricates human data. The five-task pilot remains diagnostic, designated-primary automated analysis is post-collection with fixed-order and evaluator comparability qualifications, and retrospective sensitivities remain exploratory. The original treatment reports/traces, human distribution, actual blinded ratings, agreement and automated-human reconciliation remain independently unresolved.

## Recover from cancellation without mixing attempts

The artifact download patterns in `tests.yml` include both the run ID and
`GITHUB_RUN_ATTEMPT`. A retry of only failed jobs or a single cancelled shard
does not re-upload successful earlier-attempt shards under the new attempt.
Even if the provider later displays green jobs, a complete same-attempt
artifact set is not established. Do not copy, rename, or rewrite an earlier
attempt's receipts to fill those holes. Use **Re-run all jobs** on the
ordinary offline `tests` workflow when retrying its original tested source,
not **Re-run failed jobs** or a job-only retry. Alternatively obtain a fresh
complete offline workflow for a reviewed source revision. Do not rerun
`budget-main-study`, `evaluator-recovery`, or a live workflow to resolve an
offline CI cancellation. A retry is not a guarantee of success.

Before retrying, retain the original attempt-specific run and jobs metadata
and the run-level artifact inventory. The latter includes artifacts from
multiple attempts if present, so the exact suffix matters:

```bash
repo=anupamking01/Ai-Researcher-Agent
run=45333990076
attempt=1
gh api "repos/$repo/actions/runs/$run/attempts/$attempt" > run.json
gh api "repos/$repo/actions/runs/$run/attempts/$attempt/jobs?per_page=100" > jobs.json
gh api --paginate --slurp "repos/$repo/actions/runs/$run/artifacts?per_page=100" > artifact-pages.json
```

For a complete certification candidate, the inventory must identify one
unexpired artifact for each of the 16 early diagnostic bundles, each of the
16 offline pytest bundles, and the aggregate
`vera-full-shard-replay-<run-id>-<attempt>` bundle, with the exact run/attempt
suffix. Check all pages, duplicate names and expiration flags. Do not count
`vera-unverified-failure-shard-*` as a success bundle, and do not count
artifacts with a different attempt suffix. Record the artifact IDs and retain
the unmodified inventory alongside the metadata triage receipt.
A listed, unexpired artifact is only a download candidate: it is not proof
that its bytes are retrievable, intact, or authenticated. Download and replay
the exact required bundles as described above; if metadata or bytes are
missing, preserve the incomplete classification.

### Observed cancellation checkpoint — 24 November 2026

[PR run 45333990076, attempt 1](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45333990076),
REST workflow head `1b08513929a88027c6f7e2e36e81075e6b5b6b04`,
reported completed/cancelled. Its jobs inventory reported eight successful
shards (1, 3, 6, 9, 10, 12, 14, 15), eight cancelled shards (0, 2, 4, 5,
7, 8, 11, 13), and skipped aggregate replay. The
[run-level artifact inventory](https://api.github.com/repos/anupamking01/Ai-Researcher-Agent/actions/runs/45333990076/artifacts?per_page=100)
reported 31 entries in one page, all unexpired at inspection:

| Exact attempt-1 artifact family | Listed | Missing shard indices |
| --- | ---: | --- |
| Early diagnostics | 16/16 | None |
| Offline pytest evidence | 8/16 | 0, 2, 4, 5, 7, 8, 11, 13 |
| Unverified cancellation diagnostics | 7 | 0 (among cancelled jobs) |
| Aggregate replay | 0/1 | Not applicable |

The offline evidence names align exactly with the eight successful jobs.
All sixteen early artifacts being listed does not establish that their
contents have been independently replayed; no artifact bytes were inspected
for this checkpoint. Seven cancelled shards retained unverified
diagnostics; the absence of shard 0's diagnostic artifact does not imply
that no tests ran. This inventory locates the missing evidence and shows why
a partial job retry cannot establish the existing same-attempt replay
contract. It does not establish the cause of cancellation or certify
the complete suite.

Original research artifact authentication, genuine blinded human evaluation,
and the post-collection and exploratory interpretation boundaries are
unchanged. No treatment or evaluator was rerun for this checkpoint.
