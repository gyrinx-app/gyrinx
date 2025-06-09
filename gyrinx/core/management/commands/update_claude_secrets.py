import json
import subprocess
from datetime import datetime
from typing import Dict, Optional

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Update GitHub repository secrets with Claude credentials from Mac keychain"

    # Secret mapping from JSON to GitHub secret names
    SECRET_MAPPING = {
        "accessToken": "CLAUDE_ACCESS_TOKEN",
        "refreshToken": "CLAUDE_REFRESH_TOKEN",
        "expiresAt": "CLAUDE_EXPIRES_AT",
    }

    KEYCHAIN_NAME = "Claude Code-credentials"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip confirmation prompt",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        try:
            # Step 1: Get credentials from keychain
            self.stdout.write("Fetching credentials from Mac keychain...")
            credentials = self._get_keychain_credentials()

            if not credentials:
                raise CommandError("Failed to retrieve credentials from keychain")

            # Step 2: Parse and extract required fields
            self.stdout.write("Parsing credentials...")
            secrets = self._parse_credentials(credentials)

            if not secrets:
                raise CommandError(
                    "Failed to parse credentials or missing required fields"
                )

            # Step 3: Get repository information
            self.stdout.write("Getting repository information...")
            repo_info = self._get_repo_info()

            if not repo_info:
                raise CommandError(
                    "Failed to get repository information. Make sure you're in a git repository."
                )

            # Step 4: List existing secrets in the repository
            self.stdout.write(f"\nRepository: {repo_info}")
            existing_secrets = self._list_github_secrets(repo_info)
            if existing_secrets:
                self.stdout.write("\nExisting secrets in repository:")
                for secret in existing_secrets:
                    self.stdout.write(f"  - {secret}")
            else:
                self.stdout.write("\nNo existing secrets found in repository.")

            # Step 5: Show what will be updated
            self.stdout.write("\nSecrets to update:")
            for github_name in self.SECRET_MAPPING.values():
                secret_value = secrets.get(github_name, "")
                if github_name == "CLAUDE_EXPIRES_AT":
                    # Show expires_at as human-readable date
                    try:
                        timestamp_ms = int(secret_value)
                        timestamp_s = timestamp_ms / 1000
                        expires_date = datetime.fromtimestamp(timestamp_s)
                        display_value = f"{secret_value} ({expires_date.strftime('%Y-%m-%d %H:%M:%S')})"
                    except (ValueError, TypeError):
                        display_value = secret_value
                else:
                    display_value = self._sanitize_secret(secret_value)
                self.stdout.write(f"  - {github_name}: {display_value}")

            # Step 6: Confirm unless forced or dry-run
            if not options["force"] and not options["dry_run"]:
                response = input("\nDo you want to proceed? [y/N]: ")
                if response.lower() != "y":
                    self.stdout.write("Operation cancelled.")
                    return

            # Step 7: Update GitHub secrets
            if options["dry_run"]:
                self.stdout.write("\nDRY RUN - No changes will be made")
            else:
                self.stdout.write("\nUpdating GitHub secrets...")
                self._update_github_secrets(repo_info, secrets)

            self.stdout.write(
                self.style.SUCCESS("\nSuccessfully updated GitHub secrets!")
            )

        except Exception as e:
            # Ensure we never log the actual secret values
            error_msg = str(e)
            if "sk-ant-" in error_msg:
                error_msg = "Error occurred (details hidden for security)"
            raise CommandError(f"Failed to update secrets: {error_msg}")

    def _get_keychain_credentials(self) -> Optional[str]:
        """Retrieve credentials from Mac keychain"""
        try:
            # Use security command to get the password from keychain
            result = subprocess.run(
                ["security", "find-generic-password", "-s", self.KEYCHAIN_NAME, "-w"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                self.stderr.write(f"Failed to access keychain: {result.stderr}")
                return None

            return result.stdout.strip()
        except Exception as e:
            self.stderr.write(f"Error accessing keychain: {str(e)}")
            return None

    def _parse_credentials(self, credentials_json: str) -> Optional[Dict[str, str]]:
        """Parse JSON credentials and extract required fields"""
        try:
            data = json.loads(credentials_json)
            oauth_data = data.get("claudeAiOauth", {})

            # Extract required fields
            secrets = {}
            for json_key, github_key in self.SECRET_MAPPING.items():
                value = oauth_data.get(json_key)
                if value is None:
                    self.stderr.write(
                        f"Missing required field: claudeAiOauth.{json_key}"
                    )
                    return None
                # Convert to string (important for expiresAt which is a number)
                secrets[github_key] = str(value)

            return secrets
        except json.JSONDecodeError as e:
            self.stderr.write(f"Failed to parse JSON: {str(e)}")
            return None
        except Exception as e:
            self.stderr.write(f"Error parsing credentials: {str(e)}")
            return None

    def _get_repo_info(self) -> Optional[str]:
        """Get GitHub repository information"""
        try:
            # Get the remote URL
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=True,
            )

            remote_url = result.stdout.strip()

            # Parse the URL to get owner/repo format
            # Handle both HTTPS and SSH URLs
            if remote_url.startswith("https://github.com/"):
                repo_path = remote_url.replace("https://github.com/", "").replace(
                    ".git", ""
                )
            elif remote_url.startswith("git@github.com:"):
                repo_path = remote_url.replace("git@github.com:", "").replace(
                    ".git", ""
                )
            else:
                self.stderr.write(f"Unsupported remote URL format: {remote_url}")
                return None

            return repo_path
        except subprocess.CalledProcessError as e:
            self.stderr.write(f"Git command failed: {e.stderr}")
            return None
        except Exception as e:
            self.stderr.write(f"Error getting repository info: {str(e)}")
            return None

    def _update_github_secrets(self, repo: str, secrets: Dict[str, str]) -> None:
        """Update GitHub repository secrets"""
        for secret_name, secret_value in secrets.items():
            try:
                self.stdout.write(f"  Updating {secret_name}...")

                # Use gh CLI to set the secret
                # The secret value is passed via stdin to avoid command line exposure
                result = subprocess.run(
                    ["gh", "secret", "set", secret_name, "-R", repo],
                    input=secret_value,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                if result.returncode != 0:
                    # Don't include stderr as it might contain sensitive info
                    raise Exception(f"gh command failed for {secret_name}")

                self.stdout.write(f"    ✓ {secret_name} updated")

            except Exception as e:
                # Ensure we don't log any sensitive information
                error_msg = str(e)
                if "sk-ant-" in error_msg:
                    error_msg = "Update failed (details hidden for security)"
                raise Exception(f"Failed to update {secret_name}: {error_msg}")

    def _sanitize_secret(self, secret: str) -> str:
        """Sanitize a secret for display, showing only first and last few characters"""
        if not secret:
            return "<empty>"

        if len(secret) <= 10:
            # For very short secrets, just show that they exist
            return "***"

        # For longer secrets, show first 6 and last 4 characters
        first_chars = secret[:6]
        last_chars = secret[-4:]
        middle_dots = "..." + ("*" * min(20, len(secret) - 10)) + "..."

        return f"{first_chars}{middle_dots}{last_chars}"

    def _list_github_secrets(self, repo: str) -> list[str]:
        """List existing secrets in the GitHub repository"""
        try:
            result = subprocess.run(
                ["gh", "secret", "list", "-R", repo],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                self.stderr.write(f"Failed to list secrets: {result.stderr}")
                return []

            # Parse the output - gh secret list returns tab-separated values
            # Format: NAME\tUPDATED
            secrets = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("\t")
                    if parts:
                        secrets.append(parts[0])

            return sorted(secrets)
        except Exception as e:
            self.stderr.write(f"Error listing secrets: {str(e)}")
            return []
