"""Derive shushu target names + metadata from a hostname.

Pure function — no I/O, no subprocess. Safe to call before any CF
API call so dry-run output can render the seal plan without side
effects.
"""

from __future__ import annotations

from dataclasses import dataclass

from cultureflare._secrets._types import SealMetadata, ShushuTarget
from cultureflare.cli._errors import EXIT_USER_ERROR, CfafiError


@dataclass(frozen=True)
class SealPlan:
    """Pre-computed shushu targets + metadata for a remote-login run."""

    enabled: bool
    user: str | None
    tunnel_token_target: ShushuTarget
    service_token_secret_target: ShushuTarget
    metadata: SealMetadata


def _slug(hostname: str) -> str:
    return (
        "CULTUREFLARE_"
        + hostname.upper().replace(".", "_").replace("-", "_")
    )


def _rotate_howto(hostname: str, user: str | None) -> str:
    flag = "--shushu" if user is None else f"--shushu={user}"
    return (
        f"cultureflare remote-login teardown --hostname {hostname} "
        f"{flag} --apply && cultureflare remote-login setup --hostname "
        f"{hostname} {flag} --apply ..."
    )


def derive_seal_plan(*, hostname: str, shushu_arg: str | None) -> SealPlan:
    """Translate the CLI ``--shushu[=USER]`` argument to a SealPlan.

    ``shushu_arg`` semantics:
      * ``None`` — flag not passed (sealed mode disabled).
      * ``""``   — bare ``--shushu`` (sealed mode, invoking user, no sudo).
      * ``"alice"`` — ``--shushu=alice`` (sealed mode, sudo to alice).

    Targets are computed even when ``enabled=False`` so dry-run
    rendering can preview the seal step. Hostname must be ASCII.
    """
    if not hostname.isascii():
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"hostname must be ASCII (got {hostname!r})",
            remediation="use the punycode form for IDN hostnames",
        )

    enabled = shushu_arg is not None
    user = shushu_arg if shushu_arg else None

    slug = _slug(hostname)
    tunnel_target = ShushuTarget(user=user, name=f"{slug}_TUNNEL_TOKEN")
    svc_target = ShushuTarget(user=user, name=f"{slug}_SVC_SECRET")
    metadata = SealMetadata(
        source="cultureflare/remote-login",
        purpose=f"remote-login {hostname}",
        rotate_howto=_rotate_howto(hostname, user),
    )
    return SealPlan(
        enabled=enabled,
        user=user,
        tunnel_token_target=tunnel_target,
        service_token_secret_target=svc_target,
        metadata=metadata,
    )
