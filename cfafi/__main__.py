"""Allow ``python -m cfafi`` to invoke the CLI.

Forwards to ``cultureflare.cli.main``. The shim package's
``__init__.py`` aliases all cultureflare submodules into
``sys.modules["cfafi.*"]`` so the import below resolves to the
canonical entry point.
"""

from cultureflare.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
