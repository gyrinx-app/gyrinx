import json
import os
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

    def handle(self, *args, **options):
        project = options["project"]
        port = options["port"]
        proxy_process = None

        try:
            self._check_gcloud()
            self._check_gcloud_auth()
            self._check_cloud_sql_proxy()
            self._check_adc()

            self.stdout.write("Fetching production database credentials...")
            db_config = self._fetch_db_credentials(project)

            self.stdout.write(f"Starting Cloud SQL Auth Proxy on port {port}...")
            proxy_process = self._start_proxy(project, port)

            self._print_banner(port)
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
            raise CommandError(f"Failed to parse Cloud Run service config: {e}")

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
            raise CommandError(f"Failed to parse DB_CONFIG: {e}")

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
        return result.stdout

    # -- Cloud SQL Auth Proxy --

    def _start_proxy(self, project, port):
        """Start Cloud SQL Auth Proxy and wait for it to be ready."""
        instance_connection = f"{project}:{GCP_REGION}:{CLOUD_SQL_INSTANCE}"
        proxy_process = subprocess.Popen(
            [
                "cloud-sql-proxy",
                instance_connection,
                f"--port={port}",
            ],
            stdout=subprocess.PIPE,
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

    def _print_banner(self, port):
        banner = f"""
{"=" * 54}
  WARNING: CONNECTED TO PRODUCTION DATABASE
  Instance: {CLOUD_SQL_INSTANCE}
  Proxy port: {port}
  Mode: READ-ONLY
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
    "gyrinx.core.management.commands.prodshell.ReadOnlyRouter"
]
"""

        # Write settings to a temp file inside the project package so it's importable
        import gyrinx

        settings_path = Path(gyrinx.__file__).parent / "_prodshell_settings.py"

        try:
            settings_path.write_text(settings_content)

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
