# grant port + devague 0.24.2 refresh

> cultureflare 0.17.0 seals remote-login secrets into grant (the renamed shushu) instead of a binary that no longer exists, and ships the full eight-leg devague 0.24.2 workflow skills (incl. /validate-delivery and obligations/evidence)

## Audience

- operators and mesh agents provisioning remote-login hosts on machines that now run grant 0.11.0 (spark, thor; culture-nodes and embodiment reported on #55), plus agents in this repo driving the devague workflow skills

## Before → After

- Before: on any current host '--shushu' fails with 'shushu binary not found' after the tunnel, CNAME and Access app are already created (#55 comment, gwen.culture.dev 2026-10-23), forcing a PATH shim or manual 'grant set' workaround; vendored devague skills track 0.11.1-era text against a 0.24.2 CLI; test-bash has been red on main since 49319c1
- After: 'cultureflare remote-login setup --grant --apply' seals the tunnel token and service-token secret into grant under grant-valid names and 'show' renders '<sealed: grant/USER/NAME>'; agents here run the full eight-leg devague 0.24.2 flow including /validate-delivery; main's test-bash is green

## Why it matters

- sealed-secret provisioning is the safe path for tunnel tokens (they otherwise print to stdout) and it is currently unusable; skill text that lags the CLI teaches agents moves and handoffs that no longer match, and a red main hides real regressions in every PR

## Requirements

- the secret sink execs 'grant' instead of 'shushu' (argv\[0\] at cultureflare/`_secrets`/`_shushu_sink.py`:52,64,73) with the argv otherwise unchanged — grant 0.11.0 'set/show/delete --help' accepts every flag the sink passes (--hidden --source --purpose --rotate-howto --user, value '-' on stdin), and 'grant show --json' returns the same flat {ok,name,hidden,...} envelope probe() parses (verified read-only on `CULTUREFLARE_GWEN_CULTURE_DEV_TUNNEL_TOKEN`); not-found hints/remediations (lines 31,100,112-128,155-158,180,211) name grant and 'uv tool install grant'
  - honesty: a test asserts argv\[0\]=='grant' (and \['sudo','-n','grant',...\] when a user is set) for set/show/delete, and no 'shushu' literal remains in an exec'd argv or a user-facing install hint
- a '--grant\[=USER\]' flag on remote-login setup/show/teardown (cultureflare/cli/`_commands`/`remote_login.py`:294,307,326; help text `_SHUSHU_HELP` at 46-50) is the documented surface; '--shushu\[=USER\]' stays accepted as a deprecated alias mapping to the same dest, so issue #55's existing recipes and the `rotation_howto` already stored in sealed secrets keep working
  - honesty: both '--grant' and '--shushu' parse on setup/show/teardown to the same dest, '--shushu' prints a one-line deprecation notice on stderr only (never in --json stdout), and a test covers each spelling
- sealed markers render as 'grant/USER/NAME' (cultureflare/`_remote_login`/`__init__.py`:64,92,117,123; dry-run builders cli/`_commands`/`remote_login.py`:100-107; `_render.py`:172,177,254) so 'show' renders '<sealed: grant/USER/NAME>' per #55's acceptance; the `rotation_howto` stored with each secret (`_seal_plan.py`:34-40, currently embeds '--shushu' — confirmed in the live gwen secret's metadata) names '--grant'
  - honesty: render/CLI tests assert `grant/USER/NAME` markers and `<sealed: grant/...>` in Markdown, and the stored `rotation_howto` names `--grant`
- `derive_seal_plan` refuses (CfafiError, exit 64-class user error, before any remote mutation) a derived secret name that fails grant's '^\[A-`Z_`\]\[A-Z0-`9_`\]{0,63}$' — today `_slug` (`_seal_plan.py`:27-31) only maps '.' and '-' and never checks length, so hostnames longer than 38 chars produce >64-char names, and grant show/delete exit 64 for an invalid name is indistinguishable from 'absent' (verified: 'grant show --json no-such-kebab' -> 64 'no secret named')
  - honesty: a test with a >38-char hostname and one with an unmappable char each fail in `derive_seal_plan` before any HTTP stub is hit, with exit `EXIT_USER_ERROR` and the offending name in the message
- tests drive the grant port: tests/`test_secrets_shushu_sink.py` argv assertions (e.g. argv\[:3\]==\['sudo','-n','shushu'\] at 69,221) move to grant, the opt-in integration test (tests/`test_secrets_shushu_integration.py`, gated on `SHUSHU_INTEGRATION` + which('shushu')) gates on grant, and a new test runs setup --apply --grant against a fake 'grant' executable on PATH asserting the argv, per #55's suggested acceptance
  - honesty: a test puts an executable fake 'grant' on PATH (tmp dir, PATH prepended) that records argv+stdin, runs the seal path end-to-end, and asserts the recorded argv and that the secret arrived on stdin, never argv
- `get_tunnel_token` fails loudly (CfafiError) when the endpoint's result is not base64 JSON carrying a/s/t, and the token stubs in tests (`test_remote_login_tunnel.py`:65-70 toy '{"k":"foo"}', orchestrator/render 'TUN-TOK') become a realistic a/s/t blob with a test that decodes it — #55's 'a test that base64-decodes the value would have caught this', applied as a guard since the defect itself does not reproduce
  - honesty: the guard accepts the real 240-byte a/s/t shape (fixture built from base64(json{a,s,t})) and rejects a non-base64 / missing-key value with CfafiError, and no token value appears in the error text
- the seven vendored devague skills (scope, think, challenge, spec-to-plan, assign-to-workforce, deviate, summarize-delivery) are re-vendored and validate-delivery is added, from guildmaster origin/main f0ea1b3 (guildmaster#118 re-sync) whose eight copies are byte-identical to agentculture/devague origin/main 78d9bfb = 0.24.2 — a partial refresh would leave upstream's /validate-delivery handoffs (in assign-to-workforce, challenge, deviate, summarize-delivery) dangling
  - instruction: for each skill S in (scope think challenge spec-to-plan assign-to-workforce deviate validate-delivery summarize-delivery): `git -C ../guildmaster archive origin/main .claude/skills/$S | tar -x -C "$TMP"`, copy over `.claude/skills/$S/`, then re-apply c12; verify with `diff -r` against the extracted tree
  - honesty: for each of the eight skills, 'diff -r' against guildmaster origin/main f0ea1b3 shows only the c12 divergences, and grep for '/validate-delivery' in .claude/skills resolves to an existing skill directory
- the documented local divergences are re-applied on top of the refreshed upstream text: 'type: command' in all eight SKILL.md frontmatters (upstream and guildmaster carry none; required by the culture/agex loader), SonarCloud shelldre hardening (\[\[ \]\] per S7688, positional params to locals per S7679) on think.sh / spec-to-plan.sh / assign-to-workforce.sh, and '# shellcheck disable=SC2016' at both new SC2016 sites in upstream assign-to-workforce.sh (lines 282, 632) so tests/shellcheck.sh stays clean for these scripts
  - instruction: insert 'type: command' as the last frontmatter key before the closing '---'; convert every '\[ ... \]' test to '\[\[ ... \]\]' and assign $1/$2 to locals at function entry in the three scripts; add '# shellcheck disable=SC2016' on the line above each SC2016 site; run bash tests/shellcheck.sh
  - honesty: all eight SKILL.md frontmatters contain 'type: command', 'bash tests/shellcheck.sh' passes on the three scripts, and the three scripts contain no single-bracket '\[ ' tests
- CLAUDE.md's devague section (~lines 50-65) is rewritten to list all eight skills in flow order and pin 'guildmaster f0ea1b3 / devague 0.24.2 (78d9bfb)' instead of '0.11.1 / c04b595'; CHANGELOG gets a new entry and pyproject + cultureflare/`__init__.py` bump 0.16.0 -> 0.17.0 (version-check CI requires a bump)
  - honesty: pyproject.toml and cultureflare/`__init__.py` both read 0.17.0, CHANGELOG has a 0.17.0 entry, and CLAUDE.md names f0ea1b3 / 0.24.2 and all eight skills
- JSON/Markdown step names 'shushu-tunnel-token' / 'shushu-svc-secret' (cultureflare/`_remote_login`/`__init__.py`:133-134) are renamed to 'grant-tunnel-token' / 'grant-svc-secret' — a deliberate output change recorded in CHANGELOG (q1)
  - honesty: orchestrator/render tests assert the 'grant-tunnel-token' / 'grant-svc-secret' step names and CHANGELOG lists the rename under a breaking/changed heading
- test-bash goes green: tests/shellcheck.sh and the markdownlint config skip the vendored .claude/skills/ask-colleague/ tree (findings SC2046/SC2016 at ask-colleague.sh:430,841,847,854; MD041/MD032 in prompts/\*.md) without editing those vendored bytes, and the findings are filed as one upstream issue on agentculture/colleague (q2)
  - honesty: the Tests workflow's test-bash job passes on the PR head with ask-colleague files byte-identical to main, and an upstream colleague issue URL is cited in the CHANGELOG or PR body
- .gitignore gains '.devague/' and 'docs/plans/\*-split.md' so devague working state and workforce split plans never enter commits (q3)
  - honesty: 'git check-ignore .devague/current docs/plans/x-split.md' reports both ignored, and 'git status' after a devague move shows no .devague entry
- issue #55 gets a comment with the non-reproduction evidence for point 1 (pass-through code unchanged since ab7146f; live nodes.culture.dev token 240 bytes, keys a/s/t) asking the reporter for raw output; the PR references #55 ('Refs #55') and does not close it (q4)
  - honesty: the #55 comment is posted (signed per repo convention) and contains no token value, and the PR body says 'Refs #55' rather than a closing keyword

## Honesty conditions

- both halves ship in one PR whose CI (test, test-bash, version-check) is green, and nothing in it claims #55's `tunnel_token` defect is fixed
- tests/`test_back_compat.py` passes unchanged: cfafi.`_secrets`.`_shushu_sink`, ShushuTarget and `derive_seal_plan`(`shushu_arg`=...) still import and behave identically
- pyproject.toml 'dependencies = \[\]' is unchanged in the PR diff
- the named hosts actually run grant 0.11.0 with no shushu on PATH (verified on spark: 'which shushu' empty, 'grant --version' 0.11.0)
- each clause is backed by a passing test or CI job in the PR, not by prose alone
- the before-state cites only observed facts: the #55 comment's gwen.culture.dev failure, CLAUDE.md's 0.11.1 pin, and main's failing test-bash run on 49319c1
- sealing is the only cultureflare path that keeps the tunnel token off stdout (unsealed setup prints it in Markdown and --json)
- every success signal is checkable from CI output or a recorded command in the PR, with none asserted without running it

## Success signals

- pytest + bats + shellcheck + markdownlint pass in CI (test and test-bash green); a fake-grant-on-PATH test asserts the exact argv; 'diff' of each refreshed skill against guildmaster f0ea1b3 shows only the documented divergences; a real 'setup --grant' dry-run on spark renders grant/ markers

## Scope / boundaries

- back-compat surface stays importable: module path cultureflare.`_secrets`.`_shushu_sink`, class ShushuTarget, and keyword `shushu_arg` are pinned by cfafi/`__init__.py`:34 and tests/`test_back_compat.py`:78-100 — any rename to grant-named identifiers keeps the old names as aliases
- the devague CLI is a local operator tool, not a cultureflare dependency — it was upgraded on this host 0.24.1 -> 0.24.2 via 'uv tool upgrade devague' and pyproject.toml's 'dependencies = \[\]' stays empty (CLAUDE.md 'Tooling choice')

## Non-goals

- no change to how `tunnel_token` is fetched — cultureflare/`_remote_login`/`_tunnel.py`:108-122 returns GET /`cfd_tunnel`/{id}/token .result verbatim on both create and already-exists paths, untouched since ab7146f (only 0daf358 touched the file, not this function); a read-only live run of that exact function for nodes.culture.dev and gwen.culture.dev today returns 240 bytes base64-decoding to JSON keys a/s/t, i.e. a valid connector token
- 'shushu' as a pending Pages sub-site name (CLAUDE.md:103, .claude/skills/cultureflare-write/SKILL.md:732, cultureflare-write/references/subpath-site-pattern.md:27) and historical records (CHANGELOG entries, docs/superpowers/specs+plans 2026-05-08 shushu-sealed-secrets, 2026-05-15 katvan cutover) are not rewritten — they name a different project or record past decisions

## Scope exploration

- `s1` — `cultureflare/_secrets/_shushu_sink.py + grant 0.11.0 CLI`: argv\[0\] is the literal 'shushu' in all three builders (52,64,73), resolved via PATH, FileNotFoundError is the only not-found signal; grant 0.11.0 set/show/delete accept the identical flags and show --json returns the flat envelope probe() expects (read-only probe of an existing sealed secret); exit 64 = absent, matching delete/probe semantics
  - seeds: `c2`
- `s2` — `cultureflare/cli/_commands/remote_login.py + _remote_login/__init__.py + _render.py + _seal_plan.py`: --shushu declared with nargs='?' const='' on 3 verbs (294,307,326); 'shushu/USER/NAME' marker built at 4 sites in `__init__` plus the dry-run builder; `rotation_howto` embeds the --shushu literal and is persisted into grant metadata (live gwen secret shows it), so the old flag must stay parseable
  - seeds: `c3`, `c4`
- `s3` — `cultureflare/_remote_login/_seal_plan.py (_slug, derive_seal_plan)`: names are ALREADY uppercase ('`CULTUREFLARE_`' + host.upper() with . and - -> `_`), single commit 5d30808 since creation — the issue body's 'kebab-case on 0.15.0' claim is not supported by this repo; real gaps are length (13+host+13 > 64 for host > 38 chars) and unmapped chars, plus exit-64 overload in show/delete
  - seeds: `c5`
- `s4` — `cfafi/__init__.py + tests/test_back_compat.py`: the cfafi shim explicitly imports `_secrets`.`_shushu_sink` and `_secrets`.`_types`; back-compat tests assert identity of the module, ShushuTarget, `derive_seal_plan` and the `shushu_arg` keyword
  - seeds: `c6`
- `s5` — `tests/ (sink, integration, orchestrator, cli, render, seal_plan, types, back_compat)`: no test uses a fake binary on PATH today — sink tests monkeypatch subprocess.run; orchestrator tests monkeypatch `_shushu_sink`.seal/probe/delete at ~9 sites; render tests assert 'shushu/alice/...' markers
  - seeds: `c7`
- `s6` — `cultureflare/_remote_login/_tunnel.py + git history + live CF read (#55 point 1)`: token path is pass-through and unchanged since the rename commit; live GET for the issue's own tunnel (nodes.culture.dev, created 2026-09-02, `config_src`=cloudflare) yields a valid 240-byte a/s/t connector token now; the 51-byte value in #55 is unexplained by the code — the commenter's 0.11.0-vs-0.15.0 comparison mixed sealed vs unsealed modes
  - seeds: `c8`, `c9`
- `s7` — `docs + CHANGELOG + cultureflare-write skill docs`: grep shows 23 files mention shushu; only the Python package + tests refer to the secrets tool — the CLAUDE.md/skill-doc hits are the zehut/shushu sub-site roadmap, and docs/superpowers/\* + CHANGELOG are dated history
  - seeds: `c10`
- `s8` — `devague + guildmaster origin/main vs .claude/skills/{8 skills}`: all 7 local skills lag 0.24.2 (scope gains q\* seeds + scope --amend + subagent fan-out; assign-to-workforce gains split-plan --write, End state, validate-delivery handoff; challenge/summarize-delivery gain lapse ledger); validate-delivery absent locally; guildmaster == devague byte-for-byte; neither carries type: command or \[\[ \]\] hardening; upstream SKILL.md files pass markdownlint, upstream assign-to-workforce.sh raises 2 SC2016
  - seeds: `c11`, `c12`
- `s9` — `CLAUDE.md + CHANGELOG.md + pyproject.toml`: CLAUDE.md pins 'devague 0.11.1 / c04b595' and lists only the trio; the four skills from mass-update 49319c1 are undocumented there; no docs/skill-sources.md exists; pyproject is 0.16.0
  - seeds: `c13`

## Open parks

- [unknown_nonblocking] Where #55's 51-byte `tunnel_token` value came from is unexplained — not from cultureflare's pass-through path (verified live); candidates: a different field/command, a wrapped/truncated Markdown line, or a transient CF response. Needs the reporter's raw output.
- [unknown_nonblocking] Whether grant 0.11.0's '--user NAME' self-escalates or still needs the sink's 'sudo -n' wrapper (`_shushu_sink.py`:34-41), and its exit codes beyond 64 (sink maps 66 -> needs-root, 65/67 -> API) — help text says only '(sudo) operate on another user's store'; resolve via 'grant explain' / grant source during implementation.
