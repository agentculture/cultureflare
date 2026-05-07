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
