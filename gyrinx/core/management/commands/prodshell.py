import json
import shutil
import socket
import subprocess
import time

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

            self.stdout.write("Fetching production database credentials...")
            db_config = self._fetch_db_credentials(project)

            self.stdout.write(f"Starting Cloud SQL Auth Proxy on port {port}...")
            proxy_process = self._start_proxy(project, port)

            self._configure_database(db_config, port)
            self._install_read_only_router()
            self._print_banner(port)
            self._launch_shell()
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

        env_vars = {}
        for env in containers[0].get("env", []):
            env_vars[env["name"]] = env.get("value", "")

        # Parse DB_CONFIG for user/password
        db_config_raw = env_vars.get("DB_CONFIG", "{}")
        try:
            db_config = json.loads(db_config_raw)
        except json.JSONDecodeError as e:
            raise CommandError(f"Failed to parse DB_CONFIG from Cloud Run: {e}")

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

    # -- Database configuration --

    def _configure_database(self, db_config, port):
        """Override Django's DATABASES at runtime to point at the proxy."""
        from django.conf import settings

        settings.DATABASES["default"] = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db_config["name"],
            "USER": db_config["user"],
            "PASSWORD": db_config["password"],
            "HOST": "127.0.0.1",
            "PORT": str(port),
        }

        # Close existing connections so Django reconnects with new settings
        from django import db

        db.connections.close_all()

        # Verify the connection works
        try:
            from django.db import connection

            connection.ensure_connection()
        except Exception as e:
            raise CommandError(f"Failed to connect to production database: {e}")

        self.stdout.write("Connected to production database.")

    # -- Read-only enforcement --

    def _install_read_only_router(self):
        """Install a database router that blocks all write operations."""
        from django.conf import settings

        settings.DATABASE_ROUTERS = [
            "gyrinx.core.management.commands.prodshell.ReadOnlyRouter"
        ]

    # -- Shell --

    def _print_banner(self, port):
        self.stdout.write("")
        self.stdout.write(self.style.ERROR("=" * 54))
        self.stdout.write(
            self.style.ERROR("  WARNING: CONNECTED TO PRODUCTION DATABASE")
        )
        self.stdout.write(self.style.ERROR(f"  Instance: {CLOUD_SQL_INSTANCE}"))
        self.stdout.write(self.style.ERROR(f"  Proxy port: {port}"))
        self.stdout.write(self.style.ERROR("  Mode: READ-ONLY"))
        self.stdout.write(
            self.style.ERROR("  All write operations will raise RuntimeError")
        )
        self.stdout.write(self.style.ERROR("=" * 54))
        self.stdout.write("")

    def _launch_shell(self):
        """Launch shell_plus with all models imported."""
        from django.core.management import call_command

        call_command("shell_plus")


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
