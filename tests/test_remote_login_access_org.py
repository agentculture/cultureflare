"""Tests for cfafi._remote_login._access_org."""

import pytest

from cfafi._remote_login._access_org import find_org, ensure_org
from cfafi.cli._errors import CfafiError, EXIT_USER_ERROR


def test_find_org_returns_auth_domain_when_present(http_stub):
    http_stub.set("GET", "/accounts/acc-1/access/organizations", {
        "success": True, "errors": [], "messages": [],
        "result": {
            "name": "AgentCulture",
            "auth_domain": "agentculture.cloudflareaccess.com",
            "session_duration": "24h",
        },
    })
    org = find_org(account_id="acc-1")
    assert org == {
        "name": "AgentCulture",
        "auth_domain": "agentculture.cloudflareaccess.com",
        "session_duration": "24h",
    }


def test_find_org_returns_none_when_result_is_null(http_stub):
    http_stub.set("GET", "/accounts/acc-1/access/organizations", {
        "success": True, "errors": [], "messages": [], "result": None,
    })
    assert find_org(account_id="acc-1") is None


def test_ensure_org_returns_existing_without_posting(http_stub):
    http_stub.set("GET", "/accounts/acc-1/access/organizations", {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "AgentCulture", "auth_domain": "x.cloudflareaccess.com"},
    })
    auth_domain, created = ensure_org(
        account_id="acc-1", name="AgentCulture",
        auth_domain="x.cloudflareaccess.com",
    )
    assert auth_domain == "x.cloudflareaccess.com"
    assert created is False
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert posts == []


def test_ensure_org_posts_when_absent(http_stub):
    http_stub.queue(
        {"success": True, "errors": [], "messages": [], "result": None},
    )
    http_stub.set("POST", "/accounts/acc-1/access/organizations", {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "AgentCulture", "auth_domain": "x.cloudflareaccess.com"},
    })
    auth_domain, created = ensure_org(
        account_id="acc-1", name="AgentCulture",
        auth_domain="x.cloudflareaccess.com",
    )
    assert auth_domain == "x.cloudflareaccess.com"
    assert created is True
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][2] == {"name": "AgentCulture", "auth_domain": "x.cloudflareaccess.com"}


def test_ensure_org_refuses_when_existing_auth_domain_differs(http_stub):
    http_stub.set("GET", "/accounts/acc-1/access/organizations", {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "Other", "auth_domain": "other.cloudflareaccess.com"},
    })
    with pytest.raises(CfafiError) as exc:
        ensure_org(
            account_id="acc-1", name="AgentCulture",
            auth_domain="x.cloudflareaccess.com",
        )
    assert exc.value.code == EXIT_USER_ERROR
    assert "auth_domain" in exc.value.message
