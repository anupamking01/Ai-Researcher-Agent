# Checkout credential isolation in read-only VERA research audits

Four evidence-audit workflows independently read frozen scientific files or
exploratory derivatives. Even though they request read-only GitHub permissions,
`actions/checkout` otherwise stores checkout authentication in Git config,
making it available to later Python scripts and subprocesses.

All current checkouts in these workflows now explicitly use
`persist-credentials: false`:

- `.github/workflows/exploratory-pareto-stability.yml` (1 checkout);
- `.github/workflows/git-canonical-escrow-offline-audit.yml` (2 checkouts);
- `.github/workflows/preserved-canonical-package-audit.yml` (2 checkouts);
- `.github/workflows/retained-canonical-archive-audit.yml` (2 checkouts).

The workflows retain their existing immutable checkout action pins and
read-only `contents: read` (plus `actions: read` where needed). Git fetching
immutable history in the public exploratory workflow does not require persistent
checkout credentials. The two retained-archive workflows explicitly scope
`GH_TOKEN` to the Actions API download/metadata steps; they do not obtain it
from checkout Git configuration.

`tests/test_read_only_audit_checkout_tokens.py` checks each workflow's exact
job, checkout count, SHA-pinned action, absent persistence, and permissions.
Synthetic regressions reject omitted/true/dynamic no-persist controls,
additional unguarded checkout, and workflow/job token escalation. These tests
are offline and consume no provider budget.

**Scope:** This change intentionally does not modify
`canonical-main-study-analysis.yml` or `durable-canonical-git-escrow.yml`.
They contain explicit Git publishing pushes and need a separately designed
short-lived push-token mechanism before persisted credentials can be removed.
This safeguard does not authenticate the missing original 40 treatment reports
or traces; it does not run treatments, adjust frozen estimates, or constitute
human validation. The five-task pilot remains diagnostic; the designated-primary
automated analysis has a documented post-collection freeze chronology; all
retrospective sensitivity work remains exploratory; actual blinded human
annotations are pending.
