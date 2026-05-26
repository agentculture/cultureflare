#!/usr/bin/env bash
# Delete a single Single Redirect rule from a zone's
# http_request_dynamic_redirect ruleset.
#
# Usage:
#   cf-redirect-delete.sh ZONE FROM_HOST [--apply] [--json]
#
# Default is DRY-RUN: resolves the zone, finds the dynamic-redirect
# ruleset, locates the one rule whose expression matches FROM_HOST,
# refuses if the match is ambiguous, prints the DELETE URL it would
# hit, and exits 0 WITHOUT mutating anything. Pass --apply to actually
# DELETE.
#
# This deletes ONE RULE, not the whole ruleset. A zone's redirect
# ruleset can hold many rules (e.g. www -> apex, several subdomain
# 301s); removing one leaves the rest untouched. CF's per-rule
# endpoint is DELETE /zones/:zone/rulesets/:ruleset/rules/:rule, which
# returns the updated ruleset.
#
# ZONE is the zone whose ruleset holds the rule (e.g. culture.dev),
# which is NOT the same as FROM_HOST when FROM_HOST is a subdomain
# (e.g. agex.culture.dev). Both are explicit so nothing is inferred.
#
# Flags:
#   --apply   actually DELETE (without it, this is a dry-run)
#   --json    raw CloudFlare response envelope (or simulated body in dry-run)
#
# Exits 1 on: zone not found, no redirect ruleset on the zone, no rule
#   matching FROM_HOST (already gone), ambiguous match (>1 rule),
#   API error. Exits 2 on usage error.

set -euo pipefail
shopt -s inherit_errexit

mode=md
apply=0
positional=()

for arg in "$@"; do
  case "$arg" in
    --json)   mode=json ;;
    --apply)  apply=1 ;;
    -h|--help)
      awk 'NR==1{next} /^#/{sub(/^# ?/, ""); print; next} {exit}' "$0"
      exit 0
      ;;
    -*)
      printf '%s\n' "ERROR: unknown flag: $arg" >&2
      exit 2
      ;;
    *)
      positional+=("$arg")
      ;;
  esac
done

if (( ${#positional[@]} != 2 )); then
  printf '%s\n' "ERROR: expected ZONE and FROM_HOST positional args, got ${#positional[@]}" >&2
  printf '%s\n' "usage: cf-redirect-delete.sh ZONE FROM_HOST [--apply] [--json]" >&2
  exit 2
fi
zone_name="${positional[0]}"
from_host="${positional[1]}"

# Validate hostnames early — FROM_HOST is spliced into a jq match token
# below, and ZONE goes into the lookup. Same shape as the sibling scripts.
host_re='^[a-zA-Z0-9][a-zA-Z0-9.-]*$'
for h in "$zone_name" "$from_host"; do
  if [[ ! "$h" =~ $host_re ]]; then
    printf '%s\n' "ERROR: invalid hostname: $h" >&2
    exit 2
  fi
done

# shellcheck source=../../cloudflare/scripts/_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

# Resolve ZONE to a zone ID.
zones_json=$(cf_api_paginated /zones)
# shellcheck disable=SC2016  # single-quoted jq filter
zone_id=$(printf '%s' "$zones_json" | jq -r --arg name "$zone_name" \
  '[.result[] | select(.name == $name) | .id] | .[0] // ""')

if [[ -z "$zone_id" ]]; then
  printf '%s\n' "ERROR: zone $zone_name not found in this account" >&2
  exit 1
fi

# Find the zone-level dynamic-redirect ruleset. Same selector as
# cf-redirect-create.sh's idempotency check.
rulesets_json=$(cf_api_paginated "/zones/$zone_id/rulesets")
# shellcheck disable=SC2016  # single-quoted jq filter
ruleset_id=$(printf '%s' "$rulesets_json" | jq -r '
  [
    .result[]
    | select(.phase == "http_request_dynamic_redirect")
    | select(.kind == "zone")
    | .id
  ] | .[0] // ""
')

if [[ -z "$ruleset_id" ]]; then
  printf '%s\n' "ERROR: no redirect ruleset (http_request_dynamic_redirect) on zone $zone_name (nothing to delete)" >&2
  exit 1
fi

# The rulesets LIST endpoint omits the rules array; fetch the ruleset
# DETAIL to enumerate rules. Single-object GET, so cf_api not _paginated.
ruleset_detail=$(cf_api "/zones/$zone_id/rulesets/$ruleset_id")

# Match rules whose expression contains the exact quoted host token
# `http.host eq "FROM_HOST"`. The surrounding quotes anchor the match:
# searching for `"agex.culture.dev"` will not hit `"notagex.culture.dev"`
# (preceded by a non-quote) nor the www wildcard rule (which has no
# `http.host eq "..."` clause). cf-redirect-create.sh emits exactly this
# clause (plus an optional `or (http.host eq "www.FROM_HOST")`), so a
# --www-created rule is matched by its apex host too.
# shellcheck disable=SC2016  # single-quoted jq filter
matches_json=$(printf '%s' "$ruleset_detail" | jq --arg h "$from_host" '
  [
    (.result.rules // [])[]
    | select(.expression | contains("http.host eq \"" + $h + "\""))
    | {id, expression,
       target: (.action_parameters.from_value.target_url.expression
                // .action_parameters.from_value.target_url // "—"),
       status_code: (.action_parameters.from_value.status_code // "—")}
  ]
')
match_count=$(printf '%s' "$matches_json" | jq 'length')

if (( match_count == 0 )); then
  printf '%s\n' "ERROR: no redirect rule for host '$from_host' in zone $zone_name's ruleset (nothing to delete)" >&2
  exit 1
fi
if (( match_count > 1 )); then
  printf '%s\n' "ERROR: ambiguous match in zone $zone_name: host '$from_host' matches $match_count rules" >&2
  printf '%s\n' "$matches_json" | jq -r '.[] | "  - \(.id)  \(.expression)"' >&2
  exit 1
fi

rule_id=$(printf '%s' "$matches_json" | jq -r '.[0].id')
rule_expression=$(printf '%s' "$matches_json" | jq -r '.[0].expression')
rule_target=$(printf '%s' "$matches_json" | jq -r '.[0].target')
rule_status=$(printf '%s' "$matches_json" | jq -r '.[0].status_code')

delete_path="/zones/$zone_id/rulesets/$ruleset_id/rules/$rule_id"

render_summary_kv() {
  printf -- '- **zone:** %s (id=%s)\n' "$zone_name" "$zone_id"
  printf -- '- **from:** %s\n' "$from_host"
  printf -- '- **ruleset_id:** %s\n' "$ruleset_id"
  printf -- '- **rule_id:** %s\n' "$rule_id"
  printf -- '- **expression:** %s\n' "$rule_expression"
  printf -- '- **target:** %s\n' "$rule_target"
  printf -- '- **status:** %s\n' "$rule_status"
  return 0
}

if (( apply == 0 )); then
  if [[ "$mode" == "json" ]]; then
    # shellcheck disable=SC2016  # single-quoted jq filter
    jq -n \
      --arg zone_id "$zone_id" \
      --arg ruleset_id "$ruleset_id" \
      --arg rule_id "$rule_id" \
      --arg delete_path "$delete_path" \
      '{success: true, errors: [], messages: ["dry-run: no changes applied"],
        result: {dry_run: true, zone_id: $zone_id, ruleset_id: $ruleset_id,
                 rule_id: $rule_id, would_delete: $delete_path}}'
    exit 0
  fi
  printf '**Dry-run — no changes applied**\n\n'
  render_summary_kv
  # shellcheck disable=SC2016  # literal backticks wrap markdown inline code
  printf '\n**would DELETE** `%s`\n' "$delete_path"
  exit 0
fi

# Apply path. CF returns the UPDATED ruleset (minus the deleted rule).
response=$(cf_api "$delete_path" -X DELETE)

if [[ "$mode" == "json" ]]; then
  printf '%s\n' "$response"
  exit 0
fi

remaining=$(printf '%s' "$response" | jq -r '.result.rules | length // 0' 2>/dev/null || printf '%s' '?')
printf '**Redirect rule deleted**\n\n'
render_summary_kv
printf -- '- **remaining rules in ruleset:** %s\n' "$remaining"
