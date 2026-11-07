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

# Validate the effective ordered firewall policy, not only jump membership.
# A chain missing its REJECT or an earlier OUTPUT ACCEPT bypasses isolation.
verify_family_policy() {
  local executable="$1"
  local actual_chain expected_chain output_rules first_output_rule=""
  if ! actual_chain="$(sudo -n "$executable" -w -S "$chain")"; then
    echo "Cannot inspect $executable offline chain" >&2
    return 1
  fi
  # Some iptables versions include the chain declaration in -S CHAIN.
  if [[ "$actual_chain" == "-N $chain"* ]]; then
    actual_chain="$(printf '%s\n' "$actual_chain" | tail -n +2)"
  fi
  # iptables -S can print a normalized default --reject-with option.
  # Both serializations reject egress; do not accept other ICMP target modes.
  local expected_reject="-A $chain -j REJECT" default_reject
  local observed_allow observed_reject line_count
  observed_allow="$(printf '%s\n' "$actual_chain" | sed -n '1p')"
  observed_reject="$(printf '%s\n' "$actual_chain" | sed -n '2p')"
  line_count="$(printf '%s\n' "$actual_chain" | wc -l)"
  if [[ "$executable" == "iptables" ]]; then
    default_reject="$expected_reject --reject-with icmp-port-unreachable"
  else
    default_reject="$expected_reject --reject-with icmp6-port-unreachable"
  fi
  if [[ "$line_count" -ne 2 ||
        "$observed_allow" != "-A $chain -o lo -j RETURN" ||
        ( "$observed_reject" != "$expected_reject" &&
          "$observed_reject" != "$default_reject" ) ]]; then
    echo "Unsafe $executable offline chain policy: $actual_chain" >&2
    return 1
  fi
  if ! output_rules="$(sudo -n "$executable" -w -S OUTPUT)"; then
    echo "Cannot inspect $executable OUTPUT precedence" >&2
    return 1
  fi
  while IFS= read -r rule; do
    if [[ "$rule" == "-A OUTPUT "* ]]; then
      first_output_rule="$rule"
      break
    fi
  done <<< "$output_rules"
  if [[ "$first_output_rule" != "-A OUTPUT -j $chain" ]]; then
    echo "Unsafe $executable OUTPUT rule precedence" >&2
    return 1
  fi
}
verify_family_policy iptables
verify_family_policy ip6tables
echo "Offline pytest egress isolation active (IPv4 + IPv6; loopback allowed; policy inspected)."
python -m pytest -q "$@"
