from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = "Check for conflicting migrations (multiple leaf nodes per app)."

    def handle(self, *args, **options):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        conflicts = loader.detect_conflicts()

        if not conflicts:
            self.stdout.write("No migration conflicts detected.")
            return

        messages = []
        for app_label, migration_names in sorted(conflicts.items()):
            names = ", ".join(sorted(migration_names))
            messages.append(f"  {app_label}: {names}")

        raise CommandError(
            "Conflicting migrations detected!\n" + "\n".join(messages) + "\n\n"
            "These migrations branch from the same parent and need a "
            "merge migration.\n"
            "Run: manage makemigrations --merge"
        )
