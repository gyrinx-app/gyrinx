"""A grant of a slot may carry the pick the slot arrives settled on.

The Clan House Outcast case (design/house-and-territory-tables.md): an
Outcast gang picks a Clan House, and for campaign purposes counts as a
gang of that House. Every gang carries a hidden Gang supertype slot;
Clan House gang types build it in with a starting pick, and the Outcast
gang's Clan House pick *gives* the same slot with the House already
picked. ``ef_adds(slot, with_pick=…)`` is the grant-side twin of a
built-in's starting pick.

What this file holds still: the given pick is a fact a "has picked"
condition reads, on the bearer and on every member of a gang that holds
it; it is not a line, opens no choice and is worth nothing; it stands on
the slot, so it goes the moment the slot does; it runs its own
modifiers; and a pick is refused without a slot, with a slot of another
type, or with a slot that is shown on the card.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card, render_gang
from n26.library.models import AddsAssignable
from n26.library.prose import prose_for, sentence_for
from n26.tests.sandbox.actions import (
    add_built_in,
    assign,
    choose,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    create_wargear,
    ef_adds,
    ef_removes,
    found_gang,
    has_pickable,
    hire,
    modifier,
    remove,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
    targets_model,
)

pytestmark = pytest.mark.django_db


# --- The supertype: a hidden gang-level choice with marker pickables --------


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def supertype(default_pack):
    return create_slot_type(
        "Gang supertype", plural_name="Gang supertypes", allows_repeats=False
    )


@pytest.fixture
def houses(supertype):
    """Markers carrying no modifiers of their own; rules key on them."""
    return {name: create_pickable(name, supertype) for name in ("Goliath", "Escher")}


@pytest.fixture
def supertypes(supertype, houses):
    return create_picklist("Gang supertypes", supertype, members=list(houses.values()))


@pytest.fixture
def supertype_slot(supertype, supertypes):
    """Hidden: the sheet never prints a "Gang supertype" line."""
    return create_slot(
        "Gang supertype", supertype, supertypes, assigned_to="gang", hidden=True
    )


@pytest.fixture
def shown_slot(supertype, supertypes):
    """The same choice, shown — what a grant may not carry a pick for."""
    return create_slot("Shown supertype", supertype, supertypes, assigned_to="gang")


@pytest.fixture
def gang_type(default_pack):
    return create_gang_type("Outcasts")


@pytest.fixture
def goliath_rule(gang_type, houses):
    """A rule for every fighter of a gang that has picked Goliath — the
    shape a journal's "Goliath Controlled" boon takes on a model."""
    rule = create_rule("Goliath Controlled")
    modifier(
        "Outcasts: Goliath Controlled",
        targets_every_model(has_pickable(houses["Goliath"])),
        ef_adds(rule),
        carried_by=gang_type,
    )
    return rule


@pytest.fixture
def clan_house(default_pack, supertype_slot, houses):
    """The Outcast choice: its own slot type, its own pickables. Picking
    Goliath gives the gang's supertype slot with Goliath already picked."""
    slot_type = create_slot_type("Clan House")
    goliath = create_pickable("Clan House: Goliath", slot_type)
    modifier(
        "Clan House: Goliath — the gang counts as Goliath",
        targets_gang_alone(),
        ef_adds(supertype_slot, with_pick=houses["Goliath"]),
        carried_by=goliath,
    )
    clan_houses = create_picklist("Clan Houses", slot_type, members=[goliath])
    slot = create_slot("Clan House", slot_type, clan_houses, assigned_to="gang")
    return slot, goliath


@pytest.fixture
def leader(person_type, gang_type, clan_house):
    slot, _ = clan_house
    profile = create_profile("Outcast Leader", person_type, gang_type, price=120)
    add_built_in(profile, slot)
    return profile


@pytest.fixture
def scav(person_type, gang_type):
    return create_profile("Scav", person_type, gang_type, price=40)


@pytest.fixture
def gang(owner, gang_type):
    return found_gang("The Forgotten", gang_type, owner=owner, budget=1000)


def card_of(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return card, compute(card, index)


def drawn_card(miniature):
    card, computed = card_of(miniature)
    return build_model_card(miniature, card=card, computed=computed)


def gang_computed(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index)


def names(contributions):
    return [contribution.name for contribution in contributions]


def pick_clan_house(gang, boss, clan_house):
    _, goliath = clan_house
    (slot,) = [s for s in card_of(boss)[1].choices if s.kind_label == "Clan House"]
    choose(slot.anchor.assignment, goliath)


# --- On a model ------------------------------------------------------------


class TestAGrantCarriesItsPickOntoTheBearer:
    """The simplest shape: kit on a fighter gives a hidden slot with its
    pick. The pick is a fact about the fighter and nothing more — no
    line, no open choice, no rating."""

    @pytest.fixture
    def badge_slot(self, supertype, supertypes):
        return create_slot("Own supertype", supertype, supertypes, hidden=True)

    @pytest.fixture
    def badge(self, badge_slot, houses):
        gear = create_wargear("Goliath badge")
        modifier(
            "Goliath badge: counts as Goliath",
            targets_model(),
            ef_adds(badge_slot, with_pick=houses["Goliath"]),
            carried_by=gear,
        )
        return gear

    def test_the_pick_is_a_fact_a_condition_reads(
        self, gang, scav, badge, goliath_rule
    ):
        rat = hire(gang, scav, "Rat", paid=40)
        assign(badge, miniature=rat)

        _, computed = card_of(rat)

        assert names(computed.picks) == ["Goliath"]
        assert names(computed.rules) == ["Goliath Controlled"]

    def test_it_opens_no_choice_and_draws_no_line(self, gang, scav, badge):
        rat = hire(gang, scav, "Rat", paid=40)
        assign(badge, miniature=rat)

        _, computed = card_of(rat)
        drawn = drawn_card(rat)

        assert computed.choices == []
        assert drawn.choices == []
        assert [line.name for line in drawn.equipment] == ["Goliath badge"]
        assert drawn.remarks == []

    def test_it_is_worth_nothing(self, gang, scav, badge):
        rat = hire(gang, scav, "Rat", paid=40)
        before = gang.rating

        assign(badge, miniature=rat)

        gang.refresh_from_db()
        assert gang.rating == before
        assert_reconciled(gang)

    def test_a_fighter_without_the_grant_is_not_reached(
        self, gang, scav, badge, goliath_rule
    ):
        rat = hire(gang, scav, "Rat", paid=40)
        other = hire(gang, scav, "Other", paid=40)
        assign(badge, miniature=rat)

        assert names(card_of(other)[1].rules) == []
        assert names(card_of(other)[1].picks) == []

    def test_the_granted_pick_gives_in_turn(self, gang, scav, badge, houses):
        """The pick runs its own modifiers: the index follows the grant
        to the pick, or nothing it gives would ever load."""
        modifier(
            "Goliath: muscle",
            targets_model(),
            ef_adds(create_rule("Goliath Muscle")),
            carried_by=houses["Goliath"],
        )
        rat = hire(gang, scav, "Rat", paid=40)
        assign(badge, miniature=rat)

        assert names(card_of(rat)[1].rules) == ["Goliath Muscle"]

    def test_removing_the_carrier_takes_the_pick(self, gang, scav, badge, goliath_rule):
        rat = hire(gang, scav, "Rat", paid=40)
        given = assign(badge, miniature=rat)

        remove(given)

        _, computed = card_of(rat)
        assert names(computed.picks) == []
        assert names(computed.rules) == []
        assert_reconciled(gang)

    def test_a_removal_naming_the_slot_takes_the_pick(
        self, gang, scav, badge, badge_slot, goliath_rule
    ):
        """The pick stands on the slot, not on the carrier: take the slot
        away and the pick goes with it, while the carrier stays.

        Only the pick is asserted on. A rule a later round granted on the
        strength of the pick is settled the way every chain is — the
        removal's consequences are followed once, after the rounds — so
        on the bearer's own card it stands in the same read, exactly as a
        rule conditioned on a subtype a removed hidden gave would.
        """
        stripped = create_wargear("Anonymity")
        modifier(
            "Anonymity: no supertype",
            targets_model(),
            ef_removes(badge_slot),
            carried_by=stripped,
        )
        rat = hire(gang, scav, "Rat", paid=40)
        assign(badge, miniature=rat)
        assign(stripped, miniature=rat)

        _, computed = card_of(rat)

        assert names(computed.picks) == []
        assert sorted(line.name for line in drawn_card(rat).equipment) == [
            "Anonymity",
            "Goliath badge",
        ]


# --- On the gang -----------------------------------------------------------


class TestAGangHoldsAGrantedPick:
    """The Outcast case. The Clan House pick is the gang's; what it gives
    lands on the gang; and a pick the gang holds is a fact about every
    member, whether written or given, and whether or not the grant
    echoes."""

    def test_the_pick_lands_on_the_gang(self, gang, leader, clan_house):
        boss = hire(gang, leader, "Boss", paid=120)

        assert names(gang_computed(gang).picks) == []
        pick_clan_house(gang, boss, clan_house)

        assert names(gang_computed(gang).picks) == ["Goliath"]

    def test_every_member_counts_as_goliath(
        self, gang, leader, scav, clan_house, goliath_rule
    ):
        """The grant is the gang's alone — it echoes nothing — and the
        fighters still pass "has picked Goliath", exactly as the members
        of a gang whose founding wrote the pick down would."""
        boss = hire(gang, leader, "Boss", paid=120)
        rat = hire(gang, scav, "Rat", paid=40)
        assert names(card_of(boss)[1].rules) == []
        assert names(card_of(rat)[1].rules) == []

        pick_clan_house(gang, boss, clan_house)

        assert names(card_of(boss)[1].rules) == ["Goliath Controlled"]
        assert names(card_of(rat)[1].rules) == ["Goliath Controlled"]
        late = hire(gang, scav, "Late", paid=40)
        assert names(card_of(late)[1].rules) == ["Goliath Controlled"]
        assert_reconciled(gang)

    def test_the_gang_alone_grant_does_not_echo_the_pick_itself(
        self, gang, leader, scav, clan_house
    ):
        """The fact reaches the members; the pick's own guest list does
        not, because the grant said the gang alone."""
        boss = hire(gang, leader, "Boss", paid=120)
        rat = hire(gang, scav, "Rat", paid=40)
        pick_clan_house(gang, boss, clan_house)

        _, computed = card_of(rat)

        assert names(computed.picks) == []
        assert names(computed.echoed) == []

    def test_the_sheet_draws_no_supertype_line(self, gang, leader, clan_house):
        boss = hire(gang, leader, "Boss", paid=120)
        pick_clan_house(gang, boss, clan_house)

        sheet = render_gang(gang)

        # The Clan House question is the Leader's; the gang's own card
        # asks nothing, and no line anywhere names the supertype.
        assert sheet.choices == []
        (boss_card,) = sheet.models
        assert [line.kind_label for line in boss_card.questions] == ["Clan House"]
        assert "supertype" not in str(sheet.rows).lower()
        assert "supertype" not in str(sheet.rules).lower()
        assert "supertype" not in str(boss_card.equipment).lower()

    def test_it_is_worth_nothing(self, gang, leader, clan_house):
        boss = hire(gang, leader, "Boss", paid=120)
        before = gang.rating

        pick_clan_house(gang, boss, clan_house)

        gang.refresh_from_db()
        assert gang.rating == before
        assert_reconciled(gang)

    def test_taking_the_clan_house_pick_back_takes_the_supertype(
        self, gang, leader, scav, clan_house, goliath_rule
    ):
        _, goliath = clan_house
        boss = hire(gang, leader, "Boss", paid=120)
        rat = hire(gang, scav, "Rat", paid=40)
        pick_clan_house(gang, boss, clan_house)

        remove(Assignment.objects.get(pickable=goliath, archived=False))

        assert names(gang_computed(gang).picks) == []
        assert names(card_of(boss)[1].rules) == []
        assert names(card_of(rat)[1].rules) == []
        assert_reconciled(gang)

    def test_a_removal_naming_the_slot_takes_the_pick(
        self, gang, leader, scav, clan_house, supertype_slot, goliath_rule
    ):
        boss = hire(gang, leader, "Boss", paid=120)
        rat = hire(gang, scav, "Rat", paid=40)
        pick_clan_house(gang, boss, clan_house)
        outlawed = create_hidden(
            "Outlawed", effects=[(targets_gang_alone(), ef_removes(supertype_slot))]
        )

        assign(outlawed, gang=gang)

        assert names(gang_computed(gang).picks) == []
        assert names(card_of(rat)[1].rules) == []

    def test_a_grant_that_echoes_runs_the_picks_own_modifiers_on_everyone(
        self, gang, gang_type, scav, supertype_slot, houses
    ):
        """Scoped to the gang and everyone, the pick rides the members'
        cards as the gang's guest and what it gives reaches them."""
        modifier(
            "Goliath: muscle",
            targets_every_model(),
            ef_adds(create_rule("Goliath Muscle")),
            carried_by=houses["Goliath"],
        )
        marker = create_hidden(
            "Founded Goliath",
            effects=[
                (targets_gang(), ef_adds(supertype_slot, with_pick=houses["Goliath"]))
            ],
        )
        rat = hire(gang, scav, "Rat", paid=40)

        assign(marker, gang=gang)

        _, computed = card_of(rat)
        assert names(computed.rules) == ["Goliath Muscle"]
        assert names(computed.echoed) == ["Gang supertype", "Goliath"]

    def test_the_sheet_reads_flat_however_many_members(
        self, gang, leader, scav, clan_house, goliath_rule
    ):
        """Two prefetch paths join the budget — the pick, and what it
        carries — and neither grows with the roster."""
        boss = hire(gang, leader, "Boss", paid=120)
        pick_clan_house(gang, boss, clan_house)
        with CaptureQueriesContext(connection) as few:
            render_gang(gang)

        for name in ("Rat", "Cat", "Bat"):
            hire(gang, scav, name, paid=40)
        with CaptureQueriesContext(connection) as more:
            render_gang(gang)

        assert len(more) <= len(few)


# --- Refusals ---------------------------------------------------------------


class TestWhatAGrantMayNotCarry:
    """A pick belongs to a hidden slot of its own type. Each refusal is
    said in words by the verb, by the row, and — where the database can
    say it — by a constraint."""

    def test_a_pick_with_no_slot(self, houses, default_pack):
        with pytest.raises(ValidationError, match="belongs to a slot"):
            ef_adds(create_rule("Loud"), with_pick=houses["Goliath"])

    def test_a_pick_of_another_type(self, supertype_slot, clan_house):
        _, goliath_house = clan_house
        with pytest.raises(ValidationError, match="offers Gang supertype pickables"):
            ef_adds(supertype_slot, with_pick=goliath_house)

    def test_a_pick_for_a_slot_that_is_shown(self, shown_slot, houses):
        with pytest.raises(ValidationError, match="shown on the card"):
            ef_adds(shown_slot, with_pick=houses["Goliath"])

    def test_the_row_says_the_same(
        self, shown_slot, supertype_slot, houses, clan_house
    ):
        _, goliath_house = clan_house
        with pytest.raises(ValidationError, match="belongs to a slot"):
            AddsAssignable(with_pick=houses["Goliath"]).clean()
        with pytest.raises(ValidationError, match="offers Gang supertype pickables"):
            AddsAssignable(slot=supertype_slot, with_pick=goliath_house).clean()
        with pytest.raises(ValidationError, match="shown on the card"):
            AddsAssignable(slot=shown_slot, with_pick=houses["Goliath"]).clean()

    def test_the_database_refuses_a_pick_with_no_slot(self, houses, default_pack):
        rule = create_rule("Loud")
        with pytest.raises(IntegrityError), transaction.atomic():
            AddsAssignable.objects.create(rule=rule, with_pick=houses["Goliath"])

    def test_the_plain_grant_is_unchanged(self, default_pack):
        grant = ef_adds(create_rule("Quiet"))
        assert grant.with_pick is None
        assert str(grant) == "adds Quiet"


# --- What the authoring pages say ------------------------------------------


class TestWhatTheAuthoringPagesSay:
    def texts(self, said):
        return [sentence.text for sentence in said]

    def test_the_pickable_says_it_is_chosen_from_the_start_never_given(
        self, clan_house, houses
    ):
        said = self.texts(prose_for(houses["Goliath"]).referenced_by)

        assert "Chosen from the start for the Gang supertype slot." in said
        assert not any(text.startswith("Given") for text in said)

    def test_the_slot_is_still_given(self, clan_house, supertype_slot):
        said = self.texts(prose_for(supertype_slot).referenced_by)

        assert any(text.startswith("Given to the gang by") for text in said)

    def test_the_grant_names_its_pick(self, clan_house, houses, supertype_slot):
        _, goliath_house = clan_house
        (row,) = goliath_house.modifiers.all()

        sentence = sentence_for(row, carriage=None)

        assert "Gang supertype" in sentence.text
        assert "with Goliath already picked" in sentence.text


class TestTheComposer:
    """The pick control rides the grant form because the slot declares
    it, drawn only when the kind chosen is a slot (library/offers.py)."""

    def test_the_form_asks_for_a_pick_beside_a_slot(self, default_pack):
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        form = generate_form(specs()["ef_adds"])()

        assert "with_pick" in form.fields
        attrs = form.fields["with_pick"].widget.attrs
        assert attrs["data-union-of"] == "thing"
        assert attrs["data-union-member"] == "slot"

    def test_a_pick_typed_for_another_kind_is_dropped(self, houses, default_pack):
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        rule = create_rule("Loud")
        form = generate_form(specs()["ef_adds"])(
            {
                "thing_kind": "rule",
                "thing_rule": str(rule.pk),
                "with_pick": str(houses["Goliath"].pk),
            }
        )

        assert form.is_valid(), form.errors
        grant = form.compile()
        assert grant.rule == rule
        assert grant.with_pick is None

    def test_a_pick_beside_a_slot_is_kept(self, supertype_slot, houses):
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        form = generate_form(specs()["ef_adds"])(
            {
                "thing_kind": "slot",
                "thing_slot": str(supertype_slot.pk),
                "with_pick": str(houses["Goliath"].pk),
            }
        )

        assert form.is_valid(), form.errors
        grant = form.compile()
        assert grant.slot == supertype_slot
        assert grant.with_pick == houses["Goliath"]

    def test_a_pick_of_another_type_is_refused_on_its_field(
        self, supertype_slot, default_pack
    ):
        """The row's own refusal lands on the pick control, so the page
        redraws with it instead of failing the request."""
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        other = create_slot_type("Legacy", plural_name="Legacies")
        stranger = create_pickable("Cawdor", other)
        form = generate_form(specs()["ef_adds"])(
            {
                "thing_kind": "slot",
                "thing_slot": str(supertype_slot.pk),
                "with_pick": str(stranger.pk),
            }
        )

        assert not form.is_valid()
        (error,) = form.errors["with_pick"]
        assert "offers Gang supertype pickables" in error

    def test_a_pick_beside_a_shown_slot_is_refused_on_its_field(
        self, shown_slot, houses
    ):
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        form = generate_form(specs()["ef_adds"])(
            {
                "thing_kind": "slot",
                "thing_slot": str(shown_slot.pk),
                "with_pick": str(houses["Goliath"].pk),
            }
        )

        assert not form.is_valid()
        (error,) = form.errors["with_pick"]
        assert "Only a hidden slot can be given with its pick" in error

    def test_the_composer_page_redraws_a_refused_pick(self, client, shown_slot, houses):
        """The modifier views catch a duplicate name and nothing else, so
        the form has to hold the refusal itself for the page to show it."""
        from n26.library.models import Modifier

        client.force_login(User.objects.create_user("author", is_staff=True))
        response = client.post(
            "/n26/authoring/modifiers/new/",
            {
                "scope_kind": "targets_gang",
                "effect_kind": "ef_adds",
                "what-thing_kind": "slot",
                "what-thing_slot": str(shown_slot.pk),
                "what-with_pick": str(houses["Goliath"].pk),
                "conditions-TOTAL_FORMS": "0",
                "conditions-INITIAL_FORMS": "0",
            },
        )

        assert response.status_code == 200
        assert "Only a hidden slot can be given with its pick" in (
            response.content.decode()
        )
        assert Modifier.objects.count() == 0

    def test_editing_a_grant_opens_on_its_pick(self, supertype_slot, houses):
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        grant = ef_adds(supertype_slot, with_pick=houses["Goliath"])

        form = generate_form(specs()["ef_adds"]).opened_on(grant)

        assert form.initial["thing_kind"] == "slot"
        assert form.initial["with_pick"] == houses["Goliath"]
