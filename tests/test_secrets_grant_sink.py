"""Tests for cultureflare._secrets._grant_sink — subprocess.run mocked."""

import json
import os
import subprocess

import pytest

from cultureflare._secrets._grant_sink import seal
from cultureflare._secrets._types import SealMetadata, GrantTarget
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
        GrantTarget(user=None, name="MY_SECRET"),
        b"the-secret",
        _META,
    )

    assert len(fake.calls) == 1
    argv = fake.calls[0]["argv"]
    assert argv[0] == "grant"
    assert "--user" not in argv
    assert "--hidden" in argv
    assert "set" in argv
    assert "MY_SECRET" in argv
    assert argv[-1] == "-"


def test_seal_cross_user_argv_uses_sudo(monkeypatch):
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake)

    seal(
        GrantTarget(user="alice", name="MY_SECRET"),
        b"the-secret",
        _META,
    )

    argv = fake.calls[0]["argv"]
    assert argv[:3] == ["sudo", "-n", "grant"]
    assert "--user" in argv
    assert argv[argv.index("--user") + 1] == "alice"


def test_seal_passes_metadata_flags(monkeypatch):
    fake = _FakeRun(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake)

    seal(
        GrantTarget(user=None, name="MY_SECRET"),
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
        GrantTarget(user=None, name="MY_SECRET"),
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
    target = GrantTarget(user=None, name="MY_SECRET")
    with pytest.raises(TypeError, match="bytes"):
        seal(
            target,
            "this-is-a-str",  # type: ignore[arg-type]
            _META,
        )


def test_seal_exit_64_maps_to_user_error(monkeypatch):
    fake = _FakeRun(returncode=64, stderr=b"name already exists")
    monkeypatch.setattr(subprocess, "run", fake)

    target = GrantTarget(user=None, name="N")
    with pytest.raises(CfafiError) as exc:
        seal(target, b"x", _META)
    assert exc.value.code == EXIT_USER_ERROR
    assert "already exists" in (exc.value.message + exc.value.remediation).lower() \
        or "grant" in exc.value.message.lower()


def test_seal_exit_65_maps_to_api(monkeypatch):
    fake = _FakeRun(returncode=65, stderr=b"store corrupt")
    monkeypatch.setattr(subprocess, "run", fake)

    target = GrantTarget(user=None, name="N")
    with pytest.raises(CfafiError) as exc:
        seal(target, b"x", _META)
    assert exc.value.code == EXIT_API


def test_seal_exit_66_root_required_maps_to_user_error(monkeypatch):
    fake = _FakeRun(returncode=66, stderr=b"requires root")
    monkeypatch.setattr(subprocess, "run", fake)

    target = GrantTarget(user="alice", name="N")
    with pytest.raises(CfafiError) as exc:
        seal(target, b"x", _META)
    assert exc.value.code == EXIT_USER_ERROR
    assert "sudo" in (exc.value.remediation + exc.value.message).lower()


def test_seal_filenotfound_returns_install_remediation(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError(2, "No such file or directory: 'grant'")
    monkeypatch.setattr(subprocess, "run", boom)

    target = GrantTarget(user=None, name="N")
    with pytest.raises(CfafiError) as exc:
        seal(target, b"x", _META)
    assert exc.value.code == EXIT_USER_ERROR
    assert "uv tool install grant" in exc.value.remediation


# ---------------------------------------------------------------------------
# probe() tests
# ---------------------------------------------------------------------------

from cultureflare._secrets._grant_sink import probe  # noqa: E402


def test_probe_returns_metadata_dict_when_present(monkeypatch):
    # grant show --json emits a flat object: {"ok": true, "name": ..., ...}
    raw = {"ok": True, "name": "MY_SECRET", "hidden": True,
           "source": "cultureflare/remote-login"}

    class _Run:
        def __call__(self, argv, **kwargs):
            assert "show" in argv
            assert "--json" in argv
            return subprocess.CompletedProcess(
                args=argv, returncode=0,
                stdout=json.dumps(raw).encode(),
                stderr=b"",
            )

    monkeypatch.setattr(subprocess, "run", _Run())
    out = probe(GrantTarget(user=None, name="MY_SECRET"))
    expected = {k: v for k, v in raw.items() if k != "ok"}
    assert out == expected


def test_probe_returns_none_when_record_absent(monkeypatch):
    err = json.dumps({"ok": False,
                      "error": {"code": "NOT_FOUND",
                                "message": "no such record"}}).encode()

    class _Run:
        def __call__(self, argv, **kwargs):
            return subprocess.CompletedProcess(
                args=argv, returncode=64, stdout=err, stderr=b"",
            )

    monkeypatch.setattr(subprocess, "run", _Run())
    out = probe(GrantTarget(user=None, name="MISSING"))
    assert out is None


def test_probe_uses_sudo_for_cross_user(monkeypatch):
    captured: list[list[str]] = []

    class _Run:
        def __call__(self, argv, **kwargs):
            captured.append(argv)
            return subprocess.CompletedProcess(
                args=argv, returncode=0,
                stdout=b'{"ok": true, "name": "X"}',
                stderr=b"",
            )

    monkeypatch.setattr(subprocess, "run", _Run())
    probe(GrantTarget(user="alice", name="X"))
    assert len(captured) == 1, f"expected exactly 1 subprocess call, got {len(captured)}"
    argv = captured[0]
    assert argv[:3] == ["sudo", "-n", "grant"]
    assert "--user" in argv
    assert argv[argv.index("--user") + 1] == "alice"


def test_probe_other_error_raises(monkeypatch):
    class _Run:
        def __call__(self, argv, **kwargs):
            return subprocess.CompletedProcess(
                args=argv, returncode=65, stdout=b"", stderr=b"corrupt",
            )

    monkeypatch.setattr(subprocess, "run", _Run())
    target = GrantTarget(user=None, name="X")
    with pytest.raises(CfafiError) as exc:
        probe(target)
    assert exc.value.code == EXIT_API


def test_probe_filenotfound_raises(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError(2, "No such file: grant")
    monkeypatch.setattr(subprocess, "run", boom)
    target = GrantTarget(user=None, name="X")
    with pytest.raises(CfafiError) as exc:
        probe(target)
    assert exc.value.code == EXIT_USER_ERROR


# ---------------------------------------------------------------------------
# delete() tests
# ---------------------------------------------------------------------------

from cultureflare._secrets._grant_sink import delete  # noqa: E402


def test_delete_returns_true_on_success(monkeypatch):
    class _Run:
        def __call__(self, argv, **kwargs):
            assert "delete" in argv
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout=b"", stderr=b"",
            )
    monkeypatch.setattr(subprocess, "run", _Run())
    assert delete(GrantTarget(user=None, name="X")) is True


def test_delete_returns_false_when_already_absent(monkeypatch):
    class _Run:
        def __call__(self, argv, **kwargs):
            return subprocess.CompletedProcess(
                args=argv, returncode=64, stdout=b"", stderr=b"no such record",
            )
    monkeypatch.setattr(subprocess, "run", _Run())
    assert delete(GrantTarget(user=None, name="X")) is False


def test_delete_uses_sudo_for_cross_user(monkeypatch):
    captured: list[list[str]] = []

    class _Run:
        def __call__(self, argv, **kwargs):
            captured.append(argv)
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout=b"", stderr=b"",
            )

    monkeypatch.setattr(subprocess, "run", _Run())
    delete(GrantTarget(user="alice", name="X"))
    assert len(captured) == 1, f"expected exactly 1 subprocess call, got {len(captured)}"
    argv = captured[0]
    assert argv[:3] == ["sudo", "-n", "grant"]
    assert "--user" in argv
    assert argv[argv.index("--user") + 1] == "alice"


def test_delete_other_error_raises(monkeypatch):
    class _Run:
        def __call__(self, argv, **kwargs):
            return subprocess.CompletedProcess(
                args=argv, returncode=70, stdout=b"", stderr=b"grant bug",
            )
    monkeypatch.setattr(subprocess, "run", _Run())
    target = GrantTarget(user=None, name="X")
    with pytest.raises(CfafiError) as exc:
        delete(target)
    assert exc.value.code == EXIT_API


# ---------------------------------------------------------------------------
# sudo -n no-creds test
# ---------------------------------------------------------------------------


def test_seal_sudo_no_password_cached_remediation(monkeypatch):
    """Bug fix: sudo -n failing with 'password is required' maps to a
    curated CfafiError with a sudo -v / NOPASSWD remediation hint."""
    fake = _FakeRun(
        returncode=1,
        stderr=b"sudo: a password is required\n",
    )
    monkeypatch.setattr(subprocess, "run", fake)

    target = GrantTarget(user="alice", name="N")
    with pytest.raises(CfafiError) as exc:
        seal(target, b"x", _META)
    assert exc.value.code == EXIT_USER_ERROR
    assert (
        "sudo -v" in exc.value.remediation
        or "NOPASSWD" in exc.value.remediation
    )


def test_not_found_message_names_grant(monkeypatch):
    def _raise(argv, **kwargs):
        raise FileNotFoundError(2, "nope")

    monkeypatch.setattr(subprocess, "run", _raise)
    target = GrantTarget(user=None, name="X")
    with pytest.raises(CfafiError) as exc:
        seal(target, b"v", _META)
    assert "grant binary not found" in exc.value.message
    assert "uv tool install grant" in exc.value.remediation
    assert "shushu" not in exc.value.message + exc.value.remediation


def test_shushu_aliases_point_at_grant():
    import cultureflare._secrets._grant_sink as g
    import cultureflare._secrets._shushu_sink as s
    from cultureflare._secrets import _types

    assert s is g
    assert _types.ShushuTarget is _types.GrantTarget


def test_seal_with_fake_grant_on_path(tmp_path, monkeypatch):
    """Real subprocess: a fake ``grant`` on PATH records argv + stdin."""
    import sys

    log = tmp_path / "record.json"
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "grant"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"json.dump({{'argv': sys.argv[1:], 'stdin': sys.stdin.read()}}, "
        f"open({str(log)!r}, 'w'))\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:" + os.environ.get("PATH", ""))

    seal(GrantTarget(user=None, name="MY_SECRET"), b"s3cr3t", _META)

    rec = json.loads(log.read_text())
    assert rec["stdin"] == "s3cr3t"
    assert rec["argv"] == [
        "set", "--hidden",
        "--source", "cultureflare/remote-login",
        "--purpose", "remote-login app.example.com",
        "--rotate-howto", "rotate me",
        "MY_SECRET", "-",
    ]
    assert "s3cr3t" not in rec["argv"]


# --- review #61 findings 7 + 9 ------------------------------------------

def test_exit_64_remediation_uses_sudo_and_user_for_cross_user(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _FakeRun(returncode=64, stderr=b"exists"))
    target = GrantTarget(user="alice", name="MY_SECRET")
    with pytest.raises(CfafiError) as ei:
        seal(target, b"x", _META)
    rem = ei.value.remediation
    assert "sudo -n grant show --user alice MY_SECRET" in rem
    assert "sudo -n grant delete --user alice MY_SECRET" in rem


def test_exit_64_remediation_plain_for_self(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _FakeRun(returncode=64, stderr=b"exists"))
    target = GrantTarget(user=None, name="MY_SECRET")
    with pytest.raises(CfafiError) as ei:
        seal(target, b"x", _META)
    assert "`grant show MY_SECRET`" in ei.value.remediation
    assert "sudo" not in ei.value.remediation


def test_missing_binary_raises_typed_not_found(monkeypatch):
    from cultureflare._secrets._grant_sink import GrantNotFoundError

    def boom(argv, **kw):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", boom)
    target = GrantTarget(user=None, name="MY_SECRET")
    with pytest.raises(GrantNotFoundError):
        seal(target, b"x", _META)


def test_sudo_command_not_found_is_typed_not_found(monkeypatch):
    from cultureflare._secrets._grant_sink import GrantNotFoundError, probe

    monkeypatch.setattr(subprocess, "run", _FakeRun(
        returncode=1, stderr=b"sudo: grant: command not found\n",
    ))
    target = GrantTarget(user="alice", name="MY_SECRET")
    with pytest.raises(GrantNotFoundError) as ei:
        probe(target)
    assert "secure_path" in ei.value.remediation
