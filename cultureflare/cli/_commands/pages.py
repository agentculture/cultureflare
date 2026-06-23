"""``cultureflare pages <subnoun> <verb>`` — CloudFlare Pages.

v0 exposes ``pages deployments create`` only — trigger a new deployment
for a git-connected project (production build, or a preview build when
``--branch`` names a non-production branch). The bash counterpart at
``.claude/skills/cultureflare-write/scripts/cf-pages-deployment-create.sh``
is the behavioural reference: same dry-run default, same direct-upload
guard, same production-vs-preview branch classification, and the same
preview branch-alias URL (predicted on dry-run, authoritative on apply).
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

# CF derives a preview's subdomain label from the branch name and truncates
# it; 28 chars is CF's documented branch-alias label limit.
_ALIAS_LABEL_MAXLEN = 28


def _branch_alias_host(branch: str, subdomain: str) -> str | None:
    """Predict the CF Pages preview branch-alias host for ``branch``.

    CF builds a preview subdomain label from the branch: lowercase, every
    run of non-alphanumerics collapses to a single dash, leading/trailing
    dashes stripped, and the label truncated to 28 chars. The alias host is
    ``<label>.<project-subdomain>`` (e.g. ``feat-x.tools-culture-dev.pages.dev``).

    Returns ``None`` when the branch normalizes to an empty label (a
    punctuation-only branch like ``---`` or ``///``) — there is no valid
    alias host to predict, and emitting ``.<subdomain>`` would be a malformed
    URL.

    Best-effort — CF is the authority. The apply path reports CF's real
    ``aliases``; this prediction is only for the dry-run preview, and a long
    branch name may truncate differently.
    """
    label = re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")
    label = label[:_ALIAS_LABEL_MAXLEN].rstrip("-")
    if not label:
        return None
    return f"{label}.{subdomain}"


def _validate_args(project: str, branch: str | None) -> None:
    """Raise CfafiError for an invalid project name or branch name."""
    if not _PROJECT_RE.match(project):
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"invalid project name: {project}",
            remediation="project names are lowercase letters, digits, dots, dashes",
        )
    if branch is not None and not _BRANCH_RE.match(branch):
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"invalid --branch: {branch}",
            remediation="branch names use letters, digits, and . _ / -",
        )


def _resolve_project(account_id: str, project: str, project_enc: str) -> tuple[str, str, str]:
    """Fetch project detail; return (source_type, production_branch, subdomain).

    ``subdomain`` is the project's canonical ``*.pages.dev`` host, used to
    build the preview branch-alias URL (falls back to ``<project>.pages.dev``
    if CF omits it). Raises CfafiError when the project has no git source
    (Direct Upload).
    """
    detail = _api.http_request("GET", f"/accounts/{account_id}/pages/projects/{project_enc}")
    result = detail.get("result") or {}
    source_type = (result.get("source") or {}).get("type") or ""
    production_branch = result.get("production_branch") or "main"
    subdomain = result.get("subdomain") or f"{project}.pages.dev"
    if not source_type:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"project {project} has no git source (Direct Upload)",
            remediation=(
                "Direct Upload projects build via wrangler / the direct-upload API,"
                " not a branch"
            ),
        )
    return source_type, production_branch, subdomain


def cmd_pages_deployments_create(args: argparse.Namespace) -> None:
    """Trigger a Pages deployment. See cmd_dns_create for the no-explicit-0 rationale."""
    _validate_args(args.project, args.branch)

    account_id = require_env("CLOUDFLARE_ACCOUNT_ID")
    project_enc = urllib.parse.quote(args.project, safe="")

    # Project detail: existence check + production_branch default + git-source guard.
    source_type, production_branch, subdomain = _resolve_project(
        account_id, args.project, project_enc
    )

    branch = args.branch if args.branch is not None else production_branch
    environment = "production" if branch == production_branch else "preview"
    deploy_path = f"/accounts/{account_id}/pages/projects/{project_enc}/deployments"
    json_mode = bool(getattr(args, "json", False))

    # A preview deployment (non-production branch) gets a predictable branch
    # alias; production serves the canonical + custom domains, no branch alias.
    # A branch that normalizes to an empty label yields no host (None) — skip.
    predicted_alias: str | None = None
    if environment == "preview":
        alias_host = _branch_alias_host(branch, subdomain)
        if alias_host is not None:
            predicted_alias = f"https://{alias_host}"

    if not args.apply:
        if json_mode:
            result: dict[str, object] = {
                "project": args.project, "branch": branch,
                "environment": environment, "would_post": deploy_path,
            }
            if predicted_alias is not None:
                result["predicted_alias"] = predicted_alias
            emit_json(dry_run_envelope(result))
        else:
            emit_result("**Dry-run — no changes applied**\n", json_mode=False)
            pairs = [
                ("project", args.project),
                ("source", source_type),
                ("branch", branch),
                ("environment", environment),
            ]
            if predicted_alias is not None:
                pairs.append(("predicted alias", predicted_alias))
            emit_kv(pairs)
            emit_result(
                f"\n**would POST** `{deploy_path}` (branch={branch})",
                json_mode=False,
            )
        return

    response = _api.http_request("POST", deploy_path, form={"branch": branch})
    if json_mode:
        emit_json(response)
        return
    _render_deployment(args, source_type, branch, environment, response)


def _render_deployment(
    args: argparse.Namespace,
    source_type: str,
    branch: str,
    environment: str,
    response: dict[str, object],
) -> None:
    """Render a triggered deployment, surfacing CF's authoritative branch aliases."""
    dep = response.get("result") or {}
    stage = dep.get("latest_stage") or {}
    emit_result("**Deployment triggered**\n", json_mode=False)
    pairs = [
        ("project", args.project),
        ("source", source_type),
        ("branch", branch),
        ("environment", environment),
        ("deployment", f"{dep.get('short_id', '—')} (id={dep.get('id', '—')})"),
        ("stage", f"{stage.get('name', '—')}/{stage.get('status', '—')}"),
        ("url", dep.get("url", "—")),
    ]
    # CF's own branch-alias URLs (authoritative). Present for previews; usually
    # empty for production. The predictable URL reviewers / `cicd status` key on.
    aliases = dep.get("aliases") or []
    if aliases:
        pairs.append(("aliases", ", ".join(aliases)))
    emit_kv(pairs)


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
        help=(
            "Branch to build (default: the project's production_branch). A "
            "non-production branch makes a preview deployment, whose "
            "branch-alias URL is reported for posting on a PR."
        ),
    )
    c.add_argument("--apply", action="store_true", help="Actually POST (without it, dry-run).")
    c.add_argument("--json", action="store_true", help="Emit raw/synthetic JSON envelope.")
    c.set_defaults(func=cmd_pages_deployments_create)
