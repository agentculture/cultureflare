"""End-to-end tests for `cfafi remote-login` via main([...])."""

import json

import pytest

from cultureflare.cli._errors import EXIT_USER_ERROR, CfafiError

from cultureflare.cli import main


@pytest.fixture
def remote_login_parser():
    from cultureflare.cli import _build_parser
    return _build_parser()


def _zones_one(name="culture.dev", zid="zid-1"):
    return {
        "success": True, "errors": [], "messages": [],
        "result": [{"id": zid, "name": name}],
        "result_info": {"page": 1, "total_pages": 1},
    }


def _verify_alive(status="active"):
    """Mirror real `/user/tokens/verify`: id/status/not_before/expires_on only."""
    return {
        "success": True, "errors": [], "messages": [],
        "result": {
            "id": "tok-1",
            "status": status,
            "not_before": "2026-01-01T00:00:00Z",
            "expires_on": "2027-01-01T00:00:00Z",
        },
    }


def test_setup_dry_run_prints_plan_and_does_not_post(http_stub, capsys):
    http_stub.set("GET", "/user/tokens/verify", _verify_alive())
    http_stub.set("GET", "/zones", _zones_one())
    rc = main([
        "remote-login", "setup",
        "--hostname", "irc.culture.dev",
        "--service", "http://localhost:8080",
        "--allow", "me@example.com",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dry-run" in out
    assert "## Plan" in out
    assert "irc.culture.dev" in out
    assert "http://localhost:8080" in out
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert posts == []


def test_setup_requires_at_least_one_allow(http_stub, capsys):
    http_stub.set("GET", "/user/tokens/verify", _verify_alive())
    http_stub.set("GET", "/zones", _zones_one())
    rc = main([
        "remote-login", "setup",
        "--hostname", "irc.culture.dev",
        "--service", "http://localhost:8080",
    ])
    assert rc != 0


def test_setup_no_access_dry_run_skips_access_and_needs_no_allow(http_stub, capsys):
    # --no-access: tunnel + DNS only; --allow is not required and the plan
    # explicitly skips Cloudflare Access.
    http_stub.set("GET", "/user/tokens/verify", _verify_alive())
    http_stub.set("GET", "/zones", _zones_one())
    rc = main([
        "remote-login", "setup",
        "--hostname", "vllm.culture.dev",
        "--service", "http://127.0.0.1:8000",
        "--no-access",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dry-run" in out
    assert "skip Cloudflare Access" in out
    assert "Zero Trust org" not in out
    assert "allow-policy" not in out
    assert [c for c in http_stub.calls if c[0] == "POST"] == []


def test_setup_no_access_rejects_allow_flags(http_stub, capsys):
    rc = main([
        "remote-login", "setup",
        "--hostname", "vllm.culture.dev",
        "--service", "http://127.0.0.1:8000",
        "--no-access",
        "--allow", "me@example.com",
    ])
    err = capsys.readouterr().err
    assert rc != 0
    assert "no-access" in err


def test_setup_requires_service(http_stub, capsys):
    # argparse raises SystemExit at parse time; the structured error
    # message still goes to stderr via _CfafiArgumentParser.error().
    with pytest.raises(SystemExit) as exc:
        main([
            "remote-login", "setup",
            "--hostname", "irc.culture.dev",
            "--allow", "me@example.com",
        ])
    err = capsys.readouterr().err
    assert exc.value.code != 0
    assert "--service" in err


def test_setup_rejects_invalid_service_url(http_stub, capsys):
    http_stub.set("GET", "/user/tokens/verify", _verify_alive())
    http_stub.set("GET", "/zones", _zones_one())
    rc = main([
        "remote-login", "setup",
        "--hostname", "irc.culture.dev",
        "--allow", "me@example.com",
        "--service", "localhost:8080",  # missing scheme
    ])
    err = capsys.readouterr().err
    assert rc != 0
    assert "--service" in err
    assert "scheme://host" in err


def test_setup_preflight_blocks_when_token_inactive(http_stub, capsys):
    http_stub.set("GET", "/user/tokens/verify", _verify_alive(status="disabled"))
    rc = main([
        "remote-login", "setup",
        "--hostname", "irc.culture.dev",
        "--service", "http://localhost:8080",
        "--allow", "me@example.com",
    ])
    err = capsys.readouterr().err
    assert rc != 0
    assert "'disabled'" in err


def test_show_emits_json_when_flagged(http_stub, capsys):
    http_stub.set("GET", "/user/tokens/verify", _verify_alive())
    http_stub.set("GET", "/zones", _zones_one())
    http_stub.set("GET", "/accounts/test-account/access/organizations", {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "AC", "auth_domain": "ac.cloudflareaccess.com"},
    })
    http_stub.set("GET", "/accounts/test-account/cfd_tunnel",
                  {"success": True, "errors": [], "messages": [], "result": [],
                   "result_info": {"page": 1, "total_pages": 1}})
    http_stub.set("GET", "/zones/zid-1/dns_records",
                  {"success": True, "errors": [], "messages": [], "result": [],
                   "result_info": {"page": 1, "total_pages": 1}})
    http_stub.set("GET", "/accounts/test-account/access/apps",
                  {"success": True, "errors": [], "messages": [], "result": [],
                   "result_info": {"page": 1, "total_pages": 1}})
    http_stub.set("GET", "/accounts/test-account/access/service_tokens",
                  {"success": True, "errors": [], "messages": [], "result": [],
                   "result_info": {"page": 1, "total_pages": 1}})
    rc = main([
        "remote-login", "show",
        "--hostname", "irc.culture.dev", "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["success"] is True
    assert payload["result"]["team_domain"] == "ac.cloudflareaccess.com"
    assert payload["result"]["tunnel"] is None


def test_teardown_dry_run_does_not_delete(http_stub, capsys):
    http_stub.set("GET", "/user/tokens/verify", _verify_alive())
    http_stub.set("GET", "/zones", _zones_one())
    rc = main([
        "remote-login", "teardown",
        "--hostname", "irc.culture.dev",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dry-run" in out
    deletes = [c for c in http_stub.calls if c[0] == "DELETE"]
    assert deletes == []


def test_setup_argparse_accepts_no_shushu_flag(remote_login_parser):
    args = remote_login_parser.parse_args([
        "remote-login", "setup", "--hostname", "app.example.com",
        "--service", "http://localhost:8080", "--allow", "x@y",
    ])
    assert args.shushu is None
    assert args.service == "http://localhost:8080"


def test_setup_argparse_bare_shushu_yields_empty_string(remote_login_parser):
    args = remote_login_parser.parse_args([
        "remote-login", "setup", "--hostname", "app.example.com",
        "--service", "http://localhost:8080",
        "--allow", "x@y", "--shushu",
    ])
    assert args.shushu == ""


def test_setup_argparse_shushu_with_user(remote_login_parser):
    args = remote_login_parser.parse_args([
        "remote-login", "setup", "--hostname", "app.example.com",
        "--service", "http://localhost:8080",
        "--allow", "x@y", "--shushu=alice",
    ])
    assert args.shushu == "alice"


def test_show_argparse_accepts_shushu(remote_login_parser):
    args = remote_login_parser.parse_args([
        "remote-login", "show", "--hostname", "app.example.com", "--shushu=alice",
    ])
    assert args.shushu == "alice"


def test_teardown_argparse_accepts_shushu(remote_login_parser):
    args = remote_login_parser.parse_args([
        "remote-login", "teardown", "--hostname", "app.example.com", "--shushu",
    ])
    assert args.shushu == ""


# ---------------------------------------------------------------------------
# Task 12: dry-run with --shushu includes seal steps
# ---------------------------------------------------------------------------

def test_cmd_setup_dryrun_with_shushu_lists_seal_steps(capsys, monkeypatch):
    import argparse
    from cultureflare.cli._commands.remote_login import cmd_setup

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc-1")
    monkeypatch.setattr(
        "cultureflare.cli._commands.remote_login.check_token_alive",
        lambda: None,
    )
    monkeypatch.setattr(
        "cultureflare.cli._commands.remote_login.resolve_zone",
        lambda hostname: ("zone-1", "example.com"),
    )

    ns = argparse.Namespace(
        hostname="app.example.com", allow=["x@y"], allow_domain=[],
        service="http://localhost:8080",
        with_service_token=True, session_duration="24h",
        tunnel_name=None, app_name=None, service_token_name=None,
        json=False, apply=False, shushu="alice",
    )
    cmd_setup(ns)
    out = capsys.readouterr().out
    assert "grant/alice/CULTUREFLARE_APP_EXAMPLE_COM_TUNNEL_TOKEN" in out
    assert "grant/alice/CULTUREFLARE_APP_EXAMPLE_COM_SVC_SECRET" in out


# ---------------------------------------------------------------------------
# t7: --grant flag with deprecated --shushu alias
# ---------------------------------------------------------------------------

_VERB_ARGV = {
    "setup": [
        "--hostname", "app.example.com", "--service", "http://localhost:8080",
        "--allow", "x@y",
    ],
    "show": ["--hostname", "app.example.com"],
    "teardown": ["--hostname", "app.example.com"],
}

_SPELLINGS = [
    ("--grant", ""),
    ("--grant=alice", "alice"),
    ("--shushu", ""),
    ("--shushu=alice", "alice"),
]


@pytest.mark.parametrize("verb", sorted(_VERB_ARGV))
@pytest.mark.parametrize("flag,expected_user", _SPELLINGS)
def test_grant_and_shushu_spellings_resolve_same_seal_user(
    remote_login_parser, capsys, verb, flag, expected_user,
):
    from cultureflare.cli._commands.remote_login import _seal_from_args

    args = remote_login_parser.parse_args(
        ["remote-login", verb, *_VERB_ARGV[verb], flag],
    )
    seal = _seal_from_args(args)
    assert seal.enabled is True
    assert (seal.user or "") == expected_user
    err = capsys.readouterr().err
    if flag.startswith("--shushu"):
        assert err.count("--shushu is deprecated; use --grant") == 1
        assert len(err.strip().splitlines()) == 1
    else:
        assert err == ""


@pytest.mark.parametrize("verb", sorted(_VERB_ARGV))
def test_no_grant_flag_disables_sealing(remote_login_parser, capsys, verb):
    from cultureflare.cli._commands.remote_login import _seal_from_args

    args = remote_login_parser.parse_args(["remote-login", verb, *_VERB_ARGV[verb]])
    assert _seal_from_args(args).enabled is False
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("verb", sorted(_VERB_ARGV))
def test_grant_and_shushu_together_is_user_error(remote_login_parser, verb):
    from cultureflare.cli._commands.remote_login import _seal_from_args

    args = remote_login_parser.parse_args(
        ["remote-login", verb, *_VERB_ARGV[verb], "--grant=a", "--shushu=b"],
    )
    with pytest.raises(CfafiError) as exc:
        _seal_from_args(args)
    assert exc.value.code == EXIT_USER_ERROR
    assert "mutually exclusive" in exc.value.message


@pytest.mark.parametrize("flag", ["--grant=alice", "--shushu=alice"])
def test_cmd_setup_dryrun_json_sealed_in_uses_grant_markers(
    capsys, monkeypatch, flag,
):
    import argparse
    from cultureflare.cli._commands.remote_login import cmd_setup

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc-1")
    monkeypatch.setattr(
        "cultureflare.cli._commands.remote_login.check_token_alive",
        lambda: None,
    )
    monkeypatch.setattr(
        "cultureflare.cli._commands.remote_login.resolve_zone",
        lambda hostname: ("zone-1", "example.com"),
    )
    from cultureflare.cli import _build_parser
    ns = _build_parser().parse_args([
        "remote-login", "setup", *_VERB_ARGV["setup"],
        "--with-service-token", "--json", flag,
    ])
    assert isinstance(ns, argparse.Namespace)
    cmd_setup(ns)
    cap = capsys.readouterr()
    body = json.loads(cap.out)  # stdout must stay pure JSON
    sealed = body["result"]["sealed_in"]
    assert sealed["tunnel_token"].startswith("grant/alice/")
    assert sealed["service_token_client_secret"].startswith("grant/alice/")
    if flag.startswith("--shushu"):
        assert cap.err.count("deprecated") == 1
    else:
        assert cap.err == ""
