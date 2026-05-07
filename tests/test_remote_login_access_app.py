"""Tests for cfafi._remote_login._access_app."""

from cfafi._remote_login._access_app import find_app, ensure_app, delete_app


def _list_envelope(*apps):
    return {
        "success": True, "errors": [], "messages": [],
        "result": list(apps),
        "result_info": {"page": 1, "total_pages": 1},
    }


def test_find_app_returns_app_when_domain_matches(http_stub):
    http_stub.queue(_list_envelope(
        {"id": "app-a", "domain": "other.example.com"},
        {"id": "app-b", "domain": "irc.culture.dev"},
    ))
    a = find_app(account_id="acc-1", hostname="irc.culture.dev")
    assert a == {"id": "app-b", "domain": "irc.culture.dev"}


def test_find_app_returns_none_when_no_match(http_stub):
    http_stub.queue(_list_envelope())
    assert find_app(account_id="acc-1", hostname="irc.culture.dev") is None


def test_ensure_app_returns_existing(http_stub):
    http_stub.queue(_list_envelope({"id": "app-b", "domain": "irc.culture.dev"}))
    aid, created = ensure_app(
        account_id="acc-1", hostname="irc.culture.dev",
        app_name="irc.culture.dev", session_duration="24h",
    )
    assert aid == "app-b"
    assert created is False
    assert [c for c in http_stub.calls if c[0] == "POST"] == []


def test_ensure_app_posts_when_absent(http_stub):
    http_stub.queue(_list_envelope())
    http_stub.set("POST", "/accounts/acc-1/access/apps", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "app-new", "domain": "irc.culture.dev"},
    })
    aid, created = ensure_app(
        account_id="acc-1", hostname="irc.culture.dev",
        app_name="irc.culture.dev", session_duration="24h",
    )
    assert aid == "app-new"
    assert created is True
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert posts[0][2] == {
        "name": "irc.culture.dev",
        "domain": "irc.culture.dev",
        "type": "self_hosted",
        "session_duration": "24h",
    }


def test_delete_app_calls_delete_with_id(http_stub):
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/apps/app-b",
        {"success": True, "errors": [], "messages": [], "result": {"id": "app-b"}},
    )
    delete_app(account_id="acc-1", app_id="app-b")
    assert http_stub.calls == [("DELETE", "/accounts/acc-1/access/apps/app-b", None, {})]
