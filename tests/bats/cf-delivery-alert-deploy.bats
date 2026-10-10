#!/usr/bin/env bats

load test_helper

setup() {
  cf_bats_setup
  WRITE_SCRIPTS="$SKILL_DIR/../cfafi-write/scripts"
  export ALERT_SHARED_SECRET="unit-test-secret-value"
  ARGS=(delivery-alert --from=alerts@example.test --recipients=a@example.test,b@example.test --compatibility-date=2026-04-20)
}

@test "dry-run makes no API call, redacts secret, shows bindings" {
  run bash "$WRITE_SCRIPTS/cf-delivery-alert-deploy.sh" "${ARGS[@]}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Dry-run"* ]]
  [[ "$output" == *'"type": "send_email"'* ]]
  [[ "$output" == *"ALERT_RECIPIENTS"* ]]
  [[ "$output" == *"a@example.test,b@example.test"* ]]
  [[ "$output" != *"unit-test-secret-value"* ]]
  [ ! -s "$BATS_TEST_TMPDIR/curl.log" ]
}

@test "dry-run --json is redacted and flags secret_set" {
  run bash "$WRITE_SCRIPTS/cf-delivery-alert-deploy.sh" "${ARGS[@]}" --json
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.result.secret_set == true'
  echo "$output" | jq -e '.result.would_put.metadata.bindings | map(select(.name=="ALERT_SECRET"))[0].text == "<redacted>"'
  [[ "$output" != *"unit-test-secret-value"* ]]
}

@test "--apply PUTs multipart with send_email binding and enables subdomain" {
  cf_mock "/workers/scripts/delivery-alert"           "workers_script_create_ok.json"
  cf_mock "/workers/scripts/delivery-alert/subdomain" "workers_script_subdomain_enabled.json"
  run bash "$WRITE_SCRIPTS/cf-delivery-alert-deploy.sh" "${ARGS[@]}" --apply
  [ "$status" -eq 0 ]
  [[ "$output" == *"deployed"* ]]
  [[ "$output" != *"unit-test-secret-value"* ]]
  cf_assert_called "-X	PUT"
  cf_assert_called "metadata=@"
  cf_assert_called ";filename=worker.js"
  cf_assert_called "/workers/scripts/delivery-alert/subdomain"
  # secret travels in a temp file, never in argv
  ! grep -qF "unit-test-secret-value" "$BATS_TEST_TMPDIR/curl.log"
}

@test "--apply without secret exits 1 and calls nothing" {
  unset ALERT_SHARED_SECRET
  run bash "$WRITE_SCRIPTS/cf-delivery-alert-deploy.sh" "${ARGS[@]}" --apply
  [ "$status" -eq 1 ]
  [[ "$output" == *"empty or unset"* ]]
  [ ! -s "$BATS_TEST_TMPDIR/curl.log" ]
}

@test "usage errors exit 2" {
  run bash "$WRITE_SCRIPTS/cf-delivery-alert-deploy.sh" delivery-alert --recipients=a@example.test
  [ "$status" -eq 2 ]
  run bash "$WRITE_SCRIPTS/cf-delivery-alert-deploy.sh" delivery-alert --from=alerts@example.test
  [ "$status" -eq 2 ]
  run bash "$WRITE_SCRIPTS/cf-delivery-alert-deploy.sh" delivery-alert --from=alerts@example.test --recipients=notanemail
  [ "$status" -eq 2 ]
  run bash "$WRITE_SCRIPTS/cf-delivery-alert-deploy.sh" "${ARGS[@]}" --bogus
  [ "$status" -eq 2 ]
}
