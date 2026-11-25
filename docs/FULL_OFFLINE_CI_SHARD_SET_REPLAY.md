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

## Compare the retained aggregate receipt to independent replay

The aggregate archive is a separate evidence object, not one of the 32
per-shard bundles. Download its exact artifact ID, preserve its archive
bytes, and stage its single `vera-full-shard-replay.json` member separately.
A matching archive checksum does not establish that the aggregate JSON
agrees with the independently replayed shard evidence.

For a tested checkout containing the aggregate-comparison option, add
`--retained-aggregate-receipt /trusted-download/aggregate/vera-full-shard-replay.json`
to the full replay command above. Supply the early-evidence root as well.
The verifier compares the bounded, regular-file receipt bytes to the exact
canonical JSON it independently recomputes from all 32 bundles; an altered
count, run identity, digest, duplicate key, or even changed serialization
fails before a successful replay is printed. It does not read identity from
the aggregate receipt or change the existing workflow's output format.

For older tested checkouts lacking this flag, run the original verifier
with both roots and redirect its stdout to a **new** local file; after
successful exit compare that file to the retained aggregate using
`cmp -- recomputed.json /trusted-download/aggregate/vera-full-shard-replay.json`.
Do not replace or normalize the retained file to make it match. Use the
actual tested checkout, not a newer branch merely to obtain the new flag.

A matching aggregate establishes only local cross-artifact consistency,
not provider authenticity, job completion, or actual execution. A missing
aggregate cannot be manufactured from the per-shard replay to certify a
cancelled run. The independent metadata, artifact inventory, checksum and
scientific-evidence gates remain distinct.


## Complete same-attempt CI evidence checkpoint — 25 November 2026

After the bounded pytest parameter-ID correction in branch commit
`74b75bb5e7be9c54054dc7384a5d38ce5b80416d`, the
[full offline PR run 45526533438, attempt 1](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45526533438)
reported completed/success, including all sixteen shard jobs and the aggregate
replay job. The [attempt-specific run response](https://api.github.com/repos/anupamking01/Ai-Researcher-Agent/actions/runs/45526533438/attempts/1)
and [17-job inventory](https://api.github.com/repos/anupamking01/Ai-Researcher-Agent/actions/runs/45526533438/attempts/1/jobs?per_page=100)
reported the same branch head and attempt. The tested integration checkout
reported by the [aggregate job log](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45526533438/job/138912610559)
was `ee1e1d54ac5102f441f9641eab070d9e9233cac5`, not the REST branch head. Its
Git commit parents are the then-current main head
`f66768b4af38664eb4cc373b7d7161d8b5b8de69` and the branch head above.

The aggregate job log printed status
`complete_sixteen_shard_local_replay_consistent_not_independently_attested`:
8475 passing pytest cases, 4 warnings,
264 source test modules, sixteen replayed pytest shards,
and sixteen replayed pre-install diagnostics. Summing the log's per-shard
counts reproduces the reported pytest and module totals. These are reported
software-test counts, not experimental sample sizes. The independently
scheduled [runner-provenance PR run 45526533380, attempt 1](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45526533380)
also completed successfully: its [job log](https://github.com/anupamking01/Ai-Researcher-Agent/actions/runs/45526533380/job/138911183437)
reports pytest 8.3.2, 594 passing tests, and all four bounded-ID
oversized-report regression cases passing. This confirms the fix under the
pinned pytest version and is consistent with the earlier cancellation
hypothesis; it does not retrospectively prove the cause of any interrupted
run.

### Retrieval ledger for the complete attempt

The [run-level artifact response](https://api.github.com/repos/anupamking01/Ai-Researcher-Agent/actions/runs/45526533438/artifacts?per_page=100)
listed exactly 33 distinct unexpired artifacts at inspection, with a unique
ID and provider-declared SHA-256 for each expected name. All names have
the same run/attempt suffix. Preserve these exact archive IDs and compare
downloaded bytes against the listed digests before replay. This table is a
derived retrieval index, not an original REST snapshot or an independent
checksum receipt.

| Artifact name | Artifact ID | Provider-declared SHA-256 |
| --- | ---: | --- |
| `vera-stdlib-evaluation-shard-0-45526533438-1` | 14982014524 | `21f177ed7c432b56f360b3c751fca05b5d482f02ee4ee4ec028c6f1d724b4390` |
| `vera-stdlib-evaluation-shard-1-45526533438-1` | 14982811313 | `adcb0a452663a9d7458a36e804721ef0d0d4d7cb2ad0fc13dcf44c284a58c50a` |
| `vera-stdlib-evaluation-shard-2-45526533438-1` | 14983225868 | `6e6ce45252f5eb8d06b837084c01af506b0c8f62afcb732767a1c407c9ac8b8c` |
| `vera-stdlib-evaluation-shard-3-45526533438-1` | 14982372144 | `f690d0f7c995e60ebc82e57499fb2e1f53d8cc7141850aabc156d61924af5db1` |
| `vera-stdlib-evaluation-shard-4-45526533438-1` | 14982905883 | `31896d0789df6b70ddd6f1d37f78122689068ec1dacddf64be1c3e822e69614d` |
| `vera-stdlib-evaluation-shard-5-45526533438-1` | 14983250805 | `46a36342e997fbdd8c88d9a6e0db5ce4aee7677b1368a94a160aa207b9de4bdb` |
| `vera-stdlib-evaluation-shard-6-45526533438-1` | 14982481865 | `8f096a7894a665144357b12266bb065714a7d07daf84230f0f5172265a7c86ac` |
| `vera-stdlib-evaluation-shard-7-45526533438-1` | 14982044475 | `34e525e1830d7ae8f4717c41bad0046881c0c3e3f5635d36927fa3bef62cc733` |
| `vera-stdlib-evaluation-shard-8-45526533438-1` | 14982541911 | `e939aaa904217a3f866f8c441f9a6621c73919380192c88f468a2fc54d649c34` |
| `vera-stdlib-evaluation-shard-9-45526533438-1` | 14983380406 | `6fa5fb4aa21d520bf4672be517c19515ca3620cc0ca779254b5ff45a92b6b94c` |
| `vera-stdlib-evaluation-shard-10-45526533438-1` | 14982367353 | `43a73449f241356e8697bca0a27cfda8b4eb60aefa81bb623d91ab91ddc5bbe5` |
| `vera-stdlib-evaluation-shard-11-45526533438-1` | 14983196201 | `39440e31b91183ea5a54e4c79109b0d297fdb6922254ac20c5df003b13095879` |
| `vera-stdlib-evaluation-shard-12-45526533438-1` | 14982202972 | `f4fcf519773245d82c548911b49258ba597bf000445249fa6e9d6ec4c2136ee7` |
| `vera-stdlib-evaluation-shard-13-45526533438-1` | 14982412204 | `d0fe3b12dd42825d6f2bc97384ab95b25939feb23535cba332072c819e2d0621` |
| `vera-stdlib-evaluation-shard-14-45526533438-1` | 14983051549 | `c812568c9ad6712e6a5cd0ee9a87712d2cc03edc22a5b0a61fd5e90a361f5df2` |
| `vera-stdlib-evaluation-shard-15-45526533438-1` | 14982621976 | `619370a2dcb9476c5366af05d1e7be1d7e4c67d7666944aae3001c7421281244` |
| `vera-offline-tests-shard-0-45526533438-1` | 14982382278 | `34caae9b43ffb00f4110967f861f60a9e19c4555a04cc380ff7a29568ce5fd71` |
| `vera-offline-tests-shard-1-45526533438-1` | 14982029480 | `ffd1b24b695c52734122cb6933d671981498272ee2cab169bc80502b92b80f79` |
| `vera-offline-tests-shard-2-45526533438-1` | 14982512301 | `2d219548b834de8028dbd5f4f30deeec85e7c518f9da490bfbef67db0c567644` |
| `vera-offline-tests-shard-3-45526533438-1` | 14983400265 | `48d9c5e6b2617927401e7d08f5052ecd25a8ba1a2e2a607721833cde3c6e3990` |
| `vera-offline-tests-shard-4-45526533438-1` | 14982631658 | `ef8d2249da0f8ede6e6128503caf24ffa45c4b124be630a5e2726daa85d22b0b` |
| `vera-offline-tests-shard-5-45526533438-1` | 14982144138 | `366a418d078864aa4aae7f17724a69b84949fc7fb21d60798a1f6d6bf2abdff2` |
| `vera-offline-tests-shard-6-45526533438-1` | 14982138347 | `0f86e1fa452287fd16fe2736293d51934db18f6a98e146e13af6955222f3e5a0` |
| `vera-offline-tests-shard-7-45526533438-1` | 14981269941 | `5ec64b856d19a5548d4c692776e7cf157b9a92b12d33ceb427c12e7d0409269f` |
| `vera-offline-tests-shard-8-45526533438-1` | 14982681731 | `47a2246c4a68e2b7acafb1809eef3833d2f289c1538842151f9386591f5b6825` |
| `vera-offline-tests-shard-9-45526533438-1` | 14982189084 | `1996970c4164d1c407f53ebdc3daf97093c7fecd177a3c6d185fae33b7162e77` |
| `vera-offline-tests-shard-10-45526533438-1` | 14982427114 | `177a9969170c90c2cce81159052a149c8d94ee6d16373dad4b6c20bf4a1becb4` |
| `vera-offline-tests-shard-11-45526533438-1` | 14983635285 | `aaa61a483b0963c362049c122a93bbfe5d6030228979d5f6cec06e92bc3b2444` |
| `vera-offline-tests-shard-12-45526533438-1` | 14982303531 | `f3f2ae62c3703dbbc8a2f365cf1ac8731b8cbf717d37d73dfadd03f05d9074b5` |
| `vera-offline-tests-shard-13-45526533438-1` | 14983605467 | `62e038346de21d4bb53b5700e1b0da4f0e59cec296f52347a6da51af5cb79ffd` |
| `vera-offline-tests-shard-14-45526533438-1` | 14982179185 | `057c70950a87fda824bcafd93d015d9aedb3b922d70013d9da167520a1e58d62` |
| `vera-offline-tests-shard-15-45526533438-1` | 14982362482 | `858af1cfb0792df837f2c5bbae3c5ba3512b74c865a339a6faf82b08e84ed43e` |
| `vera-full-shard-replay-45526533438-1` | 14983325938 | `b69570a1babd1116e58a43f1994f0d5e3ff2a81f66868e55f0aebd9d96ff17d9` |

The aggregate log reports successful local source-bound replay and the
provider reports successful artifact retention. **External archive download,
byte matching and independent replay were not performed for this checkpoint.**
To reproduce, retain the original run/jobs/artifact JSON, download the exact
33 ZIPs, compare archive digests using the metadata auditor and replay the
32 shard bundles with the retained aggregate receipt using the actual
tested checkout `ee1e1d54ac5102f441f9641eab070d9e9233cac5`. Never substitute
the current PR merge SHA or combine later attempts.

This checkpoint is scoped to the tested checkout above, not to subsequent
commits. It records a successful offline CI run and provider-reported
in-run replay, not independent runner attestation, original research source
authentication, prospective confirmation or human evaluation. Original
treatment and evaluator-recovery artifact inventories remained empty at
inspection. The five-task pilot remains diagnostic, the frozen automated
analysis remains post-collection with design and measurement qualifications,
retrospective sensitivities remain exploratory, and human ratings, agreement
and automated-human reconciliation remain pending. No treatments or
evaluators were rerun and no frozen outcomes changed.
