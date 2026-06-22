"""``cultureflare explain <path>...`` — markdown docs lookup by noun/verb path."""

from __future__ import annotations

import argparse

from cultureflare.cli._errors import EXIT_USER_ERROR, CfafiError
from cultureflare.cli._output import emit_result

# Keys are tuples of path tokens. Empty tuple = index.
_CATALOG: dict[tuple[str, ...], str] = {
    (): """\
# cultureflare

CloudFlare Agent First Interface. Run `cultureflare learn` for the full
self-teaching prompt.

Available paths (v0.1.0):

- `cultureflare whoami` — verify the configured CloudFlare API token
- `cultureflare zones list` — list zones in the token's account
- `cultureflare dns create` — create a DNS record (dry-run by default)
- `cultureflare pages deployments create` — trigger a Pages build (dry-run by default)
- `cultureflare learn` — self-teaching prompt
- `cultureflare explain <path>...` — this lookup

Ask for any one with `cultureflare explain <path>`, e.g.
`cultureflare explain dns create`.
""",
    ("whoami",): """\
# cultureflare whoami

Verify the configured CloudFlare API token.

Calls `GET /user/tokens/verify`. Renders a markdown key-value list of
the token id, status, not-before, and expires-on; `--json` emits the
raw CloudFlare envelope.

## Flags

- `--json` — emit the raw CloudFlare response envelope.

## Exit codes

- `0` — token is active
- `2` — CLOUDFLARE_API_TOKEN not set
- `3` — authentication error (token expired, revoked, or scope-mismatch)
- `4` — upstream error
""",
    ("zones",): """\
# cultureflare zones

Zone-level inventory. Current verbs:

- `cultureflare zones list` — list every zone visible to the token

More verbs land in future minor releases.
""",
    ("zones", "list"): """\
# cultureflare zones list

List zones accessible to the configured token.

Walks `GET /zones` with pagination (per_page=50). Renders a markdown
table of ID / NAME / STATUS / PLAN; `--json` emits a synthetic
single-envelope aggregating every page.

## Flags

- `--json` — emit synthetic JSON envelope.
""",
    ("dns",): """\
# cultureflare dns

DNS record management. Current verbs:

- `cultureflare dns create` — create a record (dry-run by default)

More verbs (`list`, `delete`, `update`) land in future minor releases.
""",
    ("dns", "create"): """\
# cultureflare dns create

Create a DNS record in a CloudFlare zone. **Dry-run by default.**

```
cultureflare dns create ZONE TYPE NAME CONTENT [--proxied] [--ttl N] [--comment STR] [--apply] [--json]
```

## Behaviour

Dry-run (no `--apply`): resolves the zone, checks no matching
type+name+content record already exists, prints the exact JSON body
it would POST, and exits 0 without mutating anything.

`--apply`: actually POSTs the record. Idempotency guard still
applies — if a matching record already exists, the command exits 1
without creating a duplicate.

## Flags

- `--proxied` — orange-cloud the record (CF intercepts HTTP traffic).
- `--ttl N` — TTL seconds (default 1 = automatic; 60–86400 for manual).
- `--comment STR` — free-text note attached to the record.
- `--apply` — actually POST. Without it, this is a dry-run.
- `--json` — emit raw CloudFlare response envelope (or a synthetic
  `{result: {dry_run: true, ...}}` envelope in dry-run mode).

## Record types

`A`, `AAAA`, `CNAME`, `TXT`, `MX`, `NS`, `SRV`, `CAA`. Extend
`_SUPPORTED_TYPES` in `cultureflare/cli/_commands/dns.py` if you need more.

## Exit codes

- `0` — success (dry-run printed, or record created with --apply)
- `1` — zone not found, record already exists, or bad flag combination
- `2` — CLOUDFLARE_API_TOKEN not set
- `3` — authentication error
- `4` — upstream CloudFlare API error
""",
    ("pages",): """\
# cultureflare pages

CloudFlare Pages projects and deployments. Current verbs:

- `cultureflare pages deployments create` — trigger a deployment / build (dry-run by default)

More verbs (`projects list/create/delete`, `deployments list/delete/purge`)
land in future minor releases.
""",
    ("pages", "deployments"): """\
# cultureflare pages deployments

Pages deployment management. Current verbs:

- `cultureflare pages deployments create` — trigger a new deployment (dry-run by default)
""",
    ("pages", "deployments", "create"): """\
# cultureflare pages deployments create

Trigger a new deployment for a git-connected Pages project. **Dry-run by default.**

```
cultureflare pages deployments create PROJECT [--branch BRANCH] [--apply] [--json]
```

## Behaviour

Resolves the project (confirming it exists and has a git source), then
determines the branch to build: `--branch` if given, otherwise the
project's `production_branch`. A build on the production branch is a
**production** deployment; any other branch is a **preview**.

Dry-run (no `--apply`): prints the deployments endpoint it would POST to
and the branch, and exits 0 without mutating anything.

`--apply`: POSTs `multipart/form-data` to
`/accounts/<id>/pages/projects/<project>/deployments` with the `branch`
field. CloudFlare clones the repo at that branch's HEAD server-side and
builds — so this works even when an API-created project never got its
GitHub webhook (pushes don't auto-deploy in that case).

Direct Upload projects have no git source and are refused.

## Flags

- `--branch BRANCH` — branch to build (default: project production_branch).
- `--apply` — actually POST. Without it, this is a dry-run.
- `--json` — emit raw CloudFlare response envelope (or a synthetic
  `{result: {dry_run: true, ...}}` envelope in dry-run mode).

## Exit codes

- `0` — success (dry-run printed, or deployment triggered with --apply)
- `1` — invalid project/branch name, or Direct Upload project
- `2` — CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID not set
- `3` — authentication error
- `4` — upstream CloudFlare API error (incl. project not found)
""",
    ("learn",): """\
# cultureflare learn

Print a self-teaching prompt for agent consumers. Supports `--json`
for a structured payload. Run `cultureflare learn` for the full text.
""",
    ("explain",): """\
# cultureflare explain

Look up markdown docs for any noun/verb path. Empty path = index.

Examples:

```
cultureflare explain
cultureflare explain whoami
cultureflare explain dns create
```
""",
}


def resolve(path: tuple[str, ...]) -> str:
    if path in _CATALOG:
        return _CATALOG[path]
    raise CfafiError(
        code=EXIT_USER_ERROR,
        message=f"no docs for path: {' '.join(path)!r}",
        remediation="run `cultureflare explain` with no arguments for the index",
    )


def cmd_explain(args: argparse.Namespace) -> int:
    path = tuple(args.path) if args.path else ()
    markdown = resolve(path)
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result({"path": list(path), "markdown": markdown}, json_mode=True)
    else:
        emit_result(markdown, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "explain",
        help="Print markdown docs for a noun/verb path (e.g. 'cultureflare explain dns create').",
    )
    p.add_argument("path", nargs="*", help="Command path tokens; empty = index.")
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_explain)
