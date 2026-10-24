# Delivery Summary — grant port + devague 0.24.2 refresh

plan: `grant-port-devague-0-24-2-refresh` · run: `complete` · date: `2026-10-23`
baseline: `devague summary skeleton`

## Intent

> cultureflare 0.17.0 seals remote-login secrets into grant (the renamed shushu) instead of a binary that no longer exists, and ships the full eight-leg devague 0.24.2 workflow skills (incl. /validate-delivery and obligations/evidence)

After: 'cultureflare remote-login setup --grant --apply' seals the tunnel token and service-token secret into grant under grant-valid names and 'show' renders '<sealed: grant/USER/NAME>'; agents here run the full eight-leg devague 0.24.2 flow including /validate-delivery; main's test-bash is green

## Planned Work

Quoted verbatim from the `devague summary` skeleton (plan `grant-port-devague-0-24-2-refresh`, 9 tasks, 5 waves):

- `t1` — Port the secret sink to grant: new cultureflare/`_secrets`/`_grant_sink.py` (argv\[0\]='grant', hints/remediations name grant + 'uv tool install grant'); `_shushu_sink.py` becomes a sys.modules alias of `_grant_sink`; `_types.py` gains GrantTarget with ShushuTarget = GrantTarget; tests renamed/updated (`test_secrets_grant_sink.py`, `test_secrets_types.py`, integration test gated on `GRANT_INTEGRATION` + which('grant')) plus a fake-'grant'-on-PATH test
- `t2` — Guard the tunnel token shape: cultureflare/`_remote_login`/`_tunnel.py` `get_tunnel_token` raises CfafiError unless result base64-decodes to JSON with keys a/s/t (error text never contains the value); tests/`test_remote_login_tunnel.py` and the 'TUN-TOK' token stubs in tests/`test_remote_login_orchestrator.py` switch to a realistic base64(json{a,s,t}) fixture
- `t3` — Re-vendor the eight devague skills from guildmaster origin/main f0ea1b3 into .claude/skills/{scope,think,challenge,spec-to-plan,assign-to-workforce,deviate,validate-delivery,summarize-delivery}/ and re-apply local divergences: 'type: command' in each SKILL.md frontmatter; \[\[ \]\] (S7688) and positional-params-to-locals (S7679) in the three scripts; '# shellcheck disable=SC2016' at assign-to-workforce.sh's SC2016 sites
- `t4` — Fix CI hygiene: tests/shellcheck.sh and the markdownlint-cli2 config skip .claude/skills/ask-colleague/ (vendored from colleague; bytes untouched); .gitignore gains '.devague/' and 'docs/plans/\*-split.md' (replacing devague's auto-added .devague/questions/ + .devague/reviews/ lines); file one upstream issue on agentculture/colleague listing SC2046/SC2016 (ask-colleague.sh:430,841,847,854) and MD041/MD032 (prompts/\*.md)
- `t5` — Validate grant names in the seal plan: cultureflare/`_remote_login`/`_seal_plan.py` `derive_seal_plan` accepts `grant_arg` (`shushu_arg` kept as a keyword alias), refuses any derived name not matching ^\[A-`Z_`\]\[A-Z0-`9_`\]{0,63}$ with a user-error CfafiError naming the offending name, and `_rotate_howto` embeds '--grant\[=USER\]'; tests in tests/`test_remote_login_seal_plan.py`
- `t6` — Rename markers and step names in the orchestrator + renderer: cultureflare/`_remote_login`/`__init__.py` builds 'grant/USER/NAME' markers and step names 'grant-tunnel-token' / 'grant-svc-secret', calls `_grant_sink`, partial-seal remediation names --grant; `_render.py` dry-run lines and '?? (grant not installed)'; update tests/`test_remote_login_orchestrator.py`, `test_remote_login_render.py`, `test_remote_login_common.py`
- `t7` — Add --grant\[=USER\] to the remote-login CLI: cultureflare/cli/`_commands`/`remote_login.py` declares --grant on setup/show/teardown with --shushu as a deprecated alias to the same dest (stderr-only deprecation note), help text and dry-run `sealed_in` markers use grant/; tests in tests/`test_cli_remote_login.py`
- `t8` — Release bookkeeping: bump 0.16.0 -> 0.17.0 via .claude/skills/version-bump/scripts/bump.py minor (pyproject.toml, cultureflare/`__init__.py`, CHANGELOG entry covering the grant port, step-name rename, token guard, skills refresh, CI fix, upstream colleague issue URL); rewrite CLAUDE.md's devague section to list all eight skills in flow order pinned to guildmaster f0ea1b3 / devague 0.24.2 (78d9bfb); refresh uv.lock
- `t9` — Final gate (main agent): full local suite (pytest, bats, tests/shellcheck.sh, tests/markdownlint.sh) green; a real 'cultureflare remote-login setup --hostname `TEST_HOST` --grant' DRY-RUN on spark renders grant/ markers; post the #55 comment with the non-reproduction evidence (no token value, signed); open the PR with 'Refs #55' via the cicd skill and drive CI (test, test-bash, version-check) to green

## Actual Delivery

All 9 plan tasks accounted for. Merged to `main` as squash commit `e3f61dd` (PR #61); per-task branch commits (`85a9b23`, `10b9246`, `4cc28bf`, `871dfdb`, `a7d503f`, `ca622ef`, `9d0a5ba`, `8c90b72`) are folded into it.

| Plan task | Status | What actually landed |
|-----------|--------|----------------------|
| `t1` | delivered | `cultureflare/_secrets/_grant_sink.py` execs `grant`; `_shushu_sink` is a `sys.modules` alias; `GrantTarget` with `ShushuTarget = GrantTarget`; renamed sink/integration tests; fake-`grant`-on-PATH test (assertion strengthened to full-argv equality in `0c7132f`). Post-review additions: typed `GrantNotFoundError` (incl. sudo `secure_path` miss) and exact `sudo -n … --user` remediation. |
| `t2` | delivered | `get_tunnel_token` shape guard (EXIT_API, value never echoed), shared `FAKE_TUNNEL_TOKEN` fixture. Post-review: tolerates surrounding whitespace and the URL-safe alphabet. |
| `t3` | delivered | Eight devague SKILL.md files byte-verbatim from guildmaster `f0ea1b3` (= devague `0.24.2`), `validate-delivery` added; `[[ ]]` / S7679 / SC2016 hardening on the three CLI-driving scripts only (approved deviation `d1`). Built by the main agent rather than a subagent, at the user's suggestion. |
| `t4` | delivered | `tests/shellcheck.sh` + `.markdownlint-cli2.yaml` skip vendored `ask-colleague`; `.gitignore` ignores `.devague/` and `docs/plans/*-split.md`; upstream issue agentculture/colleague#501 filed by the main agent. |
| `t5` | delivered | `derive_seal_plan(grant_arg=…, shushu_arg=…)` with grant-name validation and `--grant` rotate-howto. Post-review: validation scoped to `setup` via `validate_names` (show/teardown skip it). |
| `t6` | delivered | `grant/USER/NAME` markers, `grant-tunnel-token` / `grant-svc-secret` step names, renderer text; t6/t7 test overlap reconciled in `1c50a1c`. |
| `t7` | delivered | `--grant[=USER]` on setup/show/teardown, hidden deprecated `--shushu` with one stderr warning, mutual-exclusion error, `grant/` dry-run markers. |
| `t8` | delivered | 0.17.0 (pyproject, CHANGELOG, `uv.lock`), CLAUDE.md devague section listing all eight skills; also corrected the stale baked `__version__` default (0.13.0). |
| `t9` | partial | Full local suite green; #55 comment posted; PR #61 opened with `Refs #55`; CI green (test, test-bash, version-check, SonarCloud 0 issues). Not met: the acceptance criterion asked the spark dry-run to show `<sealed: grant/` markers and `grant-*` step names — a dry-run renders neither (both appear only under `--apply`); the dry-run showed `grant/<self>/…` in `sealed_in`, and a real `show --grant` probe of `gwen.culture.dev` returned `grant/spark/…_TUNNEL_TOKEN — present`. |

## Mid-work Decisions

- `d1` — t3 vendors the devague 0.24.2 shape (8 SKILL.md + 3 CLI-driving scripts) and skips guildmaster f0ea1b3's 5 extra method-only resolvers (scope.sh, challenge.sh, deviate.sh, validate-delivery.sh, summarize-delivery.sh); h8's diff-vs-guildmaster therefore also shows those 5 'Only in guildmaster' entries — the 5 resolvers exist only in guildmaster, not devague; devague's SKILL.md text and 'devague learn' say method-only skills have no scripts/; user chose this shape 2026-10-24
- Upstream SKILL.md files already carry `type: command` (it sits below line 8 of the frontmatter, which the scope survey missed), so t3 made no frontmatter edit; the documented local divergence shrank to the three scripts.
- t3 was taken by the main agent instead of a subagent — the user offered it as the riskiest task.
- t4's `.gitignore` block was appended rather than replacing devague's auto-added lines (those were uncommitted in the main checkout only; discarded there).
- `.devague/**` added to markdownlint ignores (delta `b3`) so local lint runs match CI.
- `--grant` + `--shushu` together (and `grant_arg` + `shushu_arg`) is a user error (delta `b1`) — not in the plan, added by t5/t7.
- o4's evidence pass exposed a weak fake-`grant` assertion (prefix/suffix only, a corrupted `--hidden` passed); the test was strengthened before evidence was filed.
- A `/code-review` of PR #61 found 9 issues; fixed in-PR: setup-only name guard (2), tolerant token guard (5), exact sudo/`--user` remediation (7), typed `GrantNotFoundError` instead of `"not found"` substring matching (9), CHANGELOG migration note that `--shushu` now targets the grant store (1). Finding 8 kept by design (library alias = `cfafi` back-compat). Findings 3/6 (vendored `assign-to-workforce.sh`) filed upstream as agentculture/devague#123; finding 4 already tracked as devague#120 item 4.
- SonarCloud reported 14 × `python:S5778` in `tests/test_secrets_grant_sink.py` (10 inherited via the file rename); fixed by hoisting `GrantTarget(...)` out of `pytest.raises` blocks (`23b9128`).

## Drift From Plan

| Plan item | Reason for divergence | Classification |
|-----------|-----------------------|----------------|
| `t3` (`d1`) | the 5 resolvers exist only in guildmaster, not devague; devague's SKILL.md text and 'devague learn' say method-only skills have no scripts/; user chose this shape 2026-10-24 | acceptable |
| `t3` | plan said to re-apply `type: command`; upstream already carries it, so no edit was needed (SKILL.md files are verbatim) | acceptable |
| `t5` | contract made `derive_seal_plan` refuse invalid names whenever sealing is enabled; review showed that blocked `teardown --grant` for long hostnames, so the guard is now `setup`-only (`validate_names`); c5/h5 still hold for setup | acceptable |
| `t1`, `t2` | post-review behavior beyond the task contract (typed not-found error, sudo `secure_path` detection, exact remediation; whitespace/URL-safe token tolerance) | acceptable |
| `t8` | also fixed the stale baked `__version__` default — `bump.py` only rewrites it when it equals the old version, so once it drifted (0.13.0) later bumps skipped it silently | acceptable |
| `t9` | dry-run cannot show `<sealed: grant/…>` or `grant-*` step names; those are covered by unit tests (o6 sensitivity-probed) but were not observed live under `--apply` | needs-follow-up |

## Evidence

Re-verified read-only on merged `main` at `e3f61dd` (evidence records `e1`–`e7` cite pre-squash branch commits; the tested code is identical in `e3f61dd`):

- tests: `uv run pytest -q` — 306 passed, 3 skipped (opt-in `GRANT_INTEGRATION=1` tests, not run)
- tests: the 19 node ids cited by `e1`–`e6` plus `tests/test_cli_remote_login.py::test_only_setup_validates_grant_names` — pass
- tests: `bats tests/bats/` — 278 / 278 ok
- lint: `bash tests/shellcheck.sh` — exit 0; `bash tests/markdownlint.sh` — 0 errors
- CI: Tests workflow run 40043648062 on `e3f61dd` — success; PR #61 SonarCloud — Quality Gate OK, 0 issues, 0 hotspots
- sensitivity probes: each obligation's behavior was mutated and its tests failed (o1: 3 fail, o2: 8, o3: 4, o4: 1 after strengthening, o5: 1, o6: 2), then reverted
- live (read-only, spark, grant 0.11.0, no `shushu`): `remote-login show --hostname gwen.culture.dev --grant` → tunnel token `present`; `nodes.culture.dev` / `gwen.culture.dev` token endpoint → 240-byte base64 JSON with `a`/`s`/`t`
- vendored: `git diff 49319c1 e3f61dd -- .claude/skills/ask-colleague` — empty
- commits: `49319c1..e3f61dd`
- PRs / issues: #61 (merged), #55 (open, comment posted), agentculture/colleague#501, agentculture/devague#123

## Delivery Claims

Rows `c2`–`c21` are rendered by `devague summary` from approved evidence `e1`–`e7`; the confidence column maps the recorded strength to a level. No lapses were filed.

| Claim | Confidence | Evidence |
|-------|------------|----------|
| `c2` — the secret sink execs 'grant' instead of 'shushu' (argv\[0\] at cultureflare/`_secrets`/`_shushu_sink.py`:52,64,73) with the argv otherwise unchanged — grant 0.11.0 'set/show/delete --help' accepts every flag the sink passes (--hidden --source --purpose --rotate-howto --user, value '-' on stdin), and 'grant show --json' returns the same flat {ok,name,hidden,...} envelope probe() parses (verified read-only on `CULTUREFLARE_GWEN_CULTURE_DEV_TUNNEL_TOKEN`); not-found hints/remediations (lines 31,100,112-128,155-158,180,211) name grant and 'uv tool install grant' | high (sensitivity) | `tests/test_secrets_grant_sink.py::test_seal_self_user_argv_no_sudo,test_seal_cross_user_argv_uses_sudo,test_seal_secret_passed_via_stdin_not_argv,test_seal_with_fake_grant_on_path` (run 2026-10-23) |
| `c3` — a '--grant\[=USER\]' flag on remote-login setup/show/teardown (cultureflare/cli/`_commands`/`remote_login.py`:294,307,326; help text `_SHUSHU_HELP` at 46-50) is the documented surface; '--shushu\[=USER\]' stays accepted as a deprecated alias mapping to the same dest, so issue #55's existing recipes and the `rotation_howto` already stored in sealed secrets keep working | high (sensitivity) | `tests/test_cli_remote_login.py (alias-resolution, deprecation-stderr, dry-run JSON tests added in t7)` (run 2026-10-23) |
| `c5` — `derive_seal_plan` refuses (CfafiError, exit 64-class user error, before any remote mutation) a derived secret name that fails grant's '^\[A-`Z_`\]\[A-Z0-`9_`\]{0,63}$' — today `_slug` (`_seal_plan.py`:27-31) only maps '.' and '-' and never checks length, so hostnames longer than 38 chars produce >64-char names, and grant show/delete exit 64 for an invalid name is indistinguishable from 'absent' (verified: 'grant show --json no-such-kebab' -> 64 'no secret named') | high (sensitivity) | `tests/test_remote_login_seal_plan.py::test_invalid_derived_name_refused_when_sealing_enabled,test_invalid_derived_name_refused_for_bare_flag,test_invalid_derived_name_allowed_when_sealing_disabled` (run 2026-10-23) |
| `c7` — tests drive the grant port: tests/`test_secrets_shushu_sink.py` argv assertions (e.g. argv\[:3\]==\['sudo','-n','shushu'\] at 69,221) move to grant, the opt-in integration test (tests/`test_secrets_shushu_integration.py`, gated on `SHUSHU_INTEGRATION` + which('shushu')) gates on grant, and a new test runs setup --apply --grant against a fake 'grant' executable on PATH asserting the argv, per #55's suggested acceptance | high (sensitivity) | `tests/test_secrets_grant_sink.py::test_seal_with_fake_grant_on_path` (run 2026-10-23) |
| `c9` — `get_tunnel_token` fails loudly (CfafiError) when the endpoint's result is not base64 JSON carrying a/s/t, and the token stubs in tests (`test_remote_login_tunnel.py`:65-70 toy '{"k":"foo"}', orchestrator/render 'TUN-TOK') become a realistic a/s/t blob with a test that decodes it — #55's 'a test that base64-decodes the value would have caught this', applied as a guard since the defect itself does not reproduce | high (sensitivity) | `tests/test_remote_login_tunnel.py::test_get_tunnel_token_returns_runtime_token,test_get_tunnel_token_rejects_bad_shape_without_leaking` (run 2026-10-23) |
| `c20` — JSON/Markdown step names 'shushu-tunnel-token' / 'shushu-svc-secret' (cultureflare/`_remote_login`/`__init__.py`:133-134) are renamed to 'grant-tunnel-token' / 'grant-svc-secret' — a deliberate output change recorded in CHANGELOG (q1) | high (sensitivity) | `tests/test_remote_login_orchestrator.py (seal step-name assertions)` (run 2026-10-23) |
| `c21` — test-bash goes green: tests/shellcheck.sh and the markdownlint config skip the vendored .claude/skills/ask-colleague/ tree (findings SC2046/SC2016 at ask-colleague.sh:430,841,847,854; MD041/MD032 in prompts/\*.md) without editing those vendored bytes, and the findings are filed as one upstream issue on agentculture/colleague (q2) | high (execution) | `GitHub Actions Tests workflow, job test-bash (run 40041200460) on PR #61` (run 2026-10-23) |
| `c11`/`c12` — the eight devague skills are refreshed to 0.24.2 with only the documented script divergences | high | commit `e3f61dd` · `diff` against guildmaster `f0ea1b3` (task t3) · `bash tests/shellcheck.sh` exit 0 |
| `c13` — 0.17.0 released and CLAUDE.md documents all eight skills | high | `pyproject.toml` · PyPI `cultureflare==0.17.0` (Publish to PyPI run on `e3f61dd` succeeded) |
| `c22` — devague state and split plans are gitignored | high | `.gitignore` · `git check-ignore .devague/current docs/plans/x-split.md` (task t4) |
| `c23` — #55 carries the non-reproduction evidence; PR references, does not close it | high | issue #55 comment · PR #61 body `Refs #55` |
| `setup --grant --apply` renders `<sealed: grant/USER/NAME>` and records `grant-*` step names end-to-end | medium | unit tests only (`tests/test_remote_login_render.py`, o6 / `e6`) — not observed under a live `--apply` |
| #55's 51-byte `tunnel_token` is explained | unverified | (does not reproduce; awaiting reporter — not claimed fixed) |

## Remaining Work / Follow-up

- `t9` — observe `<sealed: grant/…>` and `grant-*` step names under a real `setup --grant --apply` (e.g. the next provisioning run) — operator.
- #55 point 1 — the 51-byte token stays unexplained; awaiting the reporter's raw output; issue remains open.
- Opt-in `GRANT_INTEGRATION=1` tests were not run (they write to a real grant store) — run once on a scratch user.
- Upgrade `cultureflare` to 0.17.0 on other hosts (thor and any remote-login host still on ≤ 0.16) — `uv tool upgrade cultureflare`.
- Drop the `ask-colleague` lint skip once agentculture/colleague#501 lands and is re-vendored.
- Re-vendor `assign-to-workforce` once agentculture/devague#123 and devague#120 item 4 are fixed.
- `.claude/skills/version-bump/scripts/bump.py` rewrites the baked `__version__` in `cultureflare/__init__.py` only when it equals the old version (a drifted value is skipped silently), and leaves a double blank line in CHANGELOG (MD012) — harden the script.
- Former shushu stores on other hosts: anything sealed by `shushu` must be removed with `shushu delete` (0.17.0 `--shushu` targets the grant store).
