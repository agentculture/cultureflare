"""HTTP + pagination helpers for the CloudFlare v4 API.

Ports `cf_api` and `cf_api_paginated` from
.claude/skills/cloudflare/scripts/_lib.sh. Stdlib only (urllib + json).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator, NoReturn

from cultureflare import __version__
from cultureflare._env import require_env
from cultureflare.cli._errors import EXIT_API, EXIT_AUTH, CfafiError

CF_API_BASE = "https://api.cloudflare.com/client/v4"
_DEFAULT_PER_PAGE = 50


def _encode_multipart(fields: dict[str, Any], boundary: str) -> bytes:
    """Encode ``fields`` as a ``multipart/form-data`` body.

    Hand-rolled (stdlib has no request-side multipart encoder) and kept
    minimal: simple text fields only, which is all CloudFlare's
    create-deployment endpoint needs (an optional ``branch``). Values are
    stringified; keys are assumed safe (caller-validated branch names).
    """
    lines: list[str] = []
    for key, value in fields.items():
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="{key}"')
        lines.append("")
        lines.append(str(value))
    lines.append(f"--{boundary}--")
    lines.append("")
    return "\r\n".join(lines).encode("utf-8")


def http_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    form: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform one CloudFlare API request, returning the parsed JSON envelope.

    Raises CfafiError on HTTP 4xx/5xx. 401/403 → EXIT_AUTH, everything
    else → EXIT_API. The CloudFlare error envelope (``.errors[0]``) is
    preserved in ``CfafiError.message`` when present.

    ``payload`` sends a JSON body; ``form`` sends a ``multipart/form-data``
    body (CF Pages' create-deployment endpoint requires multipart, not
    JSON). They are mutually exclusive.
    """
    if payload is not None and form is not None:
        raise ValueError("http_request: pass payload or form, not both")
    token = require_env("CLOUDFLARE_API_TOKEN")
    url = CF_API_BASE + path
    if query:
        url = f"{url}?{urllib.parse.urlencode({k: str(v) for k, v in query.items()})}"

    body: bytes | None = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": f"cultureflare/{__version__} (github.com/agentculture/cultureflare)",
    }
    if form is not None:
        boundary = "----cultureflareFormBoundaryZ9x7Z9x7Z9x7"
        body = _encode_multipart(form, boundary)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310,E501  # nosec B310 - bounded to CF_API_BASE
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        _raise_http_error(exc)
    except urllib.error.URLError as exc:
        raise CfafiError(
            code=EXIT_API,
            message=f"CloudFlare API transport failure: {exc.reason}",
            remediation="check network connectivity and api.cloudflare.com reachability",
        ) from None


def _raise_http_error(exc: urllib.error.HTTPError) -> NoReturn:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"errors": [{"code": exc.code, "message": raw or exc.reason}]}
    errors = data.get("errors") or [{"code": exc.code, "message": exc.reason}]
    first = errors[0]
    code_category = EXIT_AUTH if exc.code in (401, 403) else EXIT_API
    cf_code_raw = first.get("code", exc.code)
    cf_error_code = cf_code_raw if isinstance(cf_code_raw, int) else None
    raise CfafiError(
        code=code_category,
        message=f"CloudFlare API {cf_code_raw}: {first.get('message', exc.reason)}",
        remediation=(
            "check token scopes against docs/SETUP.md"
            if code_category == EXIT_AUTH
            else f"HTTP {exc.code} from CloudFlare; inspect the request body and retry"
        ),
        cf_error_code=cf_error_code,
    ) from None


def paginate(
    path: str,
    *,
    query: dict[str, Any] | None = None,
    per_page: int = _DEFAULT_PER_PAGE,
) -> Iterator[dict[str, Any]]:
    """Yield every row from a paginated CloudFlare list endpoint.

    Merges ``page`` and ``per_page`` into the caller's ``query`` (without
    mutating it), walking until ``result_info.total_pages`` is reached.
    """
    page = 1
    base_query = dict(query or {})
    base_query.setdefault("per_page", per_page)
    while True:
        q = dict(base_query)
        q["page"] = page
        data = http_request("GET", path, query=q)
        for row in data.get("result") or []:
            yield row
        info = data.get("result_info") or {}
        total_pages = int(info.get("total_pages") or 1)
        if page >= total_pages:
            return
        page += 1
