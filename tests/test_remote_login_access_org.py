"""Tests for cfafi._remote_login._access_org."""

import pytest

from cfafi._remote_login._access_org import find_org, ensure_org
from cfafi.cli._errors import CfafiError, EXIT_API, EXIT_AUTH, EXIT_USER_ERROR


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


def test_find_org_returns_none_when_access_not_enabled(http_stub):
    # CF returns HTTP 4xx with `code: 9999, message:
    # "access.api.error.not_enabled: ..."` before Zero Trust is
    # enabled on the account. The helper must swallow that into None
    # so callers fall into their cleaner ZT-disabled branch rather
    # than bubbling CF's raw error.
    http_stub.set(
        "GET", "/accounts/acc-1/access/organizations",
        CfafiError(
            code=EXIT_API,
            message=(
                "CloudFlare API 9999: access.api.error.not_enabled: "
                "Access is not enabled. Visit the Access dashboard..."
            ),
            remediation="HTTP 404 from CloudFlare; inspect the request body and retry",
        ),
    )
    assert find_org(account_id="acc-1") is None


def test_find_org_propagates_other_errors(http_stub):
    # Non-9999 CfafiErrors (e.g. auth / 403 from missing scopes) must
    # propagate so the operator sees the real cause instead of a
    # silently-empty org.
    http_stub.set(
        "GET", "/accounts/acc-1/access/organizations",
        CfafiError(
            code=EXIT_AUTH,
            message="CloudFlare API 10000: Authentication error",
            remediation="check token scopes against docs/SETUP.md",
        ),
    )
    with pytest.raises(CfafiError) as exc:
        find_org(account_id="acc-1")
    assert exc.value.code == EXIT_AUTH
    assert "Authentication error" in exc.value.message


def test_find_org_does_not_swallow_unrelated_error_with_9999_substring(http_stub):
    # The check is anchored on "CloudFlare API 9999:" so an unrelated
    # error whose message merely contains "9999" or "not_enabled" as
    # substrings (e.g. an id or a different field) must still propagate.
    http_stub.set(
        "GET", "/accounts/acc-1/access/organizations",
        CfafiError(
            code=EXIT_API,
            message=(
                "CloudFlare API 12345: tunnel id 9999-aaaa not_enabled flag "
                "in unrelated context"
            ),
            remediation="HTTP 500 from CloudFlare; inspect the request body and retry",
        ),
    )
    with pytest.raises(CfafiError) as exc:
        find_org(account_id="acc-1")
    assert exc.value.code == EXIT_API
    assert "12345" in exc.value.message


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
