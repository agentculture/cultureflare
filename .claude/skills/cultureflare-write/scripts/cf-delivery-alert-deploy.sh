#!/usr/bin/env bash
# Deploy the delivery-alert Worker (templates/delivery-alert.js).
#
# Usage:
#   ALERT_SHARED_SECRET=... cf-delivery-alert-deploy.sh NAME \
#     --from=ADDR --recipients=ADDR[,ADDR...] [flags]
#
# Default is DRY-RUN: prints the metadata (bindings, secret REDACTED) that
# would be sent and makes NO API call at all. Pass --apply to PUT the
# script (idempotent: re-running updates the same Worker), then set the
# workers.dev subdomain state.
#
# Prerequisites for --apply:
#   * CLOUDFLARE_API_TOKEN has Account · Workers Scripts · Edit
#   * Email Routing enabled on the sender's zone; every recipient is a
#     VERIFIED destination address (the send_email binding refuses others)
#
# The shared secret is read from an env var (never argv, never printed).
#
# Flags:
#   --from=ADDR               sender address (ALERT_FROM), e.g. on culture.dev
#   --recipients=A,B          comma-separated verified destinations
#                             (ALERT_RECIPIENTS). Never read from requests.
#   --secret-env=VAR          env var holding the bearer secret
#                             (default: ALERT_SHARED_SECRET)
#   --from-file=PATH          Worker source (default: the delivery-alert.js
#                             template next to this script)
#   --compatibility-date=DATE YYYY-MM-DD (default: today)
#   --no-workers-dev          disable the NAME.<account>.workers.dev subdomain
#   --apply                   actually deploy (without it, dry-run)
#   --json                    JSON output
#
# Bindings created: ALERT_EMAIL (send_email), ALERT_FROM + ALERT_RECIPIENTS
# (plain_text), ALERT_SECRET (secret_text).
#
# Exits 1 on missing secret (--apply), missing file, or API error.
# Exits 2 on usage error.

set -euo pipefail
shopt -s inherit_errexit

mode=md
apply=0
from_addr=""
recipients=""
secret_env="ALERT_SHARED_SECRET"
from_file="$(dirname "${BASH_SOURCE[0]}")/../templates/delivery-alert.js"
compat_date=""
workers_dev=1
positional=()

for arg in "$@"; do
  case "$arg" in
    --json)                 mode=json ;;
    --apply)                apply=1 ;;
    --from=*)               from_addr="${arg#*=}" ;;
    --recipients=*)         recipients="${arg#*=}" ;;
    --secret-env=*)         secret_env="${arg#*=}" ;;
    --from-file=*)          from_file="${arg#*=}" ;;
    --compatibility-date=*) compat_date="${arg#*=}" ;;
    --no-workers-dev)       workers_dev=0 ;;
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
  echo "ERROR: expected NAME positional arg, got ${#positional[@]}" >&2
  echo "usage: cf-delivery-alert-deploy.sh NAME --from=ADDR --recipients=A,B [flags]" >&2
  exit 2
fi
name="${positional[0]}"
if [[ ! "$name" =~ ^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?$ ]]; then
  echo "ERROR: invalid worker name: $name" >&2
  exit 2
fi

email_re='^[^[:space:],@]+@[^[:space:],@]+\.[^[:space:],@]+$'
if [[ -z "$from_addr" || ! "$from_addr" =~ $email_re ]]; then
  echo "ERROR: --from=ADDR is required and must be an email address" >&2
  exit 2
fi
if [[ -z "$recipients" ]]; then
  echo "ERROR: --recipients=A,B is required" >&2
  exit 2
fi
IFS=',' read -r -a rcpt_arr <<< "$recipients"
rcpt_clean=()
for r in "${rcpt_arr[@]}"; do
  r="${r//[[:space:]]/}"
  if [[ ! "$r" =~ $email_re ]]; then
    echo "ERROR: invalid recipient address in --recipients" >&2
    exit 2
  fi
  rcpt_clean+=("$r")
done
recipients_csv=$(IFS=','; printf '%s' "${rcpt_clean[*]}")

if [[ ! "$secret_env" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "ERROR: --secret-env must be a valid env var name" >&2
  exit 2
fi
secret="${!secret_env:-}"

if [[ ! -f "$from_file" ]]; then
  echo "ERROR: --from-file not found or not a regular file: $from_file" >&2
  exit 1
fi
if [[ -z "$compat_date" ]]; then
  compat_date=$(date -u +%Y-%m-%d)
fi
if [[ ! "$compat_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: --compatibility-date must be YYYY-MM-DD, got: $compat_date" >&2
  exit 2
fi

# shellcheck source=../../cultureflare/scripts/_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
cf_require_account_id

# build_metadata SECRET_VALUE — emits the upload metadata JSON.
build_metadata() {
  local secret_value="$1"
  # shellcheck disable=SC2016  # single-quoted jq filter
  jq -n --arg date "$compat_date" --arg from "$from_addr" \
        --arg rcpt "$recipients_csv" --arg secret "$secret_value" \
    '{main_module: "worker.js", compatibility_date: $date,
      bindings: [
        {type: "send_email", name: "ALERT_EMAIL"},
        {type: "plain_text",  name: "ALERT_FROM",       text: $from},
        {type: "plain_text",  name: "ALERT_RECIPIENTS", text: $rcpt},
        {type: "secret_text", name: "ALERT_SECRET",     text: $secret}
      ]}'
}

if (( apply == 0 )); then
  redacted=$(build_metadata "<redacted>")
  if [[ "$mode" == "json" ]]; then
    # shellcheck disable=SC2016  # single-quoted jq filter
    jq -n --argjson metadata "$redacted" --arg name "$name" \
          --arg account "$CLOUDFLARE_ACCOUNT_ID" \
          --arg secret_env "$secret_env" \
          --argjson secret_set "$([[ -n "$secret" ]] && echo true || echo false)" \
      '{success: true, errors: [], messages: ["dry-run: no changes applied"],
        result: {dry_run: true, account_id: $account, name: $name,
                 secret_env: $secret_env, secret_set: $secret_set,
                 would_put: {metadata: $metadata}}}'
    exit 0
  fi
  printf '**Dry-run — no changes applied (no API calls made)**\n\n'
  printf -- '- **name:** %s\n- **account:** %s\n' "$name" "$CLOUDFLARE_ACCOUNT_ID"
  printf -- '- **secret env var:** %s (%s)\n' "$secret_env" "$([[ -n "$secret" ]] && echo set || echo NOT SET)"
  # shellcheck disable=SC2016  # literal backticks wrap markdown inline code
  printf '\n**would PUT** `/accounts/%s/workers/scripts/%s`\n\n' "$CLOUDFLARE_ACCOUNT_ID" "$name"
  # shellcheck disable=SC2016  # literal backticks fence a markdown code block
  printf 'metadata (secret redacted):\n\n```json\n%s\n```\n' "$redacted"
  exit 0
fi

if [[ -z "$secret" ]]; then
  echo "ERROR: env var $secret_env is empty or unset; refusing to deploy without a secret" >&2
  exit 1
fi

meta_tmp=$(mktemp "${TMPDIR:-/tmp}/cf-delivery-alert-metadata.XXXXXX.json")
trap 'rm -f "$meta_tmp"' EXIT
build_metadata "$secret" > "$meta_tmp"

# `;filename=worker.js` is required, see cf-worker-create.sh for why.
response=$(curl -sS -X PUT \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -F "metadata=@$meta_tmp;type=application/json;filename=metadata.json" \
  -F "worker.js=@$from_file;type=application/javascript+module;filename=worker.js" \
  "$CF_API_BASE/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$name")

if ! printf '%s' "$response" | jq -e '.success == true' >/dev/null 2>&1; then
  echo "ERROR: CloudFlare API request failed: PUT /accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$name" >&2
  printf '%s' "$response" | jq '.errors // .' >&2 || printf '%s\n' "$response" >&2
  exit 1
fi

subdomain_body=$(jq -n --argjson enabled "$workers_dev" \
  '{enabled: ($enabled == 1), previews_enabled: false}')
subdomain_response=$(cf_api \
  "/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$name/subdomain" \
  -X POST --data-binary "$subdomain_body")

if [[ "$mode" == "json" ]]; then
  jq -n --argjson upload "$response" --argjson subdomain "$subdomain_response" \
    '{success: true, errors: [], messages: [],
      result: {upload: $upload.result, subdomain: $subdomain.result}}'
  exit 0
fi

printf '**Delivery-alert Worker deployed**\n\n'
printf -- '- **name:** %s\n' "$name"
printf -- '- **etag:** %s\n' "$(printf '%s' "$response" | jq -r '.result.etag // "—"')"
printf -- '- **workers_dev_enabled:** %s\n' "$(printf '%s' "$subdomain_response" | jq -r '.result.enabled')"
