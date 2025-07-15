"""
Django management command that loads fixture data and overwrites existing data.
This command will delete existing objects and replace them with fixture data.
"""

import json

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = (
        "Load fixture data and overwrite any existing objects with the same primary key"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "fixture_file", type=str, help="Path to the fixture file (JSON format)"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Show detailed progress"
        )

    def handle(self, *args, **options):
        fixture_file = options["fixture_file"]
        dry_run = options.get("dry_run", False)
        verbose = options.get("verbose", False)

        try:
            with open(fixture_file, "r") as f:
                fixture_data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f"Fixture file '{fixture_file}' not found")
        except json.JSONDecodeError as e:
            raise CommandError(f"Invalid JSON in fixture file: {e}")

        if dry_run:
            self.stdout.write("DRY RUN - No changes will be made")

        # Group objects by model
        objects_by_model = {}
        for obj_data in fixture_data:
            model_label = obj_data["model"]
            if model_label not in objects_by_model:
                objects_by_model[model_label] = []
            objects_by_model[model_label].append(obj_data)

        # Separate historical models from regular models
        historical_models = {}
        regular_models = {}

        for model_label, objects in objects_by_model.items():
            if "historical" in model_label.lower():
                historical_models[model_label] = objects
            else:
                regular_models[model_label] = objects

        # Clear all data from regular models first (in reverse dependency order)
        if not dry_run:
            self.stdout.write("Clearing existing data...")
            # Temporarily disable foreign key checks for clearing
            with connection.cursor() as cursor:
                cursor.execute("SET session_replication_role = 'replica';")
            try:
                self._clear_all_models(regular_models, verbose)
            finally:
                # Re-enable foreign key checks
                with connection.cursor() as cursor:
                    cursor.execute("SET session_replication_role = 'origin';")

        # Process regular models
        self._process_models(regular_models, dry_run, verbose)

        # Then process historical models if needed
        if historical_models:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipping {len(historical_models)} historical model types - these should be managed by django-simple-history"
                )
            )
            if verbose:
                for model_label in historical_models:
                    self.stdout.write(f"  - {model_label}")

        total_regular = sum(len(objs) for objs in regular_models.values())
        total_historical = sum(len(objs) for objs in historical_models.values())

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY RUN complete - would process {total_regular} objects (skipped {total_historical} historical records)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully processed {total_regular} objects from {fixture_file} (skipped {total_historical} historical records)"
                )
            )

    def _process_models(self, models_dict, dry_run, verbose):
        """Process a dictionary of models and their objects."""
        if dry_run:
            # In dry run mode, just count objects
            for model_label, objects in models_dict.items():
                if verbose:
                    self.stdout.write(
                        f"Would load {len(objects)} objects for {model_label}"
                    )
            return

        # Create a temporary file with just the regular models
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Flatten all objects from regular models
            all_objects = []
            for objects in models_dict.values():
                all_objects.extend(objects)

            json.dump(all_objects, f, indent=2)
            temp_file = f.name

        try:
            # Use Django's built-in loaddata which handles dependencies properly
            if verbose:
                self.stdout.write("Loading fixture data...")

            # Disable foreign key checks temporarily for loading
            with connection.cursor() as cursor:
                cursor.execute("SET session_replication_role = 'replica';")

            try:
                # Load the data
                call_command("loaddata", temp_file, verbosity=2 if verbose else 1)
            finally:
                # Re-enable foreign key checks
                with connection.cursor() as cursor:
                    cursor.execute("SET session_replication_role = 'origin';")

        finally:
            # Clean up temp file
            import os

            os.unlink(temp_file)

    def _clear_all_models(self, models_dict, verbose):
        """Clear all data from models before loading new data."""
        # Get all model classes
        model_classes = []
        for model_label in models_dict.keys():
            try:
                app_label, model_name = model_label.split(".")
                model = apps.get_model(app_label, model_name)
                model_classes.append((model_label, model))
            except (ValueError, LookupError):
                continue

        # Clear in reverse order to handle dependencies
        for model_label, model in reversed(model_classes):
            try:
                count = model.objects.all().count()
                if count > 0:
                    with connection.cursor() as cursor:
                        # Use plain TRUNCATE without CASCADE since foreign keys are disabled
                        cursor.execute(f'TRUNCATE TABLE "{model._meta.db_table}"')
                    if verbose:
                        self.stdout.write(f"Cleared {count} objects from {model_label}")
            except Exception:
                # Fallback to DELETE without cascading
                try:
                    # Delete only objects in this table, not related objects
                    with connection.cursor() as cursor:
                        cursor.execute(f'DELETE FROM "{model._meta.db_table}"')  # nosec B608
                        count = cursor.rowcount
                    if verbose and count > 0:
                        self.stdout.write(f"Deleted {count} objects from {model_label}")
                except Exception as e2:
                    if verbose:
                        self.stdout.write(
                            self.style.WARNING(f"Could not clear {model_label}: {e2}")
                        )

    def _extract_unique_fields(self, error, model):
        """Try to extract field names from unique constraint error message."""
        error_str = str(error)

        # Common patterns for unique constraint field names
        if "Key (" in error_str and ")=" in error_str:
            # PostgreSQL format: Key (field_name)=(value)
            start = error_str.find("Key (") + 5
            end = error_str.find(")=", start)
            if start > 4 and end > start:
                field_name = error_str[start:end]
                # Map database column to model field
                for field in model._meta.fields:
                    if field.column == field_name or field.name == field_name:
                        return [field.name]

        return None
