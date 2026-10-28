# Historical GitHub Actions artifact availability inventory

**Purpose:** Identify which original VERA run artifacts are still *listed* by GitHub Actions without downloading data, replacing missing reports, or rerunning any treatment/evaluator. This is a recovery-triage diagnostic, **not** an authenticity check or a human-evaluation result.

Run:

    python -m scripts.audit_historical_workflow_artifacts

The tool makes read-only GitHub REST requests. Public requests work without authentication subject to rate limits; set an appropriately scoped environment variable named GITHUB_TOKEN (or GH_TOKEN) when needed. Never place a token on the command line or in a published research receipt. The command prints a JSON inventory; it does not create files or use a browser, and its offline unit tests mock the API.

## Historical anchors

The tool validates both identity and workflow conclusion **before** examining any artifact listing:

| Role | Run | Historical head SHA | Workflow conclusion | Exact expected artifact |
| --- | --- | --- | --- | --- |
| 40 treatment executions | 34620917346 | c3c15e46a8eec3a8bbc24c968eedc0548172a897 | failure | budget-main-study-34620917346 |
| Evaluator-only recovery | 34783525480 | 8733ce492abc74e7b2966ed22ce08d3fddec43ca | success | budget-main-study-recovered-34783525480 |
| Canonical analysis | 36070798723 | 06c6a9ab0b1d01257e8985fbb09c999cef115779 | success | canonical-main-study-analysis-36070798723 |

The original workflow concluded *failure* because the common evaluator did not finish in that run; it is not a claim that any of the original 40 treatment cells failed. The original and evaluator-recovery workflow definitions used **30-day artifact retention**, while the canonical-analysis snapshot used **90 days**. Version-controlled canonical CSVs and verified analysis outputs do not replace the missing 40 original report/trace sources.

## Checks and interpretation

The inventory pins the historical run ID, workflow name, source SHA, completion status, and conclusion. It walks bounded artifact-listing pages, checks total-count consistency, rejects duplicate artifact IDs or cross-run associations, and counts only the **exact expected artifact name**. A different artifact on the same run cannot stand in for original evidence.

The output distinguishes **named artifact absent**, **named artifact expired**, and **named nonexpired artifact listed**. An API error, bad metadata, or incomplete pagination is an explicit failure, never silently reported as absent. Nonexpired means the GitHub API lists an unexpired artifact; it does **not** prove that its ZIP can actually be downloaded, unpacked, matched to the intended 40 cells, or authenticated against independently retained archival fingerprints.

As observed on **2026-10-28**, the two original/recovery runs returned no artifacts in their run-scoped listings. The canonical-analysis run still listed artifact **10837878458**, expiry **2026-12-23T23:03:46Z**. These are point-in-time API observations; the inventory command must be rerun for current status. Nothing here proves an original archive was destroyed or rules out authorized institutional/offline backups. Do **not** treat a newly generated pin for recovered material as an independently retained historical fingerprint.

Even if both original artifacts become listed, the JSON still sets historical_evidence_authenticated and human_evaluation_ready to false. Recovery must satisfy the independent trace/report source-custody checks and the blinded packet/handoff gates in HUMAN_EVAL_ARCHIVE_RECOVERY.md. No pilot, confirmatory, exploratory, or pending human-validation conclusion is changed by this read-only availability audit.

## ZIP metadata and expiry checks (availability, not custody)

For each listed artifact, the inventory checks that the GitHub-provided ZIP
size is a positive integer, that its archive download endpoint points to
the expected artifact in this repository, and that its expiry is an unambiguous
UTC timestamp. The output records zip_size_in_bytes, archive_download_url,
and github_zip_digest (when GitHub supplies a well-formed sha256 value),
so an operator can identify the specific ZIP advertised at inventory time.
This SHA-256 is GitHub-generated ZIP metadata, NOT an independently retained
file-byte fingerprint for the original 40 traces or Markdown reports.
A missing GitHub digest is represented as null, not silently synthesized.

All three run listings are evaluated against one checked_at_utc timestamp.
An artifact with expired=false but expires_at at or before that instant is
reported as named_artifact_listed_elapsed_expiry and cannot count as a
nonexpired candidate; expired=true remains expired even with a future
deadline. Ambiguous timestamps, zero-size ZIPs, malformed digest metadata,
or an unrelated ZIP endpoint fail closed. No listed metadata proves download
success, ZIP content validity, independent historical custody, or human
evaluation readiness.
