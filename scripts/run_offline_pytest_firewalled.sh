#!/usr/bin/env bash
# Block host-level outbound traffic during ordinary offline pytest.
# Install dependencies before invoking this wrapper, never under its firewall.
set -Eeuo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Offline firewall requires a Linux runner" >&2
  exit 1
fi
for executable in sudo iptables ip6tables python; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "Missing required offline-test isolation command: $executable" >&2
    exit 1
  fi
done

# Only this invocation's custom chains are ever removed.
chain="VERA_OFFLINE_$$"
v4_created=0
v4_linked=0
v6_created=0
v6_linked=0

cleanup() {
  local status=$?
  local cleanup_failed=0
  trap - EXIT INT TERM
  set +e
  if (( v6_linked )); then
    sudo -n ip6tables -w -D OUTPUT -j "$chain" || cleanup_failed=1
  fi
  if (( v4_linked )); then
    sudo -n iptables -w -D OUTPUT -j "$chain" || cleanup_failed=1
  fi
  if (( v6_created )); then
    sudo -n ip6tables -w -F "$chain" || cleanup_failed=1
    sudo -n ip6tables -w -X "$chain" || cleanup_failed=1
  fi
  if (( v4_created )); then
    sudo -n iptables -w -F "$chain" || cleanup_failed=1
    sudo -n iptables -w -X "$chain" || cleanup_failed=1
  fi
  if (( cleanup_failed )); then
    echo "CRITICAL: offline test firewall cleanup failed" >&2
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Head-of-OUTPUT jumps reject all non-loopback IPv4/IPv6 egress, including
# subprocess/native-library calls outside Python's socket interception.
sudo -n iptables -w -N "$chain"
v4_created=1
sudo -n iptables -w -A "$chain" -o lo -j RETURN
sudo -n iptables -w -A "$chain" -j REJECT
sudo -n iptables -w -I OUTPUT 1 -j "$chain"
v4_linked=1

sudo -n ip6tables -w -N "$chain"
v6_created=1
sudo -n ip6tables -w -A "$chain" -o lo -j RETURN
sudo -n ip6tables -w -A "$chain" -j REJECT
sudo -n ip6tables -w -I OUTPUT 1 -j "$chain"
v6_linked=1

sudo -n iptables -w -C OUTPUT -j "$chain"
sudo -n ip6tables -w -C OUTPUT -j "$chain"
echo "Offline pytest egress isolation active (IPv4 + IPv6; loopback allowed)."
python -m pytest -q "$@"
