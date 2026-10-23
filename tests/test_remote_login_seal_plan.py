"""Tests for cultureflare._remote_login._seal_plan."""

import pytest

from cultureflare._remote_login._seal_plan import SealPlan, derive_seal_plan
from cultureflare._secrets._types import SealMetadata, ShushuTarget
from cultureflare.cli._errors import CfafiError, EXIT_USER_ERROR


def test_disabled_when_arg_is_none():
    p = derive_seal_plan(hostname="app.example.com", shushu_arg=None)
    assert p.enabled is False


def test_enabled_invoking_user_when_arg_is_empty():
    p = derive_seal_plan(hostname="app.example.com", shushu_arg="")
    assert p.enabled is True
    assert p.user is None
    assert p.tunnel_token_target.user is None


def test_enabled_cross_user_when_arg_is_username():
    p = derive_seal_plan(hostname="app.example.com", shushu_arg="alice")
    assert p.enabled is True
    assert p.user == "alice"
    assert p.tunnel_token_target.user == "alice"
    assert p.service_token_secret_target.user == "alice"


def test_slug_uppercases_and_replaces_dots_and_dashes():
    p = derive_seal_plan(hostname="app-svc.example.com", shushu_arg="")
    assert p.tunnel_token_target.name == \
        "CULTUREFLARE_APP_SVC_EXAMPLE_COM_TUNNEL_TOKEN"
    assert p.service_token_secret_target.name == \
        "CULTUREFLARE_APP_SVC_EXAMPLE_COM_SVC_SECRET"


def test_slug_handles_single_label():
    p = derive_seal_plan(hostname="localhost", shushu_arg="")
    assert p.tunnel_token_target.name == \
        "CULTUREFLARE_LOCALHOST_TUNNEL_TOKEN"


def test_metadata_includes_hostname_in_purpose():
    p = derive_seal_plan(hostname="app.example.com", shushu_arg="")
    assert p.metadata.source == "cultureflare/remote-login"
    assert "app.example.com" in p.metadata.purpose
    assert "teardown" in p.metadata.rotate_howto
    assert "setup" in p.metadata.rotate_howto


def test_metadata_rotate_howto_includes_user_when_cross_user():
    p = derive_seal_plan(hostname="app.example.com", shushu_arg="alice")
    assert "--grant=alice" in p.metadata.rotate_howto


def test_metadata_rotate_howto_uses_bare_grant_when_self():
    p = derive_seal_plan(hostname="app.example.com", shushu_arg="")
    # bare --grant (no =USER) for the invoking-user case
    assert "--grant " in p.metadata.rotate_howto or \
           p.metadata.rotate_howto.endswith("--grant")
    assert "--grant=" not in p.metadata.rotate_howto


def test_non_ascii_hostname_raises():
    with pytest.raises(CfafiError) as exc:
        derive_seal_plan(hostname="münich.example.com", shushu_arg="")
    assert exc.value.code == EXIT_USER_ERROR
    assert "ASCII" in exc.value.message


def test_returned_targets_are_immutable():
    p = derive_seal_plan(hostname="app.example.com", shushu_arg="alice")
    assert isinstance(p.tunnel_token_target, ShushuTarget)
    assert isinstance(p.service_token_secret_target, ShushuTarget)
    assert isinstance(p.metadata, SealMetadata)


def test_disabled_plan_still_has_targets():
    # Convenience: when disabled, targets are still computed (helpful
    # for dry-run rendering that wants to show "would seal as ...").
    p = derive_seal_plan(hostname="app.example.com", shushu_arg=None)
    assert p.tunnel_token_target.name == \
        "CULTUREFLARE_APP_EXAMPLE_COM_TUNNEL_TOKEN"
    assert p.user is None


# --- grant rename + secret-name validation -------------------------------

LONG_HOST = "a" * 20 + "." + "b" * 20 + ".example.com"  # slug > 64 chars


@pytest.mark.parametrize(
    "host", [LONG_HOST, "a*b.example.com", "x" * 39 + ".com"]
)
def test_invalid_derived_name_refused_when_sealing_enabled(host):
    with pytest.raises(CfafiError) as ei:
        derive_seal_plan(hostname=host, grant_arg="alice")
    assert ei.value.code == EXIT_USER_ERROR
    assert "CULTUREFLARE_" in ei.value.message
    assert "64" in ei.value.message


def test_invalid_derived_name_refused_for_bare_flag():
    with pytest.raises(CfafiError):
        derive_seal_plan(hostname="a*b.example.com", grant_arg="")


@pytest.mark.parametrize("host", [LONG_HOST, "a*b.example.com"])
def test_invalid_derived_name_allowed_when_sealing_disabled(host):
    p = derive_seal_plan(hostname=host, grant_arg=None)
    assert p.enabled is False
    p = derive_seal_plan(hostname=host, shushu_arg=None)
    assert p.enabled is False


def test_grant_arg_and_shushu_arg_alias_equal():
    a = derive_seal_plan(hostname="app.example.com", grant_arg="alice")
    b = derive_seal_plan(hostname="app.example.com", shushu_arg="alice")
    assert a == b


def test_both_args_raises_user_error():
    with pytest.raises(CfafiError) as ei:
        derive_seal_plan(
            hostname="app.example.com", grant_arg="a", shushu_arg="b"
        )
    assert ei.value.code == EXIT_USER_ERROR


def test_rotate_howto_uses_grant_flag():
    p = derive_seal_plan(hostname="app.example.com", grant_arg="alice")
    assert "--grant=alice" in p.metadata.rotate_howto
    p = derive_seal_plan(hostname="app.example.com", grant_arg="")
    assert "--grant " in p.metadata.rotate_howto
    assert "--shushu" not in p.metadata.rotate_howto


# --- review #61 finding 2: name guard is setup-only ---------------------

_LONG_HOST = "a-really-long-subdomain-name.example.culture.dev"  # > 38 chars


def test_validate_names_false_skips_guard_when_sealing_enabled():
    plan = derive_seal_plan(
        hostname=_LONG_HOST, grant_arg="", validate_names=False,
    )
    assert plan.enabled is True
    assert len(plan.tunnel_token_target.name) > 64


def test_validate_names_defaults_to_true():
    with pytest.raises(CfafiError):
        derive_seal_plan(hostname=_LONG_HOST, grant_arg="")
