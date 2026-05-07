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
