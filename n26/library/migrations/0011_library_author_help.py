# Renames Assignable.help to library_author_help: the field is authoring
# help — for whoever wields the thing while building other content — and
# the name now says so. A rename, so anything already written survives.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0010_assignable_help"),
    ]

    operations = [
        migrations.RenameField(
            model_name="affiliation",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="affiliation",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="archetype",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="archetype",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="collection",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="collection",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="counter",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="counter",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="gangtype",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="gangtype",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="hidden",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="hidden",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="lastingeffect",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="lastingeffect",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="power",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="power",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="profile",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="profile",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="rule",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="rule",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="skill",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="skill",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="skilltree",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="skilltree",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="specialisation",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="specialisation",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="subtype",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="subtype",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="trait",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="trait",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="wargear",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="wargear",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="weapon",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="weapon",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
        migrations.RenameField(
            model_name="weaponprofile",
            old_name="help",
            new_name="library_author_help",
        ),
        migrations.AlterField(
            model_name="weaponprofile",
            name="library_author_help",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "For content authors: what this is for and how to use it "
                    "when building other content. Your own words — never the "
                    "book's rules text."
                ),
            ),
        ),
    ]
