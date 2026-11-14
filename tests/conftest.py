"""Fail closed on outbound internet traffic during the offline pytest session.

VERA's research validations must not depend on live web/API responses or spend
model budget. Loopback and Unix-domain sockets remain available for in-process
ASGI/WebSocket tests. This is an accidental-network-use guard, not an OS sandbox.
"""

from __future__ import annotations

import ipaddress
import socket

from pytest import MonkeyPatch


_ORIGINAL_BIND = socket.socket.bind
_ORIGINAL_LISTEN = socket.socket.listen
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_SENDTO = socket.socket.sendto
_ORIGINAL_SENDMSG = getattr(socket.socket, "sendmsg", None)
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_ORIGINAL_GETHOSTBYNAME = socket.gethostbyname
_ORIGINAL_GETHOSTBYNAME_EX = socket.gethostbyname_ex
_ORIGINAL_GETHOSTBYADDR = socket.gethostbyaddr
_ORIGINAL_GETNAMEINFO = socket.getnameinfo
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


def _guarded_bind(sock: socket.socket, address: object):
    """Refuse publicly reachable TCP/UDP listeners in offline tests.

    Binding to 0.0.0.0, ::, or a non-loopback interface can expose a test
    service to other machines even if the test itself makes no outbound calls.
    The rule applies only to internet-family sockets; Unix sockets are local.
    """
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0] if isinstance(address, tuple) and address else None
        if not _is_loopback_host(host):
            raise RuntimeError(
                "offline tests prohibit non-loopback network listeners: "
                f"{address!r}"
            )
    return _ORIGINAL_BIND(sock, address)


def _guarded_listen(sock: socket.socket, *args, **kwargs):
    """Reject implicit wildcard binds from listen() on an unbound TCP socket.

    On Linux, calling listen() without bind() can automatically expose a
    listener on 0.0.0.0 or ::. The bind guard alone cannot intercept that.
    Require the socket's actual local address to be loopback before listen().
    """
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        try:
            address = sock.getsockname()
        except OSError as exc:
            raise RuntimeError(
                "offline tests cannot verify network listener address"
            ) from exc
        host = address[0] if isinstance(address, tuple) and address else None
        if not _is_loopback_host(host):
            raise RuntimeError(
                "offline tests prohibit non-loopback network listeners: "
                f"{address!r}"
            )
    return _ORIGINAL_LISTEN(sock, *args, **kwargs)


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


def _require_offline_resolution_host(host: object) -> None:
    if not _is_loopback_host(host):
        raise RuntimeError(
            "offline tests prohibit external DNS/network resolution: "
            f"{host!r}"
        )


def _guarded_getaddrinfo(host, *args, **kwargs):
    # None is the standard local/wildcard name used when creating listeners.
    if host is not None:
        _require_offline_resolution_host(host)
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


def _guarded_gethostbyname(host):
    _require_offline_resolution_host(host)
    return _ORIGINAL_GETHOSTBYNAME(host)


def _guarded_gethostbyname_ex(host):
    _require_offline_resolution_host(host)
    return _ORIGINAL_GETHOSTBYNAME_EX(host)


def _guarded_gethostbyaddr(host):
    _require_offline_resolution_host(host)
    return _ORIGINAL_GETHOSTBYADDR(host)


def _guarded_getnameinfo(sockaddr, flags):
    # Even numeric-only lookups of external addresses are rejected, so callers
    # cannot silently switch to reverse DNS by changing getnameinfo flags.
    host = sockaddr[0] if isinstance(sockaddr, tuple) and sockaddr else sockaddr
    _require_offline_resolution_host(host)
    return _ORIGINAL_GETNAMEINFO(sockaddr, flags)


def pytest_sessionstart(session):
    """Install before test collection, including import-time network calls."""
    global _PATCHER
    _PATCHER = MonkeyPatch()
    _PATCHER.setattr(socket.socket, "bind", _guarded_bind)
    _PATCHER.setattr(socket.socket, "listen", _guarded_listen)
    _PATCHER.setattr(socket.socket, "connect", _guarded_connect)
    _PATCHER.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    _PATCHER.setattr(socket.socket, "sendto", _guarded_sendto)
    if _ORIGINAL_SENDMSG is not None:
        _PATCHER.setattr(socket.socket, "sendmsg", _guarded_sendmsg)
    _PATCHER.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
    _PATCHER.setattr(socket, "gethostbyname", _guarded_gethostbyname)
    _PATCHER.setattr(socket, "gethostbyname_ex", _guarded_gethostbyname_ex)
    _PATCHER.setattr(socket, "gethostbyaddr", _guarded_gethostbyaddr)
    _PATCHER.setattr(socket, "getnameinfo", _guarded_getnameinfo)


def pytest_sessionfinish(session, exitstatus):
    global _PATCHER
    if _PATCHER is not None:
        _PATCHER.undo()
        _PATCHER = None
