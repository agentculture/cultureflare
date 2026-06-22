#!/usr/bin/env bash
# Trigger a new CloudFlare Pages deployment (production build) for a
# git-connected project.
#
# Usage:
#   cf-pages-deployment-create.sh PROJECT [--branch=BRANCH] [--apply] [--json]
#
# Default is DRY-RUN: resolves the project (which confirms it exists and
# that it has a git source), determines the branch that will be built,
# prints the deployments endpoint it would POST to, and exits 0 WITHOUT
# mutating anything. Pass --apply to actually POST and kick the build.
#
# Why this exists: a Pages project created via the REST API does not
# always get its GitHub webhook installed (the dashboard connect flow
# does extra OAuth + webhook setup the API create skips), so pushes to
# the production branch may not auto-deploy. This endpoint clones the
# repo at the branch HEAD server-side, so it triggers a build regardless
# of the webhook state. It's also the manual "redeploy" primitive for any
# git-backed project.
#
# Flags:
#   --branch=BRANCH   git branch to build. Defaults to the project's
#                     production_branch (resolved from project metadata).
#                     A deployment whose branch == production_branch is a
#                     PRODUCTION deployment; any other branch is a PREVIEW.
#   --apply           actually POST (without it, this is a dry-run)
#   --json            raw CloudFlare response envelope (or simulated body
#                     in dry-run)
#
# Only works on git-connected (github / gitlab source) projects. A
# Direct Upload project has no git source to build from and is refused.
#
# Exits 1 on: project not found, direct-upload project, API error.
# Exits 2 on usage error.

set -euo pipefail
shopt -s inherit_errexit

mode=md
apply=0
branch=""
branch_set=0
positional=()

for arg in "$@"; do
  case "$arg" in
    --json)       mode=json ;;
    --apply)      apply=1 ;;
    --branch=*)   branch="${arg#*=}"; branch_set=1 ;;
    -h|--help)
      awk 'NR==1{next} /^#/{sub(/^# ?/, ""); print; next} {exit}' "$0"
      exit 0
      ;;
    -*)
      echo "ERROR: unknown flag: $arg" >&2
      exit 2
      ;;
    *)
      positional+=("$arg")
      ;;
  esac
done

if (( ${#positional[@]} != 1 )); then
  echo "ERROR: expected exactly one PROJECT positional arg, got ${#positional[@]}" >&2
  echo "usage: cf-pages-deployment-create.sh PROJECT [--branch=BRANCH] [--apply] [--json]" >&2
  exit 2
fi
project="${positional[0]}"

# Project name is CF-restricted (lowercase, digits, dashes); reject
# anything that could escape the URL path. Matches the validation in the
# sibling cf-pages-*.sh scripts.
if [[ ! "$project" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
  echo "ERROR: invalid project name: $project" >&2
  exit 2
fi

# Git branch names: alnum plus . _ / - (same set as cf-pages-project-create's
# --production-branch). Validated only when --branch is given.
if (( branch_set )); then
  branch_re='^[A-Za-z0-9._/-]{1,255}$'
  if [[ ! "$branch" =~ $branch_re ]]; then
    echo "ERROR: invalid --branch: $branch" >&2
    exit 2
  fi
fi

# shellcheck source=../../cloudflare/scripts/_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
cf_require_account_id

project_encoded=$(jq -rn --arg v "$project" '$v|@uri')

# Fetch project metadata: confirms the project exists, gives us the
# production_branch to default to, and tells us whether the project has a
# git source at all. Single-object GET → cf_api, not _paginated. Let
# cf_api's own diagnostic through (it distinguishes missing-project from
# scope/transport failures); add a resolution hint.
if ! project_json=$(cf_api "/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$project_encoded"); then
  echo "HINT: could not resolve Pages project '$project'. Check the project name with cf-pages.sh." >&2
  exit 1
fi

source_type=$(printf '%s' "$project_json" | jq -r '.result.source.type // ""')
production_branch=$(printf '%s' "$project_json" | jq -r '.result.production_branch // "main"')

# Direct Upload projects (source null/absent) have no git to build from.
if [[ -z "$source_type" ]]; then
  echo "ERROR: project $project has no git source (Direct Upload)" >&2
  echo "       there is nothing to build from a branch; deploy it with wrangler / the direct-upload API instead." >&2
  exit 1
fi

if (( branch_set )); then
  effective_branch="$branch"
else
  effective_branch="$production_branch"
fi

# Environment classification mirrors CF: branch == production_branch is a
# production deployment, anything else is a preview.
if [[ "$effective_branch" == "$production_branch" ]]; then
  environment=production
else
  environment=preview
fi

deploy_path="/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$project_encoded/deployments"

render_summary_kv() {
  printf -- '- **project:** %s\n' "$project"
  printf -- '- **source:** %s\n' "$source_type"
  printf -- '- **branch:** %s\n' "$effective_branch"
  printf -- '- **environment:** %s\n' "$environment"
  return 0
}

if (( apply == 0 )); then
  if [[ "$mode" == "json" ]]; then
    # shellcheck disable=SC2016  # single-quoted jq filter
    jq -n \
      --arg project "$project" \
      --arg branch "$effective_branch" \
      --arg environment "$environment" \
      --arg deploy_path "$deploy_path" \
      '{success: true, errors: [], messages: ["dry-run: no changes applied"],
        result: {dry_run: true, project: $project, branch: $branch,
                 environment: $environment, would_post: $deploy_path}}'
    exit 0
  fi
  printf '**Dry-run — no changes applied**\n\n'
  render_summary_kv
  # shellcheck disable=SC2016  # literal backticks wrap markdown inline code
  printf '\n**would POST** `%s` (branch=%s)\n' "$deploy_path" "$effective_branch"
  exit 0
fi

# Apply path. Multipart form POST — the deployments endpoint requires it,
# so route through cf_api_form (NOT cf_api, which forces JSON).
response=$(cf_api_form "$deploy_path" -F "branch=$effective_branch")

if [[ "$mode" == "json" ]]; then
  printf '%s\n' "$response"
  exit 0
fi

deployment_id=$(printf '%s' "$response" | jq -r '.result.id // "—"')
short_id=$(printf '%s' "$response" | jq -r '.result.short_id // "—"')
deploy_url=$(printf '%s' "$response" | jq -r '.result.url // "—"')
stage_name=$(printf '%s' "$response" | jq -r '.result.latest_stage.name // "—"')
stage_status=$(printf '%s' "$response" | jq -r '.result.latest_stage.status // "—"')

printf '**Deployment triggered**\n\n'
render_summary_kv
printf -- '- **deployment:** %s (id=%s)\n' "$short_id" "$deployment_id"
printf -- '- **stage:** %s/%s\n' "$stage_name" "$stage_status"
printf -- '- **url:** %s\n' "$deploy_url"
