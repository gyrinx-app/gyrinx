"""Refuse a branch that adds more than one leaf to an app's migration graph.

Several leaves per app are allowed on main: two branches that each added a
migration merge without renaming or repointing, and the next generated
migration joins them (see ``gyrinx.migration_graph``). What a single branch
must not do is add two leaves of its own. ``makemigrations`` never does; a
migration written by hand on a tree whose other leaf it ignored does, and its
operations may then run before the state they assume.

The base is a git ref, ``origin/main`` unless told otherwise. Without git, or
without that ref, every leaf is reported and the check passes.
"""

import subprocess  # nosec B404 — runs fixed git commands to read the base tree

from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader

from gyrinx.migration_graph import leaves_added_since


def migration_paths(loader):
    """Repo-relative directory prefix of each migrated app's migrations package."""
    prefixes = {}
    for app_label in loader.migrated_apps:
        module = loader.migrations_module(app_label)[0]
        if module:
            prefixes[module.replace(".", "/") + "/"] = app_label
    return prefixes


def _base_migration_names(base, loader):
    """Migration names per app label in the base tree, or None without git."""
    try:
        listing = subprocess.run(  # nosec B603 B607 — fixed argv, no shell
            ["git", "ls-tree", "-r", "--name-only", base],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except OSError, subprocess.CalledProcessError:
        return None
    prefixes = migration_paths(loader)
    names = {}
    for path in listing.splitlines():
        if not path.endswith(".py") or path.endswith("/__init__.py"):
            continue
        for prefix, app_label in prefixes.items():
            if path.startswith(prefix):
                names.setdefault(app_label, set()).add(path[len(prefix) : -3])
    return names


class Command(BaseCommand):
    help = "Refuse a branch that adds more than one migration leaf to an app."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base",
            default="origin/main",
            help="Git ref whose migrations already count as merged (default origin/main).",
        )

    def handle(self, *args, **options):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        leaves_by_app = {}
        for app_label, name in loader.graph.leaf_nodes():
            leaves_by_app.setdefault(app_label, []).append((app_label, name))
        forked = {
            app: leaves for app, leaves in leaves_by_app.items() if len(leaves) > 1
        }
        if not forked:
            self.stdout.write("Every app's migration graph has one leaf.")
            return

        base_names = _base_migration_names(options["base"], loader)
        if base_names is None:
            for app_label, leaves in sorted(forked.items()):
                self.stdout.write(
                    f"{app_label} has {len(leaves)} leaves; {options['base']} is not available, so none is checked."
                )
            return

        failures = []
        for app_label, leaves in sorted(forked.items()):
            new = leaves_added_since(leaves, base_names.get(app_label, set()))
            names = ", ".join(sorted(name for _, name in leaves))
            if len(new) > 1:
                failures.append(
                    f"  {app_label}: this branch adds {len(new)} leaves — "
                    + ", ".join(sorted(name for _, name in new))
                )
            else:
                self.stdout.write(
                    f"{app_label} has {len(leaves)} leaves ({names}); at most one is this branch's."
                )
        if failures:
            raise CommandError(
                "A branch may add one migration leaf per app.\n"
                + "\n".join(failures)
                + "\n\nA migration written on a tree with several leaves must depend on all of "
                "them; `manage makemigrations` does this itself. Regenerate the newer migration, "
                "or add the missing leaf to its dependencies."
            )
