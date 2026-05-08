"""Subprocess adapter for the shushu CLI.

Wraps ``shushu set / show / delete`` so the rest of cultureflare can
deposit secrets without ever touching their values in argv, logs, or
stdout. Secrets are passed as bytes via subprocess stdin only.

Maps shushu's documented exit codes (see shushu's README) to
CfafiError:

  0     → success
  64    → EXIT_USER_ERROR  (bad input, name conflict, hidden refusal)
  65    → EXIT_API         (store corrupt / unreadable)
  66    → EXIT_USER_ERROR  (requires root → use sudo / drop --user)
  67    → EXIT_API         (backend dep failed; e.g. unknown user)
  70    → EXIT_API         (shushu bug)

  FileNotFoundError → EXIT_USER_ERROR with install remediation
"""

from __future__ import annotations

import subprocess

from cultureflare._secrets._types import SealMetadata, ShushuTarget
from cultureflare.cli._errors import (
    EXIT_API, EXIT_USER_ERROR, CfafiError,
)


def _argv_for_set(target: ShushuTarget, meta: SealMetadata) -> list[str]:
    argv: list[str] = []
    if target.user is not None:
        argv.append("sudo")
    argv.extend([
        "shushu", "set", "--hidden",
        "--source", meta.source,
        "--purpose", meta.purpose,
        "--rotate-howto", meta.rotate_howto,
    ])
    if target.user is not None:
        argv.extend(["--user", target.user])
    argv.extend([target.name, "-"])
    return argv


def _map_exit_code(rc: int, stderr: bytes, target: ShushuTarget) -> CfafiError:
    msg = stderr.decode(errors="replace").strip() or f"shushu exit {rc}"
    if rc == 64:
        return CfafiError(
            code=EXIT_USER_ERROR,
            message=f"shushu rejected the request: {msg}",
            remediation=(
                f"`shushu show {target.name}` to inspect; "
                f"`shushu delete {target.name}` then retry to rotate"
            ),
        )
    if rc == 66:
        return CfafiError(
            code=EXIT_USER_ERROR,
            message=f"shushu requires root for cross-user write: {msg}",
            remediation=(
                "re-run cultureflare with sudo, or drop the --shushu=USER "
                "argument to deposit into the invoking user's vault"
            ),
        )
    return CfafiError(
        code=EXIT_API,
        message=f"shushu failed (exit {rc}): {msg}",
        remediation="`shushu doctor` for diagnostics",
    )


def seal(
    target: ShushuTarget,
    secret: bytes,
    meta: SealMetadata,
) -> None:
    """Pipe ``secret`` into ``shushu set --hidden`` for ``target``.

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
            message="shushu binary not found",
            remediation=(
                "`uv tool install shushu`, or omit --shushu to print "
                "secrets to stdout (insecure)"
            ),
        ) from exc

    if result.returncode != 0:
        raise _map_exit_code(result.returncode, result.stderr, target)
