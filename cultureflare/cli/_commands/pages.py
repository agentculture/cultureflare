"""``cultureflare pages <subnoun> <verb>`` — CloudFlare Pages.

v0 exposes ``pages deployments create`` only — trigger a new deployment
(production build) for a git-connected project. The bash counterpart at
``.claude/skills/cultureflare-write/scripts/cf-pages-deployment-create.sh``
is the behavioural reference: same dry-run default, same direct-upload
guard, same production-vs-preview branch classification.
"""

from __future__ import annotations

import argparse
import re
import urllib.parse

import cultureflare._api as _api
from cultureflare._env import require_env
from cultureflare.cli._errors import EXIT_USER_ERROR, CfafiError
from cultureflare.cli._output import dry_run_envelope, emit_json, emit_kv, emit_result

# Project names are CF-restricted (lowercase, digits, dashes); branch
# names allow the usual git set. Both feed a URL path — validate at the
# boundary for clean errors (urllib.quote handles escaping regardless).
_PROJECT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,255}$")


def cmd_pages_deployments_create(args: argparse.Namespace) -> None:
    """Trigger a Pages deployment. See cmd_dns_create for the no-explicit-0 rationale."""
    project = args.project
    if not _PROJECT_RE.match(project):
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"invalid project name: {project}",
            remediation="project names are lowercase letters, digits, dots, dashes",
        )
    if args.branch is not None and not _BRANCH_RE.match(args.branch):
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"invalid --branch: {args.branch}",
            remediation="branch names use letters, digits, and . _ / -",
        )

    account_id = require_env("CLOUDFLARE_ACCOUNT_ID")
    project_enc = urllib.parse.quote(project, safe="")

    # Project detail: existence check + production_branch default + git-source guard.
    detail = _api.http_request("GET", f"/accounts/{account_id}/pages/projects/{project_enc}")
    result = detail.get("result") or {}
    source_type = (result.get("source") or {}).get("type") or ""
    production_branch = result.get("production_branch") or "main"

    if not source_type:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"project {project} has no git source (Direct Upload)",
            remediation="Direct Upload projects build via wrangler / the direct-upload API, not a branch",
        )

    branch = args.branch if args.branch is not None else production_branch
    environment = "production" if branch == production_branch else "preview"
    deploy_path = f"/accounts/{account_id}/pages/projects/{project_enc}/deployments"
    json_mode = bool(getattr(args, "json", False))

    if not args.apply:
        if json_mode:
            emit_json(dry_run_envelope({
                "project": project, "branch": branch,
                "environment": environment, "would_post": deploy_path,
            }))
        else:
            emit_result("**Dry-run — no changes applied**\n", json_mode=False)
            emit_kv([
                ("project", project),
                ("source", source_type),
                ("branch", branch),
                ("environment", environment),
            ])
            emit_result(
                f"\n**would POST** `{deploy_path}` (branch={branch})",
                json_mode=False,
            )
        return

    response = _api.http_request("POST", deploy_path, form={"branch": branch})
    if json_mode:
        emit_json(response)
        return
    dep = response.get("result") or {}
    stage = dep.get("latest_stage") or {}
    emit_result("**Deployment triggered**\n", json_mode=False)
    emit_kv([
        ("project", project),
        ("source", source_type),
        ("branch", branch),
        ("environment", environment),
        ("deployment", f"{dep.get('short_id', '—')} (id={dep.get('id', '—')})"),
        ("stage", f"{stage.get('name', '—')}/{stage.get('status', '—')}"),
        ("url", dep.get("url", "—")),
    ])


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("pages", help="CloudFlare Pages projects and deployments.")
    pages_sub = p.add_subparsers(dest="subnoun", required=True)

    deployments = pages_sub.add_parser("deployments", help="Pages deployments.")
    dep_verbs = deployments.add_subparsers(dest="verb", required=True)

    c = dep_verbs.add_parser(
        "create",
        help="Trigger a deployment / production build (dry-run by default; --apply commits).",
    )
    c.add_argument("project", help="Pages project name, e.g. tools-culture-dev")
    c.add_argument(
        "--branch",
        default=None,
        help="Branch to build (default: the project's production_branch)",
    )
    c.add_argument("--apply", action="store_true", help="Actually POST (without it, dry-run).")
    c.add_argument("--json", action="store_true", help="Emit raw/synthetic JSON envelope.")
    c.set_defaults(func=cmd_pages_deployments_create)
