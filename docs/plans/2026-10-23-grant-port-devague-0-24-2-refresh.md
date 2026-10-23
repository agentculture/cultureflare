# Build Plan — grant port + devague 0.24.2 refresh

slug: `grant-port-devague-0-24-2-refresh` · status: `exported` · from frame: `grant-port-devague-0-24-2-refresh`

> cultureflare 0.17.0 seals remote-login secrets into grant (the renamed shushu) instead of a binary that no longer exists, and ships the full eight-leg devague 0.24.2 workflow skills (incl. /validate-delivery and obligations/evidence)

## Tasks

### t1 — Port the secret sink to grant: new cultureflare/`_secrets`/`_grant_sink.py` (argv\[0\]='grant', hints/remediations name grant + 'uv tool install grant'); `_shushu_sink.py` becomes a sys.modules alias of `_grant_sink`; `_types.py` gains GrantTarget with ShushuTarget = GrantTarget; tests renamed/updated (`test_secrets_grant_sink.py`, `test_secrets_types.py`, integration test gated on `GRANT_INTEGRATION` + which('grant')) plus a fake-'grant'-on-PATH test

- covers: c2, h2, c7, h6, c6, h15
- acceptance:
  - test asserts set/show/delete argv\[0\]=='grant' and \['sudo','-n','grant',...,'--user',U,...\] when a user is set; secret bytes arrive on stdin, never in argv
  - a test prepends a tmp dir holding an executable fake 'grant' (records argv+stdin to a file) to PATH, calls seal() with real subprocess, and asserts the recorded argv and stdin
  - FileNotFoundError maps to a CfafiError whose message says 'grant binary not found' and remediation names 'uv tool install grant'; no 'shushu' literal remains in any exec'd argv or install hint
  - 'cultureflare.`_secrets`.`_shushu_sink` is cultureflare.`_secrets`.`_grant_sink`' and ShushuTarget is GrantTarget; tests/`test_back_compat.py` passes unchanged

### t2 — Guard the tunnel token shape: cultureflare/`_remote_login`/`_tunnel.py` `get_tunnel_token` raises CfafiError unless result base64-decodes to JSON with keys a/s/t (error text never contains the value); tests/`test_remote_login_tunnel.py` and the 'TUN-TOK' token stubs in tests/`test_remote_login_orchestrator.py` switch to a realistic base64(json{a,s,t}) fixture

- covers: c9, h7
- acceptance:
  - a test with base64(json.dumps({'a':..,'s':..,'t':..})) returns the value unchanged
  - tests with a non-base64 value, base64 non-JSON, and JSON missing 't' each raise CfafiError and the raised message does not contain the input value
  - full pytest suite passes after the orchestrator stubs change

### t3 — Re-vendor the eight devague skills from guildmaster origin/main f0ea1b3 into .claude/skills/{scope,think,challenge,spec-to-plan,assign-to-workforce,deviate,validate-delivery,summarize-delivery}/ and re-apply local divergences: 'type: command' in each SKILL.md frontmatter; \[\[ \]\] (S7688) and positional-params-to-locals (S7679) in the three scripts; '# shellcheck disable=SC2016' at assign-to-workforce.sh's SC2016 sites

- covers: c11, h8, c12, h9
- acceptance:
  - for each of the eight skills, diff -r against the guildmaster f0ea1b3 tree shows only: the added 'type: command' frontmatter line, \[ -> \[\[ conversions, positional-param local assignments, and shellcheck disable comments
  - shellcheck -e SC1091 passes on think.sh, spec-to-plan.sh, assign-to-workforce.sh, and 'grep -nE "(^|\[^\[\])\[ " ' finds no single-bracket tests in them
  - every '/validate-delivery' mention under .claude/skills resolves to .claude/skills/validate-delivery/SKILL.md; markdownlint-cli2 passes on the eight SKILL.md files

### t4 — Fix CI hygiene: tests/shellcheck.sh and the markdownlint-cli2 config skip .claude/skills/ask-colleague/ (vendored from colleague; bytes untouched); .gitignore gains '.devague/' and 'docs/plans/\*-split.md' (replacing devague's auto-added .devague/questions/ + .devague/reviews/ lines); file one upstream issue on agentculture/colleague listing SC2046/SC2016 (ask-colleague.sh:430,841,847,854) and MD041/MD032 (prompts/\*.md)

- covers: c21, h12, c22, h13
- acceptance:
  - bash tests/shellcheck.sh and bash tests/markdownlint.sh both exit 0 on the branch, and git diff origin/main -- .claude/skills/ask-colleague is empty
  - git check-ignore .devague/current docs/plans/x-split.md reports both paths ignored
  - the upstream colleague issue URL is recorded for the CHANGELOG/PR body

### t5 — Validate grant names in the seal plan: cultureflare/`_remote_login`/`_seal_plan.py` `derive_seal_plan` accepts `grant_arg` (`shushu_arg` kept as a keyword alias), refuses any derived name not matching ^\[A-`Z_`\]\[A-Z0-`9_`\]{0,63}$ with a user-error CfafiError naming the offending name, and `_rotate_howto` embeds '--grant\[=USER\]'; tests in tests/`test_remote_login_seal_plan.py`

- depends on: t1
- covers: c5, h5, c6, h15
- acceptance:
  - a hostname of 39+ chars and a hostname containing an unmappable char each raise CfafiError (`EXIT_USER_ERROR`) from `derive_seal_plan` with the derived name in the message, before any HTTP stub is called
  - `derive_seal_plan`(hostname=..., `grant_arg`='alice') and (..., `shushu_arg`='alice') return equal plans; tests/`test_back_compat.py` passes unchanged
  - metadata `rotate_howto` contains '--grant' and not '--shushu'

### t6 — Rename markers and step names in the orchestrator + renderer: cultureflare/`_remote_login`/`__init__.py` builds 'grant/USER/NAME' markers and step names 'grant-tunnel-token' / 'grant-svc-secret', calls `_grant_sink`, partial-seal remediation names --grant; `_render.py` dry-run lines and '?? (grant not installed)'; update tests/`test_remote_login_orchestrator.py`, `test_remote_login_render.py`, `test_remote_login_common.py`

- depends on: t5, t2
- covers: c4, h22, c20, h11, c7, h6
- acceptance:
  - orchestrator tests assert steps named grant-tunnel-token / grant-svc-secret and `sealed_in` values 'grant/<user>/<NAME>'
  - render tests assert Markdown '<sealed: grant/alice/`CULTUREFLARE_APP_EXAMPLE_COM_TUNNEL_TOKEN`>' and dry-run 'seal `tunnel_token` into grant/...' lines
  - grep -n shushu cultureflare/`_remote_login`/`__init__.py` cultureflare/`_remote_login`/`_render.py` returns nothing

### t7 — Add --grant\[=USER\] to the remote-login CLI: cultureflare/cli/`_commands`/`remote_login.py` declares --grant on setup/show/teardown with --shushu as a deprecated alias to the same dest (stderr-only deprecation note), help text and dry-run `sealed_in` markers use grant/; tests in tests/`test_cli_remote_login.py`

- depends on: t5
- covers: c3, h3, c4, h22
- acceptance:
  - for each verb, '--grant', '--grant=alice', '--shushu', '--shushu=alice' parse to the same seal user as the grant spelling
  - --shushu prints exactly one deprecation line to stderr and nothing extra on --json stdout (stdout parses as JSON)
  - dry-run --json `sealed_in` markers start with 'grant/'

### t8 — Release bookkeeping: bump 0.16.0 -> 0.17.0 via .claude/skills/version-bump/scripts/bump.py minor (pyproject.toml, cultureflare/`__init__.py`, CHANGELOG entry covering the grant port, step-name rename, token guard, skills refresh, CI fix, upstream colleague issue URL); rewrite CLAUDE.md's devague section to list all eight skills in flow order pinned to guildmaster f0ea1b3 / devague 0.24.2 (78d9bfb); refresh uv.lock

- depends on: t1, t2, t3, t4, t5, t6, t7
- covers: c13, h10, c14, h16
- acceptance:
  - pyproject.toml and cultureflare/`__init__.py` both read 0.17.0 and CHANGELOG.md has a \[0.17.0\] entry naming the step-name rename as a change
  - CLAUDE.md names f0ea1b3, 0.24.2 and all eight skills; no '0.11.1 / c04b595' pin remains outside CHANGELOG history
  - git diff origin/main -- pyproject.toml shows 'dependencies = \[\]' unchanged; markdownlint passes on CLAUDE.md and CHANGELOG.md

### t9 — Final gate (main agent): full local suite (pytest, bats, tests/shellcheck.sh, tests/markdownlint.sh) green; a real 'cultureflare remote-login setup --hostname `TEST_HOST` --grant' DRY-RUN on spark renders grant/ markers; post the #55 comment with the non-reproduction evidence (no token value, signed); open the PR with 'Refs #55' via the cicd skill and drive CI (test, test-bash, version-check) to green

- depends on: t8
- covers: c1, h1, c23, h14, c15, h17, c16, h18, c17, h19, c18, h20, c19, h21
- acceptance:
  - local pytest, bats, shellcheck.sh and markdownlint.sh all exit 0 and their commands are recorded in the PR body
  - the dry-run output on spark shows '<sealed: grant/' markers and grant-\* step names, run with grant 0.11.0 present and no shushu on PATH
  - \#55 has the comment (no token value) and the PR body says 'Refs #55' with no closing keyword
  - PR CI jobs test, test-bash and version-check conclude success

## Risks

- [unknown_nonblocking] grant 0.11.0's '--user NAME' may self-escalate, making the sink's 'sudo -n' wrapper redundant or harmful; exit codes 65/66/67 unverified — resolve via grant explain/source during t1 and keep current mapping if unknown (task t1)
- [follow_up] \#55's 51-byte `tunnel_token` origin is unexplained; t2's guard turns any recurrence into a loud error instead of a silent bad token (task t2)
