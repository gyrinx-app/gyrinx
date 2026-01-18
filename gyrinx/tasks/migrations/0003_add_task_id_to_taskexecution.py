"""
Add task_id field to TaskExecution model.

The task_id stores the external task ID from Django's task framework
(TaskResult.id), separate from our internal UUID primary key.

This migration is safe for databases with existing TaskExecution records:
1. Adds task_id as nullable field (no constraint issues)
2. Populates existing records with unique values based on their UUID
3. Makes field non-nullable and adds unique constraint
"""

from django.db import migrations, models


def populate_task_ids(apps, schema_editor):
    """Populate task_id for any existing TaskExecution records."""
    TaskExecution = apps.get_model("tasks", "TaskExecution")
    for execution in TaskExecution.objects.filter(task_id=""):
        # Use the existing UUID primary key as the task_id for legacy records
        execution.task_id = f"legacy-{execution.id}"
        execution.save(update_fields=["task_id"])


def reverse_populate_task_ids(apps, schema_editor):
    """Reverse migration - clear task_ids."""
    TaskExecution = apps.get_model("tasks", "TaskExecution")
    TaskExecution.objects.filter(task_id__startswith="legacy-").update(task_id="")


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0002_alter_taskexecution_status_and_more"),
    ]

    operations = [
        # Step 1: Add field as nullable without unique constraint
        migrations.AddField(
            model_name="taskexecution",
            name="task_id",
            field=models.CharField(
                db_index=True,
                default="",
                help_text="External task ID from Django's task framework (TaskResult.id)",
                max_length=255,
            ),
        ),
        # Step 2: Populate any existing records with unique task_ids
        migrations.RunPython(
            populate_task_ids,
            reverse_populate_task_ids,
        ),
        # Step 3: Add unique constraint now that all values are unique
        migrations.AlterField(
            model_name="taskexecution",
            name="task_id",
            field=models.CharField(
                db_index=True,
                help_text="External task ID from Django's task framework (TaskResult.id)",
                max_length=255,
                unique=True,
            ),
        ),
    ]
