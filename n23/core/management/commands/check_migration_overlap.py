"""Report migrations on a branch that touch what main changed since it forked.

Run in a tree that holds both sides — a merge of the branch into main, or the
pull request's merge commit. The migrations main gained since the merge base
and the migrations the branch adds are read from git; their operations are
compared by ``gyrinx.migration_overlap``.

Exit status is 1 when a pair can fail a deploy or a fresh database, 0 when
every pair is clean or only needs a look. ``--json`` writes the findings for
the pull request comment.
"""

import json
import subprocess  # nosec B404 — runs fixed git commands to list changed files

from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader

from gyrinx.migration_overlap import overlaps

from .check_migration_conflicts import migration_paths


def _git(*args):
    try:
        return subprocess.run(  # nosec B603 B607 — fixed argv, no shell
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise CommandError(
            f"git {' '.join(args)} failed: {error.stderr.strip()}"
        ) from error


def _added_migrations(since, until, prefixes):
    """(app_label, name) for migration files added between two refs."""
    listing = _git(
        "diff",
        "--name-only",
        "--diff-filter=A",
        since,
        until,
        "--",
        "*/migrations/*.py",
    )
    keys = []
    for path in listing.splitlines():
        if path.endswith("/__init__.py"):
            continue
        for prefix, app_label in prefixes.items():
            if path.startswith(prefix):
                keys.append((app_label, path[len(prefix) : -3]))
    return keys


class Command(BaseCommand):
    help = "Report a branch's migrations that touch what main changed since it forked."

    def add_arguments(self, parser):
        parser.add_argument("--base", default="origin/main", help="Main, as a git ref.")
        parser.add_argument("--head", default="HEAD", help="The branch, as a git ref.")
        parser.add_argument(
            "--json", dest="json_path", help="Write the findings here as JSON."
        )

    def handle(self, *args, **options):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        prefixes = migration_paths(loader)
        merge_base = _git("merge-base", options["base"], options["head"])
        base_keys = _added_migrations(merge_base, options["base"], prefixes)
        branch_keys = _added_migrations(merge_base, options["head"], prefixes)

        missing = [
            key
            for key in [*base_keys, *branch_keys]
            if key not in loader.disk_migrations
        ]
        if missing:
            raise CommandError(
                "These migrations are not in the working tree; run this in a tree that holds both sides: "
                + ", ".join(f"{app}.{name}" for app, name in missing)
            )

        base = {key: loader.disk_migrations[key] for key in base_keys}
        branch = {key: loader.disk_migrations[key] for key in branch_keys}
        found = overlaps(base, branch)

        report = {
            "base_migrations": [f"{app}.{name}" for app, name in sorted(base_keys)],
            "branch_migrations": [f"{app}.{name}" for app, name in sorted(branch_keys)],
            "findings": [
                {
                    "severity": f.severity,
                    "base": f"{f.base[0]}.{f.base[1]}",
                    "branch": f"{f.branch[0]}.{f.branch[1]}",
                    "base_operation": f.base_touch.describe(),
                    "branch_operation": f.branch_touch.describe(),
                    "reason": f.reason,
                }
                for f in found
            ],
        }
        if options["json_path"]:
            with open(options["json_path"], "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)

        if not base_keys:
            self.stdout.write("Main has gained no migration since this branch forked.")
            return
        if not branch_keys:
            self.stdout.write("This branch adds no migration.")
            return
        if not found:
            self.stdout.write(
                f"{len(branch_keys)} branch migration(s) and {len(base_keys)} new on main touch nothing in common."
            )
            return
        for f in found:
            self.stdout.write(
                f"[{f.severity}] main {f.base[0]}.{f.base[1]} ({f.base_touch.describe()}) "
                f"vs branch {f.branch[0]}.{f.branch[1]} ({f.branch_touch.describe()}): {f.reason}"
            )
        if any(f.severity == "blocks" for f in found):
            raise CommandError(
                "A migration on this branch collides with one main gained since it forked."
            )
