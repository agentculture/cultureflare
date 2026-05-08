"""Back-compat smoke tests for the legacy `cfafi` import path.

The Python module on disk is now `cultureflare/`. The `cfafi` package
is a thin shim (`cfafi/__init__.py`) that aliases every
``cultureflare.*`` submodule into ``sys.modules`` under the legacy
``cfafi.*`` name. Module / class identity therefore holds across the
boundary — ``cfafi.cli.main is cultureflare.cli.main`` is True, and
``except CfafiError`` from either namespace catches errors raised
from the other.
"""

from __future__ import annotations


def test_top_level_import_works():
    import cfafi  # noqa: F401
    import cultureflare

    assert cfafi.__version__ == cultureflare.__version__
    assert cfafi.__version__  # non-empty


def test_cfafi_cli_main_is_cultureflare_cli_main():
    from cfafi.cli import main as cfafi_main
    from cultureflare.cli import main as cultureflare_main

    assert cfafi_main is cultureflare_main


def test_cfafi_remote_login_orchestrator_is_cultureflare_orchestrator():
    from cfafi._remote_login import setup as cfafi_setup
    from cfafi._remote_login import show as cfafi_show
    from cfafi._remote_login import teardown as cfafi_teardown
    from cultureflare._remote_login import setup, show, teardown

    assert cfafi_setup is setup
    assert cfafi_show is show
    assert cfafi_teardown is teardown


def test_cfafi_api_module_is_cultureflare_api_module():
    import cfafi._api as cfafi_api
    import cultureflare._api as cultureflare_api

    assert cfafi_api is cultureflare_api


def test_cfafi_error_class_identity_preserved():
    # Catching a cultureflare-side CfafiError using `from cfafi…
    # import CfafiError` must work — `is` identity holds.
    from cfafi.cli._errors import CfafiError as CfafiAlias
    from cultureflare.cli._errors import CfafiError

    assert CfafiAlias is CfafiError


def test_python_m_cfafi_runs_cli():
    # `python -m cfafi --version` requires `cfafi/__main__.py` to exist;
    # qodo flagged that PR #27 deleted it. The shim must be present
    # alongside the package's __init__.py so the legacy `python -m`
    # invocation pattern keeps working.
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "cfafi", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # _resolve_prog falls back to canonical "cultureflare" when argv[0]
    # is `__main__.py` (the python -m … invocation).
    assert "cultureflare" in result.stdout
