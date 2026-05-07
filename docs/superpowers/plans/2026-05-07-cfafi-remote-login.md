# `cfafi remote-login` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an action-oriented `cfafi remote-login` noun (verbs: `setup`, `show`, `teardown`) that owns the full Cloudflare-side sequence to put a hostname behind Cloudflare Access via a Tunnel.

**Architecture:** Internal helper package `cfafi/_remote_login/` with one module per resource type (Access org, tunnel, DNS, Access app, allow-policy, service token), each exporting `find_*` / `ensure_*` / `delete_*` functions. An orchestrator (`__init__.py`) composes them in order for `setup`, in parallel for `show`, in reverse for `teardown`. A CLI module (`cfafi/cli/_commands/remote_login.py`) wires argparse + rendering. Pre-flight token-scope validation runs before any orchestration.

**Tech Stack:** Python 3.12, stdlib only (no new runtime deps), pytest with the existing `http_stub` fixture.

**Spec:** `docs/superpowers/specs/2026-05-07-cfafi-remote-login-design.md`

**Branch:** `feat/remote-login-action` (already created off `main`; the design doc is committed as `47e364d`).

---

## File Structure

**New files (cfafi package):**

| Path | Responsibility |
|---|---|
| `cfafi/_remote_login/__init__.py` | Public orchestrator: `setup()`, `show()`, `teardown()`, plus `Context` + result dataclasses |
| `cfafi/_remote_login/_common.py` | `Context` dataclass, `derive_names()`, hostname → zone resolution |
| `cfafi/_remote_login/_preflight.py` | `check_token_scopes()` against `/user/tokens/verify` response |
| `cfafi/_remote_login/_access_org.py` | `find_org()`, `ensure_org()` |
| `cfafi/_remote_login/_tunnel.py` | `find_tunnel()`, `ensure_tunnel()`, `get_tunnel_token()`, `delete_tunnel()` |
| `cfafi/_remote_login/_dns.py` | `find_cname()`, `ensure_cname()`, `delete_cname()` |
| `cfafi/_remote_login/_access_app.py` | `find_app()`, `ensure_app()`, `delete_app()` |
| `cfafi/_remote_login/_access_policy.py` | `find_policy()`, `ensure_allow_policy()`, `delete_policy()` |
| `cfafi/_remote_login/_service_token.py` | `find_service_token()`, `ensure_service_token()`, `delete_service_token()` |
| `cfafi/_remote_login/_render.py` | Markdown / JSON envelope rendering for setup/show/teardown |
| `cfafi/cli/_commands/remote_login.py` | argparse wiring, calls orchestrator, calls renderer |

**New test files (one per module):**

`tests/test_remote_login_common.py`,
`tests/test_remote_login_preflight.py`,
`tests/test_remote_login_access_org.py`,
`tests/test_remote_login_tunnel.py`,
`tests/test_remote_login_dns.py`,
`tests/test_remote_login_access_app.py`,
`tests/test_remote_login_access_policy.py`,
`tests/test_remote_login_service_token.py`,
`tests/test_remote_login_orchestrator.py`,
`tests/test_remote_login_render.py`,
`tests/test_cli_remote_login.py`.

**Modified files:**

| Path | Change |
|---|---|
| `cfafi/cli/__init__.py` | Register the new `remote_login` command in `_build_parser()` |
| `docs/SETUP.md` | New section: "Operator token scopes" listing the five scopes for `remote-login` |
| `pyproject.toml` | Version bump (minor — new feature) |
| `CHANGELOG.md` | New `[Unreleased]` → `[0.2.0]` section |

---

## Task 1: Scaffold the package directory

**Files:**
- Create: `cfafi/_remote_login/__init__.py` (empty placeholder)
- Create: `cfafi/_remote_login/_common.py` (empty placeholder)

- [ ] **Step 1: Create the package directory with empty modules**

```bash
mkdir -p cfafi/_remote_login
: > cfafi/_remote_login/__init__.py
: > cfafi/_remote_login/_common.py
```

- [ ] **Step 2: Verify package imports cleanly**

Run: `python -c "import cfafi._remote_login"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add cfafi/_remote_login/
git commit -m "feat(remote-login): scaffold _remote_login package"
```

---

## Task 2: Common types — `Context`, `derive_names`, zone resolution

**Files:**
- Create: `tests/test_remote_login_common.py`
- Modify: `cfafi/_remote_login/_common.py`

`Context` is a frozen dataclass passed to every helper. `derive_names()` produces the default tunnel/app/service-token names from a hostname. `resolve_zone()` finds the zone-id whose name is a suffix of the hostname.

- [ ] **Step 1: Write failing tests for `derive_names`**

Create `tests/test_remote_login_common.py`:

```python
"""Tests for cfafi._remote_login._common."""

from cfafi._remote_login._common import Context, derive_names, resolve_zone
from cfafi.cli._errors import CfafiError
import pytest


def test_derive_names_slugs_hostname_for_tunnel():
    n = derive_names(hostname="irc.culture.dev")
    assert n.tunnel_name == "irc-culture-dev"


def test_derive_names_app_name_defaults_to_hostname():
    n = derive_names(hostname="irc.culture.dev")
    assert n.app_name == "irc.culture.dev"


def test_derive_names_service_token_default_suffix():
    n = derive_names(hostname="irc.culture.dev")
    assert n.service_token_name == "irc.culture.dev-svc"


def test_derive_names_overrides_take_precedence():
    n = derive_names(
        hostname="irc.culture.dev",
        tunnel_name="custom-tun",
        app_name="custom-app",
        service_token_name="custom-svc",
    )
    assert n.tunnel_name == "custom-tun"
    assert n.app_name == "custom-app"
    assert n.service_token_name == "custom-svc"


def test_derive_names_policy_name_is_app_name_dash_allow():
    n = derive_names(hostname="irc.culture.dev")
    assert n.policy_name == "irc.culture.dev-allow"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_common.py -v`
Expected: ImportError or "module has no attribute 'derive_names'".

- [ ] **Step 3: Implement `_common.py` minimally to pass derive_names tests**

```python
"""Common types and pure helpers for the remote-login orchestrator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Names:
    tunnel_name: str
    app_name: str
    service_token_name: str
    policy_name: str


def derive_names(
    *,
    hostname: str,
    tunnel_name: str | None = None,
    app_name: str | None = None,
    service_token_name: str | None = None,
) -> Names:
    """Derive default resource names from a hostname.

    The slugged tunnel name replaces dots with dashes so it survives
    CloudFlare's tunnel-name validation (alphanumerics + dashes only).
    """
    tn = tunnel_name or hostname.replace(".", "-")
    an = app_name or hostname
    stn = service_token_name or f"{hostname}-svc"
    return Names(
        tunnel_name=tn,
        app_name=an,
        service_token_name=stn,
        policy_name=f"{an}-allow",
    )


@dataclass(frozen=True)
class Context:
    """Runtime context shared across all _remote_login helpers."""

    account_id: str
    zone_id: str
    hostname: str
    names: Names
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_common.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Add zone-resolution tests**

Append to `tests/test_remote_login_common.py`:

```python
def test_resolve_zone_returns_id_for_exact_zone_match(http_stub):
    http_stub.queue({
        "success": True, "errors": [], "messages": [],
        "result": [
            {"id": "zid-1", "name": "culture.dev"},
            {"id": "zid-2", "name": "example.com"},
        ],
        "result_info": {"page": 1, "total_pages": 1},
    })
    assert resolve_zone("irc.culture.dev") == ("zid-1", "culture.dev")


def test_resolve_zone_picks_longest_matching_suffix(http_stub):
    # Defends against shadowed zones like example.com vs sub.example.com
    http_stub.queue({
        "success": True, "errors": [], "messages": [],
        "result": [
            {"id": "zid-short", "name": "example.com"},
            {"id": "zid-long", "name": "sub.example.com"},
        ],
        "result_info": {"page": 1, "total_pages": 1},
    })
    assert resolve_zone("api.sub.example.com") == ("zid-long", "sub.example.com")


def test_resolve_zone_raises_when_no_zone_matches(http_stub):
    http_stub.queue({
        "success": True, "errors": [], "messages": [],
        "result": [{"id": "zid-1", "name": "culture.dev"}],
        "result_info": {"page": 1, "total_pages": 1},
    })
    with pytest.raises(CfafiError) as exc:
        resolve_zone("irc.example.com")
    assert "no zone in this account" in exc.value.message.lower()
```

- [ ] **Step 6: Run tests to verify the new ones fail**

Run: `uv run pytest tests/test_remote_login_common.py -v`
Expected: 3 new tests fail with "no attribute 'resolve_zone'".

- [ ] **Step 7: Implement `resolve_zone`**

Append to `cfafi/_remote_login/_common.py`:

```python
import cfafi._api as _api  # noqa: E402  (after dataclass defs to keep top-of-file lean)
from cfafi.cli._errors import EXIT_USER_ERROR, CfafiError


def resolve_zone(hostname: str) -> tuple[str, str]:
    """Return (zone_id, zone_name) for the longest-suffix zone match.

    Raises CfafiError(EXIT_USER_ERROR) if no zone in the account
    is a suffix of the hostname.
    """
    candidates: list[tuple[str, str]] = []
    for zone in _api.paginate("/zones"):
        name = zone.get("name") or ""
        if hostname == name or hostname.endswith("." + name):
            candidates.append((zone.get("id", ""), name))
    if not candidates:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message=f"no zone in this account is a suffix of {hostname}",
            remediation="run `cfafi zones list` to see accessible zones",
        )
    candidates.sort(key=lambda z: len(z[1]), reverse=True)
    return candidates[0]
```

- [ ] **Step 8: Run all tests in this file**

Run: `uv run pytest tests/test_remote_login_common.py -v`
Expected: 8 tests pass.

- [ ] **Step 9: Commit**

```bash
git add cfafi/_remote_login/_common.py tests/test_remote_login_common.py
git commit -m "feat(remote-login): Context, derive_names, resolve_zone"
```

---

## Task 3: Pre-flight token scope check

**Files:**
- Create: `cfafi/_remote_login/_preflight.py`
- Create: `tests/test_remote_login_preflight.py`

`/user/tokens/verify` returns `{result: {policies: [{permission_groups: [{name: "..."}]}]}}` — we walk that structure and assert the operation's required scopes are all covered.

- [ ] **Step 1: Write failing tests**

Create `tests/test_remote_login_preflight.py`:

```python
"""Tests for cfafi._remote_login._preflight."""

import pytest

from cfafi._remote_login._preflight import check_token_scopes
from cfafi.cli._errors import CfafiError, EXIT_AUTH


def _verify_response(*scope_names: str) -> dict:
    return {
        "success": True, "errors": [], "messages": [],
        "result": {
            "id": "tok-1",
            "status": "active",
            "policies": [{
                "permission_groups": [{"name": s} for s in scope_names],
                "resources": {},
            }],
        },
    }


def test_passes_when_all_required_scopes_present(http_stub):
    http_stub.queue(_verify_response(
        "Cloudflare Tunnel Write",
        "Access: Apps and Policies Write",
        "Access: Organizations Write",
        "DNS Write",
    ))
    # Should not raise.
    check_token_scopes(operation="setup", with_service_token=False)


def test_passes_when_with_service_token_and_st_scope_present(http_stub):
    http_stub.queue(_verify_response(
        "Cloudflare Tunnel Write",
        "Access: Apps and Policies Write",
        "Access: Service Tokens Write",
        "Access: Organizations Write",
        "DNS Write",
    ))
    check_token_scopes(operation="setup", with_service_token=True)


def test_raises_when_required_scope_missing(http_stub):
    http_stub.queue(_verify_response("DNS Write"))  # missing tunnel + access
    with pytest.raises(CfafiError) as exc:
        check_token_scopes(operation="setup", with_service_token=False)
    assert exc.value.code == EXIT_AUTH
    assert "Cloudflare Tunnel Write" in exc.value.message


def test_show_only_requires_read_scopes(http_stub):
    http_stub.queue(_verify_response(
        "Cloudflare Tunnel Read",
        "Access: Apps and Policies Read",
        "DNS Read",
    ))
    check_token_scopes(operation="show", with_service_token=False)


def test_teardown_does_not_require_organizations_write(http_stub):
    # We never delete the ZT org, so teardown shouldn't demand that scope.
    http_stub.queue(_verify_response(
        "Cloudflare Tunnel Write",
        "Access: Apps and Policies Write",
        "DNS Write",
    ))
    check_token_scopes(operation="teardown", with_service_token=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_preflight.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `_preflight.py`**

```python
"""Pre-flight token-scope validation.

CloudFlare permission-group names (as returned by
``/user/tokens/verify``) are stable strings; we hard-code the ones we
care about. If a future scope rename happens upstream we'll see the
mismatch in tests before it bites operators.
"""

from __future__ import annotations

from typing import Literal

import cfafi._api as _api
from cfafi.cli._errors import EXIT_AUTH, CfafiError

Operation = Literal["setup", "show", "teardown"]

# Required permission-group names per operation. Read scopes suffice
# for `show`; everything else needs Write.
_REQUIRED: dict[Operation, set[str]] = {
    "setup": {
        "Cloudflare Tunnel Write",
        "Access: Apps and Policies Write",
        "Access: Organizations Write",
        "DNS Write",
    },
    "show": {
        "Cloudflare Tunnel Read",
        "Access: Apps and Policies Read",
        "DNS Read",
    },
    "teardown": {
        "Cloudflare Tunnel Write",
        "Access: Apps and Policies Write",
        "DNS Write",
    },
}

_SERVICE_TOKEN_SCOPE = "Access: Service Tokens Write"


def _granted_scopes(verify_response: dict) -> set[str]:
    result = verify_response.get("result") or {}
    policies = result.get("policies") or []
    out: set[str] = set()
    for pol in policies:
        for pg in pol.get("permission_groups") or []:
            name = pg.get("name")
            if name:
                out.add(name)
    return out


def check_token_scopes(*, operation: Operation, with_service_token: bool) -> None:
    """Raise CfafiError(EXIT_AUTH) if the configured token lacks any scope.

    Calls ``GET /user/tokens/verify`` once and walks the response.
    """
    response = _api.http_request("GET", "/user/tokens/verify")
    granted = _granted_scopes(response)
    required = set(_REQUIRED[operation])
    if operation == "setup" and with_service_token:
        required.add(_SERVICE_TOKEN_SCOPE)

    missing = sorted(required - granted)
    if missing:
        raise CfafiError(
            code=EXIT_AUTH,
            message=(
                "configured CLOUDFLARE_API_TOKEN is missing required scopes: "
                + ", ".join(missing)
            ),
            remediation=(
                "mint a token with these permission groups in the CloudFlare "
                "dashboard (My Profile → API Tokens → Create Token → "
                "Custom token). See docs/SETUP.md § Operator token scopes."
            ),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_preflight.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cfafi/_remote_login/_preflight.py tests/test_remote_login_preflight.py
git commit -m "feat(remote-login): pre-flight token-scope validator"
```

---

## Task 4: Access organization helper (find / ensure)

**Files:**
- Create: `cfafi/_remote_login/_access_org.py`
- Create: `tests/test_remote_login_access_org.py`

`GET /accounts/{id}/access/organizations` returns one record (the org) under `result` (singular dict, not a list — Access has one org per account). If absent, CF returns success with `result: null` or HTTP 404 depending on version; treat both as "no org".

- [ ] **Step 1: Write failing tests**

Create `tests/test_remote_login_access_org.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_access_org.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `_access_org.py`**

```python
"""CloudFlare Access organization (Zero Trust) helpers."""

from __future__ import annotations

import cfafi._api as _api
from cfafi.cli._errors import EXIT_USER_ERROR, CfafiError


def find_org(*, account_id: str) -> dict | None:
    """Return the Access org dict, or None if Zero Trust is not enabled."""
    response = _api.http_request(
        "GET", f"/accounts/{account_id}/access/organizations"
    )
    return response.get("result") or None


def ensure_org(
    *, account_id: str, name: str, auth_domain: str
) -> tuple[str, bool]:
    """Find or create the Zero Trust organization.

    Returns (auth_domain, created). If an org exists with a *different*
    auth_domain than requested, raises EXIT_USER_ERROR rather than
    overwriting — operators reset Zero Trust from the dashboard, not
    from cfafi.
    """
    existing = find_org(account_id=account_id)
    if existing is not None:
        existing_domain = existing.get("auth_domain") or ""
        if existing_domain and existing_domain != auth_domain:
            raise CfafiError(
                code=EXIT_USER_ERROR,
                message=(
                    f"Zero Trust org already exists with auth_domain="
                    f"{existing_domain!r}, refusing to repoint to "
                    f"{auth_domain!r}"
                ),
                remediation=(
                    "either pass --auth-domain matching the existing org, "
                    "or reset Zero Trust from the dashboard"
                ),
            )
        return existing.get("auth_domain") or auth_domain, False

    response = _api.http_request(
        "POST",
        f"/accounts/{account_id}/access/organizations",
        payload={"name": name, "auth_domain": auth_domain},
    )
    created = (response.get("result") or {})
    return created.get("auth_domain") or auth_domain, True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_access_org.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cfafi/_remote_login/_access_org.py tests/test_remote_login_access_org.py
git commit -m "feat(remote-login): Access org find/ensure helpers"
```

---

## Task 5: Tunnel helper (find / ensure / get-token / delete)

**Files:**
- Create: `cfafi/_remote_login/_tunnel.py`
- Create: `tests/test_remote_login_tunnel.py`

CloudFlare endpoints: `GET/POST /accounts/{id}/cfd_tunnel`, `GET /accounts/{id}/cfd_tunnel/{tid}/token`, `DELETE /accounts/{id}/cfd_tunnel/{tid}?force=true`.

The list endpoint returns *all* tunnels (including deleted ones unless `is_deleted=false` filter is passed). We always pass `is_deleted=false` to skip tombstones.

- [ ] **Step 1: Write failing tests**

Create `tests/test_remote_login_tunnel.py`:

```python
"""Tests for cfafi._remote_login._tunnel."""

import pytest

from cfafi._remote_login._tunnel import (
    find_tunnel, ensure_tunnel, get_tunnel_token, delete_tunnel,
)


def _list_envelope(*tunnels):
    return {
        "success": True, "errors": [], "messages": [],
        "result": list(tunnels),
        "result_info": {"page": 1, "total_pages": 1},
    }


def test_find_tunnel_returns_id_when_name_matches(http_stub):
    http_stub.queue(_list_envelope(
        {"id": "tun-a", "name": "other"},
        {"id": "tun-b", "name": "irc-culture-dev"},
    ))
    t = find_tunnel(account_id="acc-1", name="irc-culture-dev")
    assert t == {"id": "tun-b", "name": "irc-culture-dev"}


def test_find_tunnel_returns_none_when_no_match(http_stub):
    http_stub.queue(_list_envelope({"id": "tun-a", "name": "other"}))
    assert find_tunnel(account_id="acc-1", name="missing") is None


def test_find_tunnel_lists_with_is_deleted_false(http_stub):
    http_stub.queue(_list_envelope())
    find_tunnel(account_id="acc-1", name="x")
    method, path, payload, query = http_stub.calls[0]
    assert method == "GET"
    assert path == "/accounts/acc-1/cfd_tunnel"
    assert query.get("is_deleted") == "false"


def test_ensure_tunnel_returns_existing(http_stub):
    http_stub.queue(_list_envelope({"id": "tun-b", "name": "irc-culture-dev"}))
    tid, created = ensure_tunnel(account_id="acc-1", name="irc-culture-dev")
    assert tid == "tun-b"
    assert created is False
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert posts == []


def test_ensure_tunnel_posts_when_absent(http_stub):
    http_stub.queue(_list_envelope())
    http_stub.set("POST", "/accounts/acc-1/cfd_tunnel", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "tun-new", "name": "irc-culture-dev"},
    })
    tid, created = ensure_tunnel(account_id="acc-1", name="irc-culture-dev")
    assert tid == "tun-new"
    assert created is True
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][2] == {"name": "irc-culture-dev", "config_src": "cloudflare"}


def test_get_tunnel_token_returns_runtime_token(http_stub):
    http_stub.set(
        "GET", "/accounts/acc-1/cfd_tunnel/tun-b/token",
        {"success": True, "errors": [], "messages": [], "result": "eyJrIjoiZm9vIn0="},
    )
    assert get_tunnel_token(account_id="acc-1", tunnel_id="tun-b") == "eyJrIjoiZm9vIn0="


def test_delete_tunnel_passes_force_true(http_stub):
    http_stub.set(
        "DELETE", "/accounts/acc-1/cfd_tunnel/tun-b",
        {"success": True, "errors": [], "messages": [], "result": {"id": "tun-b"}},
    )
    delete_tunnel(account_id="acc-1", tunnel_id="tun-b")
    method, path, payload, query = http_stub.calls[0]
    assert method == "DELETE"
    assert path == "/accounts/acc-1/cfd_tunnel/tun-b"
    assert query.get("force") == "true"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_tunnel.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `_tunnel.py`**

```python
"""CloudFlare cfd_tunnel helpers (Cloudflared / 'remote-managed' tunnels)."""

from __future__ import annotations

import cfafi._api as _api


def find_tunnel(*, account_id: str, name: str) -> dict | None:
    """Return the tunnel dict whose .name matches, or None.

    Always filters out deleted tunnels (CF retains tombstones with the
    same name but distinct IDs; querying without is_deleted=false leads
    to ambiguous matches).
    """
    for tun in _api.paginate(
        f"/accounts/{account_id}/cfd_tunnel",
        query={"is_deleted": "false"},
    ):
        if tun.get("name") == name:
            return tun
    return None


def ensure_tunnel(*, account_id: str, name: str) -> tuple[str, bool]:
    """Find or create a cloudflare-managed tunnel by name."""
    existing = find_tunnel(account_id=account_id, name=name)
    if existing is not None:
        return existing["id"], False
    response = _api.http_request(
        "POST",
        f"/accounts/{account_id}/cfd_tunnel",
        payload={"name": name, "config_src": "cloudflare"},
    )
    return response["result"]["id"], True


def get_tunnel_token(*, account_id: str, tunnel_id: str) -> str:
    """Fetch the runtime token (passed to `cloudflared tunnel run --token`).

    Refetchable on every call; not a one-shot secret.
    """
    response = _api.http_request(
        "GET",
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/token",
    )
    token = response.get("result")
    if not isinstance(token, str):
        raise RuntimeError(
            f"unexpected /cfd_tunnel/{tunnel_id}/token response shape"
        )
    return token


def delete_tunnel(*, account_id: str, tunnel_id: str) -> None:
    """DELETE the tunnel with ?force=true to drop active connections."""
    _api.http_request(
        "DELETE",
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}",
        query={"force": "true"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_tunnel.py -v`
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cfafi/_remote_login/_tunnel.py tests/test_remote_login_tunnel.py
git commit -m "feat(remote-login): tunnel helpers"
```

---

## Task 6: DNS CNAME helper (find / ensure / delete)

**Files:**
- Create: `cfafi/_remote_login/_dns.py`
- Create: `tests/test_remote_login_dns.py`

The CNAME content is `<tunnel-id>.cfargotunnel.com` and must be **proxied** for Access to gate it. If a CNAME exists at the hostname pointing somewhere other than our tunnel, we raise rather than try to repoint (per spec § State & idempotency).

- [ ] **Step 1: Write failing tests**

Create `tests/test_remote_login_dns.py`:

```python
"""Tests for cfafi._remote_login._dns."""

import pytest

from cfafi._remote_login._dns import find_cname, ensure_cname, delete_cname
from cfafi.cli._errors import CfafiError, EXIT_USER_ERROR


def _list_envelope(*records):
    return {
        "success": True, "errors": [], "messages": [],
        "result": list(records),
        "result_info": {"page": 1, "total_pages": 1},
    }


def test_find_cname_returns_record_when_present(http_stub):
    http_stub.queue(_list_envelope({
        "id": "rec-1", "type": "CNAME", "name": "irc.culture.dev",
        "content": "tun-b.cfargotunnel.com", "proxied": True,
    }))
    rec = find_cname(zone_id="zid-1", hostname="irc.culture.dev")
    assert rec == {
        "id": "rec-1", "type": "CNAME", "name": "irc.culture.dev",
        "content": "tun-b.cfargotunnel.com", "proxied": True,
    }


def test_find_cname_returns_none_when_no_record(http_stub):
    http_stub.queue(_list_envelope())
    assert find_cname(zone_id="zid-1", hostname="irc.culture.dev") is None


def test_ensure_cname_returns_existing_when_target_matches(http_stub):
    http_stub.queue(_list_envelope({
        "id": "rec-1", "type": "CNAME", "name": "irc.culture.dev",
        "content": "tun-b.cfargotunnel.com", "proxied": True,
    }))
    rid, created = ensure_cname(
        zone_id="zid-1", hostname="irc.culture.dev", tunnel_id="tun-b",
    )
    assert rid == "rec-1"
    assert created is False
    assert [c for c in http_stub.calls if c[0] == "POST"] == []


def test_ensure_cname_raises_when_existing_points_elsewhere(http_stub):
    http_stub.queue(_list_envelope({
        "id": "rec-1", "type": "CNAME", "name": "irc.culture.dev",
        "content": "other.example.com", "proxied": True,
    }))
    with pytest.raises(CfafiError) as exc:
        ensure_cname(
            zone_id="zid-1", hostname="irc.culture.dev", tunnel_id="tun-b",
        )
    assert exc.value.code == EXIT_USER_ERROR
    assert "other.example.com" in exc.value.message


def test_ensure_cname_posts_when_absent(http_stub):
    http_stub.queue(_list_envelope())
    http_stub.set("POST", "/zones/zid-1/dns_records", {
        "success": True, "errors": [], "messages": [],
        "result": {
            "id": "rec-new", "type": "CNAME", "name": "irc.culture.dev",
            "content": "tun-b.cfargotunnel.com", "proxied": True,
        },
    })
    rid, created = ensure_cname(
        zone_id="zid-1", hostname="irc.culture.dev", tunnel_id="tun-b",
    )
    assert rid == "rec-new"
    assert created is True
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][2]["type"] == "CNAME"
    assert posts[0][2]["name"] == "irc.culture.dev"
    assert posts[0][2]["content"] == "tun-b.cfargotunnel.com"
    assert posts[0][2]["proxied"] is True
    assert posts[0][2]["ttl"] == 1


def test_delete_cname_calls_delete_with_record_id(http_stub):
    http_stub.set(
        "DELETE", "/zones/zid-1/dns_records/rec-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "rec-1"}},
    )
    delete_cname(zone_id="zid-1", record_id="rec-1")
    assert http_stub.calls == [("DELETE", "/zones/zid-1/dns_records/rec-1", None, {})]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_dns.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `_dns.py`**

```python
"""CNAME helpers for the remote-login orchestrator."""

from __future__ import annotations

import cfafi._api as _api
from cfafi.cli._errors import EXIT_USER_ERROR, CfafiError


def find_cname(*, zone_id: str, hostname: str) -> dict | None:
    """Return the CNAME record at hostname, or None."""
    for rec in _api.paginate(
        f"/zones/{zone_id}/dns_records",
        query={"type": "CNAME", "name": hostname},
    ):
        return rec
    return None


def ensure_cname(
    *, zone_id: str, hostname: str, tunnel_id: str
) -> tuple[str, bool]:
    """Find or create a proxied CNAME hostname → <tunnel_id>.cfargotunnel.com.

    Raises EXIT_USER_ERROR if an existing CNAME at hostname points
    somewhere else (we refuse to repoint; that's a teardown decision).
    """
    target = f"{tunnel_id}.cfargotunnel.com"
    existing = find_cname(zone_id=zone_id, hostname=hostname)
    if existing is not None:
        if existing.get("content") != target:
            raise CfafiError(
                code=EXIT_USER_ERROR,
                message=(
                    f"DNS CNAME at {hostname} already points to "
                    f"{existing.get('content')!r} — refusing to repoint to "
                    f"{target!r}"
                ),
                remediation=(
                    f"run `cfafi remote-login teardown --hostname {hostname} "
                    f"--apply` first, or change the record in the dashboard"
                ),
            )
        return existing["id"], False

    body = {
        "type": "CNAME",
        "name": hostname,
        "content": target,
        "ttl": 1,
        "proxied": True,
        "comment": f"Managed by cfafi remote-login for {hostname}",
    }
    response = _api.http_request(
        "POST", f"/zones/{zone_id}/dns_records", payload=body
    )
    return response["result"]["id"], True


def delete_cname(*, zone_id: str, record_id: str) -> None:
    """DELETE the DNS record by id."""
    _api.http_request(
        "DELETE", f"/zones/{zone_id}/dns_records/{record_id}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_dns.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cfafi/_remote_login/_dns.py tests/test_remote_login_dns.py
git commit -m "feat(remote-login): DNS CNAME helpers"
```

---

## Task 7: Access app helper (find / ensure / delete)

**Files:**
- Create: `cfafi/_remote_login/_access_app.py`
- Create: `tests/test_remote_login_access_app.py`

`POST /accounts/{id}/access/apps` body: `{"name", "domain", "type": "self_hosted", "session_duration"}`. List endpoint takes optional `?domain=...` query but we'll filter client-side for simplicity (Access apps per account are usually small in number).

- [ ] **Step 1: Write failing tests**

Create `tests/test_remote_login_access_app.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_access_app.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `_access_app.py`**

```python
"""CloudFlare Access application (self-hosted) helpers."""

from __future__ import annotations

import cfafi._api as _api


def find_app(*, account_id: str, hostname: str) -> dict | None:
    """Return the Access app whose .domain == hostname, or None."""
    for app in _api.paginate(f"/accounts/{account_id}/access/apps"):
        if app.get("domain") == hostname:
            return app
    return None


def ensure_app(
    *,
    account_id: str,
    hostname: str,
    app_name: str,
    session_duration: str,
) -> tuple[str, bool]:
    """Find or create a self-hosted Access app on hostname."""
    existing = find_app(account_id=account_id, hostname=hostname)
    if existing is not None:
        return existing["id"], False
    response = _api.http_request(
        "POST",
        f"/accounts/{account_id}/access/apps",
        payload={
            "name": app_name,
            "domain": hostname,
            "type": "self_hosted",
            "session_duration": session_duration,
        },
    )
    return response["result"]["id"], True


def delete_app(*, account_id: str, app_id: str) -> None:
    """DELETE the Access app by id (cascades to its policies)."""
    _api.http_request(
        "DELETE", f"/accounts/{account_id}/access/apps/{app_id}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_access_app.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cfafi/_remote_login/_access_app.py tests/test_remote_login_access_app.py
git commit -m "feat(remote-login): Access app helpers"
```

---

## Task 8: Access allow-policy helper (find / ensure / delete)

**Files:**
- Create: `cfafi/_remote_login/_access_policy.py`
- Create: `tests/test_remote_login_access_policy.py`

Include shapes:
- email: `{"email": {"email": "user@example.com"}}`
- email-domain: `{"email_domain": {"domain": "example.com"}}` (strip the leading `@` if the operator passed `--allow-domain @example.com`).

- [ ] **Step 1: Write failing tests**

Create `tests/test_remote_login_access_policy.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_access_policy.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `_access_policy.py`**

```python
"""CloudFlare Access allow-policy helpers."""

from __future__ import annotations

import cfafi._api as _api
from cfafi.cli._errors import EXIT_USER_ERROR, CfafiError


def build_include(*, emails: list[str], domains: list[str]) -> list[dict]:
    """Convert operator-supplied allow lists into Access include shapes.

    Domains may be passed with or without a leading '@'; we normalise
    by stripping it. We refuse an empty include list — an Access app
    with no allow rule blocks everyone.
    """
    if not emails and not domains:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message="at least one of --allow / --allow-domain is required",
            remediation="pass --allow user@example.com or --allow-domain @example.com",
        )
    include: list[dict] = [{"email": {"email": e}} for e in emails]
    for d in domains:
        normalised = d.lstrip("@")
        include.append({"email_domain": {"domain": normalised}})
    return include


def find_policy(*, account_id: str, app_id: str, name: str) -> dict | None:
    """Return the policy on the app whose .name matches, or None."""
    for pol in _api.paginate(
        f"/accounts/{account_id}/access/apps/{app_id}/policies"
    ):
        if pol.get("name") == name:
            return pol
    return None


def ensure_allow_policy(
    *,
    account_id: str,
    app_id: str,
    name: str,
    emails: list[str],
    domains: list[str],
) -> tuple[str, bool]:
    """Find or create an allow-policy on the Access app."""
    include = build_include(emails=emails, domains=domains)
    existing = find_policy(account_id=account_id, app_id=app_id, name=name)
    if existing is not None:
        return existing["id"], False
    response = _api.http_request(
        "POST",
        f"/accounts/{account_id}/access/apps/{app_id}/policies",
        payload={"name": name, "decision": "allow", "include": include},
    )
    return response["result"]["id"], True


def delete_policy(*, account_id: str, app_id: str, policy_id: str) -> None:
    """DELETE a policy on the Access app."""
    _api.http_request(
        "DELETE",
        f"/accounts/{account_id}/access/apps/{app_id}/policies/{policy_id}",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_access_policy.py -v`
Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cfafi/_remote_login/_access_policy.py tests/test_remote_login_access_policy.py
git commit -m "feat(remote-login): Access allow-policy helpers"
```

---

## Task 9: Service token helper (find / ensure / delete)

**Files:**
- Create: `cfafi/_remote_login/_service_token.py`
- Create: `tests/test_remote_login_service_token.py`

Service tokens are the one-shot-secret resource. `POST` returns `{client_id, client_secret}` exactly once. `find` only returns `client_id` (no secret), so an existing-token re-run cannot reproduce the secret — `ensure_service_token` returns `(client_id, client_secret_or_None, created)`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_remote_login_service_token.py`:

```python
"""Tests for cfafi._remote_login._service_token."""

import pytest

from cfafi._remote_login._service_token import (
    find_service_token, ensure_service_token, delete_service_token,
)
from cfafi.cli._errors import CfafiError, EXIT_USER_ERROR


def _list_envelope(*tokens):
    return {
        "success": True, "errors": [], "messages": [],
        "result": list(tokens),
        "result_info": {"page": 1, "total_pages": 1},
    }


def test_find_service_token_returns_record_when_present(http_stub):
    http_stub.queue(_list_envelope(
        {"id": "st-a", "name": "other-svc", "client_id": "cid-a"},
        {"id": "st-b", "name": "irc-svc", "client_id": "cid-b"},
    ))
    t = find_service_token(account_id="acc-1", name="irc-svc")
    assert t == {"id": "st-b", "name": "irc-svc", "client_id": "cid-b"}


def test_find_service_token_returns_none_when_missing(http_stub):
    http_stub.queue(_list_envelope())
    assert find_service_token(account_id="acc-1", name="missing") is None


def test_ensure_service_token_raises_when_existing_with_strict(http_stub):
    # strict=True means: existing token of this name is an error,
    # because we can't surface the (one-shot) secret.
    http_stub.queue(_list_envelope(
        {"id": "st-b", "name": "irc-svc", "client_id": "cid-b"},
    ))
    with pytest.raises(CfafiError) as exc:
        ensure_service_token(account_id="acc-1", name="irc-svc", strict=True)
    assert exc.value.code == EXIT_USER_ERROR
    assert "secret is not retrievable" in exc.value.message


def test_ensure_service_token_returns_existing_with_no_secret_when_lax(http_stub):
    # strict=False means: caller (e.g. teardown's planner) accepts
    # 'no secret available'. setup() will pass strict=True.
    http_stub.queue(_list_envelope(
        {"id": "st-b", "name": "irc-svc", "client_id": "cid-b"},
    ))
    cid, secret, created = ensure_service_token(
        account_id="acc-1", name="irc-svc", strict=False,
    )
    assert cid == "cid-b"
    assert secret is None
    assert created is False


def test_ensure_service_token_posts_when_absent(http_stub):
    http_stub.queue(_list_envelope())
    http_stub.set("POST", "/accounts/acc-1/access/service_tokens", {
        "success": True, "errors": [], "messages": [],
        "result": {
            "id": "st-new", "name": "irc-svc",
            "client_id": "cid-new", "client_secret": "secret-shhh",
        },
    })
    cid, secret, created = ensure_service_token(
        account_id="acc-1", name="irc-svc", strict=True,
    )
    assert cid == "cid-new"
    assert secret == "secret-shhh"
    assert created is True
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert posts[0][2] == {"name": "irc-svc"}


def test_delete_service_token_calls_delete(http_stub):
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/service_tokens/st-b",
        {"success": True, "errors": [], "messages": [], "result": {"id": "st-b"}},
    )
    delete_service_token(account_id="acc-1", token_id="st-b")
    assert http_stub.calls == [
        ("DELETE", "/accounts/acc-1/access/service_tokens/st-b", None, {}),
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_service_token.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `_service_token.py`**

```python
"""CloudFlare Access service-token helpers.

Service tokens are the only one-shot-secret resource cfafi creates.
``client_secret`` is returned exactly once, by the POST response;
list / get endpoints never expose it again.
"""

from __future__ import annotations

import cfafi._api as _api
from cfafi.cli._errors import EXIT_USER_ERROR, CfafiError


def find_service_token(*, account_id: str, name: str) -> dict | None:
    """Return the service-token record whose .name matches, or None."""
    for tok in _api.paginate(f"/accounts/{account_id}/access/service_tokens"):
        if tok.get("name") == name:
            return tok
    return None


def ensure_service_token(
    *, account_id: str, name: str, strict: bool
) -> tuple[str, str | None, bool]:
    """Find or create a service token.

    Returns (client_id, client_secret_or_None, created).

    ``strict=True`` (used by setup with --with-service-token): if a
    token of this name already exists, raise — its secret can't be
    re-surfaced and the operator likely wanted a fresh one.

    ``strict=False`` (used by show/teardown planners): return the
    existing record with secret=None.
    """
    existing = find_service_token(account_id=account_id, name=name)
    if existing is not None:
        if strict:
            raise CfafiError(
                code=EXIT_USER_ERROR,
                message=(
                    f"service token {name!r} already exists; secret is not "
                    "retrievable"
                ),
                remediation=(
                    f"pass --service-token-name=<other> or run "
                    f"`cfafi remote-login teardown --hostname <host> --apply` "
                    f"first"
                ),
            )
        return existing.get("client_id") or "", None, False

    response = _api.http_request(
        "POST",
        f"/accounts/{account_id}/access/service_tokens",
        payload={"name": name},
    )
    result = response.get("result") or {}
    return (
        result.get("client_id") or "",
        result.get("client_secret"),
        True,
    )


def delete_service_token(*, account_id: str, token_id: str) -> None:
    """DELETE a service token by id."""
    _api.http_request(
        "DELETE", f"/accounts/{account_id}/access/service_tokens/{token_id}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_service_token.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cfafi/_remote_login/_service_token.py tests/test_remote_login_service_token.py
git commit -m "feat(remote-login): service-token helpers"
```

---

## Task 10: Orchestrator — `setup`, `show`, `teardown`

**Files:**
- Modify: `cfafi/_remote_login/__init__.py`
- Create: `tests/test_remote_login_orchestrator.py`
- Modify: `cfafi/_remote_login/_common.py` (add `SetupResult`, `ShowResult`, `TeardownResult` dataclasses)

The orchestrator is the only place that calls all helpers. It takes a fully-populated `Context` and a small parameters object, returns a result dataclass per verb. It does NOT do CLI parsing or rendering — those live separately. This keeps the orchestrator unit-testable through the same `http_stub`.

- [ ] **Step 1: Add result dataclasses to `_common.py`**

Append to `cfafi/_remote_login/_common.py`:

```python
@dataclass
class StepRecord:
    """One step of a setup or teardown plan."""
    name: str           # e.g. "tunnel", "dns", "access-app"
    action: str         # "ensured" | "skipped" | "deleted" | "absent"
    detail: str         # human-readable, no secrets


@dataclass
class SetupResult:
    team_domain: str | None
    tunnel_id: str
    tunnel_name: str
    tunnel_token: str
    dns_record_id: str
    dns_target: str
    access_app_id: str
    policy_id: str
    policy_emails: list[str]
    policy_domains: list[str]
    service_token_client_id: str | None
    service_token_client_secret: str | None
    steps: list[StepRecord]


@dataclass
class ShowResult:
    team_domain: str | None
    tunnel: dict | None
    dns: dict | None
    access_app: dict | None
    policy: dict | None
    service_token: dict | None


@dataclass
class TeardownResult:
    steps: list[StepRecord]
```

- [ ] **Step 2: Write failing tests for `setup`**

Create `tests/test_remote_login_orchestrator.py`:

```python
"""Tests for the cfafi._remote_login orchestrator."""

import pytest

from cfafi._remote_login import setup, show, teardown
from cfafi._remote_login._common import (
    Context, derive_names, SetupResult, ShowResult, TeardownResult,
)


def _ctx(hostname="irc.culture.dev"):
    return Context(
        account_id="acc-1",
        zone_id="zid-1",
        hostname=hostname,
        names=derive_names(hostname=hostname),
    )


def _zt_existing():
    return {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "AC", "auth_domain": "ac.cloudflareaccess.com"},
    }


def _empty_list():
    return {
        "success": True, "errors": [], "messages": [],
        "result": [], "result_info": {"page": 1, "total_pages": 1},
    }


def _list_envelope(*items):
    return {
        "success": True, "errors": [], "messages": [],
        "result": list(items),
        "result_info": {"page": 1, "total_pages": 1},
    }


def test_setup_runs_all_six_steps_in_order_when_nothing_exists(http_stub):
    # 1. ZT find  -> existing
    # 2. tunnel list -> empty -> POST tunnel
    # 3. tunnel-token GET
    # 4. dns list -> empty -> POST dns
    # 5. apps list -> empty -> POST app
    # 6. policies list -> empty -> POST policy
    # 7. service-tokens list -> empty -> POST svc token
    http_stub.queue(
        _zt_existing(),                                       # 1
        _empty_list(),                                        # 2 list tunnels
    )
    http_stub.set("POST", "/accounts/acc-1/cfd_tunnel", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "tun-1", "name": "irc-culture-dev"},
    })
    http_stub.set(
        "GET", "/accounts/acc-1/cfd_tunnel/tun-1/token",
        {"success": True, "errors": [], "messages": [], "result": "TUN-TOK"},
    )
    http_stub.queue(
        _empty_list(),                                        # 4 list dns
    )
    http_stub.set("POST", "/zones/zid-1/dns_records", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "rec-1"},
    })
    http_stub.queue(
        _empty_list(),                                        # 5 list apps
    )
    http_stub.set("POST", "/accounts/acc-1/access/apps", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "app-1"},
    })
    http_stub.queue(
        _empty_list(),                                        # 6 list policies
    )
    http_stub.set(
        "POST", "/accounts/acc-1/access/apps/app-1/policies",
        {"success": True, "errors": [], "messages": [],
         "result": {"id": "pol-1"}},
    )
    http_stub.queue(
        _empty_list(),                                        # 7 list svc tokens
    )
    http_stub.set("POST", "/accounts/acc-1/access/service_tokens", {
        "success": True, "errors": [], "messages": [],
        "result": {
            "id": "st-1", "name": "irc.culture.dev-svc",
            "client_id": "CID", "client_secret": "SEC",
        },
    })

    result = setup(
        ctx=_ctx(),
        emails=["me@example.com"],
        domains=[],
        with_service_token=True,
        session_duration="24h",
    )
    assert isinstance(result, SetupResult)
    assert result.team_domain == "ac.cloudflareaccess.com"
    assert result.tunnel_id == "tun-1"
    assert result.tunnel_token == "TUN-TOK"
    assert result.dns_record_id == "rec-1"
    assert result.access_app_id == "app-1"
    assert result.policy_id == "pol-1"
    assert result.service_token_client_id == "CID"
    assert result.service_token_client_secret == "SEC"
    assert [s.name for s in result.steps] == [
        "zero-trust-org", "tunnel", "dns", "access-app",
        "allow-policy", "service-token",
    ]


def test_setup_skips_service_token_step_when_not_requested(http_stub):
    http_stub.queue(_zt_existing(), _empty_list())  # 1, 2
    http_stub.set("POST", "/accounts/acc-1/cfd_tunnel", {
        "success": True, "errors": [], "messages": [],
        "result": {"id": "tun-1"},
    })
    http_stub.set(
        "GET", "/accounts/acc-1/cfd_tunnel/tun-1/token",
        {"success": True, "errors": [], "messages": [], "result": "TUN-TOK"},
    )
    http_stub.queue(_empty_list())  # 4 dns
    http_stub.set("POST", "/zones/zid-1/dns_records",
                  {"success": True, "errors": [], "messages": [],
                   "result": {"id": "rec-1"}})
    http_stub.queue(_empty_list())  # 5 apps
    http_stub.set("POST", "/accounts/acc-1/access/apps",
                  {"success": True, "errors": [], "messages": [],
                   "result": {"id": "app-1"}})
    http_stub.queue(_empty_list())  # 6 policies
    http_stub.set("POST", "/accounts/acc-1/access/apps/app-1/policies",
                  {"success": True, "errors": [], "messages": [],
                   "result": {"id": "pol-1"}})

    result = setup(
        ctx=_ctx(), emails=["me@example.com"], domains=[],
        with_service_token=False, session_duration="24h",
    )
    assert result.service_token_client_id is None
    assert result.service_token_client_secret is None
    assert "service-token" not in [s.name for s in result.steps]
    # The service-token endpoint must never be called.
    paths = [c[1] for c in http_stub.calls]
    assert "/accounts/acc-1/access/service_tokens" not in paths


def test_show_reports_partial_state(http_stub):
    # ZT exists, tunnel exists, DNS missing, app missing, no policies, no svc.
    http_stub.set("GET", "/accounts/acc-1/access/organizations", {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "AC", "auth_domain": "ac.cloudflareaccess.com"},
    })
    http_stub.queue(
        _list_envelope({"id": "tun-1", "name": "irc-culture-dev"}),  # tunnels
        _empty_list(),                                                # dns
        _empty_list(),                                                # apps
        # apps absent → orchestrator skips listing policies
        _empty_list(),                                                # svc tokens
    )
    result = show(ctx=_ctx())
    assert isinstance(result, ShowResult)
    assert result.team_domain == "ac.cloudflareaccess.com"
    assert result.tunnel == {"id": "tun-1", "name": "irc-culture-dev"}
    assert result.dns is None
    assert result.access_app is None
    assert result.policy is None
    assert result.service_token is None


def test_teardown_reverses_setup_skipping_zt_org(http_stub):
    # Find: app exists with policy; tunnel exists; dns exists; svc exists.
    # Order of deletes: service-token, policy, app, dns, tunnel.
    http_stub.queue(
        _list_envelope({"id": "st-1", "name": "irc.culture.dev-svc",
                        "client_id": "CID"}),                 # find svc
    )
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/service_tokens/st-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "st-1"}},
    )
    http_stub.queue(
        _list_envelope({"id": "app-1", "domain": "irc.culture.dev"}),  # find app
        _list_envelope({"id": "pol-1", "name": "irc.culture.dev-allow"}),  # find policy
    )
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/apps/app-1/policies/pol-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "pol-1"}},
    )
    http_stub.set(
        "DELETE", "/accounts/acc-1/access/apps/app-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "app-1"}},
    )
    http_stub.queue(
        _list_envelope({                                       # find dns
            "id": "rec-1", "type": "CNAME", "name": "irc.culture.dev",
            "content": "tun-1.cfargotunnel.com", "proxied": True,
        }),
    )
    http_stub.set(
        "DELETE", "/zones/zid-1/dns_records/rec-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "rec-1"}},
    )
    http_stub.queue(
        _list_envelope({"id": "tun-1", "name": "irc-culture-dev"}),  # find tunnel
    )
    http_stub.set(
        "DELETE", "/accounts/acc-1/cfd_tunnel/tun-1",
        {"success": True, "errors": [], "messages": [], "result": {"id": "tun-1"}},
    )
    result = teardown(ctx=_ctx(), keep_tunnel=False)
    assert isinstance(result, TeardownResult)
    assert [s.name for s in result.steps] == [
        "service-token", "allow-policy", "access-app", "dns", "tunnel",
    ]
    # ZT org never deleted.
    delete_paths = [c[1] for c in http_stub.calls if c[0] == "DELETE"]
    assert all("organizations" not in p for p in delete_paths)


def test_teardown_keep_tunnel_skips_tunnel_delete(http_stub):
    http_stub.queue(_empty_list())  # find svc -> none
    http_stub.queue(_empty_list())  # find app -> none
    http_stub.queue(_empty_list())  # find dns -> none
    # tunnel listing is skipped entirely under keep_tunnel
    result = teardown(ctx=_ctx(), keep_tunnel=True)
    assert "tunnel" not in [s.name for s in result.steps]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_orchestrator.py -v`
Expected: ImportError on `setup`/`show`/`teardown`.

- [ ] **Step 4: Implement orchestrator in `cfafi/_remote_login/__init__.py`**

```python
"""Remote-login orchestrator.

Composes the per-resource helpers under ``_remote_login/_*`` into the
three operator-facing actions: ``setup`` (create or ensure), ``show``
(read), ``teardown`` (delete in reverse). All three take a populated
``Context`` and return a typed result dataclass; they do NOT perform
CLI parsing or rendering. The CLI module wraps them.
"""

from __future__ import annotations

from cfafi._remote_login._access_app import (
    delete_app, ensure_app, find_app,
)
from cfafi._remote_login._access_org import ensure_org, find_org
from cfafi._remote_login._access_policy import (
    delete_policy, ensure_allow_policy, find_policy,
)
from cfafi._remote_login._common import (
    Context, SetupResult, ShowResult, StepRecord, TeardownResult,
)
from cfafi._remote_login._dns import delete_cname, ensure_cname, find_cname
from cfafi._remote_login._service_token import (
    delete_service_token, ensure_service_token, find_service_token,
)
from cfafi._remote_login._tunnel import (
    delete_tunnel, ensure_tunnel, find_tunnel, get_tunnel_token,
)

__all__ = ["setup", "show", "teardown"]


def setup(
    *,
    ctx: Context,
    emails: list[str],
    domains: list[str],
    with_service_token: bool,
    session_duration: str,
) -> SetupResult:
    """Run the full six-step setup against the live CF API."""
    steps: list[StepRecord] = []

    # 1. Zero Trust org — ensured but never created automatically here:
    #    if absent, ensure_org would need an auth_domain we don't yet
    #    know. For first-time onboarding, we surface a clear error so
    #    the operator can pass --auth-domain (a follow-up flag) or do
    #    the ZT init in the dashboard. v1 assumes ZT already exists.
    org = find_org(account_id=ctx.account_id)
    if org is None:
        from cfafi.cli._errors import EXIT_USER_ERROR, CfafiError
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message="Zero Trust is not enabled for this account",
            remediation=(
                "enable Zero Trust at "
                "https://one.dash.cloudflare.com/?to=/:account/access "
                "(pick a team subdomain), then re-run setup"
            ),
        )
    team_domain = org.get("auth_domain")
    steps.append(StepRecord(
        name="zero-trust-org", action="ensured",
        detail=f"existing auth_domain={team_domain}",
    ))

    # 2. Tunnel.
    tunnel_id, tunnel_created = ensure_tunnel(
        account_id=ctx.account_id, name=ctx.names.tunnel_name,
    )
    steps.append(StepRecord(
        name="tunnel",
        action="ensured" if tunnel_created else "skipped",
        detail=f"{ctx.names.tunnel_name} (id={tunnel_id})",
    ))
    tunnel_token = get_tunnel_token(
        account_id=ctx.account_id, tunnel_id=tunnel_id,
    )

    # 3. DNS CNAME → tunnel.
    dns_id, dns_created = ensure_cname(
        zone_id=ctx.zone_id, hostname=ctx.hostname, tunnel_id=tunnel_id,
    )
    dns_target = f"{tunnel_id}.cfargotunnel.com"
    steps.append(StepRecord(
        name="dns",
        action="ensured" if dns_created else "skipped",
        detail=f"CNAME {ctx.hostname} → {dns_target}",
    ))

    # 4. Access app.
    app_id, app_created = ensure_app(
        account_id=ctx.account_id,
        hostname=ctx.hostname,
        app_name=ctx.names.app_name,
        session_duration=session_duration,
    )
    steps.append(StepRecord(
        name="access-app",
        action="ensured" if app_created else "skipped",
        detail=f"id={app_id}",
    ))

    # 5. Allow-policy.
    policy_id, policy_created = ensure_allow_policy(
        account_id=ctx.account_id, app_id=app_id,
        name=ctx.names.policy_name,
        emails=emails, domains=domains,
    )
    steps.append(StepRecord(
        name="allow-policy",
        action="ensured" if policy_created else "skipped",
        detail=f"id={policy_id}",
    ))

    # 6. Service token (optional).
    svc_cid: str | None = None
    svc_secret: str | None = None
    if with_service_token:
        svc_cid, svc_secret, svc_created = ensure_service_token(
            account_id=ctx.account_id,
            name=ctx.names.service_token_name,
            strict=True,
        )
        steps.append(StepRecord(
            name="service-token",
            action="ensured" if svc_created else "skipped",
            detail=f"client_id={svc_cid}",
        ))

    return SetupResult(
        team_domain=team_domain,
        tunnel_id=tunnel_id,
        tunnel_name=ctx.names.tunnel_name,
        tunnel_token=tunnel_token,
        dns_record_id=dns_id,
        dns_target=dns_target,
        access_app_id=app_id,
        policy_id=policy_id,
        policy_emails=list(emails),
        policy_domains=list(domains),
        service_token_client_id=svc_cid,
        service_token_client_secret=svc_secret,
        steps=steps,
    )


def show(*, ctx: Context) -> ShowResult:
    """Read every resource setup would create, returning presence/absence."""
    org = find_org(account_id=ctx.account_id)
    tunnel = find_tunnel(
        account_id=ctx.account_id, name=ctx.names.tunnel_name,
    )
    dns = find_cname(zone_id=ctx.zone_id, hostname=ctx.hostname)
    app = find_app(account_id=ctx.account_id, hostname=ctx.hostname)
    policy = (
        find_policy(
            account_id=ctx.account_id,
            app_id=app["id"],
            name=ctx.names.policy_name,
        )
        if app is not None
        else None
    )
    svc = find_service_token(
        account_id=ctx.account_id, name=ctx.names.service_token_name,
    )
    return ShowResult(
        team_domain=(org or {}).get("auth_domain"),
        tunnel=tunnel,
        dns=dns,
        access_app=app,
        policy=policy,
        service_token=svc,
    )


def teardown(*, ctx: Context, keep_tunnel: bool) -> TeardownResult:
    """Delete in reverse-dependency order. ZT org is never touched."""
    steps: list[StepRecord] = []

    # 1. Service token.
    svc = find_service_token(
        account_id=ctx.account_id, name=ctx.names.service_token_name,
    )
    if svc is not None:
        delete_service_token(account_id=ctx.account_id, token_id=svc["id"])
        steps.append(StepRecord(
            name="service-token", action="deleted", detail=f"id={svc['id']}",
        ))

    # 2. Allow-policy + 3. Access app.
    app = find_app(account_id=ctx.account_id, hostname=ctx.hostname)
    if app is not None:
        policy = find_policy(
            account_id=ctx.account_id, app_id=app["id"],
            name=ctx.names.policy_name,
        )
        if policy is not None:
            delete_policy(
                account_id=ctx.account_id, app_id=app["id"],
                policy_id=policy["id"],
            )
            steps.append(StepRecord(
                name="allow-policy", action="deleted",
                detail=f"id={policy['id']}",
            ))
        delete_app(account_id=ctx.account_id, app_id=app["id"])
        steps.append(StepRecord(
            name="access-app", action="deleted", detail=f"id={app['id']}",
        ))

    # 4. DNS.
    dns = find_cname(zone_id=ctx.zone_id, hostname=ctx.hostname)
    if dns is not None:
        delete_cname(zone_id=ctx.zone_id, record_id=dns["id"])
        steps.append(StepRecord(
            name="dns", action="deleted", detail=f"id={dns['id']}",
        ))

    # 5. Tunnel.
    if not keep_tunnel:
        tun = find_tunnel(
            account_id=ctx.account_id, name=ctx.names.tunnel_name,
        )
        if tun is not None:
            delete_tunnel(account_id=ctx.account_id, tunnel_id=tun["id"])
            steps.append(StepRecord(
                name="tunnel", action="deleted", detail=f"id={tun['id']}",
            ))

    return TeardownResult(steps=steps)
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest tests/test_remote_login_orchestrator.py -v`
Expected: 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add cfafi/_remote_login/__init__.py cfafi/_remote_login/_common.py tests/test_remote_login_orchestrator.py
git commit -m "feat(remote-login): orchestrator (setup/show/teardown)"
```

---

## Task 11: Renderer — markdown + JSON envelope

**Files:**
- Create: `cfafi/_remote_login/_render.py`
- Create: `tests/test_remote_login_render.py`

The renderer takes a result dataclass and returns either a markdown string or a JSON-serialisable envelope. Section keys (`**CF_TEAM_DOMAIN:**` etc.) are stable, per spec.

- [ ] **Step 1: Write failing tests**

Create `tests/test_remote_login_render.py`:

```python
"""Tests for cfafi._remote_login._render."""

from cfafi._remote_login._common import (
    SetupResult, ShowResult, StepRecord, TeardownResult,
)
from cfafi._remote_login._render import (
    render_setup_markdown, render_setup_json,
    render_show_markdown, render_show_json,
    render_teardown_markdown, render_teardown_json,
    render_setup_dryrun_markdown,
)


def _setup_fixture(with_st: bool = True) -> SetupResult:
    return SetupResult(
        team_domain="ac.cloudflareaccess.com",
        tunnel_id="tun-1", tunnel_name="irc-culture-dev",
        tunnel_token="TUN-TOK",
        dns_record_id="rec-1",
        dns_target="tun-1.cfargotunnel.com",
        access_app_id="app-1",
        policy_id="pol-1",
        policy_emails=["me@example.com"],
        policy_domains=["@example.com"],
        service_token_client_id="CID" if with_st else None,
        service_token_client_secret="SEC" if with_st else None,
        steps=[
            StepRecord("zero-trust-org", "ensured", "existing"),
            StepRecord("tunnel", "ensured", "irc-culture-dev"),
            StepRecord("dns", "ensured", "CNAME"),
            StepRecord("access-app", "ensured", "id=app-1"),
            StepRecord("allow-policy", "ensured", "id=pol-1"),
            *([StepRecord("service-token", "ensured", "CID")] if with_st else []),
        ],
    )


def test_render_setup_markdown_includes_all_section_keys():
    md = render_setup_markdown(_setup_fixture(), hostname="irc.culture.dev")
    for key in (
        "**CF_TEAM_DOMAIN:**", "**TUNNEL_NAME:**", "**TUNNEL_ID:**",
        "**TUNNEL_TOKEN:**", "**DNS:**", "**ACCESS_APP_ID:**",
        "**POLICY:**",
        "**SERVICE_TOKEN_CLIENT_ID:**", "**SERVICE_TOKEN_CLIENT_SECRET:**",
    ):
        assert key in md, f"missing section {key}"
    assert "TUN-TOK" in md
    assert "SEC" in md
    assert "## Steps" in md
    assert "Remote login set up" in md


def test_render_setup_markdown_omits_service_token_when_absent():
    md = render_setup_markdown(_setup_fixture(with_st=False), hostname="irc.culture.dev")
    assert "**SERVICE_TOKEN_CLIENT_ID:**" not in md
    assert "**SERVICE_TOKEN_CLIENT_SECRET:**" not in md


def test_render_setup_json_envelope_shape():
    env = render_setup_json(_setup_fixture(), hostname="irc.culture.dev")
    assert env["success"] is True
    assert env["errors"] == []
    r = env["result"]
    assert r["team_domain"] == "ac.cloudflareaccess.com"
    assert r["tunnel_token"] == "TUN-TOK"
    assert r["service_token_client_secret"] == "SEC"
    assert r["dns"]["target"] == "tun-1.cfargotunnel.com"


def test_render_setup_dryrun_markdown_shows_plan_and_no_secrets():
    md = render_setup_dryrun_markdown(
        hostname="irc.culture.dev",
        tunnel_name="irc-culture-dev",
        app_name="irc.culture.dev",
        emails=["me@example.com"],
        domains=[],
        with_service_token=True,
        session_duration="24h",
    )
    assert "Dry-run" in md
    assert "## Plan" in md
    assert "TUN-TOK" not in md
    assert "tunnel" in md.lower()
    assert "dns" in md.lower()


def test_render_show_markdown_marks_missing_resources():
    show = ShowResult(
        team_domain="ac.cloudflareaccess.com",
        tunnel={"id": "tun-1", "name": "irc-culture-dev"},
        dns=None,
        access_app=None,
        policy=None,
        service_token=None,
    )
    md = render_show_markdown(show, hostname="irc.culture.dev")
    assert "Remote login state" in md
    assert "tun-1" in md
    assert "(not found)" in md  # dns / app / policy / svc all missing


def test_render_teardown_markdown_lists_deleted_steps():
    td = TeardownResult(steps=[
        StepRecord("service-token", "deleted", "id=st-1"),
        StepRecord("allow-policy", "deleted", "id=pol-1"),
        StepRecord("access-app", "deleted", "id=app-1"),
        StepRecord("dns", "deleted", "id=rec-1"),
        StepRecord("tunnel", "deleted", "id=tun-1"),
    ])
    md = render_teardown_markdown(td, hostname="irc.culture.dev")
    assert "Remote login torn down" in md
    for s in ("service-token", "allow-policy", "access-app", "dns", "tunnel"):
        assert s in md


def test_render_show_json_envelope_shape():
    show = ShowResult(
        team_domain="ac.cloudflareaccess.com",
        tunnel={"id": "tun-1", "name": "irc-culture-dev"},
        dns=None,
        access_app=None,
        policy=None,
        service_token=None,
    )
    env = render_show_json(show, hostname="irc.culture.dev")
    assert env["success"] is True
    r = env["result"]
    assert r["team_domain"] == "ac.cloudflareaccess.com"
    assert r["tunnel"]["id"] == "tun-1"
    assert r["dns"] is None


def test_render_teardown_json_envelope_shape():
    td = TeardownResult(steps=[
        StepRecord("dns", "deleted", "id=rec-1"),
    ])
    env = render_teardown_json(td, hostname="irc.culture.dev")
    assert env["success"] is True
    assert env["result"]["steps"][0]["name"] == "dns"
    assert env["result"]["steps"][0]["action"] == "deleted"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_remote_login_render.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `_render.py`**

```python
"""Markdown + JSON renderers for the remote-login result dataclasses."""

from __future__ import annotations

from cfafi._remote_login._common import (
    SetupResult, ShowResult, TeardownResult,
)


def render_setup_markdown(result: SetupResult, *, hostname: str) -> str:
    lines: list[str] = []
    lines.append(f"## Remote login set up — {hostname}")
    lines.append("")
    lines.append(f"- **CF_TEAM_DOMAIN:** {result.team_domain or '(not set)'}")
    lines.append(f"- **TUNNEL_NAME:** {result.tunnel_name}")
    lines.append(f"- **TUNNEL_ID:** {result.tunnel_id}")
    lines.append(f"- **TUNNEL_TOKEN:** {result.tunnel_token}")
    lines.append(
        f"- **DNS:** CNAME {hostname} → {result.dns_target} (proxied)"
    )
    lines.append(f"- **ACCESS_APP_ID:** {result.access_app_id}")
    policy_bits = []
    if result.policy_emails:
        policy_bits.append(f"allow [{', '.join(result.policy_emails)}]")
    if result.policy_domains:
        policy_bits.append(f"allow-domain [{', '.join(result.policy_domains)}]")
    lines.append(f"- **POLICY:** {'; '.join(policy_bits)}")
    if result.service_token_client_id is not None:
        lines.append(
            f"- **SERVICE_TOKEN_CLIENT_ID:** {result.service_token_client_id}"
        )
    if result.service_token_client_secret is not None:
        lines.append(
            f"- **SERVICE_TOKEN_CLIENT_SECRET:** "
            f"{result.service_token_client_secret}"
        )
    lines.append("")
    lines.append("## Steps")
    for i, step in enumerate(result.steps, start=1):
        lines.append(f"{i}. ✓ {step.action} {step.name} ({step.detail})")
    return "\n".join(lines) + "\n"


def render_setup_json(result: SetupResult, *, hostname: str) -> dict:
    return {
        "success": True, "errors": [], "messages": [],
        "result": {
            "hostname": hostname,
            "team_domain": result.team_domain,
            "tunnel_name": result.tunnel_name,
            "tunnel_id": result.tunnel_id,
            "tunnel_token": result.tunnel_token,
            "dns": {
                "record_id": result.dns_record_id,
                "target": result.dns_target,
            },
            "access_app_id": result.access_app_id,
            "policy": {
                "id": result.policy_id,
                "emails": list(result.policy_emails),
                "domains": list(result.policy_domains),
            },
            "service_token_client_id": result.service_token_client_id,
            "service_token_client_secret": result.service_token_client_secret,
            "steps": [
                {"name": s.name, "action": s.action, "detail": s.detail}
                for s in result.steps
            ],
        },
    }


def render_setup_dryrun_markdown(
    *,
    hostname: str,
    tunnel_name: str,
    app_name: str,
    emails: list[str],
    domains: list[str],
    with_service_token: bool,
    session_duration: str,
) -> str:
    lines: list[str] = []
    lines.append("**Dry-run — no changes applied**")
    lines.append("")
    lines.append(f"## Plan for {hostname}")
    lines.append("1. ensure Zero Trust org (existing required for v1)")
    lines.append(f"2. ensure tunnel `{tunnel_name}`")
    lines.append(
        f"3. ensure DNS CNAME {hostname} → <tunnel_id>.cfargotunnel.com (proxied)"
    )
    lines.append(
        f"4. ensure Access app `{app_name}` (session_duration={session_duration})"
    )
    policy_parts: list[str] = []
    if emails:
        policy_parts.append(f"allow [{', '.join(emails)}]")
    if domains:
        policy_parts.append(f"allow-domain [{', '.join(domains)}]")
    lines.append(f"5. ensure allow-policy ({'; '.join(policy_parts)})")
    if with_service_token:
        lines.append("6. ensure service-token (one-shot secret)")
    lines.append("")
    lines.append("Pass --apply to commit.")
    return "\n".join(lines) + "\n"


def render_show_markdown(result: ShowResult, *, hostname: str) -> str:
    lines: list[str] = []
    lines.append(f"## Remote login state — {hostname}")
    lines.append("")
    lines.append(
        f"- **zero-trust-org:** {result.team_domain or '(not found)'}"
    )
    if result.tunnel is not None:
        lines.append(
            f"- **tunnel:** {result.tunnel.get('name')} "
            f"(id={result.tunnel.get('id')})"
        )
    else:
        lines.append("- **tunnel:** (not found)")
    if result.dns is not None:
        lines.append(
            f"- **dns:** CNAME {hostname} → {result.dns.get('content')} "
            f"({'proxied' if result.dns.get('proxied') else 'unproxied'}) ✓"
        )
    else:
        lines.append("- **dns:** (not found)")
    lines.append(
        f"- **access-app:** "
        f"{'id=' + result.access_app['id'] if result.access_app else '(not found)'}"
    )
    lines.append(
        f"- **policies:** "
        f"{'1 allow rule' if result.policy else '(not found)'}"
    )
    if result.service_token is not None:
        lines.append(
            f"- **service-token:** {result.service_token.get('name')} "
            f"(id={result.service_token.get('id')}, "
            f"secret not retrievable)"
        )
    else:
        lines.append("- **service-token:** (not found)")
    return "\n".join(lines) + "\n"


def render_show_json(result: ShowResult, *, hostname: str) -> dict:
    return {
        "success": True, "errors": [], "messages": [],
        "result": {
            "hostname": hostname,
            "team_domain": result.team_domain,
            "tunnel": result.tunnel,
            "dns": result.dns,
            "access_app": result.access_app,
            "policy": result.policy,
            "service_token": result.service_token,
        },
    }


def render_teardown_markdown(
    result: TeardownResult, *, hostname: str
) -> str:
    lines: list[str] = []
    lines.append(f"## Remote login torn down — {hostname}")
    lines.append("")
    if not result.steps:
        lines.append("Nothing to delete.")
        return "\n".join(lines) + "\n"
    for i, step in enumerate(result.steps, start=1):
        lines.append(f"{i}. ✓ {step.action} {step.name} ({step.detail})")
    return "\n".join(lines) + "\n"


def render_teardown_json(
    result: TeardownResult, *, hostname: str
) -> dict:
    return {
        "success": True, "errors": [], "messages": [],
        "result": {
            "hostname": hostname,
            "steps": [
                {"name": s.name, "action": s.action, "detail": s.detail}
                for s in result.steps
            ],
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_remote_login_render.py -v`
Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cfafi/_remote_login/_render.py tests/test_remote_login_render.py
git commit -m "feat(remote-login): markdown + JSON renderers"
```

---

## Task 12: CLI command file — argparse + glue

**Files:**
- Create: `cfafi/cli/_commands/remote_login.py`
- Create: `tests/test_cli_remote_login.py`

This is the only file that touches argparse and that calls `emit_result` / `emit_json`. It does:

1. Parse args.
2. Resolve account (`require_env("CLOUDFLARE_ACCOUNT_ID")`) + zone via `resolve_zone(hostname)`.
3. Run `check_token_scopes(operation=..., with_service_token=...)`.
4. For `setup` dry-run: render the dry-run markdown / synthetic JSON envelope and return.
5. For `setup --apply` / `show` / `teardown`: call the orchestrator, render the result.
6. Errors raised as `CfafiError` propagate to the existing `_dispatch` error handler.

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_remote_login.py`:

```python
"""End-to-end tests for `cfafi remote-login` via main([...])."""

import json

from cfafi.cli import main


def _zones_one(name="culture.dev", zid="zid-1"):
    return {
        "success": True, "errors": [], "messages": [],
        "result": [{"id": zid, "name": name}],
        "result_info": {"page": 1, "total_pages": 1},
    }


def _verify_full_scopes(with_st=False):
    pgs = [
        "Cloudflare Tunnel Write",
        "Access: Apps and Policies Write",
        "Access: Organizations Write",
        "DNS Write",
    ]
    if with_st:
        pgs.append("Access: Service Tokens Write")
    return {
        "success": True, "errors": [], "messages": [],
        "result": {
            "id": "tok-1", "status": "active",
            "policies": [{"permission_groups": [{"name": p} for p in pgs],
                          "resources": {}}],
        },
    }


def test_setup_dry_run_prints_plan_and_does_not_post(http_stub, capsys):
    http_stub.queue(_verify_full_scopes(), _zones_one())
    rc = main([
        "remote-login", "setup",
        "--hostname", "irc.culture.dev",
        "--allow", "me@example.com",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dry-run" in out
    assert "## Plan" in out
    assert "irc.culture.dev" in out
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert posts == []


def test_setup_requires_at_least_one_allow(http_stub, capsys):
    http_stub.queue(_verify_full_scopes(), _zones_one())
    rc = main([
        "remote-login", "setup",
        "--hostname", "irc.culture.dev",
    ])
    out = capsys.readouterr().out
    err = capsys.readouterr().err
    assert rc != 0


def test_setup_preflight_blocks_when_token_lacks_scope(http_stub, capsys):
    http_stub.queue({
        "success": True, "errors": [], "messages": [],
        "result": {"id": "tok-1", "status": "active",
                   "policies": [{"permission_groups": [{"name": "DNS Read"}],
                                 "resources": {}}]},
    })
    rc = main([
        "remote-login", "setup",
        "--hostname", "irc.culture.dev",
        "--allow", "me@example.com",
    ])
    err = capsys.readouterr().err
    assert rc != 0
    assert "missing required scopes" in err


def test_show_emits_json_when_flagged(http_stub, capsys):
    # verify (read scopes) → zones → ZT → tunnels → dns → apps → svc
    http_stub.queue({
        "success": True, "errors": [], "messages": [],
        "result": {"id": "tok-1", "status": "active",
                   "policies": [{"permission_groups": [
                       {"name": "Cloudflare Tunnel Read"},
                       {"name": "Access: Apps and Policies Read"},
                       {"name": "DNS Read"},
                   ], "resources": {}}]},
    })
    http_stub.queue(_zones_one())
    http_stub.set("GET", "/accounts/test-account/access/organizations", {
        "success": True, "errors": [], "messages": [],
        "result": {"name": "AC", "auth_domain": "ac.cloudflareaccess.com"},
    })
    http_stub.queue(
        {"success": True, "errors": [], "messages": [], "result": [],
         "result_info": {"page": 1, "total_pages": 1}},  # tunnels
        {"success": True, "errors": [], "messages": [], "result": [],
         "result_info": {"page": 1, "total_pages": 1}},  # dns
        {"success": True, "errors": [], "messages": [], "result": [],
         "result_info": {"page": 1, "total_pages": 1}},  # apps
        {"success": True, "errors": [], "messages": [], "result": [],
         "result_info": {"page": 1, "total_pages": 1}},  # svc
    )
    rc = main([
        "remote-login", "show",
        "--hostname", "irc.culture.dev", "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["success"] is True
    assert payload["result"]["team_domain"] == "ac.cloudflareaccess.com"
    assert payload["result"]["tunnel"] is None


def test_teardown_dry_run_does_not_delete(http_stub, capsys):
    http_stub.queue(_verify_full_scopes(), _zones_one())
    rc = main([
        "remote-login", "teardown",
        "--hostname", "irc.culture.dev",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dry-run" in out
    deletes = [c for c in http_stub.calls if c[0] == "DELETE"]
    assert deletes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_remote_login.py -v`
Expected: command not found / argparse rejects `remote-login`.

- [ ] **Step 3: Implement `cfafi/cli/_commands/remote_login.py`**

```python
"""``cfafi remote-login`` — setup / show / teardown a hostname behind Access."""

from __future__ import annotations

import argparse

from cfafi._env import require_env
from cfafi._remote_login import setup, show, teardown
from cfafi._remote_login._common import Context, derive_names, resolve_zone
from cfafi._remote_login._preflight import check_token_scopes
from cfafi._remote_login._render import (
    render_setup_dryrun_markdown, render_setup_json, render_setup_markdown,
    render_show_json, render_show_markdown,
    render_teardown_json, render_teardown_markdown,
)
from cfafi.cli._errors import EXIT_USER_ERROR, CfafiError
from cfafi.cli._output import emit_json, emit_result


def _build_context(hostname: str) -> Context:
    account_id = require_env("CLOUDFLARE_ACCOUNT_ID")
    zone_id, _zone_name = resolve_zone(hostname)
    return Context(
        account_id=account_id,
        zone_id=zone_id,
        hostname=hostname,
        names=derive_names(hostname=hostname),  # overrides applied by caller
    )


def _ctx_with_overrides(args: argparse.Namespace) -> Context:
    base = _build_context(args.hostname)
    names = derive_names(
        hostname=args.hostname,
        tunnel_name=getattr(args, "tunnel_name", None),
        app_name=getattr(args, "app_name", None),
        service_token_name=getattr(args, "service_token_name", None),
    )
    return Context(
        account_id=base.account_id, zone_id=base.zone_id,
        hostname=base.hostname, names=names,
    )


def cmd_setup(args: argparse.Namespace) -> None:
    if not args.allow and not args.allow_domain:
        raise CfafiError(
            code=EXIT_USER_ERROR,
            message="at least one of --allow / --allow-domain is required",
            remediation="pass --allow user@example.com or --allow-domain @example.com",
        )
    json_mode = bool(args.json)
    check_token_scopes(operation="setup", with_service_token=args.with_service_token)
    ctx = _ctx_with_overrides(args)

    if not args.apply:
        if json_mode:
            emit_json({
                "success": True, "errors": [], "messages": ["dry-run: no changes applied"],
                "result": {
                    "dry_run": True,
                    "hostname": args.hostname,
                    "tunnel_name": ctx.names.tunnel_name,
                    "app_name": ctx.names.app_name,
                    "with_service_token": args.with_service_token,
                    "session_duration": args.session_duration,
                    "emails": list(args.allow),
                    "domains": list(args.allow_domain),
                },
            })
        else:
            emit_result(
                render_setup_dryrun_markdown(
                    hostname=args.hostname,
                    tunnel_name=ctx.names.tunnel_name,
                    app_name=ctx.names.app_name,
                    emails=list(args.allow),
                    domains=list(args.allow_domain),
                    with_service_token=args.with_service_token,
                    session_duration=args.session_duration,
                ),
                json_mode=False,
            )
        return

    result = setup(
        ctx=ctx,
        emails=list(args.allow),
        domains=list(args.allow_domain),
        with_service_token=args.with_service_token,
        session_duration=args.session_duration,
    )
    if json_mode:
        emit_json(render_setup_json(result, hostname=args.hostname))
    else:
        emit_result(
            render_setup_markdown(result, hostname=args.hostname),
            json_mode=False,
        )


def cmd_show(args: argparse.Namespace) -> None:
    json_mode = bool(args.json)
    check_token_scopes(operation="show", with_service_token=False)
    ctx = _ctx_with_overrides(args)
    result = show(ctx=ctx)
    if json_mode:
        emit_json(render_show_json(result, hostname=args.hostname))
    else:
        emit_result(
            render_show_markdown(result, hostname=args.hostname),
            json_mode=False,
        )


def cmd_teardown(args: argparse.Namespace) -> None:
    json_mode = bool(args.json)
    check_token_scopes(operation="teardown", with_service_token=False)
    ctx = _ctx_with_overrides(args)

    if not args.apply:
        msg = (
            f"**Dry-run — no changes applied**\n\n"
            f"`teardown --hostname {args.hostname}` would delete (in order): "
            f"service-token, allow-policy, access-app, dns, "
            f"{'tunnel' if not args.keep_tunnel else '(tunnel kept)'}.\n"
        )
        if json_mode:
            emit_json({
                "success": True, "errors": [],
                "messages": ["dry-run: no changes applied"],
                "result": {
                    "dry_run": True, "hostname": args.hostname,
                    "keep_tunnel": args.keep_tunnel,
                },
            })
        else:
            emit_result(msg, json_mode=False)
        return

    result = teardown(ctx=ctx, keep_tunnel=args.keep_tunnel)
    if json_mode:
        emit_json(render_teardown_json(result, hostname=args.hostname))
    else:
        emit_result(
            render_teardown_markdown(result, hostname=args.hostname),
            json_mode=False,
        )


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "remote-login",
        help="Set up / show / tear down a hostname behind Cloudflare Access.",
    )
    verbs = p.add_subparsers(dest="verb", required=True)

    s = verbs.add_parser("setup", help="Create or ensure the full set.")
    s.add_argument("--hostname", required=True, help="e.g. irc.culture.dev")
    s.add_argument(
        "--allow", action="append", default=[],
        help="Email to allow (repeatable).",
    )
    s.add_argument(
        "--allow-domain", action="append", default=[],
        help="Email-domain to allow, e.g. @example.com (repeatable).",
    )
    s.add_argument("--tunnel-name", default=None,
                   help="Override the derived tunnel name.")
    s.add_argument("--app-name", default=None,
                   help="Override the derived Access app name.")
    s.add_argument("--service-token-name", default=None,
                   help="Override the derived service-token name.")
    s.add_argument("--with-service-token", action="store_true",
                   help="Also create a service token (one-shot secret).")
    s.add_argument("--session-duration", default="24h",
                   help="Access session duration (default 24h).")
    s.add_argument("--apply", action="store_true",
                   help="Actually mutate (default: dry-run).")
    s.add_argument("--json", action="store_true",
                   help="Emit JSON envelope on stdout.")
    s.set_defaults(func=cmd_setup)

    sh = verbs.add_parser("show", help="Inspect the current state for a hostname.")
    sh.add_argument("--hostname", required=True)
    sh.add_argument("--tunnel-name", default=None)
    sh.add_argument("--app-name", default=None)
    sh.add_argument("--service-token-name", default=None)
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_show)

    t = verbs.add_parser("teardown", help="Delete in reverse-dependency order.")
    t.add_argument("--hostname", required=True)
    t.add_argument("--tunnel-name", default=None)
    t.add_argument("--app-name", default=None)
    t.add_argument("--service-token-name", default=None)
    t.add_argument("--keep-tunnel", action="store_true",
                   help="Keep the tunnel; delete only DNS/Access resources.")
    t.add_argument("--apply", action="store_true",
                   help="Actually mutate (default: dry-run).")
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=cmd_teardown)
```

- [ ] **Step 4: Wire the command into the CLI dispatcher**

Edit `cfafi/cli/__init__.py` — inside `_build_parser`, after the `_dns` import and registration:

```python
    # Deferred imports keep cli import-side effects tight.
    from cfafi.cli._commands import dns as _dns
    from cfafi.cli._commands import explain as _explain
    from cfafi.cli._commands import learn as _learn
    from cfafi.cli._commands import remote_login as _remote_login
    from cfafi.cli._commands import whoami as _whoami
    from cfafi.cli._commands import zones as _zones
```

And after `_dns.register(sub)`:

```python
    _dns.register(sub)
    _remote_login.register(sub)
```

- [ ] **Step 5: Run all CLI tests**

Run: `uv run pytest tests/test_cli_remote_login.py tests/test_cli_entry.py -v`
Expected: all pass.

- [ ] **Step 6: Run the entire test suite to verify no regressions**

Run: `uv run pytest -v`
Expected: every test in `tests/` passes.

- [ ] **Step 7: Commit**

```bash
git add cfafi/cli/_commands/remote_login.py cfafi/cli/__init__.py tests/test_cli_remote_login.py
git commit -m "feat(remote-login): CLI command wiring"
```

---

## Task 13: Documentation — operator token scopes

**Files:**
- Modify: `docs/SETUP.md`

Add a section listing the five permission groups required for `remote-login setup`, plus a dashboard link.

- [ ] **Step 1: Read the current `docs/SETUP.md`**

Run: `cat docs/SETUP.md`
Note where the existing token-scope section ends so the new section follows it cleanly.

- [ ] **Step 2: Append the operator-token section**

Append to `docs/SETUP.md`:

```markdown
## Operator token scopes (for `cfafi remote-login`)

The read-only token described above is enough for `cfafi zones list`,
`cfafi dns list`, `cfafi whoami`, and `cfafi remote-login show`. To run
`cfafi remote-login setup` or `cfafi remote-login teardown`, mint a
**second** token with broader scopes — keep the read-only token for
day-to-day inventory.

Mint at <https://dash.cloudflare.com/profile/api-tokens> → **Create
Token** → **Custom token**. Required permission groups:

| Permission | Resource | Note |
|---|---|---|
| Account → Cloudflare Tunnel | Edit | Tunnel create/delete/get-token |
| Account → Access: Apps and Policies | Edit | Access app + allow-policy |
| Account → Access: Service Tokens | Edit | Only when using `--with-service-token` |
| Account → Access: Organizations | Edit | Validates Zero Trust org; can be downgraded to Read once ZT is enabled |
| Zone → DNS | Edit | On the zone(s) hosting your hostnames |

`cfafi remote-login` runs a pre-flight `GET /user/tokens/verify` and
errors out with the missing scopes' exact names if your token is too
narrow — you'll see a clean message rather than a 403 mid-orchestration.

**Token minting is operator-driven.** cfafi never calls
`POST /user/tokens` itself; an issue or PR proposing it will be
declined.
```

- [ ] **Step 3: Lint the markdown**

Run: `markdownlint-cli2 docs/SETUP.md`
Expected: no issues. Fix any if reported.

- [ ] **Step 4: Commit**

```bash
git add docs/SETUP.md
git commit -m "docs: operator token scopes for remote-login"
```

---

## Task 14: Version bump + changelog

**Files:**
- Modify: `pyproject.toml`
- Modify: `cfafi/__init__.py` (if `__version__` lives there too)
- Modify: `CHANGELOG.md`

`feat:` adds a new public surface → minor bump per Keep-a-Changelog conventions. Per CLAUDE.md, every PR bumps the version; the version-bump skill ships a `bump.py` script.

- [ ] **Step 1: Run the version-bump script**

```bash
echo '{"added": ["`cfafi remote-login` action: setup, show, teardown a hostname behind Cloudflare Access via Tunnel."], "changed": [], "fixed": [], "removed": []}' | \
  python3 .claude/skills/version-bump/scripts/bump.py minor
```

Expected: pyproject.toml + CHANGELOG.md updated; the script prints the new version.

- [ ] **Step 2: Verify the version-check would pass**

Run: `git diff pyproject.toml CHANGELOG.md`
Expected: pyproject.toml shows `version = "0.2.0"` (assuming current is 0.1.x); CHANGELOG.md has a new `## [0.2.0]` section.

- [ ] **Step 3: Run the full test suite one more time**

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump version for remote-login feature"
```

---

## Task 15: Push branch + open PR + invoke poll skill

This is the final task before live smoke. The user runs the live smoke test from PR review (with their throwaway hostname), redacted hostname output goes into a PR comment.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/remote-login-action
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat: cfafi remote-login action (setup/show/teardown)" --body "$(cat <<'EOF'
## Summary
- Add `cfafi remote-login` action with verbs `setup`, `show`, `teardown`.
  Owns the full Cloudflare-side sequence to put a hostname behind
  Cloudflare Access via a Tunnel: ZT org check, tunnel, DNS CNAME,
  Access app, allow-policy, optional service token.
- Idempotent (find-by-name, no-op if present), dry-run by default,
  `--apply` commits, `--json` for raw envelopes.
- Pre-flight `GET /user/tokens/verify` validates scopes before any
  orchestration so the operator sees a clean "missing scope X" instead
  of a mid-run 403.
- Closes #22 (CloudFlare-side prerequisites for an irc-lens-style
  deployment) on the action side. API-token minting stays
  operator-driven (out of scope per design).

Spec: `docs/superpowers/specs/2026-05-07-cfafi-remote-login-design.md`

## Test plan
- [ ] CI green (unit tests + markdownlint + version-check)
- [ ] Live smoke: `setup --apply` on a throwaway hostname
- [ ] Live smoke: `show` confirms all six resources present
- [ ] Live smoke: `teardown --apply` reverses cleanly
- [ ] Live smoke: `show` after teardown reports all (not found)

\u{1F916} Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Invoke the poll skill**

Per CLAUDE.md, immediately after `gh pr create`, hand off to the `poll` skill so the main session doesn't burn cycles waiting for qodo + Copilot. Pass the PR number returned by `gh pr create` (or the URL).

```
/poll <PR_NUMBER>
```

The poll subagent wakes the main session only when both reviewers have finished or the PR closes/merges.

---

## Self-Review

After plan completion, verify:

1. **Spec coverage:** Every section of `2026-05-07-cfafi-remote-login-design.md` maps to at least one task — Architecture (tasks 1, 2, 4–11), Command surface (task 12), State & idempotency (tasks 4–9), Output (task 11), Auth scopes (tasks 3, 13), Testing (every helper + orchestrator + CLI task includes its tests).

2. **Placeholder scan:** No "TBD", no "implement later", no "similar to Task N" without code, no incomplete steps.

3. **Type consistency:** `Context`, `Names`, `SetupResult`, `ShowResult`, `TeardownResult`, `StepRecord` defined in Task 2/10's `_common.py` and used identically in Tasks 4–12. `ensure_*` returns `(id, created)` everywhere except `ensure_service_token` which returns `(client_id, secret_or_None, created)`. `find_*` returns `dict | None`. `delete_*` returns `None`.

4. **Spec gap:** the spec mentions `--auth-domain` for first-time ZT onboarding obliquely; v1 actually refuses to onboard ZT and asks the operator to do it in the dashboard (see Task 10's `setup` step 1). This is a deliberate v1 narrowing — captured in the orchestrator's error message and consistent with the spec's "deliberately not reconciling state" stance, but worth flagging to the user post-implementation if they want a follow-up `cfafi remote-login init-zt --auth-domain X` verb.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-07-cfafi-remote-login.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
