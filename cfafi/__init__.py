"""Back-compat shim — `cfafi` is now `cultureflare`.

This thin shim aliases every ``cultureflare.*`` submodule to its
``cfafi.*`` counterpart in ``sys.modules`` so existing consumers who
type ``import cfafi`` or ``from cfafi.cli import main`` keep getting
the same module objects (and same classes, e.g. ``CfafiError``) the
canonical ``cultureflare`` namespace exposes. New code should use
``import cultureflare``; this module is the migration safety net.
"""

from __future__ import annotations

import sys as _sys

import cultureflare as _cultureflare

# Eagerly import every cultureflare submodule we surface from the
# public API so `from cfafi.<sub> import <name>` resolves through the
# alias loop below. Adding a new public submodule? Add it here.
import cultureflare._api  # noqa: F401
import cultureflare._env  # noqa: F401
import cultureflare._remote_login  # noqa: F401
import cultureflare._remote_login._access_app  # noqa: F401
import cultureflare._remote_login._access_org  # noqa: F401
import cultureflare._remote_login._access_policy  # noqa: F401
import cultureflare._remote_login._common  # noqa: F401
import cultureflare._remote_login._dns  # noqa: F401
import cultureflare._remote_login._preflight  # noqa: F401
import cultureflare._remote_login._render  # noqa: F401
import cultureflare._remote_login._service_token  # noqa: F401
import cultureflare._remote_login._tunnel  # noqa: F401
import cultureflare.cli  # noqa: F401
import cultureflare.cli._commands  # noqa: F401
import cultureflare.cli._commands.dns  # noqa: F401
import cultureflare.cli._commands.explain  # noqa: F401
import cultureflare.cli._commands.learn  # noqa: F401
import cultureflare.cli._commands.remote_login  # noqa: F401
import cultureflare.cli._commands.whoami  # noqa: F401
import cultureflare.cli._commands.zones  # noqa: F401
import cultureflare.cli._errors  # noqa: F401
import cultureflare.cli._output  # noqa: F401

# Snapshot via list() because we mutate _sys.modules inside the loop:
# inserting "cfafi.<name>" keys while iterating the live dict would
# raise RuntimeError: dictionary changed size during iteration.
for _name, _mod in list(_sys.modules.items()):  # NOSONAR — list() is required (snapshot)
    if _name == "cultureflare" or _name.startswith("cultureflare."):
        _sys.modules["cfafi" + _name[len("cultureflare"):]] = _mod

__version__ = _cultureflare.__version__
