"""Tests for cultureflare._secrets._shushu_sink — subprocess.run mocked."""

import subprocess

import pytest

from cultureflare._secrets._shushu_sink import seal
from cultureflare._secrets._types import SealMetadata, ShushuTarget
from cultureflare.cli._errors import (
    CfafiError, EXIT_API, EXIT_USER_ERROR,
)


_META = SealMetadata(
    source="cultureflare/remote-login",
    purpose="remote-login app.example.com",
    rotate_howto="rotate me",
)


class _FakeRun:
    """Records subprocess.run call args + returns a programmable result."""

    def __init__(self, returncode=0, stderr=b""):
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": argv, "kwargs": kwargs})
        return subprocess.CompletedProcess(
            args=argv, returncode=self.returncode,
            stdout=b"", stderr=self.stderr,
        )


def test_seal_self_user_argv_no_sudo(monkeypatch):
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake)

    seal(
        ShushuTarget(user=None, name="MY_SECRET"),
        b"the-secret",
        _META,
    )

    assert len(fake.calls) == 1
    argv = fake.calls[0]["argv"]
    assert argv[0] == "shushu"
    assert "--user" not in argv
    assert "--hidden" in argv
    assert "set" in argv
    assert "MY_SECRET" in argv
    assert argv[-1] == "-"


def test_seal_cross_user_argv_uses_sudo(monkeypatch):
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake)

    seal(
        ShushuTarget(user="alice", name="MY_SECRET"),
        b"the-secret",
        _META,
    )

    argv = fake.calls[0]["argv"]
    assert argv[:2] == ["sudo", "shushu"]
    assert "--user" in argv
    assert argv[argv.index("--user") + 1] == "alice"


def test_seal_passes_metadata_flags(monkeypatch):
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake)

    seal(
        ShushuTarget(user=None, name="MY_SECRET"),
        b"x",
        _META,
    )

    argv = fake.calls[0]["argv"]
    src_idx = argv.index("--source")
    assert argv[src_idx + 1] == "cultureflare/remote-login"
    purpose_idx = argv.index("--purpose")
    assert argv[purpose_idx + 1] == "remote-login app.example.com"
    rh_idx = argv.index("--rotate-howto")
    assert argv[rh_idx + 1] == "rotate me"


def test_seal_secret_passed_via_stdin_not_argv(monkeypatch):
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake)

    seal(
        ShushuTarget(user=None, name="MY_SECRET"),
        b"super-secret-value",
        _META,
    )

    argv = fake.calls[0]["argv"]
    kwargs = fake.calls[0]["kwargs"]
    assert b"super-secret-value" not in str(argv).encode()
    assert "super-secret-value" not in str(argv)
    assert kwargs.get("input") == b"super-secret-value"


def test_seal_str_secret_raises_typeerror(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _FakeRun())
    with pytest.raises(TypeError, match="bytes"):
        seal(
            ShushuTarget(user=None, name="MY_SECRET"),
            "this-is-a-str",  # type: ignore[arg-type]
            _META,
        )


def test_seal_exit_64_maps_to_user_error(monkeypatch):
    fake = _FakeRun(returncode=64, stderr=b"name already exists")
    monkeypatch.setattr(subprocess, "run", fake)

    with pytest.raises(CfafiError) as exc:
        seal(ShushuTarget(user=None, name="N"), b"x", _META)
    assert exc.value.code == EXIT_USER_ERROR
    assert "already exists" in (exc.value.message + exc.value.remediation).lower() \
        or "shushu" in exc.value.message.lower()


def test_seal_exit_65_maps_to_api(monkeypatch):
    fake = _FakeRun(returncode=65, stderr=b"store corrupt")
    monkeypatch.setattr(subprocess, "run", fake)

    with pytest.raises(CfafiError) as exc:
        seal(ShushuTarget(user=None, name="N"), b"x", _META)
    assert exc.value.code == EXIT_API


def test_seal_exit_66_root_required_maps_to_user_error(monkeypatch):
    fake = _FakeRun(returncode=66, stderr=b"requires root")
    monkeypatch.setattr(subprocess, "run", fake)

    with pytest.raises(CfafiError) as exc:
        seal(ShushuTarget(user="alice", name="N"), b"x", _META)
    assert exc.value.code == EXIT_USER_ERROR
    assert "sudo" in (exc.value.remediation + exc.value.message).lower()


def test_seal_filenotfound_returns_install_remediation(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError(2, "No such file or directory: 'shushu'")
    monkeypatch.setattr(subprocess, "run", boom)

    with pytest.raises(CfafiError) as exc:
        seal(ShushuTarget(user=None, name="N"), b"x", _META)
    assert exc.value.code == EXIT_USER_ERROR
    assert "uv tool install shushu" in exc.value.remediation
