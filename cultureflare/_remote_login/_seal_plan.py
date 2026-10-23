"""Derive grant target names + metadata from a hostname.

Pure function — no I/O, no subprocess. Safe to call before any CF
API call so dry-run output can render the seal plan without side
effects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cultureflare._secrets._types import SealMetadata, GrantTarget
from cultureflare.cli._errors import EXIT_USER_ERROR, CfafiError


_GRANT_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")


@dataclass(frozen=True)
class SealPlan:
    """Pre-computed grant targets + metadata for a remote-login run."""

    enabled: bool
    user: str | None
    tunnel_token_target: GrantTarget
    service_token_secret_target: GrantTarget
    metadata: SealMetadata


def _slug(hostname: str) -> str:
    return (
        "CULTUREFLARE_"
        + hostname.upper().replace(".", "_").replace("-", "_")
    )


def _rotate_howto(hostname: str, user: str | None) -> str:
    flag = "--grant" if user is None else f"--grant={user}"
    return (
        f"cultureflare remote-login teardown --hostname {hostname} "
        f"{flag} --apply && cultureflare remote-login setup --hostname "
        f"{hostname} {flag} --apply ..."
    )


def derive_seal_plan(
    *,
    hostname: str,
    grant_arg: str | None = None,
    shushu_arg: str | None = None,
    validate_names: bool = True,
) -> SealPlan:
    """Translate the CLI ``--grant[=USER]`` argument to a SealPlan.

    ``shushu_arg`` is a deprecated keyword alias for ``grant_arg``;
    passing both is a user error.

    ``validate_names`` (default True) refuses derived names grant would
    reject when sealing is enabled. ``setup`` keeps it on; ``show`` and
    ``teardown`` turn it off so an over-long hostname can still be
    inspected and torn down.

    ``grant_arg`` semantics:
      * ``None`` — flag not passed (sealed mode disabled).
      * ``""``   — bare ``--grant`` (sealed mode, invoking user, no sudo).
      * ``"alice"`` — ``--grant=alice`` (sealed mode, sudo to alice).

    Targets are computed even when ``enabled=False`` so dry-run
    rendering can preview the seal step. Hostname must be ASCII.
    """
    if grant_arg is not None and shushu_arg is not None:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message="grant_arg and shushu_arg are mutually exclusive",
            remediation="pass only --grant (--shushu is a deprecated alias)",
        )
    if grant_arg is None:
        grant_arg = shushu_arg

    if not hostname.isascii():
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"hostname must be ASCII (got {hostname!r})",
            remediation="use the punycode form for IDN hostnames",
        )

    enabled = grant_arg is not None
    user = grant_arg if grant_arg else None

    slug = _slug(hostname)
    tunnel_target = GrantTarget(user=user, name=f"{slug}_TUNNEL_TOKEN")
    svc_target = GrantTarget(user=user, name=f"{slug}_SVC_SECRET")
    if enabled and validate_names:
        for target in (tunnel_target, svc_target):
            if not _GRANT_NAME_RE.match(target.name):
                raise CfafiError(
                    code=EXIT_USER_ERROR,
                    message=(
                        f"derived grant secret name {target.name!r} is "
                        "invalid: names must match ^[A-Z_][A-Z0-9_]{0,63}$ "
                        "(max 64 chars, A-Z 0-9 and _ only)"
                    ),
                    remediation="use a shorter hostname or drop --grant",
                )
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
