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
