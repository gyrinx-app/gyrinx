"""The edition's player-facing forms.

The design system's gallery carries a twin of the create form
(n26.designsystem.forms) built on a fixed list so it renders against an
empty database. This is the real one: same fields, same words, but the
gang types are the library's own.
"""

from html.parser import HTMLParser

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from n26.core.colours import GANG_COLOURS
from n26.core.models import Campaign
from n26.core.widgets import CAMPAIGN_SUMMARY_CONFIG, RichText
from n26.library.income import INCOME_HELP
from n26.library.models import AssetType, CampaignType, GangType


def validate_gang_colour(value):
    """Refuse a colour the colour picker does not offer."""
    if value and value not in GANG_COLOURS:
        raise forms.ValidationError("Choose one of the colours shown.")


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
    # Narrowed to the types an author has left foundable and has not
    # archived, and narrowed here rather than where the cards are built, so
    # the field that validates the submission and the grid that offers it
    # read the same types. A type turned off or archived is refused on POST
    # too — a hidden card is still an id someone can type. Only this screen
    # narrows: a gang founded before a type was turned off still names it
    # everywhere it is drawn, exactly as archiving retracts nothing a gang
    # already holds.
    gang_type = forms.ModelChoiceField(
        # Nameless is narrowed away as well as unfoundable. A type whose
        # name is empty — or only whitespace, which draws the same — is an
        # empty card sorting before every real one, and no answer a player
        # could give. The verb refuses to author one
        # (n26.library.authoring.create_gang_type); a row already in a pack
        # is what this excludes.
        queryset=GangType.objects.filter(foundable=True)
        .unarchived()
        .exclude(name__regex=r"^\s*$"),
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
        validators=[validate_gang_colour],
    )

    def __init__(self, *args, include_staged=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Staged types are offered to whoever may see staged content and
        # to nobody else — narrowed here, on the field that validates the
        # submission, for the same reason foundable is: a hidden card is
        # still an id someone can type.
        if not include_staged:
            self.fields["gang_type"].queryset = self.fields["gang_type"].queryset.live()

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


class CloneGangForm(forms.Form):
    """The one fact a copied gang does not inherit."""

    name = forms.CharField(max_length=200, label="Gang name")


class CloneFighterForm(forms.Form):
    """The one fact a copied model may change."""

    name = forms.CharField(max_length=200, label="Model name")


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
        max_length=50,
        label="Colour",
        help_text="Shown next to the gang's name wherever it is listed.",
        validators=[validate_gang_colour],
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


class BaseRatingForm(forms.Form):
    rating = forms.IntegerField(
        label="Base rating",
        min_value=-(2**31) + 1,
        max_value=2**31 - 1,
        help_text="Equipment and advancements add to this figure. Credits paid stay the same.",
    )


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


#: How tall the notes editor on a model's page is, in pixels. Notes are a
#: line or two most of the time and the boxes under them are what the page
#: is for, so the editor is short and scrolls; what is written has no limit.
NOTES_EDITOR_HEIGHT = 160


class CreditsForm(forms.Form):
    """Credits added to a gang or removed from it by hand."""

    ADD = "add"
    REMOVE = "remove"

    direction = forms.ChoiceField(
        choices=[(ADD, "Add credits"), (REMOVE, "Remove credits")],
        initial=ADD,
        label="Add or remove",
    )
    #: Far above any gang's credits, and far below what the ledger's
    #: integer column holds.
    amount = forms.IntegerField(min_value=1, max_value=1_000_000, label="Credits")
    note = forms.CharField(
        max_length=255,
        required=False,
        label="Note",
        help_text="Optional. Shown in the gang's history.",
    )

    def signed_amount(self):
        """The change to the gang's credits: positive adds, negative removes."""
        amount = self.cleaned_data["amount"]
        return -amount if self.cleaned_data["direction"] == self.REMOVE else amount


class FighterNotesForm(forms.Form):
    """The edit page's notes box.

    Optional, because an emptied box is a real answer — it clears the
    notes. What the editor produces is stored as written; sanitising
    happens at render time, which is why nothing here strips tags.
    """

    notes = forms.CharField(
        required=False,
        widget=RichText(attrs={"rows": 4}, height=NOTES_EDITOR_HEIGHT),
    )


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


class _SummaryImages(HTMLParser):
    """Image sources in submitted HTML, without fetching any address."""

    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.sources.extend(value or "" for name, value in attrs if name == "src")


class CampaignForm(forms.Form):
    """Setting a campaign up, and editing one afterwards.

    ``budget`` is what a gang should be worth to join — its rating, its
    stash and the credits it has not spent. It refuses nobody: a bigger gang
    joins and wears an Over budget badge. The field's ``initial`` is 1000,
    the usual figure, so set-up opens there. Edit supplies the stored value,
    so a campaign that sets none stays blank. Blank is not zero — it means
    no budget at all — and lands as ``budget=None``.
    """

    name = forms.CharField(
        max_length=200,
        label="Campaign name",
    )
    budget = forms.IntegerField(
        required=False,
        min_value=0,
        initial=1000,
        label="Gang budget",
        help_text=(
            "What a gang should be worth to join, counting its rating, stash "
            "and unspent credits. A gang worth more than this can still join. "
            "Over-budget warnings appear only while the campaign status is "
            "Pre-campaign. Leave blank for no budget."
        ),
    )
    summary = forms.CharField(
        required=False,
        label="Summary",
        widget=RichText(mce_attrs=CAMPAIGN_SUMMARY_CONFIG),
        help_text=(
            "What this campaign is, and anything the players have agreed. "
            "Shown at the top of the campaign's page. Paste an image, upload one "
            "with the image button, or enter a public image URL."
        ),
    )

    def clean_summary(self):
        summary = self.cleaned_data["summary"]
        images = _SummaryImages()
        images.feed(summary)
        if any(
            source.strip().lower().startswith(("data:", "blob:"))
            for source in images.sources
        ):
            raise forms.ValidationError(
                "Finish uploading each image before saving, or remove it."
            )
        return summary


class EditCampaignForm(CampaignForm):
    status = forms.ChoiceField(
        choices=Campaign.Status.choices,
        required=False,
        label="Status",
        help_text="Set In progress when the campaign starts. Over-budget warnings appear only in Pre-campaign.",
    )


def _foundable_campaign_types(include_staged=False):
    """The types anybody may found on: the system pack's, unarchived, live
    unless the reader may see staged content, and never a campaign's own
    type — that one lives in a pack the arbitrator owns and is filtered out
    besides, so a system-pack row that came to be a campaign's own would
    still stay off the list."""
    return (
        CampaignType.objects.selectable(include_staged=include_staged)
        .filter(additions_to__isnull=True)
        .exclude(name__regex=r"^\s*$")
        .select_related("built_ins")
        .prefetch_related("asset_types")
    )


class FoundCampaignForm(CampaignForm):
    """Setting a campaign up: the standing facts, and what it is founded on.

    The type is asked once. It fixes what every gang that joins is given,
    and those assignments exist from the first join on — so the edit form
    is the plain ``CampaignForm``, and the type is not on it.
    """

    campaign_type = forms.ModelChoiceField(
        queryset=_foundable_campaign_types(include_staged=True),
        label="Campaign type",
        help_text=("Use pre-built campaign setups to get started quickly."),
        error_messages={
            "invalid_choice": (
                "That is not a campaign type you can found on. Select one of "
                "the types shown."
            ),
            "required": "Select a campaign type.",
        },
    )

    def __init__(self, *args, include_staged=False, **kwargs):
        super().__init__(*args, **kwargs)
        # The same narrowing as the cards, on the field that validates the
        # submission: a staged type is founded on only by a reader it was
        # offered to. Narrowed here, as the gang type is, so the two forms
        # read the same way round.
        if not include_staged:
            self.fields["campaign_type"].queryset = self.fields[
                "campaign_type"
            ].queryset.live()

    def campaign_type_choices(self):
        """The cards the view draws for ``campaign_type``, one per type.

        The same types the field validates against, said once, in the
        shape ``CreateGangForm.gang_type_choices`` uses: ``checked`` is
        worked out here so a redisplay after a failed submit keeps the
        reader's pick. Each card carries what founding on the type gives —
        its description, its asset types, what every gang starts with, and
        any campaign-wide rules — so the picker reads as choosing a
        rulebook rather than a name.
        """
        from n26.core.campaigns import summarise_campaign_type

        submitted = str(self["campaign_type"].value() or "")
        return [
            summarise_campaign_type(row, checked=str(row.pk) == submitted)
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


class StakeChoiceField(forms.ModelChoiceField):
    """A campaign asset, named with the gang holding it now."""

    def label_from_instance(self, obj):
        if obj.held:
            return f"{obj} (held by {obj.holder.gang.name})"
        return f"{obj} (not held)"


def stakes_offered(battle):
    """The campaign assets a battle could stake: those its participants
    hold now, and whatever it already stakes. None for a new battle."""
    from n26.core.models import CampaignAsset

    if battle is None:
        return None
    return (
        CampaignAsset.objects.filter(campaign_id=battle.campaign_id)
        .filter(
            Q(
                holder__left__isnull=True,
                holder__gang__in=battle.gangs.values("pk"),
            )
            | Q(pk=battle.stake_id)
        )
        .select_related("asset__asset_type", "holder__gang")
    )


def stake_noun(stakes):
    """What the stake is called: the asset type's own word where every
    asset on offer is of one type, and "Asset" otherwise."""
    labels = {stake.asset.asset_type.label_singular for stake in stakes}
    if len(labels) != 1:
        return "Asset"
    label = labels.pop()
    return label[:1].upper() + label[1:]


class BattleForm(forms.Form):
    """A battle's identity and participants, and on edit its outcome.

    A new battle carries no outcome fields: players add it before the
    game, choose crews from its page, and record the outcome afterwards
    by editing it.
    """

    scenario = forms.CharField(max_length=200, label="Scenario")

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
    result = forms.ChoiceField(label="Outcome")
    winners = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        label="Winning gangs",
        widget=forms.CheckboxSelectMultiple,
    )
    stake = StakeChoiceField(
        queryset=None,
        required=False,
        empty_label="Nothing staked",
    )
    stake_awarded_to = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="Stays with the gang that held it before the battle",
    )
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, playing, battle=None, **kwargs):
        from n26.core.campaigns import stake_came_from
        from n26.core.models import Battle

        super().__init__(*args, **kwargs)
        self.fields["gangs"].queryset = playing
        self.fields["winners"].queryset = playing
        for name in ("gangs", "winners"):
            self.fields[name].widget.attrs["class"] = (
                "size-4 shrink-0 accent-[var(--color-accent)] focus-ring"
            )
        self.fields["result"].choices = Battle.Result.choices
        self.fields["result"].initial = Battle.Result.NOT_RECORDED
        if battle is None:
            for name in ("revision", "result", "winners"):
                del self.fields[name]
        else:
            self.initial.update(
                scenario=battle.scenario,
                date=battle.date.isoformat(),
                gangs=[gang.pk for gang in battle.gangs.all()],
                result=battle.result,
                winners=[gang.pk for gang in battle.winners.all()],
                revision=battle.revision,
                stake=battle.stake_id,
                stake_awarded_to=battle.stake_awarded_to_id,
            )
        stakes = stakes_offered(battle)
        if not stakes:
            # Nothing to stake: the fields go, and saving leaves the
            # battle's stake as it is.
            del self.fields["stake"]
            del self.fields["stake_awarded_to"]
            self.stake_label = ""
            return
        self.fields["stake"].queryset = stakes
        # The gang that held it before the battle is the empty choice, so it
        # is not offered again by name.
        came_from = stake_came_from(battle)
        awardable = self._awardable(playing, battle)
        if came_from is not None:
            awardable = awardable.exclude(pk=came_from.pk)
            self.fields["stake_awarded_to"].empty_label = f"Stays with {came_from.name}"
            if battle.stake_awarded_to_id == came_from.pk:
                self.initial["stake_awarded_to"] = None
        self.fields["stake_awarded_to"].queryset = awardable
        from n26.core.campaigns import a_stake

        noun = stake_noun(stakes)
        self.stake_label = f"{noun} staked"
        self.fields["stake"].label = self.stake_label
        self.fields["stake"].error_messages["invalid_choice"] = (
            f"Select {a_stake(noun)} a participant holds."
        )
        self.fields["stake_awarded_to"].label = f"{noun} goes to"
        self.fields["stake_awarded_to"].error_messages["invalid_choice"] = (
            f"Select a participant to give the {noun[:1].lower() + noun[1:]} to."
        )

    def _awardable(self, playing, battle):
        """The gangs the stake can go to: the participants being saved,
        so a gang added in this save can win it. Saving checks again."""
        if not self.is_bound:
            return battle.gangs.order_by("name")
        try:
            return playing.filter(pk__in=self.data.getlist("gangs")).order_by("name")
        except ValidationError, ValueError:
            return playing.none()

    def clean(self):
        from n26.core.models import Battle

        cleaned = super().clean()
        if all(field in cleaned for field in ("result", "gangs", "winners")):
            try:
                Battle.validate_outcome(
                    result=cleaned["result"],
                    gangs=cleaned["gangs"],
                    winners=cleaned["winners"],
                )
            except forms.ValidationError as exc:
                self.add_error(None, exc)
        return cleaned


class AddAssetForm(forms.Form):
    """Assets to add to a campaign.

    The assets offered are the ones the campaign deals in — those of the
    Holding asset types of its type and of its own additions — so the form
    cannot add a Settlement or an asset of another campaign type.
    ``offered`` has no default for the same reason a gang picker has none:
    a queryset built without one would accept anything.
    """

    asset = forms.ModelMultipleChoiceField(
        queryset=None,
        label="Assets",
        error_messages={
            "invalid_choice": "That asset is not one this campaign deals in.",
            "required": "Select one or more assets to add.",
        },
    )
    request_key = forms.UUIDField(required=False)
    name = forms.CharField(
        required=False,
        max_length=200,
        label="Name in this campaign",
        help_text="Optional. Leave blank to use the asset's own name.",
    )
    income = forms.IntegerField(
        required=False,
        min_value=0,
        label="Income override",
        max_value=2147483647,
        help_text="Optional. Leave blank to use each asset's catalogue income. Applies to every selected asset.",
    )

    def __init__(self, *args, offered, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["asset"].queryset = offered
        if self.is_bound:
            for asset in offered.filter(pk__in=self["asset"].value() or []):
                self.fields[f"name_{asset.pk}"] = forms.CharField(
                    required=False, max_length=200, label=f"Rename {asset}"
                )
        from uuid import uuid4

        self.fields["request_key"].initial = uuid4

    def clean(self):
        from uuid import uuid4

        data = super().clean()
        data["request_key"] = data.get("request_key") or uuid4()
        assets = data.get("asset")
        if assets is not None and len(assets) > 1 and data.get("name"):
            self.add_error(
                "name", "Select one asset to give it a custom name in this campaign."
            )
        data["names"] = {
            str(asset.pk): data.get(f"name_{asset.pk}", "") for asset in assets or []
        }
        if assets is not None and len(assets) > 1 and any(data["names"].values()):
            self.add_error(
                "name", "Select one asset to give it a custom name in this campaign."
            )
        return data


class AssignAssetForm(forms.Form):
    """Which gang playing the campaign an asset goes to."""

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


# --- What the arbitrator adds ------------------------------------------------
#
# Small forms for the arbitrator's own controls on the campaign page: each
# writes one kind of thing into the campaign's pack through
# ``CampaignOperation``. None of them asks what an asset does beyond its
# income — an asset here has a name, its words and that figure, and
# nothing else.


class AddAssetTypeForm(forms.Form):
    """A new asset type for one campaign: its label and its ownership."""

    label_singular = forms.CharField(
        max_length=200,
        label="Label",
        help_text='What one of these is called, e.g. "Territory".',
    )
    label_plural = forms.CharField(
        required=False,
        max_length=200,
        label="Plural label",
        help_text=(
            'What several of them are called, e.g. "Territories". Leave '
            "blank and an s is added."
        ),
    )
    ownership = forms.ChoiceField(
        choices=AssetType.Ownership.choices,
        initial=AssetType.Ownership.HOLDING,
        label="Ownership",
        widget=forms.RadioSelect,
        error_messages={"required": "Select Inherent or Transferable."},
    )


class NewAssetForm(forms.Form):
    """A new asset under one of the campaign's asset types.

    ``asset_types`` are the asset types the campaign deals in — the shared
    type's and the campaign's own — and have no default for the reason
    every picker here has none: a queryset built without one would accept
    any asset type at all.
    """

    asset_type = forms.ModelChoiceField(
        queryset=None,
        label="Asset type",
        error_messages={
            "invalid_choice": "That is not an asset type this campaign deals in.",
            "required": "Select an asset type.",
        },
    )
    name = forms.CharField(max_length=200, label="Name")
    annotation = forms.CharField(
        required=False,
        max_length=200,
        label="Annotation",
        help_text="Optional. Shown in brackets after the name.",
    )
    income = forms.IntegerField(
        required=False,
        min_value=0,
        initial=0,
        label="Income",
        max_value=2147483647,
        help_text=INCOME_HELP,
    )

    def __init__(self, *args, asset_types, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["asset_type"].queryset = asset_types


class AddCounterForm(forms.Form):
    """A counter every gang in the campaign tracks, and where it opens."""

    name = forms.CharField(
        max_length=200,
        label="Name",
        help_text='e.g. "Reputation".',
    )
    opening = forms.IntegerField(
        min_value=0,
        initial=0,
        label="Starting value",
    )


class AddLabelForm(forms.Form):
    """A question every gang settles by picking one option."""

    name = forms.CharField(
        max_length=200,
        label="Name",
        help_text='What the choice is called, e.g. "Faction".',
    )
    options = forms.CharField(
        label="Options",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text='One option per line, e.g. "Law Abiding" then "Outlaw".',
    )

    def clean_options(self):
        """The options as a list: blank lines dropped, each one stripped,
        and no two the same however they are cased — the library keeps
        them apart by name, and a player picking between two options
        that read alike has nothing to go on."""
        lines = [line.strip() for line in self.cleaned_data["options"].splitlines()]
        options = [line for line in lines if line]
        if not options:
            raise forms.ValidationError("Give at least one option, one per line.")
        seen = set()
        for option in options:
            if option.casefold() in seen:
                raise forms.ValidationError(f"{option} is listed twice.")
            seen.add(option.casefold())
        if any(len(option) > 200 for option in options):
            raise forms.ValidationError("An option can be at most 200 characters.")
        return options


# --- Asset tables --------------------------------------------------------------
#
# The forms behind the two Roll dialogs on the campaign page and the
# arbitrator's Tables pages. Every picker here takes its queryset from the
# view, for the reason every campaign picker does: one built without it
# would accept a table or an asset the campaign has no business with.


class RollAssetForm(forms.Form):
    """A roll on one of the tables offered: which table, and the roll
    where the reader made it themselves rather than here.

    Whether an entered roll is one the die can make is the operation's
    question, since only it knows which table's die is being rolled by
    the time both fields are read.
    """

    table = forms.ModelChoiceField(
        queryset=None,
        label="Table",
        error_messages={
            "invalid_choice": "That table is not available here.",
            "required": "Select a table.",
        },
    )
    rolled = forms.IntegerField(
        required=False,
        min_value=1,
        label="Your own roll",
        help_text="Optional. Leave blank and the roll is made for you.",
    )

    def __init__(self, *args, tables, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["table"].queryset = tables
        # One table offered is the table: nothing to select, so the field
        # settles on it whether or not the form names it.
        offered = list(tables)
        if len(offered) == 1:
            self.fields["table"].required = False
            self.only_table = offered[0]
        else:
            self.only_table = None

    def clean_table(self):
        return self.cleaned_data.get("table") or self.only_table


class PoolRollForm(RollAssetForm):
    """Generate several unclaimed assets from one selected table."""

    count = forms.IntegerField(
        required=True,
        min_value=1,
        max_value=100,
        label="Number to roll",
        help_text="Choose how many to add to the unclaimed pool, up to 100 at a time.",
        initial=1,
    )
    request_key = forms.UUIDField(required=False)

    def __init__(self, *args, **kwargs):
        from uuid import uuid4

        super().__init__(*args, **kwargs)
        # Missing quantity is the single-roll request contract. An explicit
        # blank remains a required error.
        if self.is_bound and "count" not in self.data:
            self.data = self.data.copy()
            self.data["count"] = 1
        self.fields["request_key"].initial = uuid4
        self.fields[
            "rolled"
        ].help_text = "Optional. Enter a dice roll you have already made."

    def clean(self):
        from uuid import uuid4

        data = super().clean()
        data["request_key"] = data.get("request_key") or uuid4()
        if (data.get("count") or 0) > 1 and data.get("rolled") is not None:
            self.add_error("rolled", "Set the number to 1 to use your own roll.")
        return data


class OpenTablesForm(forms.Form):
    """Which of the tables offered every gang in the campaign may roll on.
    Unticked is closed; the view reads the difference from what stood
    before."""

    open = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        error_messages={
            "invalid_choice": "You cannot make that table available here.",
        },
    )

    def __init__(self, *args, tables, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["open"].queryset = tables


class NewTableForm(forms.Form):
    """A new asset table for one campaign: what it lists, its name and
    its die."""

    asset_type = forms.ModelChoiceField(
        queryset=None,
        label="Asset type",
        error_messages={
            "invalid_choice": "That is not an asset type this campaign deals in.",
            "required": "Select an asset type.",
        },
    )
    name = forms.CharField(max_length=200, label="Name")
    dice = forms.ChoiceField(
        required=False,
        label="Dice",
        help_text="The table's die. Choose Not rolled for a plain list.",
    )

    def __init__(self, *args, asset_types, **kwargs):
        from n26.library.models import Dice

        super().__init__(*args, **kwargs)
        self.fields["asset_type"].queryset = asset_types
        self.fields["dice"].choices = [("", "Not rolled"), *Dice.choices]


class TableEntryForm(forms.Form):
    """One more asset on a table: which, and on a rolled table the band
    of rolls that lands on it. Whether the band fits the table's die is
    the table's own check, said above the entries."""

    asset = forms.ModelChoiceField(
        queryset=None,
        label="Asset",
        error_messages={
            "invalid_choice": "That asset is not one this campaign deals in.",
            "required": "Select an asset.",
        },
    )
    roll_low = forms.IntegerField(
        required=False,
        min_value=1,
        label="Lowest roll",
        help_text="The lowest roll that lands here, on a rolled table.",
    )
    roll_high = forms.IntegerField(
        required=False,
        min_value=1,
        label="Highest roll",
        help_text=(
            "The highest roll that lands here. Leave blank for a band of one roll."
        ),
    )

    def __init__(self, *args, offered, table=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["asset"].queryset = offered
        self.table = table

    def clean(self):
        """A band's ends are rolls the table's die can make.

        The library checks that a band has both ends and runs upwards;
        the column is a small integer, so a number nothing could roll has
        to be refused here, in words, before it reaches the database.
        """
        from n26.library.models import Dice

        cleaned = super().clean()
        if self.table is None or not self.table.dice:
            return cleaned
        dice = Dice(self.table.dice)
        faces = Dice.rolls(dice)
        for name in ("roll_low", "roll_high"):
            roll = cleaned.get(name)
            if roll is not None and roll not in faces:
                self.add_error(name, f"You cannot roll {roll} on a {dice.label}.")
        return cleaned


class CampaignLogFilterForm(forms.Form):
    """URL-backed filters over complete campaign acts."""

    player = forms.ChoiceField(required=False, label="Player or arbitrator")
    gang = forms.ChoiceField(required=False, label="Gang")
    kind = forms.ChoiceField(required=False, label="Action type")
    from_date = forms.DateField(required=False, label="From date")
    to_date = forms.DateField(required=False, label="To date")

    def __init__(self, *args, players, gangs, kinds, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["player"].choices = [("", "Everyone"), *players]
        self.fields["gang"].choices = [("", "All gangs"), *gangs]
        self.fields["kind"].choices = [("", "All action types"), *kinds]

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("from_date"), cleaned.get("to_date")
        if start and end and end < start:
            self.add_error("to_date", "Choose an end date on or after the start date.")
        return cleaned


class CampaignRollForm(forms.Form):
    """A generated or physical roll, attributed only within its campaign."""

    request_key = forms.UUIDField(
        widget=forms.HiddenInput,
        error_messages={
            "invalid": "This form is not recognised. Reload this page and try again.",
            "required": "Reload this page before rolling.",
        },
    )
    reason = forms.CharField(max_length=200)
    dice = forms.ChoiceField(initial="d6", widget=forms.RadioSelect)
    source = forms.ChoiceField(
        choices=[("generated", "Generate a roll"), ("manual", "I already rolled")],
        initial="generated",
        widget=forms.RadioSelect,
    )
    count = forms.IntegerField(required=False, initial=1, min_value=1, max_value=20)
    rolled = forms.IntegerField(required=False, min_value=1, max_value=1320)
    modifier_application = forms.ChoiceField(required=False, initial="total")
    modifier = forms.IntegerField(
        required=False, min_value=-2147483648, max_value=2147483647
    )
    gang = forms.ModelChoiceField(
        queryset=None, required=False, empty_label="No related gang"
    )
    battle = forms.ModelChoiceField(
        queryset=None, required=False, empty_label="No related battle"
    )

    def __init__(self, *args, campaign, **kwargs):
        from uuid import uuid4

        from n26.core.models import CampaignRoll, Gang

        super().__init__(*args, **kwargs)
        self.fields["dice"].choices = CampaignRoll.Dice.choices
        self.fields[
            "modifier_application"
        ].choices = CampaignRoll.ModifierApplication.choices
        self.fields["request_key"].initial = uuid4()
        self.fields["gang"].queryset = Gang.objects.filter(
            campaign_memberships__campaign=campaign,
            campaign_memberships__left__isnull=True,
            archived=False,
        ).order_by("name")
        self.fields["battle"].queryset = campaign.battles.order_by("-date", "-created")

    def clean(self):
        from n26.core.models import CampaignRoll

        cleaned = super().clean()
        cleaned["modifier"] = cleaned.get("modifier") or 0
        cleaned["count"] = cleaned.get("count") if self["count"].value() else 1
        cleaned["modifier_application"] = cleaned.get("modifier_application") or "total"
        if cleaned.get("source") == CampaignRoll.Source.MANUAL:
            dice, count = cleaned.get("dice"), cleaned.get("count")
            if (
                dice
                and count
                and not CampaignRoll.valid_total(dice, count, cleaned.get("rolled"))
            ):
                message = (
                    "Enter a D66 result with both digits from 1 to 6."
                    if dice == "d66" and count == 1
                    else f"Enter a possible total for {count} × {dice.upper()}."
                )
                self.add_error("rolled", message)
        elif cleaned.get("rolled") is not None:
            self.add_error("rolled", "Leave the result blank to generate a roll.")
        return cleaned


class CampaignRollOutcomeForm(forms.Form):
    outcome = forms.CharField(max_length=512, required=False, widget=forms.Textarea)


class IncomeValueForm(forms.Form):
    value = forms.IntegerField(label="Income", min_value=0)


class CounterAdjustmentForm(forms.Form):
    """A signed change to the recorded part of a counter."""

    def __init__(self, *args, maximum, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["change"] = forms.IntegerField(
            label="Amount",
            min_value=-maximum,
            max_value=maximum,
            help_text="Use a positive number to add or a negative number to remove. Recorded values stop at zero.",
        )

    def clean_change(self):
        change = self.cleaned_data["change"]
        if not change:
            raise forms.ValidationError("Enter an amount to add or remove.")
        return change
