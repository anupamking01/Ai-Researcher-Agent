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
