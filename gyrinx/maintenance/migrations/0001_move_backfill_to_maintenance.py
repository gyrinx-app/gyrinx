import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Adopt the repair audit record into the maintenance app.

    State-only: db_table stays core_backfill, so the existing rows and indexes
    are untouched. Paired with the core migration that releases it.

    ``operation`` loses its choices here. That is a Python-level change with no
    column effect — the set of repairs now comes from the maintenance registry,
    so an edition can add one without a platform migration.
    """

    initial = True

    dependencies = [
        ("core", "0213_document_pre_mod_advancement_flag"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Backfill",
                    fields=[
                        (
                            "id",
                            models.UUIDField(
                                default=uuid.uuid4,
                                editable=False,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        (
                            "created",
                            models.DateTimeField(auto_now_add=True, db_index=True),
                        ),
                        ("modified", models.DateTimeField(auto_now=True)),
                        ("operation", models.CharField(max_length=64)),
                        (
                            "list_id_scope",
                            models.UUIDField(
                                blank=True,
                                help_text="If set, the run was scoped to this single List.",
                                null=True,
                            ),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[
                                    ("running", "Running"),
                                    ("done", "Done"),
                                    ("failed", "Failed"),
                                    ("cancelled", "Cancelled"),
                                ],
                                default="done",
                                max_length=16,
                            ),
                        ),
                        ("summary", models.JSONField(blank=True, default=dict)),
                        ("error", models.TextField(blank=True, default="")),
                        (
                            "triggered_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="+",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "backfill",
                        "verbose_name_plural": "backfills",
                        "db_table": "core_backfill",
                        "ordering": ["-created"],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
