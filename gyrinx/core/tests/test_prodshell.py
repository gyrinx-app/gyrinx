import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.management.base import CommandError

from gyrinx.core.management.commands.prodshell import Command, ReadOnlyRouter


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
            cmd._start_proxy("test-project", 5433)

    @patch(
        "gyrinx.core.management.commands.prodshell.Command._port_is_open",
        return_value=True,
    )
    @patch("subprocess.Popen")
    def test_proxy_starts_successfully(self, mock_popen, mock_port_is_open, cmd):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc

        result = cmd._start_proxy("test-project", 5433)
        assert result is mock_proc

    @patch("gyrinx.core.management.commands.prodshell.time.monotonic")
    @patch(
        "gyrinx.core.management.commands.prodshell.Command._port_is_open",
        return_value=False,
    )
    @patch("gyrinx.core.management.commands.prodshell.time.sleep")
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
            cmd._start_proxy("test-project", 5433)

        mock_proc.terminate.assert_called_once()
