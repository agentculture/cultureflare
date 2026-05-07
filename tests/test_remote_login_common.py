"""Tests for cfafi._remote_login._common."""

from cfafi._remote_login._common import Context, derive_names, resolve_zone
from cfafi.cli._errors import CfafiError
import pytest


def test_derive_names_slugs_hostname_for_tunnel():
    n = derive_names(hostname="irc.culture.dev")
    assert n.tunnel_name == "irc-culture-dev"


def test_derive_names_app_name_defaults_to_hostname():
    n = derive_names(hostname="irc.culture.dev")
    assert n.app_name == "irc.culture.dev"


def test_derive_names_service_token_default_suffix():
    n = derive_names(hostname="irc.culture.dev")
    assert n.service_token_name == "irc.culture.dev-svc"


def test_derive_names_overrides_take_precedence():
    n = derive_names(
        hostname="irc.culture.dev",
        tunnel_name="custom-tun",
        app_name="custom-app",
        service_token_name="custom-svc",
    )
    assert n.tunnel_name == "custom-tun"
    assert n.app_name == "custom-app"
    assert n.service_token_name == "custom-svc"


def test_derive_names_policy_name_is_app_name_dash_allow():
    n = derive_names(hostname="irc.culture.dev")
    assert n.policy_name == "irc.culture.dev-allow"


def test_resolve_zone_returns_id_for_exact_zone_match(http_stub):
    http_stub.queue({
        "success": True, "errors": [], "messages": [],
        "result": [
            {"id": "zid-1", "name": "culture.dev"},
            {"id": "zid-2", "name": "example.com"},
        ],
        "result_info": {"page": 1, "total_pages": 1},
    })
    assert resolve_zone("irc.culture.dev") == ("zid-1", "culture.dev")


def test_resolve_zone_picks_longest_matching_suffix(http_stub):
    # Defends against shadowed zones like example.com vs sub.example.com
    http_stub.queue({
        "success": True, "errors": [], "messages": [],
        "result": [
            {"id": "zid-short", "name": "example.com"},
            {"id": "zid-long", "name": "sub.example.com"},
        ],
        "result_info": {"page": 1, "total_pages": 1},
    })
    assert resolve_zone("api.sub.example.com") == ("zid-long", "sub.example.com")


def test_resolve_zone_raises_when_no_zone_matches(http_stub):
    http_stub.queue({
        "success": True, "errors": [], "messages": [],
        "result": [{"id": "zid-1", "name": "culture.dev"}],
        "result_info": {"page": 1, "total_pages": 1},
    })
    with pytest.raises(CfafiError) as exc:
        resolve_zone("irc.example.com")
    assert "no zone in this account" in exc.value.message.lower()
