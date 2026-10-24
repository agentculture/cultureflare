"""Integration tests against the real grant binary.

Skipped unless ``GRANT_INTEGRATION=1`` and ``grant`` is on PATH.
The test owns the lifecycle of one entry name per test function so
parallel runs don't collide."""

import os
import shutil
import subprocess
import uuid

import pytest

from cultureflare._secrets._grant_sink import delete, probe, seal
from cultureflare._secrets._types import SealMetadata, GrantTarget


pytestmark = pytest.mark.skipif(
    os.environ.get("GRANT_INTEGRATION") != "1"
    or shutil.which("grant") is None,
    reason="set GRANT_INTEGRATION=1 and install grant to run",
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
    delete(GrantTarget(user=None, name=name))


def test_round_trip_seal_and_run_inject(unique_name):
    payload = b"the-quick-brown-fox-9382"
    seal(GrantTarget(user=None, name=unique_name), payload, _META)

    # probe returns metadata without value
    meta = probe(GrantTarget(user=None, name=unique_name))
    assert meta is not None
    assert meta.get("hidden") is True
    assert meta.get("value") is None or "value" not in meta

    # consume via run --inject; capture the injected env var
    out = subprocess.run(
        ["grant", "run", "--inject", f"S={unique_name}",
         "--", "bash", "-c", "printf %s \"$S\""],
        capture_output=True, check=True,
    )
    assert out.stdout == payload


def test_delete_removes_entry(unique_name):
    seal(GrantTarget(user=None, name=unique_name), b"x", _META)
    assert delete(GrantTarget(user=None, name=unique_name)) is True
    assert probe(GrantTarget(user=None, name=unique_name)) is None


def test_delete_returns_false_on_missing():
    name = f"CULTUREFLARE_NOPE_{uuid.uuid4().hex.upper()}"
    assert delete(GrantTarget(user=None, name=name)) is False
