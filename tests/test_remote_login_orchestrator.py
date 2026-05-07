"""Tests for the cfafi._remote_login orchestrator."""

import pytest

from cfafi._remote_login import setup, show, teardown
from cfafi._remote_login._common import (
    Context, derive_names, SetupResult, ShowResult, TeardownResult,
)


def _ctx(hostname="irc.culture.dev"):
    return Context(
        account_id="acc-1",
        zone_id="zid-1",
        hostname=hostname,
        names=derive_names(hostname=hostname),
    )


def _zt_existing():
    return {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "AC", "auth_domain": "ac.cloudflareaccess.com"},
    }


def _empty_list():
    return {
        "success": True, "errors": [], "messages": [],
        "result": [], "result_info": {"page": 1, "total_pages": 1},
    }


def _list_envelope(*items):
    return {
        "success": True, "errors": [], "messages": [],
        "result": list(items),
        "result_info": {"page": 1, "total_pages": 1},
    }


def test_setup_runs_all_six_steps_in_order_when_nothing_exists(http_stub):
    # Program all responses via set() so method+path keying works
    # regardless of call order (avoids queue ordering pitfalls when
    # GETs and POSTs are interleaved).
    http_stub.set("GET", "/accounts/acc-1/access/organizations", _zt_existing())
    http_stub.set("GET", "/accounts/acc-1/cfd_tunnel", _empty_list())
    http_stub.set("POST", "/accounts/acc-1/cfd_tunnel", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "tun-1", "name": "irc-culture-dev"},
    })
    http_stub.set(
        "GET", "/accounts/acc-1/cfd_tunnel/tun-1/token",
        {"success": True, "errors": [], "messages": [], "result": "TUN-TOK"},
    )
    http_stub.set("GET", "/zones/zid-1/dns_records", _empty_list())
    http_stub.set("POST", "/zones/zid-1/dns_records", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "rec-1"},
    })
    http_stub.set("GET", "/accounts/acc-1/access/apps", _empty_list())
    http_stub.set("POST", "/accounts/acc-1/access/apps", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "app-1"},
    })
    http_stub.set("GET", "/accounts/acc-1/access/apps/app-1/policies", _empty_list())
    http_stub.set(
        "POST", "/accounts/acc-1/access/apps/app-1/policies",
        {"success": True, "errors": [], "messages": [],
         "result": {"id": "pol-1"}},
    )
    http_stub.set("GET", "/accounts/acc-1/access/service_tokens", _empty_list())
    http_stub.set("POST", "/accounts/acc-1/access/service_tokens", {
        "success": True, "errors": [], "messages": [],
        "result": {
            "id": "st-1", "name": "irc.culture.dev-svc",
            "client_id": "CID", "client_secret": "SEC",
        },
    })

    result = setup(
        ctx=_ctx(),
        emails=["me@example.com"],
        domains=[],
        with_service_token=True,
        session_duration="24h",
    )
    assert isinstance(result, SetupResult)
    assert result.team_domain == "ac.cloudflareaccess.com"
    assert result.tunnel_id == "tun-1"
    assert result.tunnel_token == "TUN-TOK"
    assert result.dns_record_id == "rec-1"
    assert result.access_app_id == "app-1"
    assert result.policy_id == "pol-1"
    assert result.service_token_client_id == "CID"
    assert result.service_token_client_secret == "SEC"
    assert [s.name for s in result.steps] == [
        "zero-trust-org", "tunnel", "dns", "access-app",
        "allow-policy", "service-token",
    ]


def test_setup_skips_service_token_step_when_not_requested(http_stub):
    http_stub.set("GET", "/accounts/acc-1/access/organizations", _zt_existing())
    http_stub.set("GET", "/accounts/acc-1/cfd_tunnel", _empty_list())
    http_stub.set("POST", "/accounts/acc-1/cfd_tunnel", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "tun-1"},
    })
    http_stub.set(
        "GET", "/accounts/acc-1/cfd_tunnel/tun-1/token",
        {"success": True, "errors": [], "messages": [], "result": "TUN-TOK"},
    )
    http_stub.set("GET", "/zones/zid-1/dns_records", _empty_list())
    http_stub.set("POST", "/zones/zid-1/dns_records",
                  {"success": True, "errors": [], "messages": [],
                   "result": {"id": "rec-1"}})
    http_stub.set("GET", "/accounts/acc-1/access/apps", _empty_list())
    http_stub.set("POST", "/accounts/acc-1/access/apps",
                  {"success": True, "errors": [], "messages": [],
                   "result": {"id": "app-1"}})
    http_stub.set("GET", "/accounts/acc-1/access/apps/app-1/policies", _empty_list())
    http_stub.set("POST", "/accounts/acc-1/access/apps/app-1/policies",
                  {"success": True, "errors": [], "messages": [],
                   "result": {"id": "pol-1"}})

    result = setup(
        ctx=_ctx(), emails=["me@example.com"], domains=[],
        with_service_token=False, session_duration="24h",
    )
    assert result.service_token_client_id is None
    assert result.service_token_client_secret is None
    assert "service-token" not in [s.name for s in result.steps]
    paths = [c[1] for c in http_stub.calls]
    assert "/accounts/acc-1/access/service_tokens" not in paths


def test_show_reports_partial_state(http_stub):
    # ZT exists, tunnel exists, DNS missing, app missing, no policies, no svc.
    http_stub.set("GET", "/accounts/acc-1/access/organizations", {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "AC", "auth_domain": "ac.cloudflareaccess.com"},
    })
    http_stub.set(
        "GET", "/accounts/acc-1/cfd_tunnel",
        _list_envelope({"id": "tun-1", "name": "irc-culture-dev"}),
    )
    http_stub.set("GET", "/zones/zid-1/dns_records", _empty_list())
    http_stub.set("GET", "/accounts/acc-1/access/apps", _empty_list())
    # apps absent -> orchestrator skips listing policies
    http_stub.set("GET", "/accounts/acc-1/access/service_tokens", _empty_list())

    result = show(ctx=_ctx())
    assert isinstance(result, ShowResult)
    assert result.team_domain == "ac.cloudflareaccess.com"
    assert result.tunnel == {"id": "tun-1", "name": "irc-culture-dev"}
    assert result.dns is None
    assert result.access_app is None
    assert result.policy is None
    assert result.service_token is None


def test_teardown_reverses_setup_skipping_zt_org(http_stub):
    # Order of deletes: service-token, policy, app, dns, tunnel.
    http_stub.set(
        "GET", "/accounts/acc-1/access/service_tokens",
        _list_envelope({"id": "st-1", "name": "irc.culture.dev-svc",
                        "client_id": "CID"}),
    )
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/service_tokens/st-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "st-1"}},
    )
    http_stub.set(
        "GET", "/accounts/acc-1/access/apps",
        _list_envelope({"id": "app-1", "domain": "irc.culture.dev"}),
    )
    http_stub.set(
        "GET", "/accounts/acc-1/access/apps/app-1/policies",
        _list_envelope({"id": "pol-1", "name": "irc.culture.dev-allow"}),
    )
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/apps/app-1/policies/pol-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "pol-1"}},
    )
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/apps/app-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "app-1"}},
    )
    http_stub.set(
        "GET", "/zones/zid-1/dns_records",
        _list_envelope({
            "id": "rec-1", "type": "CNAME", "name": "irc.culture.dev",
            "content": "tun-1.cfargotunnel.com", "proxied": True,
        }),
    )
    http_stub.set(
        "DELETE", "/zones/zid-1/dns_records/rec-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "rec-1"}},
    )
    http_stub.set(
        "GET", "/accounts/acc-1/cfd_tunnel",
        _list_envelope({"id": "tun-1", "name": "irc-culture-dev"}),
    )
    http_stub.set(
        "DELETE", "/accounts/acc-1/cfd_tunnel/tun-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "tun-1"}},
    )
    result = teardown(ctx=_ctx(), keep_tunnel=False)
    assert isinstance(result, TeardownResult)
    assert [s.name for s in result.steps] == [
        "service-token", "allow-policy", "access-app", "dns", "tunnel",
    ]
    delete_paths = [c[1] for c in http_stub.calls if c[0] == "DELETE"]
    assert all("organizations" not in p for p in delete_paths)


def test_teardown_keep_tunnel_skips_tunnel_delete(http_stub):
    http_stub.set("GET", "/accounts/acc-1/access/service_tokens", _empty_list())
    http_stub.set("GET", "/accounts/acc-1/access/apps", _empty_list())
    http_stub.set("GET", "/zones/zid-1/dns_records", _empty_list())
    # tunnel listing is skipped entirely under keep_tunnel
    result = teardown(ctx=_ctx(), keep_tunnel=True)
    assert "tunnel" not in [s.name for s in result.steps]
