#!/usr/bin/env bats

load test_helper

setup() {
  cf_bats_setup
  WRITE_SCRIPTS="$SKILL_DIR/../cfafi-write/scripts"
  # The ruleset-detail GET (/rulesets/<id>) and the per-rule DELETE
  # (/rulesets/<id>/rules/<rid>) share the /rulesets/<id> prefix; the
  # stub's longest-substring-wins policy routes the DELETE to its own
  # fixture as long as the rule-path mock is registered.
}

_assert_no_delete() {
  if grep -qF -- '-X	DELETE' "$BATS_TEST_TMPDIR/curl.log" 2>/dev/null; then
    echo "expected no DELETE, but curl.log contains one:" >&2
    cat "$BATS_TEST_TMPDIR/curl.log" >&2
    return 1
  fi
  return 0
}

# --- usage errors ---

@test "cf-redirect-delete exits 2 when positional args missing" {
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev
  [ "$status" -eq 2 ]
  [[ "$output" == *"expected ZONE and FROM_HOST"* ]]
}

@test "cf-redirect-delete exits 2 on unknown flag" {
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev --bogus
  [ "$status" -eq 2 ]
  [[ "$output" == *"unknown flag"* ]]
}

@test "cf-redirect-delete exits 2 on invalid hostname" {
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev 'has"quote'
  [ "$status" -eq 2 ]
  [[ "$output" == *"invalid hostname"* ]]
}

# --- resolution errors ---

@test "cf-redirect-delete exits 1 when the zone is not in the account" {
  cf_mock "/zones?per_page" "zones_with_agentculture.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" nosuch.dev agex.nosuch.dev --apply
  [ "$status" -eq 1 ]
  [[ "$output" == *"zone nosuch.dev not found"* ]]
  _assert_no_delete
}

@test "cf-redirect-delete exits 1 when the zone has no redirect ruleset" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_empty.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev --apply
  [ "$status" -eq 1 ]
  [[ "$output" == *"no redirect ruleset"* ]]
  _assert_no_delete
}

@test "cf-redirect-delete exits 1 when no rule matches the host (nothing to delete)" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001" "ruleset_detail_culture_dev.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev nope.culture.dev --apply
  [ "$status" -eq 1 ]
  [[ "$output" == *"no redirect rule for host 'nope.culture.dev'"* ]]
  _assert_no_delete
}

@test "cf-redirect-delete exits 1 cleanly when the ruleset detail has no rules array (null guard)" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001" "ruleset_detail_no_rules.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev --apply
  [ "$status" -eq 1 ]
  [[ "$output" == *"no redirect rule for host 'agex.culture.dev'"* ]]
  # The null guard must produce the controlled message, not a jq crash.
  [[ "$output" != *"Cannot iterate over null"* ]]
  _assert_no_delete
}

@test "cf-redirect-delete exits 1 on an ambiguous match and lists candidates" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001" "ruleset_detail_dup_agex.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev
  [ "$status" -eq 1 ]
  [[ "$output" == *"ambiguous match"* ]]
  [[ "$output" == *"rule-agex-dup-a"* ]]
  [[ "$output" == *"rule-agex-dup-b"* ]]
  _assert_no_delete
}

# --- dry-run (default, no --apply) ---

@test "cf-redirect-delete dry-run prints the matched rule and would-DELETE path" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001" "ruleset_detail_culture_dev.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev
  [ "$status" -eq 0 ]
  [[ "$output" == *"**Dry-run — no changes applied**"* ]]
  [[ "$output" == *"rule-agex-0001"* ]]
  [[ "$output" == *'(http.host eq "agex.culture.dev")'* ]]
  [[ "$output" == *"culture.dev/agex"* ]]
  [[ "$output" == *"**status:** 301"* ]]
  [[ "$output" == *"**would DELETE**"* ]]
  [[ "$output" == *"/rulesets/redirect-ruleset-id-culturedev-0001/rules/rule-agex-0001"* ]]
  _assert_no_delete
}

@test "cf-redirect-delete --json dry-run emits a synthetic envelope" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001" "ruleset_detail_culture_dev.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.success == true'
  echo "$output" | jq -e '.result.dry_run == true'
  echo "$output" | jq -e '.result.rule_id == "rule-agex-0001"'
  echo "$output" | jq -e '.result.ruleset_id == "redirect-ruleset-id-culturedev-0001"'
  echo "$output" | jq -e '.result.would_delete | endswith("/rulesets/redirect-ruleset-id-culturedev-0001/rules/rule-agex-0001")'
  _assert_no_delete
}

# --- apply path ---

@test "cf-redirect-delete --apply DELETEs only the matched rule and preserves the others" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001" "ruleset_detail_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001/rules/rule-agex-0001" "ruleset_rule_delete_ok.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev --apply
  [ "$status" -eq 0 ]
  [[ "$output" == *"**Redirect rule deleted**"* ]]
  [[ "$output" == *"**remaining rules in ruleset:** 2"* ]]
  cf_assert_called "-X	DELETE"
  cf_assert_called "/rulesets/redirect-ruleset-id-culturedev-0001/rules/rule-agex-0001"
  # Preservation: the other two rules must never appear in a request path.
  ! grep -qF -- "/rules/rule-www-0002" "$BATS_TEST_TMPDIR/curl.log"
  ! grep -qF -- "/rules/rule-citation-0003" "$BATS_TEST_TMPDIR/curl.log"
}

@test "cf-redirect-delete --apply --json passes the CF response envelope through" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001" "ruleset_detail_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001/rules/rule-agex-0001" "ruleset_rule_delete_ok.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev --apply --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.success == true'
  echo "$output" | jq -e '.result.rules | length == 2'
  [[ "$output" != *"Redirect rule deleted"* ]]
}

# --- zone lookup uses pagination ---

@test "cf-redirect-delete resolves the zone via paginated /zones" {
  cf_mock "/zones?per_page"    "zones_with_agentculture.json"
  cf_mock "/rulesets?per_page" "rulesets_culture_dev.json"
  cf_mock "/rulesets/redirect-ruleset-id-culturedev-0001" "ruleset_detail_culture_dev.json"
  run bash "$WRITE_SCRIPTS/cf-redirect-delete.sh" culture.dev agex.culture.dev
  [ "$status" -eq 0 ]
  cf_assert_called "/zones?per_page=50&page=1"
}
