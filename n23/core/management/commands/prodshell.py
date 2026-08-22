import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

GCP_PROJECT = "windy-ellipse-440618-p9"
GCP_REGION = "europe-west2"
CLOUD_SQL_INSTANCE = "gyrinx-app-bootstrap-db"
CLOUD_RUN_SERVICE = "gyrinx"
PROXY_PORT = 5433
PROXY_STARTUP_TIMEOUT = 15  # seconds

# The database the federated role is granted SELECT on.
IAM_DB_NAME = "app"

# Scopes must be requested explicitly. Without them the impersonation call sends
# an empty scope list and Google rejects the whole request as malformed, which
# reads like a broken configuration rather than a missing argument.
IAM_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class Command(BaseCommand):
    help = (
        "Open a Django shell connected to the production database "
        "via Cloud SQL Auth Proxy. Read-only by default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--project",
            default=GCP_PROJECT,
            help=f"GCP project ID (default: {GCP_PROJECT})",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=PROXY_PORT,
            help=f"Local port for Cloud SQL Auth Proxy (default: {PROXY_PORT})",
        )
        parser.add_argument(
            "--auth",
            choices=["auto", "iam", "gcloud"],
            default="auto",
            help=(
                "How to authenticate. 'gcloud' signs in as you and reads the "
                "application's own database credentials. 'iam' uses federated "
                "credentials to connect as a role that can only read, which is "
                "how a cloud agent reaches production. 'auto' picks iam when "
                "federated credentials are configured (default: auto)"
            ),
        )
        parser.add_argument(
            "--db-name",
            default=None,
            help=f"Database to connect to (iam default: {IAM_DB_NAME})",
        )

    def handle(self, *args, **options):
        project = options["project"]
        port = options["port"]
        proxy_process = None
        use_iam = self._use_iam_auth(options["auth"])

        try:
            self._check_cloud_sql_proxy()

            if use_iam:
                db_config = self._iam_db_config(options["db_name"])
            else:
                self._check_gcloud()
                self._check_gcloud_auth()
                self._check_adc()
                self.stdout.write("Fetching production database credentials...")
                db_config = self._fetch_db_credentials(project)
                if options["db_name"]:
                    db_config["name"] = options["db_name"]

            self.stdout.write(f"Starting Cloud SQL Auth Proxy on port {port}...")
            proxy_process = self._start_proxy(project, port, use_iam)

            self._print_banner(port, use_iam, db_config)
            self._launch_shell(db_config, port)
        except KeyboardInterrupt:
            self.stdout.write("\nInterrupted.")
        finally:
            if proxy_process:
                self.stdout.write("Stopping Cloud SQL Auth Proxy...")
                proxy_process.terminate()
                try:
                    proxy_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proxy_process.kill()
                self.stdout.write("Cloud SQL Auth Proxy stopped.")

    # -- Pre-flight checks --

    def _check_gcloud(self):
        if not shutil.which("gcloud"):
            raise CommandError(
                "gcloud CLI not found. Install it from: "
                "https://cloud.google.com/sdk/docs/install"
            )
        self.stdout.write("Checking gcloud CLI... OK")

    def _check_gcloud_auth(self):
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError("Not authenticated with gcloud. Run: gcloud auth login")
        self.stdout.write("Checking gcloud authentication... OK")

    def _check_cloud_sql_proxy(self):
        if not shutil.which("cloud-sql-proxy"):
            raise CommandError(
                "cloud-sql-proxy not found. Install it:\n"
                "  brew install cloud-sql-proxy      (macOS)\n"
                "  gcloud components install cloud-sql-proxy  (via gcloud)\n"
                "  https://cloud.google.com/sql/docs/postgres/connect-auth-proxy"
            )
        self.stdout.write("Checking cloud-sql-proxy... OK")

    def _check_adc(self):
        """Check that Application Default Credentials are valid."""
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError(
                "Application Default Credentials not set or expired.\n"
                "The Cloud SQL Auth Proxy requires ADC. Run:\n"
                "  gcloud auth application-default login"
            )
        self.stdout.write("Checking Application Default Credentials... OK")

    # -- Federated credentials --

    @staticmethod
    def _credential_config():
        """The external_account config ADC is pointed at, if that is what it is.

        A cloud agent authenticates by exchanging a short-lived token for
        permission to act as a service account, and the file describing that
        exchange is what distinguishes it from a developer signed in with
        gcloud.
        """
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not path:
            return None
        try:
            config = json.loads(Path(path).read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return None
        if not isinstance(config, dict) or config.get("type") != "external_account":
            return None
        return config

    def _use_iam_auth(self, mode):
        if mode == "iam":
            return True
        if mode == "gcloud":
            return False
        return self._credential_config() is not None

    @staticmethod
    def _impersonated_service_account(config):
        """The account the federated credentials act as, from the config."""
        url = config.get("service_account_impersonation_url", "")
        match = re.search(r"/serviceAccounts/([^:/]+):", url)
        return match.group(1) if match else None

    def _iam_db_config(self, db_name):
        """Work out who to connect as, and prove we can become them first.

        Checking here rather than letting the connection fail means a rejected
        token is reported as a rejected token, instead of surfacing much later
        as an unexplained inability to reach the database.
        """
        config = self._credential_config()
        if config is None:
            raise CommandError(
                "No federated credentials found. GOOGLE_APPLICATION_CREDENTIALS "
                "must point at an external_account configuration file. This mode "
                "is meant for a cloud agent; on a workstation use --auth=gcloud."
            )

        service_account = self._impersonated_service_account(config)
        if not service_account:
            raise CommandError(
                "The credential configuration does not impersonate a service "
                "account, so there is no database role to connect as."
            )

        try:
            import google.auth
            import google.auth.transport.requests
        except ImportError as e:  # pragma: no cover - google-auth is installed
            raise CommandError(f"google-auth is not available: {e}") from e

        try:
            credentials, _ = google.auth.default(scopes=IAM_SCOPES)
            credentials.refresh(google.auth.transport.requests.Request())
        except Exception as e:
            raise CommandError(
                f"Could not obtain credentials for {service_account}:\n{e}\n\n"
                "The token is minted locally but exchanging it needs to reach "
                "Google, and the identity must satisfy the provider's attribute "
                "condition."
            ) from e

        self.stdout.write(f"Authenticated as {service_account}.")

        # Cloud SQL drops the trailing domain from a service account's name.
        db_user = re.sub(r"\.gserviceaccount\.com$", "", service_account)
        return {
            "name": db_name or IAM_DB_NAME,
            "user": db_user,
            # The proxy authenticates the connection, so there is no password to
            # hold, fetch, or leak.
            "password": "",
        }

    # -- Credential fetching --

    def _fetch_db_credentials(self, project):
        """Fetch DB credentials from the Cloud Run service environment."""
        result = subprocess.run(
            [
                "gcloud",
                "run",
                "services",
                "describe",
                CLOUD_RUN_SERVICE,
                f"--region={GCP_REGION}",
                f"--project={project}",
                "--format=json",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError(
                f"Failed to fetch Cloud Run service config:\n{result.stderr}"
            )

        try:
            service = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise CommandError(f"Failed to parse Cloud Run service config: {e}") from e

        # Extract env vars from the container spec
        containers = (
            service.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
        if not containers:
            raise CommandError("No containers found in Cloud Run service config")

        container_env = containers[0].get("env", [])
        env_vars = {e["name"]: e["value"] for e in container_env if "value" in e}
        secret_refs = {
            e["name"]: e["valueFrom"]["secretKeyRef"]
            for e in container_env
            if "valueFrom" in e
        }

        # DB_CONFIG may be a secret reference - resolve it
        if "DB_CONFIG" in env_vars:
            db_config_raw = env_vars["DB_CONFIG"]
        elif "DB_CONFIG" in secret_refs:
            ref = secret_refs["DB_CONFIG"]
            db_config_raw = self._fetch_secret(project, ref["name"], ref["key"])
        else:
            raise CommandError("DB_CONFIG not found in Cloud Run service config")

        try:
            db_config = json.loads(db_config_raw)
        except json.JSONDecodeError as e:
            raise CommandError(f"Failed to parse DB_CONFIG: {e}") from e

        db_user = db_config.get("user")
        db_password = db_config.get("password")
        db_name = env_vars.get("DB_NAME", "gyrinx")

        if not db_user or not db_password:
            raise CommandError(
                "Could not extract database credentials from Cloud Run config. "
                "DB_CONFIG must contain 'user' and 'password' keys."
            )

        self.stdout.write("Fetched production credentials from Cloud Run service.")
        return {
            "name": db_name,
            "user": db_user,
            "password": db_password,
        }

    def _fetch_secret(self, project, secret_name, version="latest"):
        """Fetch a secret value from Google Cloud Secret Manager."""
        result = subprocess.run(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                version,
                f"--secret={secret_name}",
                f"--project={project}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError(
                f"Failed to fetch secret '{secret_name}':\n{result.stderr}"
            )
        return result.stdout.strip()

    # -- Cloud SQL Auth Proxy --

    def _start_proxy(self, project, port, use_iam=False):
        """Start Cloud SQL Auth Proxy and wait for it to be ready."""
        instance_connection = f"{project}:{GCP_REGION}:{CLOUD_SQL_INSTANCE}"
        command = ["cloud-sql-proxy", instance_connection, f"--port={port}"]
        if use_iam:
            # Hands the connection an access token for the impersonated account
            # instead of a password.
            command.append("--auto-iam-authn")
        proxy_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Wait for the proxy to be ready by polling the port
        start = time.monotonic()
        while time.monotonic() - start < PROXY_STARTUP_TIMEOUT:
            # Check if process died
            if proxy_process.poll() is not None:
                stderr = (
                    proxy_process.stderr.read().decode() if proxy_process.stderr else ""
                )
                raise CommandError(
                    f"Cloud SQL Auth Proxy exited unexpectedly:\n{stderr}"
                )
            if self._port_is_open(port):
                self.stdout.write(f"Cloud SQL Auth Proxy ready on port {port}.")
                return proxy_process
            time.sleep(0.5)

        proxy_process.terminate()
        raise CommandError(
            f"Cloud SQL Auth Proxy did not start within {PROXY_STARTUP_TIMEOUT}s. "
            "Check your gcloud credentials and network."
        )

    @staticmethod
    def _port_is_open(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0

    # -- Shell --

    def _print_banner(self, port, use_iam=False, db_config=None):
        if use_iam:
            # Worth distinguishing: under gcloud the read-only rule is this
            # command's own doing and holds only inside it, whereas the database
            # itself refuses to let this role write.
            enforcement = "READ-ONLY (granted SELECT only; also enforced here)"
        else:
            enforcement = "READ-ONLY (enforced by this command)"
        connected_as = (db_config or {}).get("user", "unknown")
        database = (db_config or {}).get("name", "unknown")
        banner = f"""
{"=" * 54}
  WARNING: CONNECTED TO PRODUCTION DATABASE
  Instance: {CLOUD_SQL_INSTANCE}
  Database: {database}
  Connected as: {connected_as}
  Proxy port: {port}
  Mode: {enforcement}
  All write operations will raise RuntimeError
{"=" * 54}
"""
        self.stdout.write(self.style.ERROR(banner))

    def _launch_shell(self, db_config, port):
        """Launch shell_plus as a subprocess with production database settings.

        Creates a temporary settings file that points DATABASES at the proxy
        and installs a read-only database router, then runs shell_plus with
        DJANGO_SETTINGS_MODULE pointing at it.
        """
        settings_content = f"""\
# Auto-generated prodshell settings - DO NOT EDIT
from gyrinx.settings_dev import *  # noqa: F401,F403

DATABASES = {{
    "default": {{
        "ENGINE": "django.db.backends.postgresql",
        "NAME": {db_config["name"]!r},
        "USER": {db_config["user"]!r},
        "PASSWORD": {db_config["password"]!r},
        "HOST": "127.0.0.1",
        "PORT": "{port}",
    }}
}}

DATABASE_ROUTERS = [
    "n23.core.management.commands.prodshell.ReadOnlyRouter"
]
"""

        # Write settings to a temp file inside the project package so it's importable
        import gyrinx

        settings_path = Path(gyrinx.__file__).parent / "_prodshell_settings.py"

        try:
            fd = os.open(
                str(settings_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(settings_content)

            env = {**os.environ, "DJANGO_SETTINGS_MODULE": "gyrinx._prodshell_settings"}

            # Run shell_plus as a subprocess so it picks up the new settings
            result = subprocess.run(
                [sys.executable, "-m", "django", "shell_plus"],
                env=env,
            )
            if result.returncode != 0:
                raise CommandError(f"shell_plus exited with code {result.returncode}")
        finally:
            settings_path.unlink(missing_ok=True)


class ReadOnlyRouter:
    """Database router that prevents all write operations."""

    def db_for_read(self, model, **hints):
        return "default"

    def db_for_write(self, model, **hints):
        raise RuntimeError(
            "Write operations are disabled in prodshell (read-only mode)."
        )

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return False
