# Generated manually for injury system updates

from django.db import migrations, models


def convert_phase_to_default_outcome(apps, schema_editor):
    """Convert existing phase values to new default outcome values"""
    ContentInjury = apps.get_model('content', 'ContentInjury')
    
    # Map old phase values to new default outcome values
    phase_mapping = {
        'recovery': 'recovery',
        'convalescence': 'convalescence',
        'permanent': 'active',  # Permanent injuries default to active state
        'out_cold': 'recovery',  # Out cold injuries default to recovery state
    }
    
    for injury in ContentInjury.objects.all():
        if injury.phase in phase_mapping:
            injury.phase = phase_mapping[injury.phase]
            injury.save()


def reverse_default_outcome_to_phase(apps, schema_editor):
    """Reverse the conversion for rollback"""
    ContentInjury = apps.get_model('content', 'ContentInjury')
    
    # Map new default outcome values back to old phase values
    outcome_mapping = {
        'no_change': 'permanent',  # Default no_change to permanent
        'active': 'permanent',
        'recovery': 'recovery',
        'convalescence': 'convalescence',
        'dead': 'permanent',  # Dead doesn't have a direct mapping, default to permanent
    }
    
    for injury in ContentInjury.objects.all():
        if injury.phase in outcome_mapping:
            injury.phase = outcome_mapping[injury.phase]
            injury.save()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0106_alter_contentinjury_options"),
    ]

    operations = [
        # First, add the group field
        migrations.AddField(
            model_name="contentinjury",
            name="group",
            field=models.CharField(
                blank=True,
                help_text="Optional grouping for organizing injuries in selection dropdowns.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="historicalcontentinjury",
            name="group",
            field=models.CharField(
                blank=True,
                help_text="Optional grouping for organizing injuries in selection dropdowns.",
                max_length=100,
            ),
        ),
        # Run data migration to convert phase values
        migrations.RunPython(
            convert_phase_to_default_outcome,
            reverse_default_outcome_to_phase,
        ),
        # Update the phase field choices and metadata
        migrations.AlterField(
            model_name="contentinjury",
            name="phase",
            field=models.CharField(
                choices=[
                    ("no_change", "No Change"),
                    ("active", "Active"),
                    ("recovery", "Recovery"),
                    ("convalescence", "Convalescence"),
                    ("dead", "Dead"),
                ],
                default="no_change",
                help_text="The default fighter state outcome when this injury is applied.",
                max_length=20,
                verbose_name="Default Outcome",
            ),
        ),
        migrations.AlterField(
            model_name="historicalcontentinjury",
            name="phase",
            field=models.CharField(
                choices=[
                    ("no_change", "No Change"),
                    ("active", "Active"),
                    ("recovery", "Recovery"),
                    ("convalescence", "Convalescence"),
                    ("dead", "Dead"),
                ],
                default="no_change",
                help_text="The default fighter state outcome when this injury is applied.",
                max_length=20,
                verbose_name="Default Outcome",
            ),
        ),
        # Update ordering
        migrations.AlterModelOptions(
            name="contentinjury",
            options={
                "ordering": ["group", "name"],
                "verbose_name": "Injury",
                "verbose_name_plural": "Injuries",
            },
        ),
    ]