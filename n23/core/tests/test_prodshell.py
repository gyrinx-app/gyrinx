import io
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError, OutputWrapper

from n23.core.management.commands.prodshell import Command, ReadOnlyRouter


@pytest.fixture
def cmd():
    return Command()


class TestReadOnlyRouter:
    def test_db_for_read_returns_default(self):
        router = ReadOnlyRouter()
        assert router.db_for_read(None) == "default"

    def test_db_for_write_raises(self):
        router = ReadOnlyRouter()
        with pytest.raises(RuntimeError, match="Write operations are disabled"):
            router.db_for_write(None)

    def test_allow_relation_returns_true(self):
        router = ReadOnlyRouter()
        assert router.allow_relation(None, None) is True

    def test_allow_migrate_returns_false(self):
        router = ReadOnlyRouter()
        assert router.allow_migrate("default", "core") is False


class TestPreflightChecks:
    @patch("shutil.which", return_value=None)
    def test_check_gcloud_missing(self, mock_which, cmd):
        with pytest.raises(CommandError, match="gcloud CLI not found"):
            cmd._check_gcloud()

    @patch("shutil.which", return_value="/usr/bin/gcloud")
    def test_check_gcloud_found(self, mock_which, cmd):
        cmd._check_gcloud()

    @patch(
        "subprocess.run",
        return_value=MagicMock(returncode=1, stderr="not authenticated"),
    )
    def test_check_gcloud_auth_not_authenticated(self, mock_run, cmd):
        with pytest.raises(CommandError, match="Not authenticated"):
            cmd._check_gcloud_auth()

    @patch(
        "subprocess.run",
        return_value=MagicMock(returncode=0, stdout="token"),
    )
    def test_check_gcloud_auth_ok(self, mock_run, cmd):
        cmd._check_gcloud_auth()

    @patch("shutil.which", return_value=None)
    def test_check_cloud_sql_proxy_missing(self, mock_which, cmd):
        with pytest.raises(CommandError, match="cloud-sql-proxy not found"):
            cmd._check_cloud_sql_proxy()

    @patch("shutil.which", return_value="/usr/bin/cloud-sql-proxy")
    def test_check_cloud_sql_proxy_found(self, mock_which, cmd):
        cmd._check_cloud_sql_proxy()

    @patch(
        "subprocess.run",
        return_value=MagicMock(returncode=1, stderr="not set"),
    )
    def test_check_adc_not_authenticated(self, mock_run, cmd):
        with pytest.raises(CommandError, match="Application Default Credentials"):
            cmd._check_adc()

    @patch(
        "subprocess.run",
        return_value=MagicMock(returncode=0, stdout="token"),
    )
    def test_check_adc_ok(self, mock_run, cmd):
        cmd._check_adc()


class TestFetchDbCredentials:
    def _make_cloud_run_response(self, env_vars):
        """Build a mock Cloud Run service describe JSON response."""
        service = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "env": [
                                    {"name": k, "value": v} for k, v in env_vars.items()
                                ]
                            }
                        ]
                    }
                }
            }
        }
        return json.dumps(service)

    @patch("subprocess.run")
    def test_fetch_credentials_success(self, mock_run, cmd):
        env_vars = {
            "DB_CONFIG": json.dumps({"user": "prod_user", "password": "prod_pass"}),
            "DB_NAME": "prod_db",
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_cloud_run_response(env_vars),
        )
        result = cmd._fetch_db_credentials("test-project")
        assert result["name"] == "prod_db"
        assert result["user"] == "prod_user"
        assert result["password"] == "prod_pass"

    @patch("subprocess.run")
    def test_fetch_credentials_defaults_db_name(self, mock_run, cmd):
        env_vars = {
            "DB_CONFIG": json.dumps({"user": "u", "password": "p"}),
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_cloud_run_response(env_vars),
        )
        result = cmd._fetch_db_credentials("test-project")
        assert result["name"] == "gyrinx"

    @patch("subprocess.run")
    def test_fetch_credentials_gcloud_failure(self, mock_run, cmd):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="permission denied",
        )
        with pytest.raises(CommandError, match="Failed to fetch"):
            cmd._fetch_db_credentials("test-project")

    @patch("subprocess.run")
    def test_fetch_credentials_missing_user(self, mock_run, cmd):
        env_vars = {
            "DB_CONFIG": json.dumps({"password": "p"}),
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_cloud_run_response(env_vars),
        )
        with pytest.raises(CommandError, match="Could not extract"):
            cmd._fetch_db_credentials("test-project")

    @patch("subprocess.run")
    def test_fetch_credentials_missing_password(self, mock_run, cmd):
        env_vars = {
            "DB_CONFIG": json.dumps({"user": "u"}),
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_cloud_run_response(env_vars),
        )
        with pytest.raises(CommandError, match="Could not extract"):
            cmd._fetch_db_credentials("test-project")

    @patch("subprocess.run")
    def test_fetch_credentials_malformed_db_config(self, mock_run, cmd):
        env_vars = {
            "DB_CONFIG": "not-json",
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_cloud_run_response(env_vars),
        )
        with pytest.raises(CommandError, match="Failed to parse DB_CONFIG"):
            cmd._fetch_db_credentials("test-project")

    @patch("subprocess.run")
    def test_fetch_credentials_malformed_json(self, mock_run, cmd):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not-json",
        )
        with pytest.raises(
            CommandError, match="Failed to parse Cloud Run service config"
        ):
            cmd._fetch_db_credentials("test-project")

    @patch("subprocess.run")
    def test_fetch_credentials_no_containers(self, mock_run, cmd):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"spec": {"template": {"spec": {"containers": []}}}}),
        )
        with pytest.raises(CommandError, match="No containers found"):
            cmd._fetch_db_credentials("test-project")


class TestPortCheck:
    @patch("socket.socket")
    def test_port_not_open(self, mock_socket):
        mock_sock_instance = mock_socket.return_value.__enter__.return_value
        mock_sock_instance.connect_ex.return_value = 1
        assert Command._port_is_open(19999) is False


class TestProxyStartup:
    @patch("subprocess.Popen")
    def test_proxy_exits_unexpectedly(self, mock_popen, cmd):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # process exited
        mock_proc.stderr.read.return_value = b"bind error"
        mock_popen.return_value = mock_proc

        with pytest.raises(CommandError, match="exited unexpectedly"):
            cmd._start_proxy("test-project", 5433, use_iam=False)

    @patch(
        "n23.core.management.commands.prodshell.Command._port_is_open",
        return_value=True,
    )
    @patch("subprocess.Popen")
    def test_proxy_starts_successfully(self, mock_popen, mock_port_is_open, cmd):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        result = cmd._start_proxy("test-project", 5433, use_iam=False)
        assert result is mock_proc

    @patch("n23.core.management.commands.prodshell.time.monotonic")
    @patch(
        "n23.core.management.commands.prodshell.Command._port_is_open",
        return_value=False,
    )
    @patch("n23.core.management.commands.prodshell.time.sleep")
    @patch("subprocess.Popen")
    def test_proxy_startup_timeout(
        self, mock_popen, mock_sleep, mock_port_is_open, mock_monotonic, cmd
    ):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        # Simulate time exceeding PROXY_STARTUP_TIMEOUT
        mock_monotonic.side_effect = [0.0, 0.0, 20.0]

        with pytest.raises(CommandError, match="did not start within"):
            cmd._start_proxy("test-project", 5433, use_iam=False)

        mock_proc.terminate.assert_called_once()


SERVICE_ACCOUNT = "reader@example-project.iam.gserviceaccount.com"

EXTERNAL_ACCOUNT = {
    "type": "external_account",
    "audience": (
        "//iam.googleapis.com/projects/1/locations/global"
        "/workloadIdentityPools/p/providers/q"
    ),
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


class StubCredentials:
    """Stands in for credentials that refresh without reaching Google."""

    service_account_email = SERVICE_ACCOUNT

    def refresh(self, request):
        return None


class TestWhichAuthPath:
    """Which identity the command connects as, and how loudly it decides.

    The two paths hold different privileges, so choosing between them silently
    is the thing to avoid.
    """

    def test_no_credentials_anywhere_is_not_federated(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setattr(
            "n23.core.management.commands.prodshell.AGENT_CREDENTIAL_PATH",
            tmp_path / "absent.json",
        )
        assert Command._credential_config() is None

    def test_a_service_account_key_is_not_federated(self, monkeypatch, tmp_path):
        """The discriminator is the type, not merely that a file is present."""
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS",
            write_config(tmp_path, {"type": "service_account", "project_id": "x"}),
        )
        assert Command._credential_config() is None

    def test_an_external_account_config_is_federated(self, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
        )
        assert Command._credential_config() == EXTERNAL_ACCOUNT

    def test_a_named_but_unparseable_config_is_refused(self, monkeypatch, tmp_path):
        """Rather than quietly falling back to the fuller-privilege path.

        Naming a credential file and then failing to read it is a broken setup.
        Treating it as an absence would connect with the application's own
        account instead, without saying so.
        """
        path = tmp_path / "broken.json"
        path.write_text("not json at all", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(path))
        with pytest.raises(CommandError, match="could not be read"):
            Command._credential_config()

    def test_a_named_config_that_is_not_utf8_is_refused(self, monkeypatch, tmp_path):
        path = tmp_path / "binary.json"
        path.write_bytes(b"\xff\xfe\x00nonsense")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(path))
        with pytest.raises(CommandError, match="could not be read"):
            Command._credential_config()

    def test_a_named_config_that_is_absent_is_refused(self, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "absent.json")
        )
        with pytest.raises(CommandError, match="could not be read"):
            Command._credential_config()

    def test_a_named_config_that_is_not_an_object_is_refused(
        self, monkeypatch, tmp_path
    ):
        path = tmp_path / "list.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(path))
        with pytest.raises(CommandError, match="credential configuration"):
            Command._credential_config()

    def test_an_agent_is_recognised_without_the_variable(self, monkeypatch, tmp_path):
        """A shell that inherits no environment still finds the agent's config.

        Only a login or interactive shell picks the variable up, so a command
        run through `bash -c` would otherwise take the workstation path.
        """
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        path = tmp_path / "cursor-wif.json"
        path.write_text(json.dumps(EXTERNAL_ACCOUNT), encoding="utf-8")
        monkeypatch.setattr(
            "n23.core.management.commands.prodshell.AGENT_CREDENTIAL_PATH", path
        )
        assert Command._credential_config() == EXTERNAL_ACCOUNT

    def test_an_unreadable_file_at_the_agent_location_is_refused(
        self, monkeypatch, tmp_path
    ):
        """Absence is an absence; present-but-unreadable is a broken setup.

        A config that is there and cannot be read is the ownership mismatch this
        path exists to avoid. Swallowing it would take the workstation path and
        complain about a missing gcloud instead.
        """
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        path = tmp_path / "cursor-wif.json"
        path.write_text("rubbish", encoding="utf-8")
        monkeypatch.setattr(
            "n23.core.management.commands.prodshell.AGENT_CREDENTIAL_PATH", path
        )
        with pytest.raises(CommandError, match="could not be read"):
            Command._credential_config()

    def test_auto_picks_federated_when_configured(self, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
        )
        assert Command()._use_iam_auth("auto") is True

    def test_auto_falls_back_to_gcloud_on_a_workstation(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setattr(
            "n23.core.management.commands.prodshell.AGENT_CREDENTIAL_PATH",
            tmp_path / "absent.json",
        )
        assert Command()._use_iam_auth("auto") is False

    def test_asking_for_gcloud_reads_no_configuration_at_all(
        self, monkeypatch, tmp_path
    ):
        """A broken credential file must not stop someone choosing the other path."""
        path = tmp_path / "broken.json"
        path.write_text("not json", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(path))
        assert Command()._use_iam_auth("gcloud") is False

    def test_asking_for_federated_is_honoured(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        assert Command()._use_iam_auth("iam") is True


class TestFederatedDatabaseRole:
    def test_the_impersonated_account_is_read_from_the_config(self):
        assert (
            Command._impersonated_service_account(EXTERNAL_ACCOUNT) == SERVICE_ACCOUNT
        )

    def test_a_config_that_impersonates_nobody_yields_nobody(self):
        assert (
            Command._impersonated_service_account({"type": "external_account"}) is None
        )

    def test_a_percent_encoded_account_is_decoded(self):
        """An escaped @ would otherwise survive into the database role name."""
        config = {
            "service_account_impersonation_url": (
                "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
                "reader%40example-project.iam.gserviceaccount.com:generateAccessToken"
            )
        }
        assert Command._impersonated_service_account(config) == SERVICE_ACCOUNT

    def test_the_database_role_drops_the_trailing_domain(self, monkeypatch, tmp_path):
        """Cloud SQL names a service account without its domain suffix."""
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
        )
        monkeypatch.setattr(
            "google.auth.default", lambda **kwargs: (StubCredentials(), None)
        )

        config = Command()._iam_db_config(None)

        assert config["user"] == "reader@example-project.iam"
        assert config["name"] == "app"
        assert config["password"] == ""

    def test_the_database_can_be_overridden(self, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
        )
        monkeypatch.setattr(
            "google.auth.default", lambda **kwargs: (StubCredentials(), None)
        )
        assert Command()._iam_db_config("somewhere_else")["name"] == "somewhere_else"

    def test_the_role_comes_from_the_identity_actually_obtained(
        self, monkeypatch, tmp_path
    ):
        """Not from a second parse of the configuration file.

        Where the two disagree, the credentials are the authority on who this
        connection is.
        """
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
        )

        class Elsewhere(StubCredentials):
            service_account_email = "elsewhere@other.iam.gserviceaccount.com"

        monkeypatch.setattr("google.auth.default", lambda **kwargs: (Elsewhere(), None))
        assert Command()._iam_db_config(None)["user"] == "elsewhere@other.iam"

    def test_scopes_are_requested(self, monkeypatch, tmp_path):
        """Unscoped, the impersonation call is rejected as a malformed request."""
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
        )
        seen = {}

        def capture(**kwargs):
            seen.update(kwargs)
            return StubCredentials(), None

        monkeypatch.setattr("google.auth.default", capture)
        Command()._iam_db_config(None)

        assert seen["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]

    def test_federated_mode_without_credentials_says_so(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setattr(
            "n23.core.management.commands.prodshell.AGENT_CREDENTIAL_PATH",
            tmp_path / "absent.json",
        )
        with pytest.raises(CommandError, match="No federated credentials"):
            Command()._iam_db_config(None)

    def test_the_environment_is_completed_for_the_proxy(self, monkeypatch, tmp_path):
        """The proxy is a separate process and reads these from the environment.

        This is the branch that makes the case work where nothing was inherited
        — a command run through `bash -c` — so it has to set what it found.
        """
        path = tmp_path / "cursor-wif.json"
        path.write_text(json.dumps(EXTERNAL_ACCOUNT), encoding="utf-8")
        monkeypatch.setattr(
            "n23.core.management.commands.prodshell.AGENT_CREDENTIAL_PATH", path
        )
        # Recorded before deleting so that both are restored afterwards rather
        # than leaking into every later test on this worker.
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "recorded")
        monkeypatch.setenv("GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES", "recorded")
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS")
        monkeypatch.delenv("GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES")
        monkeypatch.setattr(
            "google.auth.default", lambda **kwargs: (StubCredentials(), None)
        )

        Command()._iam_db_config(None)

        assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(path)
        assert os.environ["GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES"] == "1"

    def test_an_inherited_environment_is_left_alone(self, monkeypatch, tmp_path):
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
        )
        monkeypatch.setenv("GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES", "0")
        monkeypatch.setattr(
            "google.auth.default", lambda **kwargs: (StubCredentials(), None)
        )

        Command()._iam_db_config(None)

        assert os.environ["GOOGLE_EXTERNAL_ACCOUNT_ALLOW_EXECUTABLES"] == "0"

    def test_a_refused_token_is_reported_where_it_happens(self, monkeypatch, tmp_path):
        """The exchange itself failing, rather than the lookup that precedes it.

        This is the likelier failure in practice: the credentials resolve, and
        Google then declines to issue for them.
        """
        monkeypatch.setenv(
            "GOOGLE_APPLICATION_CREDENTIALS", write_config(tmp_path, EXTERNAL_ACCOUNT)
        )

        class Refused(StubCredentials):
            def refresh(self, request):
                raise RuntimeError("rejected by the attribute condition")

        monkeypatch.setattr("google.auth.default", lambda **kwargs: (Refused(), None))

        with pytest.raises(CommandError, match="rejected by the attribute condition"):
            Command()._iam_db_config(None)


class TestProxyArguments:
    def test_federated_mode_asks_the_proxy_to_authenticate(self, cmd):
        with (
            patch("subprocess.Popen") as popen,
            patch.object(Command, "_port_is_open", return_value=True),
        ):
            popen.return_value = MagicMock(poll=MagicMock(return_value=None))
            cmd._start_proxy("test-project", 5433, use_iam=True)
        assert "--auto-iam-authn" in popen.call_args[0][0]

    def test_the_workstation_path_does_not(self, cmd):
        with (
            patch("subprocess.Popen") as popen,
            patch.object(Command, "_port_is_open", return_value=True),
        ):
            popen.return_value = MagicMock(poll=MagicMock(return_value=None))
            cmd._start_proxy("test-project", 5433, use_iam=False)
        assert "--auto-iam-authn" not in popen.call_args[0][0]

    def test_the_proxy_is_not_given_a_pipe_to_fill(self, cmd):
        """It outlives startup and keeps logging with nobody reading, so a pipe
        would eventually fill and stall every query.

        A real file is required rather than merely "not a pipe": inheriting the
        terminal would scatter proxy logs through the shell session.
        """
        with (
            patch("subprocess.Popen") as popen,
            patch.object(Command, "_port_is_open", return_value=True),
        ):
            popen.return_value = MagicMock(poll=MagicMock(return_value=None))
            cmd._start_proxy("test-project", 5433, use_iam=False)

        stderr = popen.call_args.kwargs["stderr"]
        assert stderr is not subprocess.PIPE
        assert stderr.fileno() >= 0


class TestGeneratedSettings:
    """What the shell subprocess is handed, and what is left behind afterwards.

    Each test is given its own path. Sharing the real one makes these race
    against each other under parallel test execution, which is how the suite is
    normally run.
    """

    @pytest.fixture
    def settings_path(self, monkeypatch, tmp_path):
        path = tmp_path / "_prodshell_settings.py"
        monkeypatch.setattr(Command, "_settings_path", staticmethod(lambda: path))
        return path

    def test_the_read_only_router_is_installed(self, cmd, settings_path):
        """The layer that does not depend on database privileges, so it has to
        be present even on the path that already lacks them."""
        seen = {}

        def capture(argv, env=None, **kwargs):
            seen["content"] = settings_path.read_text(encoding="utf-8")
            seen["mode"] = settings_path.stat().st_mode & 0o777
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=capture):
            cmd._launch_shell(
                {"name": "app", "user": "someone", "password": "hunter2"}, 5433
            )

        assert "ReadOnlyRouter" in seen["content"]
        assert "DATABASE_ROUTERS" in seen["content"]
        assert seen["mode"] == 0o600

    def test_the_settings_file_does_not_outlive_the_shell(self, cmd, settings_path):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            cmd._launch_shell({"name": "app", "user": "u", "password": "p"}, 5433)
        assert not settings_path.exists()

    def test_the_settings_file_is_removed_even_when_the_shell_fails(
        self, cmd, settings_path
    ):
        with patch("subprocess.run", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                cmd._launch_shell({"name": "app", "user": "u", "password": "p"}, 5433)
        assert not settings_path.exists()

    def test_a_file_left_behind_cannot_keep_a_looser_mode(self, cmd, settings_path):
        """Truncating an existing file leaves its permissions alone, and a
        production password is about to be written into it."""
        settings_path.write_text("left over", encoding="utf-8")
        settings_path.chmod(0o644)
        seen = {}

        def capture(argv, env=None, **kwargs):
            seen["mode"] = settings_path.stat().st_mode & 0o777
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=capture):
            cmd._launch_shell({"name": "app", "user": "u", "password": "p"}, 5433)

        assert seen["mode"] == 0o600

    def test_a_second_session_is_told_rather_than_overwritten(self, cmd, settings_path):
        """Overwriting would pull the settings out from under a shell that is
        about to import them."""
        settings_path.write_text("another session", encoding="utf-8")

        with patch.object(Path, "unlink"):  # the other session still holds it
            with pytest.raises(CommandError, match="another prodshell session"):
                cmd._launch_shell({"name": "app", "user": "u", "password": "p"}, 5433)


class TestBanner:
    """The banner is the only statement of what is and is not being prevented."""

    @staticmethod
    def banner_for(use_iam, db_config):
        buffer = io.StringIO()
        command = Command()
        command.stdout = OutputWrapper(buffer)
        command._print_banner(5433, use_iam, db_config)
        return buffer.getvalue()

    def test_the_workstation_path_does_not_claim_to_stop_raw_sql(self):
        """A router intercepts the ORM and nothing else, and that connection
        holds the application's own privileges."""
        printed = self.banner_for(False, {"name": "app", "user": "app-user"})
        assert "raw SQL is not" in printed

    def test_the_federated_path_says_the_grant_is_doing_the_work(self):
        printed = self.banner_for(True, {"name": "app", "user": "reader@x.iam"})
        assert "SELECT only" in printed

    def test_the_banner_names_who_and_what_is_connected(self):
        """The two paths connect as different users with different privileges,
        so which one is in play has to be visible."""
        printed = self.banner_for(True, {"name": "somedb", "user": "reader@x.iam"})
        assert "reader@x.iam" in printed
        assert "somedb" in printed
