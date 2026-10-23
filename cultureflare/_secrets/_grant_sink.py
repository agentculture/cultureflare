"""Subprocess adapter for the grant CLI.

Wraps ``grant set / show / delete`` so the rest of cultureflare can
deposit secrets without ever touching their values in argv, logs, or
stdout. Secrets are passed as bytes via subprocess stdin only.

Maps grant's documented exit codes (see grant's README) to
CfafiError:

  0     → success
  64    → EXIT_USER_ERROR  (bad input, name conflict, hidden refusal)
  65    → EXIT_API         (store corrupt / unreadable)
  66    → EXIT_USER_ERROR  (requires root → use sudo / drop --user)
  67    → EXIT_API         (backend dep failed; e.g. unknown user)
  70    → EXIT_API         (grant bug)

  FileNotFoundError → EXIT_USER_ERROR with install remediation
"""

from __future__ import annotations

import json as _json
import subprocess

from cultureflare._secrets._types import SealMetadata, GrantTarget
from cultureflare.cli._errors import (
    EXIT_API, EXIT_USER_ERROR, CfafiError,
)


_GRANT_NOT_FOUND_MSG = "grant binary not found"


def _sudo_prefix(target: GrantTarget) -> list[str]:
    """argv prefix that lifts the call to sudo when target.user is set.

    Uses ``sudo -n`` (non-interactive) so missing cached creds fail
    fast rather than blocking on a tty prompt — important when
    cultureflare runs under an agent harness without a tty.
    """
    return ["sudo", "-n"] if target.user is not None else []


def _user_flag(target: GrantTarget) -> list[str]:
    """``--user NAME`` flag pair when cross-user, else empty."""
    return ["--user", target.user] if target.user is not None else []


def _argv_for_set(target: GrantTarget, meta: SealMetadata) -> list[str]:
    return [
        *_sudo_prefix(target),
        "grant", "set", "--hidden",
        "--source", meta.source,
        "--purpose", meta.purpose,
        "--rotate-howto", meta.rotate_howto,
        *_user_flag(target),
        target.name, "-",
    ]


def _argv_for_show(target: GrantTarget) -> list[str]:
    return [
        *_sudo_prefix(target),
        "grant", "show", "--json",
        *_user_flag(target),
        target.name,
    ]


def _argv_for_delete(target: GrantTarget) -> list[str]:
    return [
        *_sudo_prefix(target),
        "grant", "delete",
        *_user_flag(target),
        target.name,
    ]


def _check_sudo_no_creds(returncode: int, stderr: bytes, target: GrantTarget) -> None:
    """Raise a curated CfafiError when sudo fails because creds aren't cached.

    Called after any subprocess.run that uses ``sudo -n``.  When the
    return code is non-zero and stderr indicates that sudo needed a
    password (but couldn't prompt because of ``-n``), we surface a
    clear remediation rather than falling through to the generic
    _map_exit_code path.
    """
    if returncode != 0 and target.user is not None:
        stderr_text = stderr.decode(errors="replace")
        if "password is required" in stderr_text or \
           "terminal is required" in stderr_text:
            raise CfafiError(
                code=EXIT_USER_ERROR,
                message=(
                    f"sudo non-interactive ran but creds not cached: "
                    f"{stderr_text.strip()}"
                ),
                remediation=(
                    "run `sudo -v` once to cache credentials, then re-run; "
                    "or configure NOPASSWD for grant in /etc/sudoers"
                ),
            )


def _map_exit_code(rc: int, stderr: bytes, target: GrantTarget) -> CfafiError:
    msg = stderr.decode(errors="replace").strip() or f"grant exit {rc}"
    if rc == 64:
        return CfafiError(
            code=EXIT_USER_ERROR,
            message=f"grant rejected the request: {msg}",
            remediation=(
                f"`grant show {target.name}` to inspect; "
                f"`grant delete {target.name}` then retry to rotate"
            ),
        )
    if rc == 66:
        return CfafiError(
            code=EXIT_USER_ERROR,
            message=f"grant requires root for cross-user write: {msg}",
            remediation=(
                "re-run cultureflare with sudo, or drop the --grant=USER "
                "argument to deposit into the invoking user's vault"
            ),
        )
    return CfafiError(
        code=EXIT_API,
        message=f"grant failed (exit {rc}): {msg}",
        remediation="`grant doctor` for diagnostics",
    )


def seal(
    target: GrantTarget,
    secret: bytes,
    meta: SealMetadata,
) -> None:
    """Pipe ``secret`` into ``grant set --hidden`` for ``target``.

    ``secret`` must be ``bytes`` so a stray ``repr()`` in a traceback
    cannot reveal the value as a string. Passing a ``str`` raises
    ``TypeError`` before any subprocess call.
    """
    if not isinstance(secret, (bytes, bytearray)):
        raise TypeError("secret must be bytes; pass str.encode('utf-8')")

    argv = _argv_for_set(target, meta)
    try:
        result = subprocess.run(
            argv, input=bytes(secret), capture_output=True, check=False,
        )
    except FileNotFoundError as exc:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=_GRANT_NOT_FOUND_MSG,
            remediation=(
                "`uv tool install grant`, or omit --grant to print "
                "secrets to stdout (insecure)"
            ),
        ) from exc

    if result.returncode != 0:
        _check_sudo_no_creds(result.returncode, result.stderr, target)
        raise _map_exit_code(result.returncode, result.stderr, target)


def probe(target: GrantTarget) -> dict | None:
    """Return grant's metadata dict for ``target.name``, or None when absent.

    Hidden entries return metadata with no ``value`` field, which is
    fine — cultureflare only cares about presence + provenance.
    Cross-user goes through sudo. Any non-64 non-zero exit is raised.
    """
    argv = _argv_for_show(target)
    try:
        result = subprocess.run(argv, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=_GRANT_NOT_FOUND_MSG,
            remediation="`uv tool install grant`",
        ) from exc

    if result.returncode == 64:
        return None
    if result.returncode != 0:
        _check_sudo_no_creds(result.returncode, result.stderr, target)
        raise _map_exit_code(result.returncode, result.stderr, target)

    payload = _json.loads(result.stdout.decode("utf-8"))
    if not payload.get("ok"):
        return None
    # grant show --json returns the metadata directly in the top-level object
    # (e.g. {"ok": true, "name": "...", "hidden": true, ...}).
    # Strip the "ok" sentinel and return the rest as the metadata dict.
    return {k: v for k, v in payload.items() if k != "ok"}


def delete(target: GrantTarget) -> bool:
    """Remove ``target.name`` from grant.

    Returns True on success, False when the record was already absent
    (grant exit 64). Other non-zero exits raise CfafiError.
    """
    argv = _argv_for_delete(target)
    try:
        result = subprocess.run(argv, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=_GRANT_NOT_FOUND_MSG,
            remediation="`uv tool install grant`",
        ) from exc

    if result.returncode == 0:
        return True
    if result.returncode == 64:
        return False
    _check_sudo_no_creds(result.returncode, result.stderr, target)
    raise _map_exit_code(result.returncode, result.stderr, target)
