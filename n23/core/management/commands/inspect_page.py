"""Inspect a local page through Django Debug Toolbar without a browser."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from gyrinx.debug_login import ensure_debug_agent_user
from gyrinx.page_inspection import (
    PANEL_NAMES,
    build_report,
    capture_request,
    render_text,
)


class Command(BaseCommand):
    help = "Inspect a local GET request using Django Debug Toolbar panel data"

    def add_arguments(self, parser):
        parser.add_argument("path", help="Local absolute path to inspect")
        parser.add_argument(
            "--username",
            default="agent",
            help="Debug agent user to authenticate as (default: agent)",
        )
        parser.add_argument(
            "--anonymous",
            action="store_true",
            help="Make the request without authenticating",
        )
        parser.add_argument(
            "--panel",
            action="append",
            choices=(*PANEL_NAMES, "all"),
            default=[],
            help="Add bounded detail for a toolbar panel; repeat as needed",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="all_panels",
            help="Add bounded detail for every supported panel",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum rows per detailed panel (default: 10)",
        )
        parser.add_argument(
            "--setting",
            action="append",
            default=[],
            help="Case-insensitive settings-name filter; repeat as needed",
        )
        parser.add_argument(
            "--warmup",
            type=int,
            default=1,
            help="Unreported cache-warming requests (default: 1)",
        )
        parser.add_argument(
            "--repeat",
            type=int,
            default=2,
            help="Measured requests used to show stability (default: 2)",
        )
        parser.add_argument(
            "--no-follow",
            action="store_false",
            dest="follow",
            help="Inspect the first response instead of following redirects",
        )
        parser.add_argument(
            "--header",
            action="append",
            default=[],
            metavar="NAME=VALUE",
            help="Request header; repeat as needed",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit structured JSON instead of compact text",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Page inspection is only available with DEBUG enabled")

        path = options["path"]
        if not path.startswith("/") or path.startswith("//"):
            raise CommandError("Path must be a local absolute path beginning with /")
        if options["limit"] < 1:
            raise CommandError("--limit must be at least 1")
        if options["warmup"] < 0:
            raise CommandError("--warmup cannot be negative")
        if options["repeat"] < 1:
            raise CommandError("--repeat must be at least 1")

        headers = self._headers(options["header"])
        client = Client(raise_request_exception=False)
        username = None
        if not options["anonymous"]:
            try:
                user = ensure_debug_agent_user(options["username"])
            except ValueError as error:
                raise CommandError(str(error)) from error
            client.force_login(user)
            username = user.username

        try:
            for _ in range(options["warmup"]):
                capture_request(
                    client,
                    path,
                    follow=options["follow"],
                    headers=headers,
                )
            captures = [
                capture_request(
                    client,
                    path,
                    follow=options["follow"],
                    headers=headers,
                )
                for _ in range(options["repeat"])
            ]
        except RuntimeError as error:
            raise CommandError(str(error)) from error

        panels = options["panel"]
        if options["all_panels"] or "all" in panels:
            panels = list(PANEL_NAMES)
        else:
            panels = list(dict.fromkeys(panels))
            if options["setting"] and "settings" not in panels:
                panels.append("settings")

        report = build_report(
            captures,
            username=username,
            warmup_requests=options["warmup"],
            detail_panels=panels,
            limit=options["limit"],
            setting_filters=options["setting"],
            project_root=Path(settings.BASE_DIR),
        )
        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str))
        else:
            self.stdout.write(render_text(report))

    @staticmethod
    def _headers(values):
        headers = {}
        for value in values:
            name, separator, header_value = value.partition("=")
            if not separator or not name.strip():
                raise CommandError("--header must use NAME=VALUE")
            headers[name.strip()] = header_value
        return headers
