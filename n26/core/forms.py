"""The edition's player-facing forms.

The design system's gallery carries a twin of the create form
(n26.designsystem.forms) built on a fixed list so it renders against an
empty database. This is the real one: same fields, same words, but the
gang types are the library's own.
"""

from django import forms

from n26.core.widgets import RichText
from n26.library.models import CampaignType, GangType


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
    # submission and the grid that offers it read the same types. A type turned
    # off is refused on POST too — a hidden card is still an id someone can
    # type. Only this screen narrows: a gang founded before a type was turned
    # off still names it everywhere it is drawn.
    gang_type = forms.ModelChoiceField(
        # Nameless is narrowed away as well as unfoundable. A type whose
        # name is empty — or only whitespace, which draws the same — is an
        # empty card sorting before every real one, and no answer a player
        # could give. The verb refuses to author one
        # (n26.library.authoring.create_gang_type); a row already in a pack
        # is what this excludes.
        queryset=GangType.objects.filter(foundable=True).exclude(name__regex=r"^\s*$"),
        label="Gang type",
        help_text=(
            "What the gang is. It decides who you can hire and what they can carry."
        ),
        error_messages={
            "invalid_choice": "That is not a gang type you can found. Select one of the types shown."
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
        help_text="Shown next to the gang's name wherever it is listed.",
    )

    def gang_type_choices(self):
        """The cards the view draws for ``gang_type``, one per type.

        The same types the field validates against, said once. Each is a
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


class EditGangForm(forms.Form):
    """Editing a standing gang: its name, its colour, and the budget.

    The type is not here. It fixed who could be hired and what the
    founding brought, and those assignments exist — a changed type would
    claim a history the ledger never wrote.

    The budget's floor is the gang's wealth: everything it owns plus the
    cash it holds. A budget below that would say the gang owes money it
    has already spent, and the one hard rule of the money model is that
    the founding budget may not be exceeded. Blank clears the budget —
    the gang spends freely again and its number is its rating. What a
    raised budget leaves over lands in credits, because credits are
    always the budget less everything spent; setting the budget to
    exactly the gang's wealth leaves exactly 0¢ in hand.
    """

    def __init__(self, gang, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gang = gang

    name = forms.CharField(
        max_length=100,
        label="Gang name",
    )
    starting_credits = forms.IntegerField(
        required=False,
        min_value=0,
        label="Credits budget",
        help_text="Leave blank to spend as much as you like.",
    )
    colour = forms.CharField(
        required=False,
        label="Colour",
        help_text="Shown next to the gang's name wherever it is listed.",
    )

    def clean_starting_credits(self):
        budget = self.cleaned_data["starting_credits"]
        # The floor binds the change, not the standing state: granted
        # content can push a gang's worth past its budget, and a rename
        # should not be refused over a budget nobody touched.
        if budget == self.gang.starting_credits:
            return budget
        if budget is not None and budget < self.gang.wealth:
            raise forms.ValidationError(
                f"{self.gang.name} is already worth {self.gang.wealth}¢ — "
                f"the budget must cover what the gang has."
            )
        return budget


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


class FighterNotesForm(forms.Form):
    """The edit page's notes box.

    Optional, because an emptied box is a real answer — it clears the
    notes. What the editor produces is stored as written; sanitising
    happens at render time, which is why nothing here strips tags.
    """

    notes = forms.CharField(required=False, widget=RichText())


class PictureForm(forms.Form):
    """An edit page's picture box, an act of its own.

    ``image`` replaces what is stored, ``remove_image`` alone clears
    it, and a submit carrying neither changes nothing. The ratio is the
    caller's — a model's picture is portrait, a gang's landscape — and
    the upload is brought to it on the way in.
    """

    image = forms.ImageField(required=False)
    remove_image = forms.BooleanField(required=False)

    def __init__(self, *args, ratio, **kwargs):
        super().__init__(*args, **kwargs)
        self.ratio = ratio

    def clean_image(self):
        from n26.core.images import to_shape

        upload = self.cleaned_data["image"]
        return to_shape(upload, self.ratio) if upload else upload


class GangNotesForm(forms.Form):
    """The gang edit page's notes box. One field, one save.

    Optional, because an emptied box is a real answer — it clears the
    notes. Stored as written, sanitised at render. Lore is a form of
    its own, so saving one cannot throw the other away.
    """

    notes = forms.CharField(
        required=False,
        widget=RichText(),
        label="Notes",
        help_text="Shown on the notes page and printed with the gang sheet. Anyone reading the gang can see them.",
    )


class GangLoreForm(forms.Form):
    """The gang edit page's lore box. One field, the notes box's shape."""

    lore = forms.CharField(
        required=False,
        widget=RichText(),
        label="Lore",
        help_text="The gang's story. Shown on the lore page, never printed.",
    )


class FighterLoreForm(forms.Form):
    """The edit page's lore box. One field, the notes box's shape."""

    lore = forms.CharField(required=False, widget=RichText())


def statline_override_form_for(profile):
    """The boxes an owner sets their own model's characteristics in.

    The authoring editor's form over the same statline type, with the
    same refusals — a value has to fit the column, and one box holds one
    characteristic. The two editors write the same kind of short string,
    and disagreeing about what can be stored would trip whoever met both.

    What differs is what an empty box means. Here it is not "no value"
    but "whatever the model's own entry prints", so the printed value is
    what a box suggests and clearing one gives the entry back. Values
    are as free as an author's: ``7++`` is the owner's business, and this
    informs rather than polices.
    """
    from n26.library.forms import statline_form_for

    printed_statline = getattr(profile, "statline", None)
    printed = (
        {stat.field_name: stat.value for stat in printed_statline.ordered_stats()}
        if printed_statline is not None
        else {}
    )

    class StatlineOverrideForm(statline_form_for(profile.statline_type)):
        @classmethod
        def opened_on(cls, miniature, data=None, prefix="statline"):
            """The same form, filled in from what this owner has already set.

            Only the cells they took over are filled: the rest are empty,
            which is how the form says the entry's own value stands.
            """
            initial = {
                override.statline_type_stat.field_name: override.value
                for override in miniature.stat_overrides.select_related(
                    "statline_type_stat__stat"
                )
            }
            return cls(data, initial=initial, prefix=prefix)

        def cells(self, placeholders=None):
            return super().cells(placeholders=placeholders or printed)

        def changes(self):
            """Which cells this submission moves, and what each says.

            One ``(type_stat, value, said)`` per cell that differs from
            what stood — an empty value clears the override and the
            entry prints again. A cleared box that held nothing is not a
            change, and a value retyped as it was is not one either, so
            saving an untouched form moves nothing and the history stays
            quiet. Values are compared in canonical form, the same one
            the override stores, so retyping ``4`` over a stored ``4"``
            is recognised as the same answer.

            ``said`` is the sentence the history keeps: the value the
            card showed — the standing override, or the entry's print —
            then what it becomes. ``Operation.set_stats`` writes both
            the cells and the sentences.
            """
            moved = []
            for type_stat in self.type_stats:
                value = (self.cleaned_data.get(type_stat.field_name) or "").strip()
                if value:
                    value = type_stat.stat.format_value(value)
                before = self.initial.get(type_stat.field_name, "")
                if value == before:
                    continue
                if not value:
                    returns = printed.get(type_stat.field_name) or "—"
                    said = (
                        f"{type_stat.short_name} {before} cleared — "
                        f"{returns} prints again"
                    )
                else:
                    showed = before or printed.get(type_stat.field_name) or "—"
                    said = f"{type_stat.short_name} {showed} → {value}"
                moved.append((type_stat, value, said[:255]))
            return moved

    return StatlineOverrideForm


class RenameFighterForm(forms.Form):
    """The one fact a rename changes.

    Required where the hire form's name is not: "you can name them later"
    is that form's promise, and this form is the later it promised.
    """

    name = forms.CharField(max_length=200, label="Name")


class CampaignForm(forms.Form):
    """Setting a campaign up, and editing one afterwards.

    ``budget`` is how much a gang should be worth to join — its rating, its
    stash and the credits it has not spent. It refuses nobody: a bigger gang
    joins and is marked as over it. The field's ``initial`` is 1000,
    the usual figure, so set-up opens there. Edit supplies the stored value,
    so a campaign that sets none stays blank. Blank is not zero — it means
    no budget at all — and lands as ``budget=None``.
    """

    name = forms.CharField(
        max_length=200,
        label="Campaign name",
        help_text="You can change this later.",
    )
    budget = forms.IntegerField(
        required=False,
        min_value=0,
        initial=1000,
        label="Gang budget",
        help_text=(
            "How much a gang should be worth to join, counting its rating, stash and unspent credits. A bigger gang still joins and is marked. Leave blank to set no budget."
        ),
    )
    summary = forms.CharField(
        required=False,
        label="Summary",
        widget=RichText(),
        help_text="What this campaign is, and anything the players have agreed.",
    )


class FoundCampaignForm(CampaignForm):
    """Setting a campaign up: the standing facts, and what it is founded on.

    The type is asked once. It fixes what every gang that joins is given,
    and those assignments exist from the first join on — so the edit form
    is the plain ``CampaignForm``, and the type is not on it.
    """

    # Only the types anybody may found on: the system pack's, unarchived.
    # A campaign's own additions type lives in a pack the arbitrator owns
    # and is never offered here, or anywhere else.
    campaign_type = forms.ModelChoiceField(
        queryset=CampaignType.objects.selectable().exclude(name__regex=r"^\s*$"),
        label="Campaign type",
        help_text=(
            "What the campaign runs on. Every gang that joins gets what the "
            "type includes."
        ),
        error_messages={
            "invalid_choice": (
                "That is not a campaign type you can found on. Select one of "
                "the types shown."
            ),
            "required": "Select a campaign type.",
        },
    )

    def campaign_type_choices(self):
        """The cards the view draws for ``campaign_type``, one per type.

        The same types the field validates against, said once, in the
        shape ``CreateGangForm.gang_type_choices`` uses: ``checked`` is
        worked out here so a redisplay after a failed submit keeps the
        reader's pick. The line under the name is the type's own help,
        which is the one thing the library says about a type to a reader.
        """
        submitted = str(self["campaign_type"].value() or "")
        return [
            {
                "value": str(row.pk),
                "label": str(row),
                "description": row.library_author_help,
                "checked": str(row.pk) == submitted,
            }
            for row in self.fields["campaign_type"].queryset
        ]


class BringGangForm(forms.Form):
    """A gang from a campaign's table, to put into it.

    The screen draws the list itself, so what the reader is told about it
    is written there. What this holds is the check: whichever gang comes
    back must be one the screen was entitled to offer, which is why
    ``gangs`` has no default — a queryset built without one would accept
    anything.
    """

    gang = forms.ModelChoiceField(
        queryset=None,
        label="Gang",
        # Reachable only by naming a gang the list did not offer, and drawn
        # on a page holding no picker — where Django's own wording would
        # tell the reader to select a valid choice from nothing.
        error_messages={
            "invalid_choice": "That gang is not on this list.",
            "required": "Select a gang to add.",
        },
    )

    def __init__(self, *args, gangs, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gang"].queryset = gangs


class BattleForm(forms.Form):
    """Writing down a battle that was fought: when, and who was in it.

    The gangs offered are the campaign's own, so the form cannot record a
    battle between gangs that were never in it. Nobody has to be named — a
    battle written down before the players are settled is still a date worth
    keeping.
    """

    date = forms.DateField(
        label="Date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    gangs = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label="Participants",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, playing=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Handed in rather than looked up, because a form has no campaign of
        # its own and a queryset built here would offer every gang there is.
        self.fields["gangs"].queryset = playing


class AddToPoolForm(forms.Form):
    """One copy of a pooled asset, to put into a campaign's pool.

    The assets offered are the campaign's catalogue — what its type and
    its additions offer, of the pooled kinds — so the form cannot put a
    Settlement in the pool or an asset the campaign does not deal in. The
    catalogue has no default for the same reason a gang picker has none:
    a queryset built without one would accept anything.
    """

    asset = forms.ModelChoiceField(
        queryset=None,
        label="Asset",
        error_messages={
            "invalid_choice": "That asset is not in this campaign's catalogue.",
            "required": "Select an asset to add.",
        },
    )
    name = forms.CharField(
        required=False,
        max_length=200,
        label="Name for this copy",
        help_text="Optional. Leave blank to use the asset's name.",
    )

    def __init__(self, *args, catalogue, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["asset"].queryset = catalogue


class GrantAssetForm(forms.Form):
    """Which gang playing the campaign a copy goes to."""

    membership = forms.ModelChoiceField(
        queryset=None,
        label="Gang",
        error_messages={
            "invalid_choice": "That gang is not in this campaign.",
            "required": "Select a gang.",
        },
    )

    def __init__(self, *args, playing, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["membership"].queryset = playing
