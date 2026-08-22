"""How prodshell decides who it is connecting to production as.

The command has two ways in: a developer signed in with gcloud, reading the
application's own database credentials, and a cloud agent holding federated
credentials that can only read. Choosing the wrong one fails a long way from the
cause, so the choice is worth pinning down.
"""

import json

import pytest
from django.core.management.base import CommandError

from n23.core.management.commands.prodshell import Command

SERVICE_ACCOUNT = "reader@example-project.iam.gserviceaccount.com"

EXTERNAL_ACCOUNT = {
    "type": "external_account",
    "audience": "//iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/providers/q",
    "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
    "token_url": "https://sts.googleapis.com/v1/token",
    "credential_source": {"executable": {"command": "/somewhere/mint.sh"}},
    "service_account_impersonation_url": (
        "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
        f"{SERVICE_ACCOUNT}:generateAccessToken"
    ),
}


def write_config(tmp_path, payload, name="creds.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_no_credentials_variable_is_not_federated(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert Command._credential_config() is None


def test_a_missing_file_is_not_federated(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "absent.json"))
    assert Command._credential_config() is None


def test_unreadable_json_is_not_federated(monkeypatch, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("not json at all", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(path))
    assert Command._credential_config() is None


def test_a_service_account_key_is_not_federated(monkeypatch, tmp_path):
    """The distinguishing mark is the type, not merely that a file is present."""
    path = write_config(tmp_path, {"type": "service_account", "project_id": "x"})
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", path)
    assert Command._credential_config() is None


def test_an_external_account_config_is_federated(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
    )
    assert Command._credential_config() == EXTERNAL_ACCOUNT


def test_auto_picks_federated_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
    )
    assert Command()._use_iam_auth("auto") is True


def test_auto_falls_back_to_gcloud_on_a_workstation(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert Command()._use_iam_auth("auto") is False


def test_explicit_choices_override_what_is_configured(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
    )
    assert Command()._use_iam_auth("gcloud") is False
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    assert Command()._use_iam_auth("iam") is True


def test_the_impersonated_account_is_read_from_the_config():
    assert Command._impersonated_service_account(EXTERNAL_ACCOUNT) == SERVICE_ACCOUNT


def test_a_config_that_impersonates_nobody_yields_nobody():
    assert Command._impersonated_service_account({"type": "external_account"}) is None


def test_the_database_role_drops_the_trailing_domain(monkeypatch, tmp_path):
    """Cloud SQL names a service account without its domain suffix."""
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
    )
    monkeypatch.setattr(
        "google.auth.default", lambda **kwargs: (_StubCredentials(), None)
    )

    config = Command()._iam_db_config(None)

    assert config["user"] == "reader@example-project.iam"
    assert config["name"] == "app"
    assert config["password"] == ""


def test_the_database_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
    )
    monkeypatch.setattr(
        "google.auth.default", lambda **kwargs: (_StubCredentials(), None)
    )
    assert Command()._iam_db_config("somewhere_else")["name"] == "somewhere_else"


def test_scopes_are_requested(monkeypatch, tmp_path):
    """Unscoped, the impersonation call is rejected as a malformed request."""
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
    )
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return _StubCredentials(), None

    monkeypatch.setattr("google.auth.default", capture)
    Command()._iam_db_config(None)

    assert seen["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]


def test_federated_mode_without_credentials_says_so(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(CommandError, match="No federated credentials"):
        Command()._iam_db_config(None)


def test_a_rejected_token_is_reported_where_it_happens(monkeypatch, tmp_path):
    """Rather than surfacing later as an unexplained connection failure."""
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
    )

    def refuse(**kwargs):
        raise RuntimeError("rejected by the attribute condition")

    monkeypatch.setattr("google.auth.default", refuse)

    with pytest.raises(CommandError, match="rejected by the attribute condition"):
        Command()._iam_db_config(None)


class _StubCredentials:
    def refresh(self, request):
        return None
