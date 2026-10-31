# Offline pytest network boundary for VERA research validation

The research branch's ordinary GitHub Actions `tests` workflow runs the full
pytest suite without live research treatments or evaluator calls. To make
accidental network dependencies fail immediately rather than silently fetching
changing web evidence or spending model budget, `tests/conftest.py` installs a
Python-socket guard at `pytest_sessionstart`, **before test-module collection**.

Within the pytest process it rejects non-loopback IPv4/IPv6 destinations for
`socket.socket.connect`, `connect_ex`, `sendto`, and `sendmsg` (where available),
and blocks non-loopback hostnames/addresses in `socket.getaddrinfo`,
`gethostbyname`, `gethostbyname_ex`, `gethostbyaddr`, and `getnameinfo`
before resolution. Python's `socket.getfqdn` calls the guarded
`gethostbyaddr` function. These older and reverse-lookup entry points matter:
`getaddrinfo` alone does not intercept every Python DNS request.
The boundary also prevents an offline test from accidentally exposing a
TCP/UDP listener on a publicly reachable interface. Internet-family
`socket.socket.bind` is restricted to explicit loopback hosts; wildcard binds
(`0.0.0.0`, `::`, or the empty host) and non-loopback interface addresses fail
before the OS bind call. This also covers Python `socket.create_server`,
which uses `bind` internally. Some kernels also implicitly bind an unbound
TCP socket to a wildcard interface when `listen()` is called without `bind()`.
The guard therefore checks the actual bound address before `socket.socket.listen`
and rejects unbound or non-loopback internet-family sockets. This closes a
public-listener bypass that guarding `bind()` alone cannot prevent. Explicit
loopback TCP/UDP listeners and Unix-domain socket paths remain supported for
integration tests. This is an inbound
exposure safeguard, not a claim that the runner has no reachable interfaces.

Loopback (`127.0.0.0/8`, `::1`, and `localhost`) remains usable by local
application-integration tests, as do Unix-domain sockets. The guard is removed
at `pytest_sessionfinish`. No external endpoint is contacted by its regression
tests: they use documentation-only public test addresses and assert that the
Python call is refused *before* invoking the original socket method.

This guard addresses **accidental Python-socket network use**, not hostile or
arbitrary code execution. It does not firewall the host or cover external
processes, native libraries or third-party resolvers bypassing the patched
Python socket functions, or operations outside pytest (including dependency
installation and separate opt-in live-smoke workflows). It is therefore not
proof of a perfectly disconnected CI runner or of any historical evidence
custody. Code requiring genuine web browsing/model calls belongs in a separate,
explicitly authorized workflow, never in offline unit tests. Running or
rerunning treatments to select more favorable results remains prohibited.

`tests/test_offline_network_guard.py` exercises blocked TCP, UDP, public
listener binds (including implicit `listen()` autobinds and
`socket.create_server`), forward
and reverse DNS (including legacy resolver entry points), external IPv6/name
targets, and permitted local socket communication. A CI
failure from an attempted external connection should be investigated and the
test converted to a synthetic/mocked fixture; do not disable the guard simply
to get a green badge. This change does not modify the frozen pilot,
confirmatory, exploratory, or human-evaluation measurements, and does not
remove the original-source recovery or blinded-human-annotation gates.


## Ordinary CI GitHub token least-privilege boundary

The normal push/PR pytest workflow (\`.github/workflows/tests.yml\`) now explicitly
grants its \`GITHUB_TOKEN\` only \`contents: read\`; all other GitHub token scopes
have no permissions. It also sets \`persist-credentials: false\` on the
SHA-pinned \`actions/checkout\` step, so checkout's authentication is not
left in Git configuration for tests or subprocesses to reuse. The unit-test
job has a 20-minute maximum runtime. This limits accidental repository
mutation and implicit credential reuse during offline scientific validation.
\`tests/test_offline_ci_token_permissions.py\` prevents an unnoticed
workflow-level scope escalation, job-level override, or reintroduction of
persisted checkout credentials.

The workflow still needs transient read access to check out code and access
public Python dependency indexes during installation. The settings do
**not** turn GitHub Actions into a network-disconnected sandbox, prevent
all credential access by arbitrary subprocesses, or prove anything about
historical experiment archives or human annotators. They do not alter,
rerun, or reinterpret pilot, frozen confirmatory, exploratory, or
pending human-validation measurements.


## Live research API secret isolation

The opt-in budget-main-study and evaluator-recovery workflows now scope
OPENAI_API_KEY to only their explicit secret-check and authorized live
search, treatment, or evaluator steps. Offline tests, compilation, dependency
installation, download, validation, summaries and uploads do not inherit the
provider credential. This reduces unintended API spending and secret access
from offline validation. It does not alter or rerun historical treatments,
the frozen common evaluator, or any scientific measurement.

The regression suite tests/test_research_workflow_provider_secret_scoping.py
checks both actual workflows and synthetic job-wide, offline-step, alias,
inline-interpolation, and missing-secret regressions. Environment scoping is
not an operating-system sandbox or a guarantee against malicious changes to
repository workflows. Historical source custody and real blinded human
ratings are still outstanding.


## Host-level outbound isolation during ordinary pytest

Ordinary offline CI runs 'bash scripts/run_offline_pytest_firewalled.sh'
**after** dependency installation and compilation. On the Linux runner this
wrapper creates short-lived private IPv4 and IPv6 iptables chains, both
inserted at the head of OUTPUT. They reject non-loopback outbound traffic
for the entire pytest process, including subprocesses/native libraries that
bypass the earlier process-local Python socket guard. Loopback and Unix
sockets remain available for local application tests.

The test fails closed if either firewall executable is unavailable, privilege
is insufficient, or either family's rules fail to install or verify. Cleanup
traps remove only this invocation's jumps and chains, preserve a failing pytest
exit status, and flag cleanup failure. Rules are removed before subsequent
GitHub Actions cache/post-processing steps. Synthetic regression tests in
'tests/test_offline_ci_network_firewall.py' verify dispatch, ordering, failed
IPv6-install rollback, and cleanup on passing/failing pytest without invoking
host firewalls. The live Linux GitHub Actions run is the enforcement check.

This egress protection covers only the ordinary pytest step. It is **not**
a complete OS sandbox or an installation-time network restriction and cannot
stop malicious processes with root access from deliberately changing firewall
rules. It does not independently authenticate historical treatment archives,
rerun treatment/evaluator calls, change frozen automated analysis, or establish
pending human-validation results.


## Verify firewall rules before offline tests

A successful `iptables -C OUTPUT -j CHAIN` shows only that a jump exists. It
cannot establish that the chain rejects external traffic or has precedence
over an earlier OUTPUT ACCEPT. Before pytest starts, the wrapper now inspects
the ordered IPv4 and IPv6 rules with `iptables -S` and `ip6tables -S`. Each
chain must consist of the loopback RETURN followed by a blanket REJECT, and its
jump must be the first OUTPUT rule. Missing REJECT rules, shadowing ACCEPT
rules, and failed inspection abort before pytest and trigger cleanup. Synthetic
regressions cover these cases without actual outbound connections or host
firewall modification. This protects against accidental misconfiguration,
not malicious privileged rule changes or missing historical source evidence.

The policy inspector accepts either a plain REJECT rule or the same rule
rendered with the tooling's explicit default ICMP port-unreachable option
(IPv4 `icmp-port-unreachable`, IPv6 `icmp6-port-unreachable`). It rejects
different targets, additional rules, or an OUTPUT bypass. This handles
iptables serialization without permitting a weaker firewall policy.
