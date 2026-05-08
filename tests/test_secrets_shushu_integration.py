"""Integration tests against the real shushu binary.

Skipped unless ``SHUSHU_INTEGRATION=1`` and ``shushu`` is on PATH.
The test owns the lifecycle of one entry name per test function so
parallel runs don't collide."""

import os
import shutil
import subprocess
import uuid

import pytest

from cultureflare._secrets._shushu_sink import delete, probe, seal
from cultureflare._secrets._types import SealMetadata, ShushuTarget


pytestmark = pytest.mark.skipif(
    os.environ.get("SHUSHU_INTEGRATION") != "1"
    or shutil.which("shushu") is None,
    reason="set SHUSHU_INTEGRATION=1 and install shushu to run",
)


_META = SealMetadata(
    source="cultureflare/remote-login",
    purpose="integration test",
    rotate_howto="not for production",
)


@pytest.fixture
def unique_name():
    name = f"CULTUREFLARE_TEST_{uuid.uuid4().hex.upper()}"
    yield name
    # best-effort cleanup
    delete(ShushuTarget(user=None, name=name))


def test_round_trip_seal_and_run_inject(unique_name):
    payload = b"the-quick-brown-fox-9382"
    seal(ShushuTarget(user=None, name=unique_name), payload, _META)

    # probe returns metadata without value
    meta = probe(ShushuTarget(user=None, name=unique_name))
    assert meta is not None
    assert meta.get("hidden") is True
    assert meta.get("value") is None or "value" not in meta

    # consume via run --inject; capture the injected env var
    out = subprocess.run(
        ["shushu", "run", "--inject", f"S={unique_name}",
         "--", "bash", "-c", "printf %s \"$S\""],
        capture_output=True, check=True,
    )
    assert out.stdout == payload


def test_delete_removes_entry(unique_name):
    seal(ShushuTarget(user=None, name=unique_name), b"x", _META)
    assert delete(ShushuTarget(user=None, name=unique_name)) is True
    assert probe(ShushuTarget(user=None, name=unique_name)) is None


def test_delete_returns_false_on_missing():
    name = f"CULTUREFLARE_NOPE_{uuid.uuid4().hex.upper()}"
    assert delete(ShushuTarget(user=None, name=name)) is False
