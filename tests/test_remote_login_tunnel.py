"""Tests for cfafi._remote_login._tunnel."""

import pytest

from cfafi._remote_login._tunnel import (
    find_tunnel, ensure_tunnel, get_tunnel_token, delete_tunnel,
)


def _list_envelope(*tunnels):
    return {
        "success": True, "errors": [], "messages": [],
        "result": list(tunnels),
        "result_info": {"page": 1, "total_pages": 1},
    }


def test_find_tunnel_returns_id_when_name_matches(http_stub):
    http_stub.queue(_list_envelope(
        {"id": "tun-a", "name": "other"},
        {"id": "tun-b", "name": "irc-culture-dev"},
    ))
    t = find_tunnel(account_id="acc-1", name="irc-culture-dev")
    assert t == {"id": "tun-b", "name": "irc-culture-dev"}


def test_find_tunnel_returns_none_when_no_match(http_stub):
    http_stub.queue(_list_envelope({"id": "tun-a", "name": "other"}))
    assert find_tunnel(account_id="acc-1", name="missing") is None


def test_find_tunnel_lists_with_is_deleted_false(http_stub):
    http_stub.queue(_list_envelope())
    find_tunnel(account_id="acc-1", name="x")
    method, path, _, query = http_stub.calls[0]
    assert method == "GET"
    assert path == "/accounts/acc-1/cfd_tunnel"
    assert query.get("is_deleted") == "false"


def test_ensure_tunnel_returns_existing(http_stub):
    http_stub.queue(_list_envelope({"id": "tun-b", "name": "irc-culture-dev"}))
    tid, created = ensure_tunnel(account_id="acc-1", name="irc-culture-dev")
    assert tid == "tun-b"
    assert created is False
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert posts == []


def test_ensure_tunnel_posts_when_absent(http_stub):
    http_stub.queue(_list_envelope())
    http_stub.set("POST", "/accounts/acc-1/cfd_tunnel", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "tun-new", "name": "irc-culture-dev"},
    })
    tid, created = ensure_tunnel(account_id="acc-1", name="irc-culture-dev")
    assert tid == "tun-new"
    assert created is True
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][2] == {"name": "irc-culture-dev", "config_src": "cloudflare"}


def test_get_tunnel_token_returns_runtime_token(http_stub):
    http_stub.set(
        "GET", "/accounts/acc-1/cfd_tunnel/tun-b/token",
        {"success": True, "errors": [], "messages": [], "result": "eyJrIjoiZm9vIn0="},
    )
    assert get_tunnel_token(account_id="acc-1", tunnel_id="tun-b") == "eyJrIjoiZm9vIn0="


def test_delete_tunnel_passes_force_true(http_stub):
    http_stub.set(
        "DELETE", "/accounts/acc-1/cfd_tunnel/tun-b",
        {"success": True, "errors": [], "messages": [], "result": {"id": "tun-b"}},
    )
    delete_tunnel(account_id="acc-1", tunnel_id="tun-b")
    method, path, _, query = http_stub.calls[0]
    assert method == "DELETE"
    assert path == "/accounts/acc-1/cfd_tunnel/tun-b"
    assert query.get("force") == "true"
