"""Common types and pure helpers for the remote-login orchestrator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Names:
    tunnel_name: str
    app_name: str
    service_token_name: str
    policy_name: str


def derive_names(
    *,
    hostname: str,
    tunnel_name: str | None = None,
    app_name: str | None = None,
    service_token_name: str | None = None,
) -> Names:
    """Derive default resource names from a hostname.

    The slugged tunnel name replaces dots with dashes so it survives
    CloudFlare's tunnel-name validation (alphanumerics + dashes only).
    """
    tn = tunnel_name or hostname.replace(".", "-")
    an = app_name or hostname
    stn = service_token_name or f"{hostname}-svc"
    return Names(
        tunnel_name=tn,
        app_name=an,
        service_token_name=stn,
        policy_name=f"{an}-allow",
    )


@dataclass(frozen=True)
class Context:
    """Runtime context shared across all _remote_login helpers."""

    account_id: str
    zone_id: str
    hostname: str
    names: Names


import cfafi._api as _api  # noqa: E402  (after dataclass defs to keep top-of-file lean)
from cfafi.cli._errors import EXIT_USER_ERROR, CfafiError


def resolve_zone(hostname: str) -> tuple[str, str]:
    """Return (zone_id, zone_name) for the longest-suffix zone match.

    Raises CfafiError(EXIT_USER_ERROR) if no zone in the account
    is a suffix of the hostname.
    """
    candidates: list[tuple[str, str]] = []
    for zone in _api.paginate("/zones"):
        name = zone.get("name") or ""
        if hostname == name or hostname.endswith("." + name):
            candidates.append((zone.get("id", ""), name))
    if not candidates:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"no zone in this account is a suffix of {hostname}",
            remediation="run `cfafi zones list` to see accessible zones",
        )
    candidates.sort(key=lambda z: len(z[1]), reverse=True)
    return candidates[0]
