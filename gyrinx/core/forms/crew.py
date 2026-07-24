"""Forms for battle crews (#1346).

Building a crew is two steps. :class:`CrewSetupForm` is the setup screen — the
selection method's configuration (pick count / draw dice) and the per-fighter
eligibility table; the method itself is URL-driven (see ``views/crew.py``) and
the form prunes itself to the fields that method uses. :class:`CrewForm` is the
selection screen — just the fighters chosen from the pool setup defined. Keeping
config and picks on separate steps is what makes a contradictory recipe, such as
an entirely random selection that also names fighters, impossible to express.
The extras form adds credit-consuming line items. None of these touch the gang's
canonical cost, credits, or audit — a crew is a virtual overlay.
"""

from django import forms
from django.utils.html import format_html

from gyrinx.core.handlers.crew import (
    CREW_ALWAYS_INCLUDED,
    CREW_ELIGIBILITY_STATES,
    CREW_ELIGIBLE,
    CREW_NOT_ELIGIBLE,
    always_included_crew_fighters,
    compute_crew_eligibility,
    eligible_crew_fighters,
    fighter_crew_status_badges,
    with_crew_cost_data,
)
from gyrinx.core.models.crew import (
    Crew,
    CrewLineItem,
    CrewMember,
    build_selection_spec,
    crew_fighter_cost,
    split_selection_spec,
)
from gyrinx.core.models.list import ListFighter

# The implicit "everything the fighter owns" card, which has no row of its own.
# Same wording as the fighter card's set switcher.
DEFAULT_SET_LABEL = "Default (all equipment)"

# The dice offered for a random draw. The model still stores/validates any
# ``DX`` for data integrity; the UI offers the ones scenarios actually use.
DICE_CHOICES = [("", "No dice"), ("D3", "D3"), ("D6", "D6")]

# One sentence per method, shown above the fields it applies to.
METHOD_INTRO = {
    Crew.CUSTOM: "You choose which fighters take part.",
    Crew.RANDOM: (
        "The fighters are drawn at random when the crew is rolled at battle start."
    ),
    Crew.HYBRID: (
        "You choose some of the fighters; the rest are drawn at random when the "
        "crew is rolled at battle start."
    ),
}

CUSTOM_COUNT_HELP = {
    Crew.CUSTOM: (
        "The number in brackets, e.g. Custom Selection (10). Leave blank if the "
        "scenario shows no number — the whole gang may take part."
    ),
    Crew.HYBRID: (
        "Hybrid Selection (X+Y): you choose the first number, the second is "
        "drawn at random."
    ),
}

RANDOM_GROUP = {
    Crew.RANDOM: (
        "How many fighters are drawn at random",
        "The number in brackets, e.g. Random Selection (D3+4).",
    ),
    Crew.HYBRID: (
        "How many are drawn at random",
        "Hybrid Selection (X+Y): you choose the first number, the second is "
        "drawn at random.",
    ),
}


class CrewFighterChoiceField(forms.ModelMultipleChoiceField):
    """Fighter checkboxes labelled ``**name** · category (rating)`` instead of
    the raw ``__str__``. Load the queryset via
    :func:`~gyrinx.core.handlers.crew.with_crew_cost_data` — the label costs each
    fighter with ``crew_fighter_cost``, which needs the stash equipment
    prefetched alongside the rest, or the list costs a query per fighter."""

    def label_from_instance(self, obj):
        return format_html(
            "<strong>{}</strong> · {} ({}¢)",
            obj.name,
            obj.content_fighter.get_category_display(),
            crew_fighter_cost(obj),
        )


def _with_crew_cost(fighter):
    """Stamp a fighter with its crew cost so the template can read it directly."""
    fighter.crew_cost = crew_fighter_cost(fighter)
    return fighter


def equipment_set_field_name(fighter_id):
    """The per-fighter equipment-set field on :class:`CrewForm`."""
    return f"equipment_set_{fighter_id}"


class CrewEquipmentSetField(forms.ModelChoiceField):
    """One fighter's "which card does this model use?" picker.

    Custom Selection lets the player choose the equipment set each chosen model
    brings, so the crew form carries one of these per eligible fighter that has
    named sets. The empty choice is the implicit Default card.

    The choices are set from the sets already loaded by ``with_related_data()``
    rather than left to ``ModelChoiceIterator``, which calls
    ``queryset.iterator()`` — that bypasses the prefetch cache and would cost a
    query per fighter on a form that lists the whole gang. The queryset is still
    the fighter's own sets, so validation can't accept another fighter's card.
    """

    def __init__(self, *, fighter, sets, **kwargs):
        super().__init__(
            queryset=fighter.equipment_sets.all(),
            required=False,
            empty_label=DEFAULT_SET_LABEL,
            label=f"Equipment set for {fighter.name}",
            widget=forms.Select(
                attrs={
                    "class": "form-select form-select-sm",
                    "aria-label": f"Equipment set for {fighter.name}",
                }
            ),
            **kwargs,
        )
        self.choices = [("", self.empty_label)] + [(s.pk, s.name) for s in sets]


class CrewForm(forms.Form):
    """The crew **selection** screen — choosing the fighters, after setup.

    Setup (method, config, eligibility) is already done and stored on the crew;
    this step just picks the fighters for Custom and Hybrid crews from the
    eligible pool that setup defined. Random crews name nobody here — they are
    drawn when the crew is confirmed — so no checkboxes are shown for them. Each
    chosen fighter with named equipment sets also picks which one they bring. The
    view hands the cleaned picks to ``handle_crew_recipe_save`` alongside the
    crew's stored method and config.
    """

    chosen_fighters = CrewFighterChoiceField(
        queryset=ListFighter.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Fighters",
        help_text="Choose the fighters for this crew.",
    )

    def __init__(self, *args, crew=None, gang=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.crew = crew
        # Gang and the whole recipe come from the stored crew — setup wrote them.
        self.gang = gang or (crew.list if crew is not None else None)
        self.method = getattr(crew, "selection_method", None) or Crew.CUSTOM
        self.custom_count = getattr(crew, "custom_count", None)
        self.included_categories = getattr(crew, "included_categories", None) or []
        self.eligibility_overrides = getattr(crew, "eligibility_overrides", None) or {}
        self.method_intro = METHOD_INTRO[self.method]

        # Loaded with the crew-cost data so the checkbox labels (category + cost)
        # and each fighter's equipment sets render without a query per fighter.
        self.eligible = (
            with_crew_cost_data(
                eligible_crew_fighters(
                    self.gang,
                    included=self.included_categories,
                    overrides=self.eligibility_overrides,
                )
            )
            if self.gang is not None
            else ListFighter.objects.none()
        )

        # Fighters that join regardless of the method (hired guns et al., or any
        # marked "included" on setup). Shown read-only on the selection screen so
        # the player can see who's coming on top of their picks / the draw.
        self.always_included_fighters = (
            [
                _with_crew_cost(fighter)
                for fighter in with_crew_cost_data(
                    always_included_crew_fighters(
                        self.gang,
                        included=self.included_categories,
                        overrides=self.eligibility_overrides,
                    )
                )
            ]
            if self.gang is not None
            else []
        )

        # Random names nobody here; Custom and Hybrid pick from the pool.
        self.shows_picks = self.method in (Crew.CUSTOM, Crew.HYBRID)
        if not self.shows_picks:
            del self.fields["chosen_fighters"]
            self.eligible_fighters = []
            self.eligible_count = self.eligible.count()
        else:
            picks_field = self.fields["chosen_fighters"]
            picks_field.queryset = self.eligible
            # Evaluate the eligible fighters once, through the field's own
            # queryset: the checkboxes, the count, and the equipment-set selects
            # below then all read from that single load.
            self.eligible_fighters = list(picks_field.queryset)
            self.eligible_count = len(self.eligible_fighters)
            # A fighter with named sets gets a select for which one they bring;
            # a fighter with only the Default card has nothing to choose.
            for fighter in self.eligible_fighters:
                sets = list(fighter.equipment_sets.all())
                if not sets:
                    continue
                # Start from the set the fighter is already using; an existing
                # member's own choice overrides this below.
                self.fields[equipment_set_field_name(fighter.pk)] = (
                    CrewEquipmentSetField(
                        fighter=fighter,
                        sets=sets,
                        initial=fighter.active_equipment_set_id,
                    )
                )
        self.has_eligible_fighters = self.eligible_count > 0

        # Initials from the existing chosen members. The saved pick count feeds
        # the server-rendered over-selection warning (the scenario's count is
        # indicative, never blocking).
        self.saved_pick_count = 0
        if crew is not None and crew.pk and self.shows_picks:
            chosen = list(crew.members.filter(source=CrewMember.CHOSEN))
            self.saved_pick_count = len(chosen)
            self.fields["chosen_fighters"].initial = [m.list_fighter_id for m in chosen]
            for member in chosen:
                field = self.fields.get(
                    equipment_set_field_name(member.list_fighter_id)
                )
                if field is not None:
                    field.initial = member.equipment_set_id

    @property
    def over_selected_note(self):
        """The over-selection callout body, or ``None`` when within the count."""
        if self.custom_count is not None and self.saved_pick_count > self.custom_count:
            return (
                f"{self.saved_pick_count} of {self.custom_count} — every pick is "
                "kept; trim the selection if you want to match the scenario."
            )
        return None

    def fighter_rows(self):
        """One row per eligible fighter for the template: the checkbox, the
        equipment-set select for fighters that have named sets (``None``
        otherwise), and the fighter's current cost. Pairing these here keeps the
        template free of dynamic field-name lookups.

        ``cost`` is the same ``crew_fighter_cost`` shown in the checkbox label,
        read from the fighters already loaded via
        :func:`~gyrinx.core.handlers.crew.with_crew_cost_data` — no query per
        fighter — and surfaced as a data attribute so a small progressive
        enhancement can total the ticked fighters. It is the fighter's whole-kit
        cost, not scoped to the equipment set they bring; the label shows the same
        number, so the running total matches what the player reads off each row.
        """
        if not self.shows_picks:
            return []
        cost_by_id = {str(f.pk): crew_fighter_cost(f) for f in self.eligible_fighters}
        rows = []
        for checkbox in self["chosen_fighters"]:
            value = checkbox.data["value"]
            name = equipment_set_field_name(value)
            rows.append(
                {
                    "checkbox": checkbox,
                    "set_field": self[name] if name in self.fields else None,
                    "cost": cost_by_id.get(str(value), 0),
                }
            )
        return rows

    def clean(self):
        cleaned = super().clean()
        picks = list(cleaned.get("chosen_fighters") or [])

        # Which card each chosen fighter brings. Only the ticked fighters count:
        # a select left set on a fighter the player then unticked is ignored.
        cleaned["equipment_sets"] = {
            fighter.pk: cleaned.get(equipment_set_field_name(fighter.pk))
            for fighter in picks
        }

        # The scenario's pick count is indicative, not enforced: every tick is
        # saved regardless, and over-picking is surfaced as a warning on the
        # screen rather than a rejection that would throw the selection away.
        return cleaned


# The eligibility screen's per-fighter control. The common pair (Eligible /
# Excluded) comes first; "Always included" sits rightmost so it doesn't read as
# "tick to pick" — it's a standing state (hired guns et al. come by default,
# regardless of the crew selected). Values are the states from handlers.crew.
ELIGIBILITY_CHOICES = [
    (CREW_ELIGIBLE, "Eligible"),
    (CREW_NOT_ELIGIBLE, "Excluded"),
    (CREW_ALWAYS_INCLUDED, "Always included"),
]


def eligibility_field_name(fighter_id):
    """The form field name carrying one fighter's eligibility choice."""
    return f"elig_{fighter_id}"


class CrewSetupForm(forms.Form):
    """The crew **setup** screen — the first step of building a crew.

    It carries everything about a crew *except which fighters are picked*: the
    optional name, the selection method's configuration (how many you choose for
    Custom, the draw dice for Random, both for Hybrid), and the per-fighter
    eligibility table (Included / Eligible / Excluded). The method itself is
    URL-driven (the view resolves ``?method=``); this form renders the numbers it
    needs. Choosing the actual fighters happens afterwards on the selection
    screen, from the pool this step defines.

    Eligibility defaults come from each fighter's category and condition (see
    :func:`gyrinx.core.handlers.crew.default_crew_eligibility_state`); only the
    fighters a player moves off their default are stored.
    """

    name = forms.CharField(
        required=False,
        label="Crew name",
        help_text="Optional — a label for this crew.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    custom_count = forms.IntegerField(
        min_value=1,
        max_value=99,
        required=False,
        label="How many fighters you choose",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "style": "width:6rem"}
        ),
    )
    random_dice = forms.ChoiceField(
        choices=DICE_CHOICES,
        required=False,
        label="Dice",
        widget=forms.Select(attrs={"class": "form-select", "style": "width:auto"}),
    )
    random_number = forms.IntegerField(
        min_value=0,
        max_value=99,
        required=False,
        label="Number",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "style": "width:6rem", "placeholder": "0"}
        ),
    )

    def __init__(
        self, *args, crew=None, gang=None, method=None, included=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.crew = crew
        # Gang comes from the view on create, or the crew on edit.
        self.gang = gang or (crew.list if crew is not None else None)
        self.method = method or getattr(crew, "selection_method", None) or Crew.CUSTOM
        # Categories opted in (hangers-on / vehicle crew); view-resolved, else the
        # crew's stored value.
        self.included_categories = (
            list(included)
            if included is not None
            else (getattr(crew, "included_categories", None) or [])
        )
        overrides = getattr(crew, "eligibility_overrides", None) or {}

        # Prune the config to the fields this method actually uses.
        if self.method == Crew.RANDOM:
            del self.fields["custom_count"]
        elif self.method == Crew.CUSTOM:
            del self.fields["random_dice"]
            del self.fields["random_number"]
        self.shows_count = "custom_count" in self.fields
        self.shows_random = "random_dice" in self.fields
        self.method_intro = METHOD_INTRO[self.method]
        if self.shows_count:
            self.fields["custom_count"].help_text = CUSTOM_COUNT_HELP[self.method]
        if self.shows_random:
            self.random_group_label, self.random_group_help = RANDOM_GROUP[self.method]

        # Config + name initials from the crew on edit.
        if crew is not None and crew.pk:
            self.fields["name"].initial = crew.name
            if self.shows_count:
                self.fields["custom_count"].initial = crew.custom_count
            if self.shows_random:
                dice, number = split_selection_spec(crew.random_spec)
                self.fields["random_dice"].initial = dice
                self.fields["random_number"].initial = number

        # Eligibility rows — computed from the gang so create (no crew yet) works
        # the same as edit. with_data so each row's cost_int_cached (a computed
        # property) reads from the prefetch rather than an N+1.
        self.rows = (
            compute_crew_eligibility(
                lst=self.gang,
                overrides=overrides,
                included_categories=self.included_categories,
                with_data=True,
            )
            if self.gang is not None
            else []
        )
        for row in self.rows:
            fighter = row["fighter"]
            self.fields[eligibility_field_name(fighter.id)] = forms.ChoiceField(
                choices=ELIGIBILITY_CHOICES,
                initial=row["effective"],
                required=True,
                label=fighter.name,
                widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
            )

    def fighter_rows(self):
        """One row per fighter for the template: the fighter, its bound radio
        field, the computed default, its current effective state, category, and
        cached cost. Pairing these here keeps the template free of dynamic
        field-name lookups."""
        out = []
        for row in self.rows:
            fighter = row["fighter"]
            out.append(
                {
                    "fighter": fighter,
                    "field": self[eligibility_field_name(fighter.id)],
                    "default": row["default"],
                    "effective": row["effective"],
                    "category": fighter.content_fighter.get_category_display(),
                    "cost": crew_fighter_cost(fighter),
                    "status_badges": fighter_crew_status_badges(fighter),
                }
            )
        return out

    def clean(self):
        cleaned = super().clean()
        # Recombine the structured dice widgets into the stored spec (blank for
        # Custom, which has no random component).
        spec = (
            build_selection_spec(
                cleaned.get("random_dice"), cleaned.get("random_number")
            )
            if self.shows_random
            else ""
        )
        cleaned["random_spec"] = spec
        count = cleaned.get("custom_count")

        # The draw always needs a number; Hybrid also needs the pick count.
        if self.method == Crew.RANDOM and not spec:
            self.add_error(
                "random_number",
                "Enter how many fighters are drawn at random — Random Selection "
                "always shows a number in brackets.",
            )
        if self.method == Crew.HYBRID:
            if not count:
                self.add_error(
                    "custom_count",
                    "Enter how many fighters you choose — the first number in "
                    "brackets.",
                )
            if not spec:
                self.add_error(
                    "random_number",
                    "Enter how many fighters are drawn at random — the second "
                    "number in brackets.",
                )

        # Store only the fighters the player moved off their computed default — a
        # clean map that self-heals as defaults change.
        overrides = {}
        for row in self.rows:
            fighter = row["fighter"]
            state = cleaned.get(eligibility_field_name(fighter.id))
            if state in CREW_ELIGIBILITY_STATES and state != row["default"]:
                overrides[str(fighter.id)] = state
        self.cleaned_overrides = overrides
        return cleaned


class CrewLoadoutsForm(forms.Form):
    """Which equipment set each fighter brings when a whole-gang crew is locked.

    A whole-gang crew has no members to hang a choice off until it is locked, so
    the choices are stored on the crew as advisory intent (see
    ``Crew.loadout_overrides``) and read back by ``Crew.resolve_loadout``. Only
    fighters with named sets get a select — a fighter with only the Default card
    has nothing to choose.

    Each select starts from the resolver, so re-opening the page shows what the
    forecast and the lock would currently do. Every offered fighter's answer is
    recorded, including the empty one: choosing Default is an explicit choice
    for this battle, not "leave it to the fighter card".
    """

    def __init__(self, *args, crew, fighters, **kwargs):
        super().__init__(*args, **kwargs)
        self.crew = crew
        self.fighters = list(fighters)
        for fighter in self.fighters:
            sets = list(fighter.equipment_sets.all())
            if not sets:
                continue
            resolved = crew.resolve_loadout(fighter)
            self.fields[equipment_set_field_name(fighter.pk)] = CrewEquipmentSetField(
                fighter=fighter,
                sets=sets,
                initial=resolved.pk if resolved else None,
            )
        self.has_fighters = bool(self.fighters)
        self.has_choices = bool(self.fields)

    def fighter_rows(self):
        """One row per eligible fighter: the fighter, their select if they have
        one, and the kit they bring when they don't (so the page still says what
        that fighter will field)."""
        rows = []
        for fighter in self.fighters:
            name = equipment_set_field_name(fighter.pk)
            resolved = self.crew.resolve_loadout(fighter)
            rows.append(
                {
                    "fighter": fighter,
                    "category": fighter.content_fighter.get_category_display(),
                    "set_field": self[name] if name in self.fields else None,
                    "loadout": resolved.name if resolved else DEFAULT_SET_LABEL,
                }
            )
        return rows

    def loadout_choices(self):
        """Cleaned map of fighter id → chosen set (``None`` = the Default card),
        for the fighters that had something to choose."""
        return {
            fighter.pk: self.cleaned_data[equipment_set_field_name(fighter.pk)]
            for fighter in self.fighters
            if equipment_set_field_name(fighter.pk) in self.fields
        }


class CrewLineItemForm(forms.ModelForm):
    """Add or edit a crew extra (tactics card, etc.) with its payment method."""

    class Meta:
        model = CrewLineItem
        fields = ["label", "cost", "payment", "reason"]
        labels = {
            "label": "What is it?",
            "cost": "Credits value",
            "payment": "Paid for with",
            "reason": "Reason",
        }
        help_texts = {
            "reason": "Optional — note why, when free or from an allowance.",
        }
        widgets = {
            "label": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. Tactics card: Ambush",
                }
            ),
            "cost": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "payment": forms.Select(attrs={"class": "form-select"}),
            "reason": forms.TextInput(attrs={"class": "form-control"}),
        }
