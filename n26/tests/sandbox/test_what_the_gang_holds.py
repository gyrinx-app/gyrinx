"""What the gang holds reaches its models, however the gang came by it.

The gang's own rows ride every member's card, so a rule built into the
gang type has always reached the fighters. This suite is the other half of
that sentence: a thing the gang was **given** — an alliance's rule, the
hidden carrier a house's rules hang off, a list a territory opens — reaches
them in exactly the same way, because from the point of view of applying
effects there is no difference between arriving built in and arriving by a
modifier.

One *gives* aimed at the gang is therefore the whole authoring step. The
rule lands on the gang's sheet, and whatever the rule itself does —
sharpens the fighters' blades, opens a list, shifts a characteristic —
happens to every member. What the gang's guest never does is draw a line on
a fighter's card, add to anybody's rating, or make its stored effects the
fighter's news: the thing belongs to the gang, and the gang says all three
once.

The corner it was written for: a house rule that improved every fighter's
weapons did nothing at all, and the fighter's own plan showed the
gang-aimed step skipped, with no mention of the rule anywhere.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.access import collections_for, gang_collections
from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card, render_gang
from n26.tests.sandbox.actions import (
    assign,
    create_affiliation,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_rule,
    create_skill,
    create_subtype,
    create_trait,
    create_wargear,
    create_weapon,
    ef_adds,
    ef_changes_stat,
    ef_removes,
    found_gang,
    give_weapon,
    has_subtypes,
    hire,
    modifier,
    op_adds_model,
    remove,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
    targets_model,
    targets_weapons,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang_type(db):
    """The house whose rules these are. Overrides the shared fixture so the
    profiles ``make_profile`` builds belong to this house."""
    return create_gang_type("Escher", starting_credits=1000)


@pytest.fixture
def backstab(default_pack):
    return create_trait("Backstab")


@pytest.fixture
def weapon_skill(person_statline_type):
    return person_statline_type.stats.get(stat__short_name="WS").stat


@pytest.fixture
def matriarchy(backstab, weapon_skill):
    """The house rule, and the two things it does to a fighter.

    The modifiers hang on the *rule*, which is what the book prints the
    behaviour under — so it does the same wherever a gang picks it up.
    """
    rule = create_rule("Matriarchy")
    modifier(
        "Matriarchy: the fighters' blades bite",
        targets_weapons(),
        ef_adds(backstab),
        carried_by=rule,
    )
    modifier(
        "Matriarchy: the fighters are quick",
        targets_every_model(),
        ef_changes_stat(weapon_skill, mode="improve", amount=1),
        carried_by=rule,
    )
    return rule


@pytest.fixture
def charter(gang_type, matriarchy):
    """The gang type's founding row: a hidden carrier that gives the rule to
    the gang. One aim, and the whole house has it."""
    hidden = create_hidden("Escher gang rules")
    modifier(
        "Escher: the gang has Matriarchy",
        targets_gang(),
        ef_adds(matriarchy),
        carried_by=hidden,
    )
    gang_type.built_ins = create_default_set("Escher founding", members=[hidden])
    gang_type.save()
    return hidden


@pytest.fixture
def knife(default_pack):
    return create_weapon("Stiletto knife", profiles=[("", 0)], price=20)


@pytest.fixture
def gang(charter, gang_type):
    return found_gang("The Bad Girls", gang_type, owner=User.objects.create_user("tom"))


@pytest.fixture
def crew(gang, make_profile, knife):
    """Two armed fighters, so "every member" means more than one."""
    profile = make_profile("Escher Ganger", price=55)
    made = {}
    for name in ("Yolanda", "Vandal"):
        made[name] = hire(gang, profile, name, paid=55)
        give_weapon(made[name], knife, paid=20)
    return made


def computed_for(miniature):
    """One model's card, computed the way every screen computes it."""
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return card, compute(card, index)


def drawn_for(miniature):
    card, computed = computed_for(miniature)
    return build_model_card(miniature, card=card, computed=computed)


def gang_computed(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index)


def traits_on(miniature, weapon_name="Stiletto knife"):
    """What a fighter's gun prints, computed traits and all."""
    weapon = next(w for w in drawn_for(miniature).weapons if w.name == weapon_name)
    return sorted(trait.name for trait in weapon.profiles[0].traits)


def stat_changes_on(miniature, stat):
    _, computed = computed_for(miniature)
    return [
        (change.mode, change.amount, change.source)
        for change in computed.stat_changes
        if change.stat == stat
    ]


class TestARuleTheGangIsGiven:
    """One *gives* aimed at the gang, and the rule works on every fighter."""

    def test_the_gang_holds_the_rule(self, gang, crew):
        assert [line.name for line in render_gang(gang).rules] == ["Matriarchy"]

    def test_the_rules_weapon_modifier_reaches_every_members_gun(self, gang, crew):
        for miniature in crew.values():
            assert traits_on(miniature) == ["Backstab"]

    def test_the_rules_model_modifier_reaches_every_member(
        self, gang, crew, weapon_skill
    ):
        for miniature in crew.values():
            assert stat_changes_on(miniature, weapon_skill) == [
                ("improve", 1, "Matriarchy")
            ]

    def test_the_fighters_plan_names_the_rule(self, gang, crew):
        """Not merely that it works: the rule is a step in the fighter's own
        plan, so the trace says where the trait came from."""
        _, computed = computed_for(crew["Yolanda"])
        steps = [step for step in computed.plan if str(step.source) == "Matriarchy"]

        assert [(step.outcome, step.echoed) for step in steps] == [
            ("reached", True),
            ("reached", True),
        ]

    def test_nothing_of_it_is_written_down(self, gang, crew, matriarchy):
        """It is worked out on every read: nothing to sell, nothing to
        reconcile."""
        from n26.core.models import Assignment

        assert not Assignment.objects.filter(rule=matriarchy).exists()
        assert_reconciled(gang)


class TestAListTheGangIsGiven:
    """A list granted to the gang is somewhere every fighter buys from."""

    @pytest.fixture
    def armoury(self, charter, knife):
        """A list the charter opens to the gang, the way an alliance does."""
        collection = create_collection("Escher Armoury", entries=[knife])
        modifier(
            "Escher: the gang buys from the Armoury",
            targets_gang(),
            ef_adds(collection),
            carried_by=charter,
        )
        return collection

    def test_every_fighter_may_buy_from_it(self, gang, crew, armoury):
        for miniature in crew.values():
            assert "Escher Armoury" in [
                access.name for access in collections_for(miniature)
            ]

    def test_the_gang_is_offered_it_once(self, gang, crew, armoury):
        """The gang reads its own grant and a member reads the gang's, and
        neither ends up with the list twice."""
        names = [access.name for access in gang_collections(gang)]

        assert names.count("Escher Armoury") == 1

    def test_a_fighter_is_offered_it_once(self, gang, crew, armoury):
        names = [access.name for access in collections_for(crew["Yolanda"])]

        assert names.count("Escher Armoury") == 1

    def test_the_listing_says_what_opened_it(self, gang, crew, armoury):
        access = next(
            access
            for access in collections_for(crew["Yolanda"])
            if access.name == "Escher Armoury"
        )

        assert access.computed and access.source == "Escher gang rules"


class TestTwoAims:
    """The older way of writing it — a *gives* at the gang and another at
    the model — still leaves the fighter with one of everything."""

    @pytest.fixture
    def also_at_the_model(self, charter, matriarchy):
        return modifier(
            "Escher: the fighters have Matriarchy",
            targets_every_model(),
            ef_adds(matriarchy),
            carried_by=charter,
        )

    def test_the_rules_stat_change_lands_once(
        self, gang, crew, weapon_skill, also_at_the_model
    ):
        assert stat_changes_on(crew["Yolanda"], weapon_skill) == [
            ("improve", 1, "Matriarchy")
        ]

    def test_the_trait_is_added_once(self, gang, crew, also_at_the_model):
        assert traits_on(crew["Yolanda"]) == ["Backstab"]

    def test_the_rule_draws_one_line(self, gang, crew, also_at_the_model):
        """Aimed at the model as well, the rule really is the fighter's — so
        it prints on their card, once."""
        assert [line.name for line in drawn_for(crew["Yolanda"]).rules] == [
            "Matriarchy"
        ]


class TestAGrantTheGangKeepsToItself:
    """The gang carrying it: applied only to the gang, and what it gives
    the gang does not reach the models — no guest, no echoed step,
    nothing to buy from."""

    @pytest.fixture
    def sealed(self, gang_type, matriarchy, knife):
        """A second founding row whose grants are the gang's alone."""
        hidden = create_hidden("Sealed archives")
        modifier(
            "Archives: the gang alone has Matriarchy",
            targets_gang_alone(),
            ef_adds(matriarchy),
            carried_by=hidden,
        )
        modifier(
            "Archives: the gang alone buys from the Vault",
            targets_gang_alone(),
            ef_adds(create_collection("The Vault", entries=[knife])),
            carried_by=hidden,
        )
        gang_type.built_ins = create_default_set("Sealed founding", members=[hidden])
        gang_type.save()
        return hidden

    @pytest.fixture
    def gang(self, sealed, gang_type):
        return found_gang(
            "The Quiet House", gang_type, owner=User.objects.create_user("tom")
        )

    def test_the_gang_holds_it_and_says_so(self, gang, crew):
        drawn = render_gang(gang)
        assert [line.name for line in drawn.rules] == ["Matriarchy"]
        assert [line.name for line in gang_collections(gang)] == ["The Vault"]

    def test_no_fighter_is_reached_by_any_of_it(self, gang, crew, weapon_skill):
        for miniature in crew.values():
            assert traits_on(miniature) == []
            assert stat_changes_on(miniature, weapon_skill) == []
            assert collections_for(miniature) == []

    def test_the_fighters_plan_never_mentions_it(self, gang, crew):
        _, computed = computed_for(crew["Yolanda"])
        assert [
            step for step in computed.plan if str(step.source) == "Matriarchy"
        ] == []
        assert computed.echoed == []


class TestWhatTheGangHoldsIsNotTheFightersToShow:
    """The guest's protections: it works on the model and belongs to the
    gang, so the gang is where it is drawn, rated and reported."""

    def test_the_rule_draws_no_line_on_a_fighters_card(self, gang, crew):
        assert drawn_for(crew["Yolanda"]).rules == []

    def test_a_granted_list_draws_no_line_either(self, gang, crew, charter, knife):
        modifier(
            "Escher: the gang buys from the Armoury",
            targets_gang(),
            ef_adds(create_collection("Escher Armoury", entries=[knife])),
            carried_by=charter,
        )

        assert drawn_for(crew["Yolanda"]).collections == []

    def test_nobody_is_worth_more_for_it(self, gang, crew):
        """A hire and a knife each, and the rule adds nothing to what either
        the fighter or the gang is worth."""
        assert drawn_for(crew["Yolanda"]).rating == 75
        assert gang.rating == 150

    def test_a_stored_effect_is_the_gangs_news_once(
        self, gang, crew, matriarchy, make_profile
    ):
        """A note saying the gang gains a Matriarch belongs on the gang's
        sheet, not on ten fighters' cards: whatever it speaks of was
        written once."""
        modifier(
            "Matriarchy: the gang gains a Matriarch",
            targets_gang(),
            op_adds_model(make_profile("Matriarch", price=120)),
            carried_by=matriarchy,
        )

        assert [effect.source for effect in gang_computed(gang).effects] == [
            "Matriarchy"
        ]
        for miniature in crew.values():
            assert drawn_for(miniature).effects == []


class TestGainingAndLosingIt:
    """A guest is there exactly while the gang holds whatever gives it.

    A gang-aimed scope has nothing to narrow to — there is one gang — so
    "conditionally" means the gang holds the giver or it does not: an
    alliance signed and later abandoned.
    """

    @pytest.fixture
    def alliance(self, default_pack):
        """An alliance whose rule sharpens the fighters' blades."""
        parry = create_trait("Parry")
        rule = create_rule("Guild Drill")
        modifier(
            "Guild Drill: the fighters parry",
            targets_weapons(),
            ef_adds(parry),
            carried_by=rule,
        )
        signed = create_affiliation("Iron Guild")
        modifier(
            "Iron Guild: the gang has Guild Drill",
            targets_gang(),
            ef_adds(rule),
            carried_by=signed,
        )
        return signed

    def test_nothing_of_it_before_the_gang_signs(self, gang, crew, alliance):
        assert "Parry" not in traits_on(crew["Yolanda"])

    def test_the_fighters_gain_it_when_the_gang_signs(self, gang, crew, alliance):
        assign(alliance, gang=gang)

        assert traits_on(crew["Yolanda"]) == ["Backstab", "Parry"]
        assert [line.name for line in render_gang(gang).rules] == [
            "Guild Drill",
            "Matriarchy",
        ]

    def test_dropping_the_alliance_takes_it_back(self, gang, crew, alliance):
        signed = assign(alliance, gang=gang)
        assert "Parry" in traits_on(crew["Yolanda"])

        remove(signed)

        assert "Parry" not in traits_on(crew["Yolanda"])


class TestWhoAGuestReaches:
    """A guest's own scope decides who it lands on, as any carrier's does."""

    @pytest.fixture
    def rank(self, matriarchy):
        """A third thing the rule does, and only for one rank."""
        leader = create_subtype("Leader")
        modifier(
            "Matriarchy: the Matriarch keeps watch",
            targets_every_model(has_subtypes(leader)),
            ef_adds(create_skill("Overwatch")),
            carried_by=matriarchy,
        )
        return leader

    def test_it_reaches_the_fighter_the_scope_names(self, gang, crew, rank):
        assign(rank, miniature=crew["Yolanda"])

        _, computed = computed_for(crew["Yolanda"])
        assert [c.name for c in computed.skills] == ["Overwatch"]

    def test_it_passes_over_everyone_else(self, gang, crew, rank):
        """Not silently: the fighter's plan shows the scope asked and
        refused, as it would for a carrier of their own."""
        _, computed = computed_for(crew["Vandal"])
        step = next(
            step for step in computed.plan if "keeps watch" in step.modifier.name
        )

        assert [c.name for c in computed.skills] == []
        assert step.outcome == "skipped"


class TestWhenTheBundleIsCancelled:
    """A corruption cancels the carrier, and the gang stops holding what it
    gave — so there is nothing to reach the fighters with."""

    @pytest.fixture
    def corruption(self, charter):
        """One aim: the thing it names is the gang's, so the gang is where
        it is cancelled, and the fighters follow."""
        corrupted = create_affiliation("Chaos Corrupted")
        modifier(
            "Corrupted: the gang loses its rules",
            targets_gang(),
            ef_removes(charter),
            carried_by=corrupted,
        )
        return corrupted

    def test_the_gang_loses_the_rule(self, gang, crew, corruption):
        assign(corruption, gang=gang)

        assert render_gang(gang).rules == []

    def test_the_fighters_lose_what_the_rule_was_doing(
        self, gang, crew, corruption, weapon_skill
    ):
        assign(corruption, gang=gang)

        assert traits_on(crew["Yolanda"]) == []
        assert stat_changes_on(crew["Yolanda"], weapon_skill) == []

    def test_a_cancelled_thing_is_nobodys_guest(self, gang, crew, corruption):
        """The gang's card settles first, removals and all, so what it no
        longer holds is never dealt onto a member."""
        assign(corruption, gang=gang)

        _, computed = computed_for(crew["Yolanda"])
        assert computed.echoed == []

    def test_dropping_the_corruption_brings_it_all_back(self, gang, crew, corruption):
        corrupted = assign(corruption, gang=gang)
        assert traits_on(crew["Yolanda"]) == []

        remove(corrupted)

        assert traits_on(crew["Yolanda"]) == ["Backstab"]


class TestOneFighterLosingIt:
    """A removal aimed at the model reaches the guest on that model's card
    and nobody else's — the gang goes on holding the rule."""

    @pytest.fixture
    def amulet(self, matriarchy):
        thing = create_wargear("Warp amulet", price=10)
        modifier(
            "Amulet: its bearer is no daughter of the house",
            targets_model(),
            ef_removes(matriarchy),
            carried_by=thing,
        )
        return thing

    def test_the_bearer_gets_nothing_from_the_rule(
        self, gang, crew, amulet, weapon_skill
    ):
        assign(amulet, miniature=crew["Yolanda"], paid=10)

        assert traits_on(crew["Yolanda"]) == []
        assert stat_changes_on(crew["Yolanda"], weapon_skill) == []

    def test_everybody_else_still_does(self, gang, crew, amulet):
        assign(amulet, miniature=crew["Yolanda"], paid=10)

        assert traits_on(crew["Vandal"]) == ["Backstab"]
        assert [line.name for line in render_gang(gang).rules] == ["Matriarchy"]

    def test_the_plan_says_what_was_taken(self, gang, crew, amulet):
        assign(amulet, miniature=crew["Yolanda"], paid=10)

        _, computed = computed_for(crew["Yolanda"])
        step = next(step for step in computed.plan if step.took_away)

        assert step.took_away == ("Matriarchy",)


class TestTheBudget:
    """Reading the gang's holdings onto a member's card is reading: the rows
    are the ones already fetched, and the sums are done in memory."""

    def test_computing_a_fighters_card_asks_nothing(
        self, gang, crew, django_assert_num_queries
    ):
        card = build_card(crew["Yolanda"], with_statlines=True)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])

        with django_assert_num_queries(0):
            assert compute(card, index).echoed

    def test_a_fighters_page_costs_the_same_as_the_gang_grows(
        self, gang, crew, make_profile, knife
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure():
            with CaptureQueriesContext(connection) as captured:
                computed_for(crew["Yolanda"])
            return len(captured.captured_queries)

        few = measure()
        profile = make_profile("Escher Juve", price=25)
        for index in range(3):
            give_weapon(hire(gang, profile, f"More {index}", paid=25), knife, paid=20)

        assert measure() == few

    def test_the_gang_sheet_costs_the_same_as_the_gang_grows(
        self, gang, crew, make_profile
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert render_gang(gang).models
            return len(captured.captured_queries)

        few = measure()
        profile = make_profile("Escher Juve", price=25)
        for index in range(3):
            hire(gang, profile, f"More {index}", paid=25)

        assert measure() == few
