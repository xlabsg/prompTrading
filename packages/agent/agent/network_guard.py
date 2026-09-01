from __future__ import annotations

import ipaddress
import os
import socket
from typing import Iterable


class NetworkGuardError(RuntimeError):
    pass


_INSTALLED = False


def _normalize_host(host: str | None) -> str:
    if not host:
        return ""
    if isinstance(host, bytes):
        try:
            host = host.decode("utf-8", "ignore")
        except Exception:
            return ""
    h = str(host).strip().lower().rstrip(".")
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    return h


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _parse_allowlist(items: Iterable[str] | None) -> list[str]:
    allow: list[str] = []
    if items is None:
        raw = os.getenv("NETWORK_ALLOWLIST", "")
        items = raw.split(",")
    for item in items:
        value = _normalize_host(str(item))
        if value:
            allow.append(value)
    return allow


def _is_allowed_host(host: str | None, allowlist: list[str]) -> bool:
    h = _normalize_host(host)
    if not h:
        return True
    if h in ("localhost", "127.0.0.1", "::1"):
        return True
    if _is_ip(h):
        return h in allowlist
    for entry in allowlist:
        if entry == h:
            return True
        if entry.startswith("*.") and (h == entry[2:] or h.endswith(entry[1:])):
            return True
    return False


def _extract_host(address: object) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    if isinstance(address, str):
        if address.startswith("/"):
            return ""
        return address
    return ""


def install_network_guard(*, allowlist: Iterable[str] | None = None, enabled: bool | None = None) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    if enabled is None:
        enabled = (os.getenv("NETWORK_GUARD_ENABLED", "") or "").strip().lower() in ("1", "true", "yes")
    if not enabled:
        return

    allow = _parse_allowlist(allowlist)
    allowed_ips: set[str] = set()

    original_getaddrinfo = socket.getaddrinfo
    original_create_connection = socket.create_connection
    original_socket_connect = socket.socket.connect

    def guarded_getaddrinfo(host: str | None, *args, **kwargs):
        if not _is_allowed_host(host, allow):
            raise NetworkGuardError(f"network_blocked:{host}")
        results = original_getaddrinfo(host, *args, **kwargs)
        for item in results:
            try:
                sockaddr = item[4]
                if sockaddr and isinstance(sockaddr, tuple) and sockaddr[0]:
                    allowed_ips.add(str(sockaddr[0]))
            except Exception:
                continue
        return results

    def guarded_create_connection(address, *args, **kwargs):
        host = _extract_host(address)
        if host and not _is_allowed_host(host, allow) and host not in allowed_ips:
            raise NetworkGuardError(f"network_blocked:{host}")
        return original_create_connection(address, *args, **kwargs)

    def guarded_socket_connect(self, address):
        host = _extract_host(address)
        if host and not _is_allowed_host(host, allow) and host not in allowed_ips:
            raise NetworkGuardError(f"network_blocked:{host}")
        return original_socket_connect(self, address)

    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]
    socket.create_connection = guarded_create_connection  # type: ignore[assignment]
    socket.socket.connect = guarded_socket_connect  # type: ignore[assignment]
    _INSTALLED = True


__all__ = ["NetworkGuardError", "install_network_guard"]
