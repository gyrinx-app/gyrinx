"""
Management command to export production content library for local development.
"""

import os
import uuid
from datetime import datetime
from decimal import Decimal
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.contrib.flatpages.models import FlatPage
from django.db import connection, connections
from django.db.migrations.recorder import MigrationRecorder

from gyrinx.content import models as content_models
from gyrinx.pages.models import FlatPageVisibility


class Command(BaseCommand):
    help = "Export production content library for local development"

    def add_arguments(self, parser):
        parser.add_argument(
            "--production-db-url",
            required=True,
            help="PostgreSQL connection string for production database",
        )
        parser.add_argument(
            "--no-backup",
            action="store_true",
            help="Skip creating a backup of the local database",
        )
        parser.add_argument(
            "--backup-dir",
            default="db_backups",
            help="Directory to store database backups (default: db_backups)",
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting content export from production...")

        try:
            # Step 1: Configure production database connection
            prod_db_url = options["production_db_url"]
            self._configure_production_db(prod_db_url)

            # Step 2: Validate connections
            try:
                self._validate_connections()
            except Exception as e:
                raise CommandError(
                    f"Database connection validation failed: {e}\n"
                    f"Ensure your production database URL is correct and accessible."
                )

            # Step 3: Check Django versions match
            self._check_django_versions()

            # Step 4: Create backup of local database
            backup_path = None
            if not options["no_backup"]:
                backup_path = self._create_local_backup(options["backup_dir"])
                self.stdout.write(
                    self.style.SUCCESS(f"Created backup at: {backup_path}")
                )

            # Step 5: Sync migration state from production
            self.stdout.write("Syncing migration state from production...")
            self._sync_migration_state()

            # Step 6: Export content models
            self.stdout.write("Exporting content models...")
            exported_data = self._export_content_models()

            # Step 7: Clear local content data
            self.stdout.write("Clearing local content data...")
            self._clear_local_content()

            # Step 8: Import content data
            self.stdout.write("Importing content data...")
            self._import_content_data(exported_data)

            # Step 9: Run remaining migrations
            self.stdout.write("Running remaining migrations...")
            call_command("migrate", verbosity=0)

            self.stdout.write(
                self.style.SUCCESS("Content export completed successfully!")
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nError: {e}"))

            # Provide cleanup instructions
            self.stdout.write("\n" + self.style.WARNING("Cleanup instructions:"))
            self.stdout.write(
                "1. If the database is in an inconsistent state, restore from backup:"
            )
            if backup_path:
                self.stdout.write(f"   python manage.py loaddata {backup_path}")
            else:
                self.stdout.write(
                    "   (No backup was created - use --no-backup flag was set)"
                )
            self.stdout.write(
                "2. Reset migration state: python manage.py migrate --fake-initial"
            )
            self.stdout.write("3. If needed, drop and recreate the database")

            raise

    def _configure_production_db(self, db_url):
        """Configure temporary production database alias"""
        # Parse the database URL manually
        # Format: postgresql://user:password@host:port/database
        from urllib.parse import urlparse

        parsed = urlparse(db_url)

        prod_config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username,
            "PASSWORD": parsed.password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
            "OPTIONS": {
                "sslmode": "require",  # For cloud databases
            },
        }

        # Add to Django's database configuration
        connections.databases["production"] = prod_config

    def _validate_connections(self):
        """Validate both local and production database connections"""
        # Test local connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        # Test production connection
        with connections["production"].cursor() as cursor:
            cursor.execute("SELECT 1")

    def _check_django_versions(self):
        """Check if Django versions match between local and production"""
        import django

        local_version = django.VERSION

        # Get production Django version from migrations
        with connections["production"].cursor() as cursor:
            cursor.execute(
                "SELECT name FROM django_migrations WHERE app = 'contenttypes' ORDER BY id DESC LIMIT 1"
            )
            result = cursor.fetchone()
            if result and result[0]:
                # Migration names often include Django version info
                # This is a heuristic check - may need adjustment
                migration_name = result[0]
                if "0002" in migration_name and local_version[0] < 2:
                    self.stdout.write(
                        self.style.WARNING(
                            "Warning: Local Django version may be incompatible with production data"
                        )
                    )

    def _create_local_backup(self, backup_dir):
        """Create a JSON backup of the local database"""
        # Create backup directory if it doesn't exist
        os.makedirs(backup_dir, exist_ok=True)

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"local_backup_{timestamp}.json"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Use dumpdata to create backup
        with open(backup_path, "w") as backup_file:
            call_command(
                "dumpdata",
                exclude=[
                    "contenttypes",
                    "auth.permission",
                    "sessions",
                    "admin.logentry",
                ],
                indent=2,
                stdout=backup_file,
                verbosity=0,
            )

        return backup_path

    def _sync_migration_state(self):
        """Sync migration state from production to local"""
        # Get production migration state
        production_migrations = []
        with connections["production"].cursor() as cursor:
            cursor.execute("SELECT app, name FROM django_migrations ORDER BY id")
            production_migrations = cursor.fetchall()

        # Clear local migration state
        MigrationRecorder(connection).migration_qs.all().delete()

        # Insert production migration state
        migration_records = [
            MigrationRecorder.Migration(app=app, name=name)
            for app, name in production_migrations
        ]
        MigrationRecorder.Migration.objects.bulk_create(migration_records)

    def _get_content_models(self):
        """Get all content models to export"""
        models = []

        # Content app models
        for name in dir(content_models):
            obj = getattr(content_models, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, content_models.Content)
                and obj != content_models.Content
                and not obj._meta.abstract
            ):
                models.append(obj)

        # Add FlatPage and FlatPageVisibility
        models.extend([FlatPage, FlatPageVisibility])

        # Sort models to handle dependencies (polymorphic parent before children)
        # ContentMod should come before its subclasses
        def sort_key(model):
            if model.__name__ == "ContentMod":
                return 0  # Parent polymorphic model first
            elif hasattr(model, "__bases__") and any(
                "ContentMod" in str(b) for b in model.__bases__
            ):
                return 1  # Polymorphic children second
            else:
                return 2  # Everything else

        models.sort(key=sort_key)

        return models

    def _export_content_models(self):
        """Export content models from production database"""
        exported_data = {}
        models = self._get_content_models()

        for model in models:
            model_name = f"{model._meta.app_label}.{model._meta.model_name}"
            self.stdout.write(f"  Exporting {model_name}...")

            # Use production database for queries
            queryset = model.objects.using("production").all()

            # Serialize the data
            data = []
            for obj in queryset:
                # Convert to dict preserving all fields including PKs
                obj_data = {}
                for field in model._meta.fields:
                    value = getattr(obj, field.name)
                    if field.is_relation and value is not None:
                        # Store the PK of related objects
                        obj_data[field.name] = (
                            str(value.pk)
                            if isinstance(value.pk, uuid.UUID)
                            else value.pk
                        )
                    elif isinstance(value, uuid.UUID):
                        obj_data[field.name] = str(value)
                    elif isinstance(value, Decimal):
                        obj_data[field.name] = str(value)
                    elif isinstance(value, datetime):
                        obj_data[field.name] = value.isoformat()
                    else:
                        obj_data[field.name] = value

                # For polymorphic models, store the polymorphic type
                if hasattr(obj, "polymorphic_ctype_id"):
                    obj_data["polymorphic_ctype_id"] = obj.polymorphic_ctype_id

                # Handle M2M relationships
                m2m_data = {}
                for field in model._meta.many_to_many:
                    pks = list(
                        getattr(obj, field.name)
                        .using("production")
                        .values_list("pk", flat=True)
                    )
                    # Convert UUID PKs to strings
                    m2m_data[field.name] = [
                        str(pk) if isinstance(pk, uuid.UUID) else pk for pk in pks
                    ]

                data.append(
                    {
                        "fields": obj_data,
                        "m2m": m2m_data,
                    }
                )

            exported_data[model_name] = {
                "model": model,
                "data": data,
            }

        return exported_data

    def _clear_local_content(self):
        """Clear existing content data from local database"""
        models = self._get_content_models()

        # Disable foreign key checks temporarily
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL DEFERRED;")

        # Delete in reverse order to handle dependencies
        for model in reversed(models):
            model_name = f"{model._meta.app_label}.{model._meta.model_name}"
            self.stdout.write(f"  Clearing {model_name}...")
            model.objects.all().delete()

    def _import_content_data(self, exported_data):
        """Import content data to local database"""
        # Process models in dependency order
        # First pass: models without foreign keys
        # Second pass: models with foreign keys
        # Third pass: M2M relationships

        # Create all objects first (without M2M)
        for model_name, model_data in exported_data.items():
            model = model_data["model"]
            self.stdout.write(f"  Importing {model_name}...")

            objects_to_create = []
            for item in model_data["data"]:
                # Convert string UUIDs back to UUID objects
                fields = {}
                for field_name, value in item["fields"].items():
                    # Skip polymorphic_ctype_id as it's handled by django-polymorphic
                    if field_name == "polymorphic_ctype_id":
                        continue

                    try:
                        field = model._meta.get_field(field_name)
                    except Exception:
                        # Field might not exist in this version
                        continue

                    if field.get_internal_type() == "UUIDField" and isinstance(
                        value, str
                    ):
                        fields[field_name] = uuid.UUID(value)
                    elif field.get_internal_type() == "DecimalField" and isinstance(
                        value, str
                    ):
                        fields[field_name] = Decimal(value)
                    elif field.get_internal_type() in [
                        "DateTimeField",
                        "DateField",
                    ] and isinstance(value, str):
                        fields[field_name] = datetime.fromisoformat(value)
                    elif (
                        field.is_relation
                        and value is not None
                        and isinstance(value, str)
                    ):
                        # UUID foreign key
                        fields[field_name + "_id"] = uuid.UUID(value)
                    elif field.is_relation and value is not None:
                        # Non-UUID foreign key
                        fields[field_name + "_id"] = value
                    else:
                        fields[field_name] = value

                obj = model(**fields)
                objects_to_create.append(obj)

            # Bulk create preserving PKs
            if objects_to_create:
                model.objects.bulk_create(objects_to_create)

        # Now handle M2M relationships
        for model_name, model_data in exported_data.items():
            model = model_data["model"]
            if not any(field.many_to_many for field in model._meta.get_fields()):
                continue

            self.stdout.write(f"  Setting M2M relationships for {model_name}...")

            for item in model_data["data"]:
                # Get the object using the appropriate PK type
                pk_value = item["fields"]["id"]
                if (
                    isinstance(pk_value, str)
                    and model._meta.pk.get_internal_type() == "UUIDField"
                ):
                    pk_value = uuid.UUID(pk_value)
                obj = model.objects.get(pk=pk_value)

                for field_name, pks in item["m2m"].items():
                    if pks:
                        # Convert UUID strings back to UUIDs if needed
                        field = model._meta.get_field(field_name)
                        related_model = field.related_model
                        if related_model._meta.pk.get_internal_type() == "UUIDField":
                            pks = [
                                uuid.UUID(pk) if isinstance(pk, str) else pk
                                for pk in pks
                            ]
                        getattr(obj, field_name).set(pks)

        # Update sequences for PostgreSQL
        with connection.cursor() as cursor:
            for model_name, model_data in exported_data.items():
                model = model_data["model"]
                table_name = model._meta.db_table

                # Update sequence for tables with serial primary keys
                if model._meta.pk.get_internal_type() in ["AutoField", "BigAutoField"]:
                    cursor.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                        f"(SELECT COALESCE(MAX(id), 1) FROM {table_name}), true);"
                    )
