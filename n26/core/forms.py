"""The edition's player-facing forms.

The design system's gallery carries a twin of the create form
(n26.designsystem.forms) built on a fixed list so it renders against an
empty database. This is the real one: same fields, same words, but the
gang types are the library's rows.
"""

from django import forms

from n26.library.models import GangType


class CreateGangForm(forms.Form):
    """Founding a gang: what it is called, what it is, and two optional
    things.

    ``starting_credits`` is the interesting one. Blank does not mean
    zero and does not mean "use a default" — it means no limit, which
    is how people play a first game before anyone has agreed a budget.
    So it is ``required=False`` with no ``initial``, and blank lands as
    ``starting_credits=None`` on the gang.
    """

    name = forms.CharField(
        max_length=200,
        label="Gang name",
        help_text="You can change this later.",
    )
    gang_type = forms.ModelChoiceField(
        queryset=GangType.objects.all(),
        label="Gang type",
        help_text=(
            "What the gang is, which fixes who you can hire and what they may carry."
        ),
    )
    starting_credits = forms.IntegerField(
        required=False,
        min_value=0,
        label="Starting credits",
        help_text="Leave blank to spend as much as you like.",
    )
    colour = forms.CharField(
        required=False,
        max_length=50,
        label="Colour",
        help_text="Shown against the gang wherever it is listed.",
    )

    def gang_type_choices(self):
        """``(value, label)`` pairs for the view component's select —
        the same rows the field validates against, said once."""
        return [(str(row.pk), str(row)) for row in self.fields["gang_type"].queryset]
