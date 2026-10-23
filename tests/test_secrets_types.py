"""Tests for cultureflare._secrets._types."""

import pytest

from cultureflare._secrets._types import SealMetadata, GrantTarget


def test_grant_target_immutable():
    t = GrantTarget(user=None, name="MY_SECRET")
    with pytest.raises(Exception):  # FrozenInstanceError subclass of Exception
        t.name = "OTHER"  # type: ignore[misc]


def test_grant_target_self_user_is_none():
    t = GrantTarget(user=None, name="MY_SECRET")
    assert t.user is None
    assert t.name == "MY_SECRET"


def test_grant_target_cross_user():
    t = GrantTarget(user="alice", name="MY_SECRET")
    assert t.user == "alice"


def test_seal_metadata_holds_three_strings():
    m = SealMetadata(
        source="cultureflare/remote-login",
        purpose="remote-login app.example.com",
        rotate_howto="cultureflare remote-login teardown && setup --grant --apply",
    )
    assert m.source == "cultureflare/remote-login"
    assert m.purpose == "remote-login app.example.com"
    assert "teardown" in m.rotate_howto


def test_shushu_target_alias_is_grant_target():
    from cultureflare._secrets._types import GrantTarget, ShushuTarget as Alias

    assert Alias is GrantTarget
