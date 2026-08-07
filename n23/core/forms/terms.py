"""Edition-specific form helpers.

These live here rather than in ``gyrinx.forms`` because they are typed on — and
semantically about — edition models: a fighter's house, and the per-fighter
terminology overrides. The generic grouping helpers they pair with
(``group_select``, ``group_sorter``) remain in the platform.
"""

from django import forms

from n23.content.models import ContentFighter
from n23.core.models.list import ListFighter


def fighter_group_key(fighter: ContentFighter):
    # Group by house name
    return fighter.house.name


def template_form_with_terms(form: forms.Form, fighter: ListFighter | None = None):
    # Get the correct terminology for this fighter
    terms = dict(
        term_singular=fighter.term_singular if fighter else "Fighter",
        term_singular__lower=fighter.term_singular.lower() if fighter else "fighter",
        term_injury_singular=fighter.term_injury_singular if fighter else "Injury",
        term_injury_singular__lower=fighter.term_injury_singular.lower()
        if fighter
        else "injury",
        term_proximal_demonstrative__lower=fighter.term_proximal_demonstrative.lower()
        if fighter
        else "this fighter",
        term_proximal_demonstrative=fighter.term_proximal_demonstrative
        if fighter
        else "This fighter",
    )
    for field in form.fields.values():
        if hasattr(field, "help_text"):
            field.help_text = field.help_text.format(**terms)
        if hasattr(field, "label"):
            field.label = field.label.format(**terms)
