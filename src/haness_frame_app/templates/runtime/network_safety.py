from __future__ import annotations

import ipaddress
import socket
import urllib.request
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit


def validate_http_target(
    url: str,
    *,
    allow_private_network: bool = False,
    allowed_domains: list[str] | None = None,
    label: str = "request",
) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{label} URL must use http:// or https://")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} URL must not contain credentials")
    domains = [item.strip().rstrip(".").lower() for item in (allowed_domains or []) if item.strip()]
    host = parsed.hostname.rstrip(".").lower()
    if domains and not any(host == item or host.endswith(f".{item}") for item in domains):
        raise ValueError(f"{label} domain is not allowed: {parsed.hostname}")
    if allow_private_network:
        return url
    default_port = 443 if parsed.scheme == "https" else 80
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or default_port)}
    except socket.gaierror as exc:
        raise ValueError(f"{label} hostname could not be resolved: {parsed.hostname}") from exc
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise ValueError(f"{label} blocked non-public address: {address}")
    return url


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, validator: Callable[[str], str]) -> None:
        self.validator = validator
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        target = urljoin(req.full_url, newurl)
        self.validator(target)
        return super().redirect_request(req, fp, code, msg, headers, target)
