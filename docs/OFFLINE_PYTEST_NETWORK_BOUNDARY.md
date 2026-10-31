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
