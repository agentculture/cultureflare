#!/usr/bin/env bash
# Delete a DNS record from a CloudFlare zone.
#
# Usage:
#   cf-dns-delete.sh ZONE NAME [--type=TYPE] [--content=VALUE] [--apply] [--json]
#
# Default is DRY-RUN: resolves the zone, finds the matching record(s),
# refuses if the match is ambiguous, prints the DELETE URL it would
# hit, and exits 0 WITHOUT mutating anything. Pass --apply to actually
# DELETE.
#
# The record is resolved by NAME (a fully-qualified record name such as
# agex.culture.dev), narrowed server-side with the optional --type /
# --content filters. The zone is an explicit positional so the blast
# radius is obvious and never inferred — this is the zone whose record
# you are deleting (e.g. culture.dev for the agex.culture.dev record).
#
# Flags:
#   --type=TYPE      narrow the match to a record type (A, AAAA, CNAME, ...)
#   --content=VALUE  narrow the match to records with this exact content
#   --apply          actually DELETE (without it, this is a dry-run)
#   --json           raw CloudFlare response envelope (or simulated body in dry-run)
#
# Exits 1 on: zone not found, no matching record (already gone),
#   ambiguous match (>1 record — narrow with --type / --content),
#   API error. Exits 2 on usage error.

set -euo pipefail
shopt -s inherit_errexit

mode=md
apply=0
type_filter=""
content_filter=""
positional=()

for arg in "$@"; do
  case "$arg" in
    --json)       mode=json ;;
    --apply)      apply=1 ;;
    --type=*)     type_filter="${arg#*=}" ;;
    --content=*)  content_filter="${arg#*=}" ;;
    -h|--help)
      # Skip line 1 (shebang), strip `# ?`, stop at the first non-comment line.
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
  printf '%s\n' "ERROR: expected ZONE and NAME positional args, got ${#positional[@]}" >&2
  printf '%s\n' "usage: cf-dns-delete.sh ZONE NAME [--type=TYPE] [--content=VALUE] [--apply] [--json]" >&2
  exit 2
fi
zone_name="${positional[0]}"
record_name="${positional[1]}"

# Validate ZONE and NAME early — both interpolate into URLs and the
# match summary. Same hostname shape used by cf-redirect-create.sh /
# cf-dns-create.sh. Anything outside it is rejected before any API call.
host_re='^[a-zA-Z0-9][a-zA-Z0-9.-]*$'
for h in "$zone_name" "$record_name"; do
  if [[ ! "$h" =~ $host_re ]]; then
    printf '%s\n' "ERROR: invalid hostname: $h" >&2
    exit 2
  fi
done

# If --type given, validate against the same set cf-dns-create.sh accepts.
if [[ -n "$type_filter" ]]; then
  case "$type_filter" in
    A|AAAA|CNAME|TXT|MX|NS|SRV|CAA) ;;
    *)
      printf '%s\n' "ERROR: unsupported record type: $type_filter (allowed: A AAAA CNAME TXT MX NS SRV CAA)" >&2
      exit 2
      ;;
  esac
fi

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

# Build the list query. Every user-supplied value that lands in the
# query string is URL-encoded, even the allowlist-validated type, to
# stay consistent with the repo-wide "encode everything from outside"
# convention. `match=all` is only meaningful with multiple filters but
# is harmless with one.
name_encoded=$(jq -rn --arg v "$record_name" '$v|@uri')
query="name=$name_encoded&match=all"
if [[ -n "$type_filter" ]]; then
  type_encoded=$(jq -rn --arg v "$type_filter" '$v|@uri')
  query="$query&type=$type_encoded"
fi
if [[ -n "$content_filter" ]]; then
  content_encoded=$(jq -rn --arg v "$content_filter" '$v|@uri')
  query="$query&content=$content_encoded"
fi

records_json=$(cf_api_paginated "/zones/$zone_id/dns_records?$query")

# shellcheck disable=SC2016  # single-quoted jq filter
matches_json=$(printf '%s' "$records_json" | jq '
  [.result[] | {id, type, name, content, proxied}]
')
match_count=$(printf '%s' "$matches_json" | jq 'length')

# Compose a human-readable selector for error messages.
selector="$record_name"
[[ -n "$type_filter" ]]    && selector="$selector type=$type_filter"
[[ -n "$content_filter" ]] && selector="$selector content=$content_filter"

if (( match_count == 0 )); then
  printf '%s\n' "ERROR: no DNS record matching '$selector' on zone $zone_name (nothing to delete)" >&2
  exit 1
fi
if (( match_count > 1 )); then
  printf '%s\n' "ERROR: ambiguous match on zone $zone_name: '$selector' matches $match_count records" >&2
  printf '%s\n' "$matches_json" | jq -r '.[] | "  - \(.id)  \(.type)  \(.content)"' >&2
  printf '%s\n' "       narrow with --type=TYPE and/or --content=VALUE." >&2
  exit 1
fi

record_id=$(printf '%s' "$matches_json" | jq -r '.[0].id')
record_type=$(printf '%s' "$matches_json" | jq -r '.[0].type')
record_content=$(printf '%s' "$matches_json" | jq -r '.[0].content')
record_proxied=$(printf '%s' "$matches_json" | jq -r '.[0].proxied')

delete_path="/zones/$zone_id/dns_records/$record_id"

render_summary_kv() {
  printf -- '- **zone:** %s (id=%s)\n' "$zone_name" "$zone_id"
  printf -- '- **type:** %s\n' "$record_type"
  printf -- '- **name:** %s\n' "$record_name"
  printf -- '- **content:** %s\n' "$record_content"
  printf -- '- **proxied:** %s\n' "$record_proxied"
  printf -- '- **record_id:** %s\n' "$record_id"
  return 0
}

if (( apply == 0 )); then
  if [[ "$mode" == "json" ]]; then
    # shellcheck disable=SC2016  # single-quoted jq filter
    jq -n \
      --arg zone_id "$zone_id" \
      --arg record_id "$record_id" \
      --arg delete_path "$delete_path" \
      '{success: true, errors: [], messages: ["dry-run: no changes applied"],
        result: {dry_run: true, zone_id: $zone_id, record_id: $record_id,
                 would_delete: $delete_path}}'
    exit 0
  fi
  printf '**Dry-run — no changes applied**\n\n'
  render_summary_kv
  # shellcheck disable=SC2016  # literal backticks wrap markdown inline code
  printf '\n**would DELETE** `%s`\n' "$delete_path"
  exit 0
fi

# Apply path.
response=$(cf_api "$delete_path" -X DELETE)

if [[ "$mode" == "json" ]]; then
  printf '%s\n' "$response"
  exit 0
fi

printf '**DNS record deleted**\n\n'
render_summary_kv
