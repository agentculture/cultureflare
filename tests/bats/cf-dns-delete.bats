#!/usr/bin/env bats

load test_helper

setup() {
  cf_bats_setup
  WRITE_SCRIPTS="$SKILL_DIR/../cfafi-write/scripts"
}

# Helper — asserts curl was NEVER invoked with `-X DELETE`.
_assert_no_delete() {
  if grep -qF -- '-X	DELETE' "$BATS_TEST_TMPDIR/curl.log" 2>/dev/null; then
    echo "expected no DELETE, but curl.log contains one:" >&2
    cat "$BATS_TEST_TMPDIR/curl.log" >&2
    return 1
  fi
  return 0
}

# --- usage errors ---

@test "cf-dns-delete exits 2 when positional args missing" {
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev
  [ "$status" -eq 2 ]
  [[ "$output" == *"expected ZONE and NAME"* ]]
}

@test "cf-dns-delete exits 2 on unknown flag" {
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev agex.culture.dev --bogus
  [ "$status" -eq 2 ]
  [[ "$output" == *"unknown flag"* ]]
}

@test "cf-dns-delete exits 2 on invalid hostname" {
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev 'bad name!'
  [ "$status" -eq 2 ]
  [[ "$output" == *"invalid hostname"* ]]
}

@test "cf-dns-delete exits 2 on unsupported --type" {
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev agex.culture.dev --type=BOGUS
  [ "$status" -eq 2 ]
  [[ "$output" == *"unsupported record type"* ]]
}

# --- resolution errors ---

@test "cf-dns-delete exits 1 when the zone is not in the account" {
  cf_mock "/zones?per_page" "zones_with_agentculture.json"
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" nosuch.dev agex.nosuch.dev --apply
  [ "$status" -eq 1 ]
  [[ "$output" == *"zone nosuch.dev not found"* ]]
  _assert_no_delete
}

@test "cf-dns-delete exits 1 when no record matches (nothing to delete)" {
  cf_mock "/zones?per_page"   "zones_with_agentculture.json"
  cf_mock "/dns_records?"     "dns_records_empty.json"
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev agex.culture.dev --apply
  [ "$status" -eq 1 ]
  [[ "$output" == *"no DNS record matching"* ]]
  [[ "$output" == *"nothing to delete"* ]]
  _assert_no_delete
}

@test "cf-dns-delete exits 1 on an ambiguous match and lists candidates" {
  cf_mock "/zones?per_page"   "zones_with_agentculture.json"
  cf_mock "/dns_records?"     "dns_records.json"
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev culture.dev
  [ "$status" -eq 1 ]
  [[ "$output" == *"ambiguous match"* ]]
  [[ "$output" == *"narrow with --type"* ]]
  _assert_no_delete
}

# --- dry-run (default, no --apply) ---

@test "cf-dns-delete dry-run prints banner, resolved record, and would-DELETE path" {
  cf_mock "/zones?per_page"   "zones_with_agentculture.json"
  cf_mock "/dns_records?"     "dns_records_agex_cname.json"
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev agex.culture.dev
  [ "$status" -eq 0 ]
  [[ "$output" == *"**Dry-run — no changes applied**"* ]]
  [[ "$output" == *"zone-id-culture-dev-bbbbbbbbbbbbbbbbbbbb"* ]]
  [[ "$output" == *"**type:** CNAME"* ]]
  [[ "$output" == *"dns-rec-agex-cname-000000000000000a"* ]]
  [[ "$output" == *"**would DELETE**"* ]]
  [[ "$output" == *"/dns_records/dns-rec-agex-cname-000000000000000a"* ]]
  _assert_no_delete
}

@test "cf-dns-delete --json dry-run emits a synthetic envelope" {
  cf_mock "/zones?per_page"   "zones_with_agentculture.json"
  cf_mock "/dns_records?"     "dns_records_agex_cname.json"
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev agex.culture.dev --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.success == true'
  echo "$output" | jq -e '.result.dry_run == true'
  echo "$output" | jq -e '.result.record_id == "dns-rec-agex-cname-000000000000000a"'
  echo "$output" | jq -e '.result.would_delete | endswith("/dns_records/dns-rec-agex-cname-000000000000000a")'
  [[ "$output" != *"Dry-run — no changes applied"* ]]
  _assert_no_delete
}

# --- apply path ---

@test "cf-dns-delete --apply DELETEs the resolved record id" {
  cf_mock "/zones?per_page" "zones_with_agentculture.json"
  cf_mock "/dns_records?"   "dns_records_agex_cname.json"
  cf_mock "/dns_records/dns-rec-agex-cname-000000000000000a" "dns_record_delete_ok.json"
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev agex.culture.dev --apply
  [ "$status" -eq 0 ]
  [[ "$output" == *"**DNS record deleted**"* ]]
  cf_assert_called "-X	DELETE"
  cf_assert_called "/zones/zone-id-culture-dev-bbbbbbbbbbbbbbbbbbbb/dns_records/dns-rec-agex-cname-000000000000000a"
}

@test "cf-dns-delete --apply --json passes the CF response envelope through" {
  cf_mock "/zones?per_page" "zones_with_agentculture.json"
  cf_mock "/dns_records?"   "dns_records_agex_cname.json"
  cf_mock "/dns_records/dns-rec-agex-cname-000000000000000a" "dns_record_delete_ok.json"
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev agex.culture.dev --apply --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.success == true'
  echo "$output" | jq -e '.result.id == "dns-rec-agex-cname-000000000000000a"'
  [[ "$output" != *"DNS record deleted"* ]]
}

# --- name resolution uses pagination ---

@test "cf-dns-delete resolves the zone via paginated /zones" {
  cf_mock "/zones?per_page" "zones_with_agentculture.json"
  cf_mock "/dns_records?"   "dns_records_agex_cname.json"
  run bash "$WRITE_SCRIPTS/cf-dns-delete.sh" culture.dev agex.culture.dev
  [ "$status" -eq 0 ]
  cf_assert_called "/zones?per_page=50&page=1"
}
