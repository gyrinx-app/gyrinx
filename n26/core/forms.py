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
    # Narrowed to the types an author has left foundable, and narrowed here
    # rather than where the cards are built, so the field that validates the
    # submission and the grid that offers it read the same rows. A type turned
    # off is refused on POST too — a hidden card is still an id someone can
    # type. Only this screen narrows: a gang founded before a type was turned
    # off still names it everywhere it is drawn.
    gang_type = forms.ModelChoiceField(
        queryset=GangType.objects.filter(foundable=True),
        label="Gang type",
        help_text=(
            "What the gang is, which fixes who you can hire and what they may carry."
        ),
        error_messages={
            "invalid_choice": "That is not a gang type you can found. Pick one of those shown."
        },
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
        """The cards the view draws for ``gang_type``, one per row.

        The same rows the field validates against, said once. Each is a
        dict rather than a ``(value, label)`` pair because a card shows
        more than a select option can: the type's badge, and the budget
        it founds a gang with. ``checked`` is computed here and not in
        the template — a redisplay after a failed submit has to re-check
        whatever came back, and comparing a submitted string to a primary
        key is the kind of thing a template does wrong quietly.
        """
        submitted = str(self["gang_type"].value() or "")
        return [
            {
                "value": str(row.pk),
                "label": str(row),
                "icon": row.artwork,
                "description": _founding_budget(row.starting_credits),
                "checked": str(row.pk) == submitted,
            }
            for row in self.fields["gang_type"].queryset
        ]


def _founding_budget(credits):
    """The line under a gang type's name on the create form.

    Blank starting credits is not zero and not a default — it means the
    game's usual budget applies — so a type that states nothing says
    nothing rather than claiming a number it does not have.
    """
    if credits is None:
        return ""
    return f"Founding budget {credits:,}¢"


class HireFighterForm(forms.Form):
    """The one real field on the hire screen.

    Which profile — and which of its options — is not a field here: every
    Hire button in the picker is the form's submit, carrying the profile,
    and the option inputs are scoped per-row by the picker itself. The
    view reads those directly, because their names are composed from the
    rows on the page rather than declared anywhere a Form could know.
    """

    name = forms.CharField(
        max_length=200,
        required=False,
        label="Name",
        help_text="Optional — you can name them later.",
    )
