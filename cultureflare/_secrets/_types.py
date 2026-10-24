"""Pure data types for the secrets-sink layer.

Lives outside ``_remote_login/`` because future verbs that mint
secrets (e.g. token rotation) reuse the same shape.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GrantTarget:
    """Where a sealed secret lives in grant.

    ``user=None`` means the invoking OS user (no sudo). A non-None
    value means cross-user: cultureflare will invoke ``sudo grant``.
    """

    user: str | None
    name: str


@dataclass(frozen=True)
class SealMetadata:
    """Provenance + operator guidance stamped on every grant entry.

    These map 1:1 to ``grant set --source / --purpose / --rotate-howto``.
    Same metadata is used for both secrets in a remote-login seal — the
    rotate-howto command line tears down and re-creates both at once.
    """

    source: str
    purpose: str
    rotate_howto: str


# Back-compat alias: shushu was renamed to grant.
ShushuTarget = GrantTarget
