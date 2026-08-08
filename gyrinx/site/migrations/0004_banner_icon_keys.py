"""Banner.icon stops being a Bootstrap Icons class and becomes a meaning.

The column used to hold free text that only Bootstrap could read, which is why
a live banner set to ``bi-blockquote-left`` could take a whole edition down.
It now holds one of the keys in ``gyrinx/site/icons.py``, and each edition
resolves that key in its own icon set.

The maps below are frozen copies rather than imports from that module. A
migration has to keep meaning what it meant on the day it ran, and the table it
was written against will keep changing after this.

Historical rows are converted too. The field's vocabulary changed wholesale, so
leaving history in the old one would show values in the history admin that mean
nothing — and restoring a banner from history would write a key that is not a
valid choice. This rewrites how a value is spelled, not what any banner said.
"""

from django.db import migrations, models

import gyrinx.site.icons

#: What each old Bootstrap class meant. Anything not listed — and the column was
#: free text, so anything at all could be in there — becomes no icon, which is
#: the one answer that is never wrong-looking.
#:
#: bi-blockquote-left is the value prod was actually running: a "we have news"
#: banner about N26, wearing a quotation mark because the field offered no
#: better option. It becomes news, which is what it was for.
LEGACY_KEYS = {
    "bi-info-circle": "info",
    "bi-info-circle-fill": "info",
    "bi-info-square": "info",
    "bi-check-circle": "success",
    "bi-check-circle-fill": "success",
    "bi-check": "success",
    "bi-check-lg": "success",
    "bi-exclamation-triangle": "warning",
    "bi-exclamation-triangle-fill": "warning",
    "bi-exclamation-circle": "warning",
    "bi-exclamation-octagon": "warning",
    "bi-bell": "news",
    "bi-bell-fill": "news",
    "bi-megaphone": "news",
    "bi-megaphone-fill": "news",
    "bi-blockquote-left": "news",
    "bi-newspaper": "news",
    "bi-star": "highlight",
    "bi-star-fill": "highlight",
    "bi-stars": "highlight",
    "bi-heart": "thanks",
    "bi-heart-fill": "thanks",
    "bi-gear": "maintenance",
    "bi-gear-fill": "maintenance",
    "bi-tools": "maintenance",
    "bi-wrench": "maintenance",
}

#: For the way back, so this migration is reversible. Not the exact inverse:
#: several old classes collapsed onto one key, and un-collapsing picks the
#: representative the new table already names.
BOOTSTRAP_BY_KEY = {
    "info": "bi-info-circle",
    "success": "bi-check-circle",
    "warning": "bi-exclamation-triangle",
    "news": "bi-bell",
    "highlight": "bi-star",
    "thanks": "bi-heart",
    "maintenance": "bi-gear",
}

#: Both tables the field lives on: the banner and its simple-history mirror.
TABLES = ("Banner", "HistoricalBanner")


def _remap(apps, mapping, already_correct):
    for name in TABLES:
        model = apps.get_model("gyrinxsite", name)
        for row in model.objects.exclude(icon="").iterator():
            if row.icon in already_correct:
                continue
            row.icon = mapping.get(row.icon, "")
            row.save(update_fields=["icon"])


def to_keys(apps, schema_editor):
    """Bootstrap classes become keys. Rows already holding a key are left be,
    so a re-run cannot blank them."""
    _remap(apps, LEGACY_KEYS, already_correct=set(BOOTSTRAP_BY_KEY))


def to_bootstrap_classes(apps, schema_editor):
    _remap(apps, BOOTSTRAP_BY_KEY, already_correct=set(LEGACY_KEYS))


class Migration(migrations.Migration):
    dependencies = [("gyrinxsite", "0003_changelog_entry")]

    operations = [
        migrations.AlterField(
            model_name="banner",
            name="icon",
            field=models.CharField(
                blank=True,
                choices=gyrinx.site.icons.CHOICES,
                help_text=(
                    "What kind of thing the banner is saying. Each edition "
                    "draws it from its own icon set — see gyrinx/site/icons.py."
                ),
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="historicalbanner",
            name="icon",
            field=models.CharField(
                blank=True,
                choices=gyrinx.site.icons.CHOICES,
                help_text=(
                    "What kind of thing the banner is saying. Each edition "
                    "draws it from its own icon set — see gyrinx/site/icons.py."
                ),
                max_length=50,
            ),
        ),
        migrations.RunPython(to_keys, to_bootstrap_classes),
    ]
