"""Tests for `cultureflare pages deployments create`."""

import json

from cultureflare.cli import main
from cultureflare.cli._errors import EXIT_API, EXIT_USER_ERROR, CfafiError

_GET_PATH = "/accounts/test-account/pages/projects/tools-culture-dev"
_POST_PATH = "/accounts/test-account/pages/projects/tools-culture-dev/deployments"


def _project_detail(*, source_type="github", production_branch="main"):
    source = {"type": source_type} if source_type else None
    return {
        "success": True, "errors": [], "messages": [],
        "result": {
            "name": "tools-culture-dev",
            "production_branch": production_branch,
            "source": source,
        },
    }


def _deployment_ok():
    return {
        "success": True, "errors": [], "messages": [],
        "result": {
            "id": "dep-123", "short_id": "dep-123"[:8],
            "environment": "production",
            "url": "https://dep-123.tools-culture-dev.pages.dev",
            "latest_stage": {"name": "queued", "status": "idle"},
        },
    }


def test_dry_run_defaults_to_production_branch_no_post(http_stub, capsys):
    http_stub.queue(_project_detail())
    rc = main(["pages", "deployments", "create", "tools-culture-dev"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dry-run" in out
    assert "would POST" in out and _POST_PATH in out
    assert "branch=main" in out
    assert "**environment:** production" in out
    methods = [c[0] for c in http_stub.calls]
    assert "POST" not in methods


def test_dry_run_branch_override_is_preview(http_stub, capsys):
    http_stub.queue(_project_detail())
    rc = main(["pages", "deployments", "create", "tools-culture-dev", "--branch", "feat/x"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "branch=feat/x" in out
    assert "**environment:** preview" in out
    assert "POST" not in [c[0] for c in http_stub.calls]


def test_json_dry_run_synthetic_envelope(http_stub, capsys):
    http_stub.queue(_project_detail())
    rc = main(["pages", "deployments", "create", "tools-culture-dev", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["success"] is True
    assert payload["result"]["dry_run"] is True
    assert payload["result"]["branch"] == "main"
    assert payload["result"]["environment"] == "production"
    assert payload["result"]["would_post"] == _POST_PATH


def test_apply_posts_branch_form_field(http_stub, capsys):
    http_stub.queue(_project_detail())
    http_stub.set("POST", _POST_PATH, _deployment_ok())
    rc = main(["pages", "deployments", "create", "tools-culture-dev", "--apply"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Deployment triggered" in out
    assert "dep-123" in out
    assert "queued/idle" in out
    posts = [c for c in http_stub.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][1] == _POST_PATH
    assert posts[0][2] is None          # no JSON payload
    assert posts[0][4] == {"branch": "main"}  # multipart form field


def test_apply_json_passthrough(http_stub, capsys):
    http_stub.queue(_project_detail())
    http_stub.set("POST", _POST_PATH, _deployment_ok())
    rc = main(["pages", "deployments", "create", "tools-culture-dev", "--apply", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["result"]["id"] == "dep-123"


def test_direct_upload_project_refused(http_stub, capsys):
    http_stub.queue(_project_detail(source_type=None))
    rc = main(["pages", "deployments", "create", "tools-culture-dev", "--apply"])
    err = capsys.readouterr().err
    assert rc == EXIT_USER_ERROR
    assert "no git source" in err
    assert "POST" not in [c[0] for c in http_stub.calls]


def test_invalid_project_name_rejected(capsys):
    rc = main(["pages", "deployments", "create", "bad name!"])
    err = capsys.readouterr().err
    assert rc == EXIT_USER_ERROR
    assert "invalid project name" in err


def test_invalid_branch_rejected(capsys):
    rc = main(["pages", "deployments", "create", "tools-culture-dev", "--branch", "bad branch!"])
    err = capsys.readouterr().err
    assert rc == EXIT_USER_ERROR
    assert "invalid --branch" in err


def test_project_not_found_propagates_api_error(http_stub, capsys):
    http_stub.queue(CfafiError(code=EXIT_API, message="CloudFlare API 8000007: not found"))
    rc = main(["pages", "deployments", "create", "tools-culture-dev"])
    err = capsys.readouterr().err
    assert rc == EXIT_API
    assert "not found" in err
    assert "POST" not in [c[0] for c in http_stub.calls]
