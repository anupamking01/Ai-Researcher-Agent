"""Regression checks for CI's default fail-closed outbound network gate."""

import socket

import pytest


def test_external_tcp_connection_is_rejected_before_dial():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(RuntimeError, match="offline tests prohibit external network"):
            client.connect(("203.0.113.5", 443))
        with pytest.raises(RuntimeError, match="offline tests prohibit external network"):
            client.connect_ex(("203.0.113.5", 443))


def test_external_dns_resolution_is_rejected_before_lookup():
    with pytest.raises(RuntimeError, match="offline tests prohibit external DNS"):
        socket.getaddrinfo("api.openai.com", 443)


def test_external_udp_datagram_is_rejected_before_send():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        with pytest.raises(RuntimeError, match="offline tests prohibit external network"):
            client.sendto(b"blocked", ("198.51.100.9", 53))
        if hasattr(client, "sendmsg"):
            with pytest.raises(RuntimeError, match="offline tests prohibit external network"):
                client.sendmsg([b"blocked"], [], 0, ("198.51.100.9", 53))


@pytest.mark.parametrize("host", ["8.8.8.8", "::ffff:8.8.8.8", "example.org"])
def test_external_ipv6_and_name_targets_are_rejected(host):
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as client:
        with pytest.raises(RuntimeError, match="offline tests prohibit external network"):
            client.connect((host, 443))


def test_local_tcp_loopback_is_available_for_app_integration():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(listener.getsockname())
            accepted, _ = listener.accept()
            with accepted:
                client.sendall(b"local")
                assert accepted.recv(5) == b"local"
    assert socket.getaddrinfo("localhost", None)


def test_unix_domain_socketpair_remains_available():
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"local")
        assert right.recv(5) == b"local"


@pytest.mark.parametrize(
    "resolver_name",
    ["gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getfqdn"],
)
def test_other_standard_dns_paths_reject_external_host_before_lookup(resolver_name):
    with pytest.raises(RuntimeError, match="offline tests prohibit external DNS"):
        getattr(socket, resolver_name)("example.invalid")


@pytest.mark.parametrize("host", ["203.0.113.24", "example.invalid"])
def test_reverse_nameinfo_rejects_external_address_even_if_numeric(host):
    flags = socket.NI_NUMERICHOST | socket.NI_NUMERICSERV
    with pytest.raises(RuntimeError, match="offline tests prohibit external DNS"):
        socket.getnameinfo((host, 443), flags)


def test_standard_local_numeric_name_lookups_remain_available():
    assert socket.gethostbyname("127.0.0.1") == "127.0.0.1"
    assert "127.0.0.1" in socket.gethostbyname_ex("127.0.0.1")[2]
    flags = socket.NI_NUMERICHOST | socket.NI_NUMERICSERV
    assert socket.getnameinfo(("127.0.0.1", 443), flags) == ("127.0.0.1", "443")
