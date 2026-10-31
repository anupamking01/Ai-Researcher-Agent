"""Fail closed on outbound internet traffic during the offline pytest session.

VERA's research validations must not depend on live web/API responses or spend
model budget. Loopback and Unix-domain sockets remain available for in-process
ASGI/WebSocket tests. This is an accidental-network-use guard, not an OS sandbox.
"""

from __future__ import annotations

import ipaddress
import socket

from pytest import MonkeyPatch


_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_SENDTO = socket.socket.sendto
_ORIGINAL_SENDMSG = getattr(socket.socket, "sendmsg", None)
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_PATCHER: MonkeyPatch | None = None


def _require_offline_destination(sock: socket.socket, destination: object) -> None:
    """Allow only loopback destinations for IPv4/IPv6 network sockets."""
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        return
    if not isinstance(destination, tuple) or not destination:
        raise RuntimeError("offline tests prohibit non-loopback socket destinations")
    host = destination[0]
    if not _is_loopback_host(host):
        raise RuntimeError(
            "offline tests prohibit external network access: "
            f"{host!r}"
        )


def _is_loopback_host(host: object) -> bool:
    if not isinstance(host, str):
        return False
    if host.casefold() in {"localhost", "localhost."}:
        return True
    try:
        # IPv6 zone IDs are valid only on scoped addresses, not remote
        # permission grants; require the literal address to be loopback.
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_connect(sock: socket.socket, destination: object):
    _require_offline_destination(sock, destination)
    return _ORIGINAL_CONNECT(sock, destination)


def _guarded_connect_ex(sock: socket.socket, destination: object):
    _require_offline_destination(sock, destination)
    return _ORIGINAL_CONNECT_EX(sock, destination)


def _guarded_sendto(sock: socket.socket, *args, **kwargs):
    destination = kwargs.get("address", args[-1] if len(args) >= 2 else None)
    if destination is not None:
        _require_offline_destination(sock, destination)
    return _ORIGINAL_SENDTO(sock, *args, **kwargs)


def _guarded_sendmsg(sock: socket.socket, *args, **kwargs):
    destination = kwargs.get("address", args[3] if len(args) >= 4 else None)
    if destination is not None:
        _require_offline_destination(sock, destination)
    return _ORIGINAL_SENDMSG(sock, *args, **kwargs)


def _guarded_getaddrinfo(host, *args, **kwargs):
    # None is the standard local/wildcard name used when creating listeners.
    if host is not None and not _is_loopback_host(host):
        raise RuntimeError(
            "offline tests prohibit external DNS/network resolution: "
            f"{host!r}"
        )
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


def pytest_sessionstart(session):
    """Install before test collection, including import-time network calls."""
    global _PATCHER
    _PATCHER = MonkeyPatch()
    _PATCHER.setattr(socket.socket, "connect", _guarded_connect)
    _PATCHER.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    _PATCHER.setattr(socket.socket, "sendto", _guarded_sendto)
    if _ORIGINAL_SENDMSG is not None:
        _PATCHER.setattr(socket.socket, "sendmsg", _guarded_sendmsg)
    _PATCHER.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)


def pytest_sessionfinish(session, exitstatus):
    global _PATCHER
    if _PATCHER is not None:
        _PATCHER.undo()
        _PATCHER = None
