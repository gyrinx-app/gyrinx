#!/usr/bin/env python
"""
Automated UI screenshot utility using Playwright.

This script automatically captures screenshots of Django views using a headless browser.
It handles authentication, multiple viewports, and before/after comparisons.

Usage:
    python scripts/screenshot.py <url_name> [options]

Examples:
    python scripts/screenshot.py core:campaign --before --args <campaign_id>
    python scripts/screenshot.py core:list --after --args <list_id>
    python scripts/screenshot.py core:campaign --viewports desktop,mobile --args <id>
"""

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import socket

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

import django
from django.conf import settings

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings_dev")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402
from asgiref.sync import sync_to_async  # noqa: E402

try:
    from playwright.async_api import async_playwright
    from playwright.sync_api import sync_playwright  # noqa: F401
except ImportError:
    print("Error: Playwright is not installed.")
    print("Please run: pip install playwright")
    sys.exit(1)


# Viewport presets
VIEWPORTS = {
    "desktop": {"width": 1200, "height": 800},
    "tablet": {"width": 768, "height": 1024},
    "mobile": {"width": 375, "height": 812},
}


def check_server_running(host="localhost", port=8000):
    """Check if the Django development server is running."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def ensure_browser_installed():
    """Check if Chromium is installed and install it if necessary."""
    try:
        # Check if chromium is already installed by trying to import and use it
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Try to launch chromium to verify it's installed
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        # Chromium not installed, install it
        print("Chromium browser not found. Installing...")
        try:
            subprocess.run(
                ["playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                text=True,
            )
            print("✓ Chromium browser installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install Chromium: {e}")
            if e.stderr:
                print(f"Error details: {e.stderr}")
            return False
        except FileNotFoundError:
            print(
                "✗ playwright command not found. Please install playwright package first."
            )
            return False


class ScreenshotCapture:
    """Handles automated screenshot capture using Playwright."""

    def __init__(self, server_url="http://localhost:8000"):
        self.server_url = server_url
        self.client = Client()

    async def authenticate(self, username="admin"):
        """Authenticate using Django test client and return session cookie."""
        User = get_user_model()

        @sync_to_async
        def get_user_and_login():
            try:
                user = User.objects.get(username=username)
                self.client.force_login(user)

                # Get session cookie
                if hasattr(self.client, "cookies"):
                    session_cookie = self.client.cookies.get(
                        settings.SESSION_COOKIE_NAME
                    )
                    if session_cookie:
                        return {
                            "name": settings.SESSION_COOKIE_NAME,
                            "value": session_cookie.value,
                            "domain": "localhost",
                            "path": "/",
                            "httpOnly": True,
                            "secure": False,
                            "sameSite": "Lax",
                        }
            except User.DoesNotExist:
                print(
                    f"Warning: User '{username}' not found, proceeding without authentication"
                )
            return None

        return await get_user_and_login()

    async def capture_screenshot(
        self,
        url_name,
        url_args=None,
        label="",
        viewport="desktop",
        theme="light",
        output_dir="ui_archive",
        full_page=True,
        selector=None,
    ):
        """Capture a screenshot of a Django view."""

        # Ensure output directory exists
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Build URL
        @sync_to_async
        def get_url_path():
            try:
                return reverse(url_name, args=url_args or [])
            except Exception as e:
                print(f"Error: Failed to reverse URL '{url_name}': {e}")
                return None

        url_path = await get_url_path()
        if url_path is None:
            return False

        full_url = f"{self.server_url}{url_path}"

        # Generate filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        url_safe_name = url_name.replace(":", "_")
        viewport_suffix = f"_{viewport}" if viewport != "desktop" else ""

        if label:
            filename = f"{url_safe_name}_{label}{viewport_suffix}_{timestamp}.png"
            latest_filename = f"{url_safe_name}_{label}{viewport_suffix}_latest.png"
        else:
            filename = f"{url_safe_name}{viewport_suffix}_{timestamp}.png"
            latest_filename = f"{url_safe_name}{viewport_suffix}_latest.png"

        filepath = output_path / filename
        latest_filepath = output_path / latest_filename

        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=True)

            # Create context with viewport
            viewport_config = VIEWPORTS.get(viewport, VIEWPORTS["desktop"])
            context = await browser.new_context(
                viewport=viewport_config,
                color_scheme=theme,
            )

            # Add authentication cookie if available
            session_cookie = await self.authenticate()
            if session_cookie:
                await context.add_cookies([session_cookie])

            # Create page and navigate
            page = await context.new_page()

            print(f"Navigating to {full_url}...")
            try:
                await page.goto(full_url, wait_until="networkidle")
            except Exception as e:
                if "net::ERR_CONNECTION_REFUSED" in str(e):
                    print(f"\n✗ Error: Could not connect to {self.server_url}")
                    print("Please ensure the Django development server is running:")
                    print("  python manage.py runserver")
                    await browser.close()
                    return False
                else:
                    raise

            # Hide Django Debug Toolbar by injecting CSS
            # This ensures the toolbar is hidden regardless of its state
            await page.add_style_tag(
                content="""
                #djDebug, #djDebugToolbar, .djdt-hidden {
                    display: none !important;
                }
                /* Also hide the sidebar panel */
                #djDebugWindow, #djDebugToolbarHandle {
                    display: none !important;
                }
            """
            )

            # Wait for any animations to complete
            await page.wait_for_timeout(1000)

            # Take screenshot
            screenshot_options = {
                "path": str(filepath),
                "full_page": full_page if not selector else False,
            }

            if selector:
                # Screenshot specific element
                element = await page.query_selector(selector)
                if element:
                    await element.screenshot(path=str(filepath))
                    print(f"✓ Screenshot of '{selector}' saved to: {filepath}")
                else:
                    print(f"✗ Selector '{selector}' not found")
                    await browser.close()
                    return False
            else:
                # Screenshot full page or viewport
                await page.screenshot(**screenshot_options)
                print(f"✓ Screenshot saved to: {filepath}")

            # Close browser
            await browser.close()

        # Copy to latest
        import shutil

        shutil.copy2(filepath, latest_filepath)
        print(f"✓ Latest screenshot saved to: {latest_filepath}")

        # Update comparison markdown
        self._update_comparison_markdown(
            output_path, url_name, label, latest_filename, viewport
        )

        return True

    def _update_comparison_markdown(
        self, output_path, url_name, label, filename, viewport
    ):
        """Update comparison markdown for before/after screenshots."""
        if label not in ["before", "after"]:
            return

        url_safe_name = url_name.replace(":", "_")
        md_file = output_path / f"{url_safe_name}_comparison.md"

        # Read existing content if file exists
        existing_content = ""
        if md_file.exists() and label == "after":
            with open(md_file, "r") as f:
                existing_content = f.read()

        with open(md_file, "w") as f:
            if label == "before":
                f.write(f"## {url_name} UI Changes\n\n")
                if viewport != "desktop":
                    f.write(f"**Viewport:** {viewport}\n\n")
                f.write("### Before\n")
                f.write(f"![Before](./{filename})\n\n")
            else:
                # Write existing content first
                if existing_content:
                    f.write(existing_content)
                f.write("### After\n")
                f.write(f"![After](./{filename})\n\n")

        print(f"✓ Comparison markdown updated: {md_file}")


async def capture_screenshots(
    url_name,
    url_args=None,
    label="",
    viewports=None,
    theme="light",
    output_dir="ui_archive",
    full_page=True,
    selector=None,
    username="admin",
):
    """Capture screenshots for specified viewports."""
    capture = ScreenshotCapture()

    # Default to desktop if no viewports specified
    if not viewports:
        viewports = ["desktop"]

    success = True
    for viewport in viewports:
        print(f"\nCapturing {viewport} screenshot...")
        result = await capture.capture_screenshot(
            url_name=url_name,
            url_args=url_args,
            label=label,
            viewport=viewport,
            theme=theme,
            output_dir=output_dir,
            full_page=full_page,
            selector=selector,
        )
        if not result:
            success = False

    return success


def main():
    parser = argparse.ArgumentParser(
        description="Automated UI screenshot capture using Playwright"
    )
    parser.add_argument(
        "url_name", nargs="?", help="Django URL name (e.g., 'core:campaign')"
    )
    parser.add_argument("--args", nargs="*", help="Arguments for the URL", default=[])
    parser.add_argument(
        "--before", action="store_true", help="Label screenshot as 'before'"
    )
    parser.add_argument(
        "--after", action="store_true", help="Label screenshot as 'after'"
    )
    parser.add_argument(
        "--label", type=str, help="Custom label for the screenshot", default=""
    )
    parser.add_argument(
        "--viewports",
        type=str,
        help="Comma-separated list of viewports (desktop,tablet,mobile)",
        default="desktop",
    )
    parser.add_argument(
        "--theme",
        choices=["light", "dark"],
        default="light",
        help="Color scheme for the screenshot",
    )
    parser.add_argument(
        "--output-dir", type=str, help="Output directory", default="ui_archive"
    )
    parser.add_argument(
        "--selector", type=str, help="CSS selector to screenshot (default: full page)"
    )
    parser.add_argument(
        "--no-full-page",
        action="store_true",
        help="Capture only the viewport (not full page)",
    )
    parser.add_argument(
        "--username", type=str, default="admin", help="Username to authenticate as"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if Playwright is installed and browsers are available",
    )

    args = parser.parse_args()

    # Check installation
    if args.check:
        try:
            import playwright  # noqa: F401

            print("✓ Playwright is installed")

            # Check if Chromium is installed
            if ensure_browser_installed():
                print("✓ Chromium browser is installed")
            else:
                print("✗ Chromium browser installation failed")
                sys.exit(1)
            return
        except ImportError:
            print("✗ Playwright is not installed")
            print("\nTo install, run:")
            print("  pip install playwright")
            return

    # Require url_name if not checking
    if not args.url_name:
        parser.error("url_name is required unless using --check")

    # Determine label
    label = args.label
    if args.before:
        label = "before"
    elif args.after:
        label = "after"

    # Parse viewports
    viewports = [v.strip() for v in args.viewports.split(",")]

    # Validate viewports
    for viewport in viewports:
        if viewport not in VIEWPORTS:
            print(f"Error: Invalid viewport '{viewport}'")
            print(f"Valid viewports: {', '.join(VIEWPORTS.keys())}")
            sys.exit(1)

    # Check if server is running
    if not check_server_running():
        print("\n✗ Error: Django development server is not running")
        print("Please start the server with:")
        print("  python manage.py runserver")
        print("\nThen run this command again.")
        sys.exit(1)

    # Ensure browser is installed before attempting to capture
    if not ensure_browser_installed():
        print("\nError: Could not install Chromium browser.")
        print("Please try installing manually with: playwright install chromium")
        sys.exit(1)

    # Run async capture
    success = asyncio.run(
        capture_screenshots(
            url_name=args.url_name,
            url_args=args.args,
            label=label,
            viewports=viewports,
            theme=args.theme,
            output_dir=args.output_dir,
            full_page=not args.no_full_page,
            selector=args.selector,
            username=args.username,
        )
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
