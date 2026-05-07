"""Tests for cfafi._remote_login._access_policy."""

import pytest

from cfafi._remote_login._access_policy import (
    build_include, find_policy, ensure_allow_policy, delete_policy,
)
from cfafi.cli._errors import CfafiError, EXIT_USER_ERROR


def _list_envelope(*policies):
    return {
        "success": True, "errors": [], "messages": [],
        "result": list(policies),
        "result_info": {"page": 1, "total_pages": 1},
    }


def test_build_include_emails():
    assert build_include(emails=["a@x.com", "b@y.com"], domains=[]) == [
        {"email": {"email": "a@x.com"}},
        {"email": {"email": "b@y.com"}},
    ]


def test_build_include_strips_leading_at_from_domains():
    assert build_include(emails=[], domains=["@example.com"]) == [
        {"email_domain": {"domain": "example.com"}},
    ]


def test_build_include_accepts_domains_without_at():
    assert build_include(emails=[], domains=["example.com"]) == [
        {"email_domain": {"domain": "example.com"}},
    ]


def test_build_include_combined():
    out = build_include(emails=["a@x.com"], domains=["@y.com"])
    assert out == [
        {"email": {"email": "a@x.com"}},
        {"email_domain": {"domain": "y.com"}},
    ]


def test_build_include_raises_when_both_lists_empty():
    with pytest.raises(CfafiError) as exc:
        build_include(emails=[], domains=[])
    assert exc.value.code == EXIT_USER_ERROR


def test_find_policy_matches_by_name(http_stub):
    http_stub.queue(_list_envelope(
        {"id": "pol-a", "name": "other"},
        {"id": "pol-b", "name": "irc.culture.dev-allow"},
    ))
    p = find_policy(
        account_id="acc-1", app_id="app-1", name="irc.culture.dev-allow",
    )
    assert p == {"id": "pol-b", "name": "irc.culture.dev-allow"}


def test_ensure_allow_policy_returns_existing(http_stub):
    http_stub.queue(_list_envelope(
        {"id": "pol-b", "name": "irc.culture.dev-allow"},
    ))
    pid, created = ensure_allow_policy(
        account_id="acc-1", app_id="app-1",
        name="irc.culture.dev-allow",
        emails=["a@x.com"], domains=[],
    )
    assert pid == "pol-b"
    assert created is False
    assert [c for c in http_stub.calls if c[0] == "POST"] == []


def test_ensure_allow_policy_posts_when_absent(http_stub):
    http_stub.queue(_list_envelope())
    http_stub.set(
        "POST", "/accounts/acc-1/access/apps/app-1/policies",
        {"success": True, "errors": [], "messages": [],
         "result": {"id": "pol-new", "name": "irc.culture.dev-allow"}},
    )
    pid, created = ensure_allow_policy(
        account_id="acc-1", app_id="app-1",
        name="irc.culture.dev-allow",
        emails=["a@x.com"], domains=["@y.com"],
    )
    assert pid == "pol-new"
    assert created is True
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert posts[0][2] == {
        "name": "irc.culture.dev-allow",
        "decision": "allow",
        "include": [
            {"email": {"email": "a@x.com"}},
            {"email_domain": {"domain": "y.com"}},
        ],
    }


def test_delete_policy_calls_delete(http_stub):
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/apps/app-1/policies/pol-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "pol-1"}},
    )
    delete_policy(account_id="acc-1", app_id="app-1", policy_id="pol-1")
    assert http_stub.calls == [
        ("DELETE", "/accounts/acc-1/access/apps/app-1/policies/pol-1", None, {}),
    ]
