#!/usr/bin/env bats

load test_helper

setup() {
  cf_bats_setup
  WRITE_SCRIPTS="$SKILL_DIR/../cfafi-write/scripts"
  # Project-detail GET and deployments POST share the
  # /accounts/.../pages/projects/culture-dev/... prefix; the stub's
  # longest-substring-wins policy disambiguates by URL suffix
  # (".../deployments" beats ".../culture-dev").
}

_assert_no_post() {
  if grep -qF -- '-X	POST' "$BATS_TEST_TMPDIR/curl.log" 2>/dev/null; then
    echo "expected no POST, but curl.log contains one:" >&2
    cat "$BATS_TEST_TMPDIR/curl.log" >&2
    return 1
  fi
  return 0
}

# --- usage errors ---

@test "cf-pages-deployment-create exits 2 when PROJECT missing" {
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh"
  [ "$status" -eq 2 ]
  [[ "$output" == *"expected exactly one PROJECT"* ]]
}

@test "cf-pages-deployment-create exits 2 on unknown flag" {
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --bogus
  [ "$status" -eq 2 ]
  [[ "$output" == *"unknown flag"* ]]
}

@test "cf-pages-deployment-create exits 2 on invalid project name" {
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" 'bad name!'
  [ "$status" -eq 2 ]
  [[ "$output" == *"invalid project name"* ]]
}

@test "cf-pages-deployment-create exits 2 on invalid --branch" {
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --branch='bad branch!'
  [ "$status" -eq 2 ]
  [[ "$output" == *"invalid --branch"* ]]
}

# --- dry-run ---

@test "cf-pages-deployment-create dry-run defaults to production_branch, no POST" {
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev
  [ "$status" -eq 0 ]
  [[ "$output" == *"**Dry-run — no changes applied**"* ]]
  [[ "$output" == *"**branch:** main"* ]]
  [[ "$output" == *"**environment:** production"* ]]
  [[ "$output" == *"would POST"* ]]
  [[ "$output" == *"/pages/projects/culture-dev/deployments"* ]]
  [[ "$output" == *"(branch=main)"* ]]
  _assert_no_post
}

@test "cf-pages-deployment-create dry-run with --branch on non-prod branch → preview" {
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --branch=feat/x
  [ "$status" -eq 0 ]
  [[ "$output" == *"**branch:** feat/x"* ]]
  [[ "$output" == *"**environment:** preview"* ]]
  # Preview predicts the branch-alias URL (feat/x → feat-x).
  [[ "$output" == *"**predicted alias:** https://feat-x.culture-dev.pages.dev"* ]]
  [[ "$output" == *"(branch=feat/x)"* ]]
  _assert_no_post
}

@test "cf-pages-deployment-create production dry-run has no predicted alias" {
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev
  [ "$status" -eq 0 ]
  [[ "$output" != *"predicted alias"* ]]
  _assert_no_post
}

@test "cf-pages-deployment-create --json dry-run preview carries predicted_alias" {
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --branch=feat/x --json
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | jq -e '.result.environment == "preview"'
  printf '%s\n' "$output" | jq -e '.result.predicted_alias == "https://feat-x.culture-dev.pages.dev"'
  _assert_no_post
}

@test "cf-pages-deployment-create preview with a punctuation-only branch emits no alias" {
  # A branch like '---' normalizes to an empty label; we must not emit
  # "https://.<subdomain>". Still a preview (branch != production_branch).
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --branch=---
  [ "$status" -eq 0 ]
  [[ "$output" == *"**environment:** preview"* ]]
  [[ "$output" != *"predicted alias"* ]]
  [[ "$output" != *"https://."* ]]
  _assert_no_post
}

@test "cf-pages-deployment-create --json preview punctuation-only branch omits predicted_alias" {
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --branch=--- --json
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | jq -e '.result.environment == "preview"'
  printf '%s\n' "$output" | jq -e 'has("result") and (.result | has("predicted_alias") | not)'
  _assert_no_post
}

@test "cf-pages-deployment-create --json dry-run emits synthetic envelope" {
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --json
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | jq -e '.success == true'
  printf '%s\n' "$output" | jq -e '.result.dry_run == true'
  printf '%s\n' "$output" | jq -e '.result.branch == "main"'
  printf '%s\n' "$output" | jq -e '.result.environment == "production"'
  _assert_no_post
}

# --- direct-upload guard ---

@test "cf-pages-deployment-create refuses a Direct Upload project" {
  # agentirc-dev detail has source: null (Direct Upload).
  cf_mock "/pages/projects/agentirc-dev" "pages_project_agentirc_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" agentirc-dev --apply
  [ "$status" -eq 1 ]
  [[ "$output" == *"no git source"* ]]
  _assert_no_post
}

# --- project not found ---

@test "cf-pages-deployment-create exits 1 when project not found" {
  cf_mock "/pages/projects/nope" "pages_project_not_found.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" nope
  [ "$status" -eq 1 ]
  _assert_no_post
}

# --- apply path ---

@test "cf-pages-deployment-create --apply POSTs branch form field and reports deployment" {
  cf_mock "/pages/projects/culture-dev/deployments" "pages_deployment_create_ok.json"
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --apply
  [ "$status" -eq 0 ]
  [[ "$output" == *"**Deployment triggered**"* ]]
  [[ "$output" == *"8313565b"* ]]
  [[ "$output" == *"**stage:** queued/idle"* ]]
  cf_assert_called '-X	POST'
  cf_assert_called 'branch=main'
}

@test "cf-pages-deployment-create --apply preview surfaces authoritative aliases" {
  cf_mock "/pages/projects/culture-dev/deployments" "pages_deployment_create_preview_ok.json"
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --branch=feat/x --apply
  [ "$status" -eq 0 ]
  [[ "$output" == *"**environment:** preview"* ]]
  # CF's authoritative alias from the response, not a prediction.
  [[ "$output" == *"**aliases:** https://feat-x.culture-dev.pages.dev"* ]]
  cf_assert_called 'branch=feat/x'
}

@test "cf-pages-deployment-create --apply production has no alias line" {
  cf_mock "/pages/projects/culture-dev/deployments" "pages_deployment_create_ok.json"
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --apply
  [ "$status" -eq 0 ]
  [[ "$output" != *"**aliases:**"* ]]
}

@test "cf-pages-deployment-create --apply --json passes response through" {
  cf_mock "/pages/projects/culture-dev/deployments" "pages_deployment_create_ok.json"
  cf_mock "/pages/projects/culture-dev" "pages_project_culture_dev_detail.json"
  run bash "$WRITE_SCRIPTS/cf-pages-deployment-create.sh" culture-dev --apply --json
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | jq -e '.success == true'
  printf '%s\n' "$output" | jq -e '.result.id == "8313565b-e95b-4804-b457-4c1a11b5fd19"'
}
