"""Combine equivalent display-only equipment, skill and rule lines with counts. Editable
assignment controls remain separate, as do different contributions, provenance, weapons
in the stash and equipment that creates pets.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.capture import differences, gang_state
from n26.core.hire import preview_model_card
from n26.core.models import Miniature
from n26.core.render import build_model_card, render_gang
from n26.core.render_text import gang_to_text, render_model_card
from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    adds,
    assign,
    create_category,
    create_default_set,
    create_power,
    create_rule,
    create_skill,
    create_wargear,
    found_gang,
    hire,
    modifier,
    op_adds_model,
    select,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Ashen Choir", gang_type, owner=player, budget=1000)


@pytest.fixture
def profile(make_profile, make_statline):
    profile = make_profile("Ganger", price=0)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return profile


@pytest.fixture
def fighter(gang, profile):
    return hire(gang, profile, "Vex")


@pytest.fixture
def respirator(default_pack):
    return create_wargear("Respirator", price=15)


@pytest.fixture
def nerves(default_pack):
    return create_skill("Nerves of Steel")


def drawn(gang, name):
    """Find a model card on the computed gang sheet."""
    return next(card for card in render_gang(gang).models if card.name == name)


class TestGearOnTheCard:
    """Equivalent wargear assignments collapse to a counted display line."""

    @pytest.fixture
    def doubled(self, fighter, respirator):
        assign(respirator, miniature=fighter, paid=15)
        assign(respirator, miniature=fighter, paid=15)
        return fighter

    def test_the_card_draws_one_line_with_the_count(self, doubled):
        (kept,) = build_model_card(doubled).equipment
        assert (kept.name, kept.count, kept.count_mark) == ("Respirator", 2, " (x2)")

    def test_the_line_names_no_assignment(self, doubled):
        (kept,) = build_model_card(doubled).equipment
        assert kept.id == ""

    def test_the_gang_sheet_writes_the_count(self, client, gang, doubled):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Respirator (x2)" in body
        assert "Respirator, Respirator" not in body

    def test_the_models_own_page_keeps_one_line_per_piece(self, client, gang, doubled):
        client.force_login(gang.owner)
        url = reverse("n26-edit-fighter", args=[doubled.pk])
        body = client.get(url).content.decode()

        assert "(x2)" not in body
        assert body.count('aria-label="More for Respirator"') == 2

    def test_the_print_page_writes_the_count(self, client, gang, doubled):
        client.force_login(gang.owner)
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()

        assert "Respirator (x2)" in paper

    def test_the_text_card_writes_the_count(self, doubled):
        text = "\n".join(render_model_card(build_model_card(doubled)))
        print("\n" + text)

        assert "Gear: Respirator (x2)" in text

    def test_one_bought_and_one_granted_stay_apart(self, gang, fighter, respirator):
        """A combined line would obscure which copy came from the granting kit."""
        kit = create_wargear("Rebreather kit", price=20)
        modifier(
            "The kit comes with a respirator",
            targets_model(),
            adds(respirator),
            carried_by=kit,
        )
        assign(kit, miniature=fighter, paid=20)
        assign(respirator, miniature=fighter, paid=15)

        lines = [
            (line.count, line.provenance.computed)
            for line in drawn(gang, "Vex").equipment
            if line.name == "Respirator"
        ]
        assert lines == [(1, False), (1, True)]

    def test_kit_that_brings_a_pet_is_one_line_per_pet(
        self, gang, fighter, person_type, gang_type, default_pack
    ):
        mastiff = Profile.objects.create(
            name="Cyber-mastiff",
            profile_type=person_type,
            gang_type=gang_type,
            price=100,
        )
        collar = create_wargear("Cyber-mastiff (pet)")
        modifier(
            "Cyber-mastiff wargear brings a pet",
            targets_model(),
            op_adds_model(mastiff),
            carried_by=collar,
        )
        assign(collar, miniature=fighter, paid=100)
        assign(collar, miniature=fighter, paid=100)

        pets = [
            line
            for line in drawn(gang, "Vex").equipment
            if line.name == "Cyber-mastiff (pet)"
        ]
        assert [line.count for line in pets] == [1, 1]
        assert Miniature.objects.filter(name="Cyber-mastiff").count() == 2


class TestSkillsAndRulesOnTheCard:
    """Repeated skills and rules use counted display lines."""

    def test_the_same_skill_twice_is_one_line_with_the_count(self, fighter, nerves):
        select(fighter, nerves)
        select(fighter, nerves)

        (kept,) = build_model_card(fighter).skills
        assert (kept.name, kept.count) == ("Nerves of Steel", 2)

    def test_the_gang_sheet_and_the_text_card_write_it(
        self, client, gang, fighter, nerves
    ):
        select(fighter, nerves)
        select(fighter, nerves)
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        text = "\n".join(render_model_card(build_model_card(fighter)))

        assert "Nerves of Steel (x2)" in body
        assert "Skills: Nerves of Steel (x2)" in text

    def test_the_same_rule_twice_is_one_line_with_the_count(
        self, fighter, default_pack
    ):
        nimble = create_rule("Nimble")
        assign(nimble, miniature=fighter)
        assign(nimble, miniature=fighter)

        (kept,) = build_model_card(fighter).rules
        assert (kept.name, kept.count) == ("Nimble", 2)


class TestTheStash:
    """Display-only stash lines show a count and per-item contribution; owner controls
    retain each assignment.
    """

    @pytest.fixture
    def stashed(self, gang, respirator):
        assign(respirator, stash=gang.stash, paid=15)
        assign(respirator, stash=gang.stash, paid=15)
        gang.refresh_from_db()
        return gang

    def test_the_sheet_holds_one_line_with_the_rating_of_one_item(self, stashed):
        sheet = render_gang(stashed)

        (kept,) = sheet.stash
        assert (kept.name, kept.count, kept.rating, kept.id) == (
            "Respirator",
            2,
            15,
            "",
        )
        assert sheet.stash_rating == 30

    def test_two_pinned_at_different_figures_are_two_lines(self, gang, respirator):
        assign(respirator, stash=gang.stash, paid=15)
        assign(respirator, stash=gang.stash, paid=10)
        gang.refresh_from_db()

        lines = sorted((line.rating, line.count) for line in render_gang(gang).stash)
        assert lines == [(10, 1), (15, 1)]

    def test_a_reader_who_does_not_own_the_gang_sees_the_count(self, client, stashed):
        body = client.get(reverse("n26-gang", args=[stashed.pk])).content.decode()

        assert "Respirator (x2)" in body
        assert "15¢" in body
        assert "Actions for Respirator" not in body

    def test_the_owner_keeps_one_line_per_item_each_with_its_menu(
        self, client, stashed
    ):
        client.force_login(stashed.owner)
        body = client.get(reverse("n26-gang", args=[stashed.pk])).content.decode()

        assert "(x2)" not in body
        assert body.count('aria-label="Actions for Respirator"') == 2

    def test_the_print_page_writes_the_count_and_the_rating_of_one_item(
        self, client, stashed
    ):
        client.force_login(stashed.owner)
        paper = client.get(reverse("n26-print", args=[stashed.pk])).content.decode()

        assert "Respirator (x2)" in paper
        assert "Respirator, Respirator" not in paper

    def test_the_text_sheet_writes_the_count(self, stashed):
        text = gang_to_text(stashed)
        print("\n" + text)

        assert "  Respirator (x2) — 15cr" in text
        assert "Stash — 30cr" in text


class TestTheHirePreview:
    """Hire previews collapse duplicate built-ins the same way as model cards."""

    def test_two_of_one_built_in_are_one_line(self, profile, respirator):
        profile.built_ins = create_default_set("Kit", members=[respirator, respirator])
        profile.save()

        (kept,) = preview_model_card(profile).equipment
        assert (kept.name, kept.count) == ("Respirator", 2)


class TestPowersAndCategoryGearOnTheCard:
    """Powers and category-specific gear groups retain counts across screen, print and
    text.
    """

    @pytest.fixture
    def crush(self, default_pack):
        family = create_category("Powers", "Whispers")
        return create_power("Crush", category=family)

    @pytest.fixture
    def iron_flesh(self, default_pack):
        upgrades = create_category(
            "Gene-smithing", "Gene-smithing", draws_its_own_row=True
        )
        return create_wargear("Iron flesh", price=30, category=upgrades)

    def test_the_same_power_twice_is_one_line_with_the_count(
        self, client, gang, fighter, crush
    ):
        select(fighter, crush)
        select(fighter, crush)

        (kept,) = build_model_card(fighter).powers
        assert (kept.name, kept.count) == ("Crush", 2)

        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        text = "\n".join(render_model_card(build_model_card(fighter)))
        assert "Crush (x2)" in body
        assert "Crush, Crush" not in body
        assert "Powers: Crush (x2)" in text

    def test_two_of_one_upgrade_are_one_line_under_their_heading(
        self, client, gang, fighter, iron_flesh
    ):
        assign(iron_flesh, miniature=fighter, paid=30)
        assign(iron_flesh, miniature=fighter, paid=30)

        card = build_model_card(fighter)
        assert card.equipment == []
        (group,) = card.gear_groups
        (kept,) = group.lines
        assert (group.name, kept.name, kept.count, kept.id) == (
            "Gene-smithing",
            "Iron flesh",
            2,
            "",
        )

        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        text = "\n".join(render_model_card(card))
        assert "Iron flesh (x2)" in body
        assert "Iron flesh, Iron flesh" not in body
        assert "Iron flesh (x2)" in paper
        assert "Gene-smithing: Iron flesh (x2)" in text

    def test_the_models_own_page_keeps_one_upgrade_line_per_piece(
        self, client, gang, fighter, iron_flesh
    ):
        assign(iron_flesh, miniature=fighter, paid=30)
        assign(iron_flesh, miniature=fighter, paid=30)
        client.force_login(gang.owner)
        body = client.get(
            reverse("n26-edit-fighter", args=[fighter.pk])
        ).content.decode()

        assert "(x2)" not in body
        assert body.count('aria-label="More for Iron flesh"') == 2


class TestTheCapture:
    """Captures preserve assignment multiplicity even when display lines collapse."""

    def test_two_of_one_wargear_capture_differently_from_one(
        self, gang, fighter, respirator
    ):
        assign(respirator, miniature=fighter, paid=15)
        one = gang_state(gang)
        assign(respirator, miniature=fighter, paid=15)
        two = gang_state(gang)

        assert differences(one, two) != []
        (model,) = two["models"].values()
        assert model["equipment"] == [("Respirator", 15), ("Respirator", 15)]

    def test_two_of_one_stashed_item_capture_as_two(self, gang, respirator):
        assign(respirator, stash=gang.stash, paid=15)
        assign(respirator, stash=gang.stash, paid=15)
        gang.refresh_from_db()

        assert gang_state(gang)["stash"] == [("Respirator", 15), ("Respirator", 15)]

    def test_the_same_skill_twice_captures_as_two(self, gang, fighter, nerves):
        select(fighter, nerves)
        select(fighter, nerves)

        (model,) = gang_state(gang)["models"].values()
        assert model["skills"] == ["Nerves of Steel", "Nerves of Steel"]


class TestABoughtAndAGrantedSkill:
    """Keep stored and computed skill lines separate so computed provenance remains
    visible. Multiple computed grants still collapse.
    """

    @pytest.fixture
    def both(self, fighter, nerves):
        kit = create_wargear("Rebreather kit", price=20)
        modifier(
            "The kit steadies its wearer",
            targets_model(),
            adds(nerves),
            carried_by=kit,
        )
        select(fighter, nerves)
        assign(kit, miniature=fighter, paid=20)
        return fighter

    def test_the_card_holds_both_lines_apart(self, gang, both):
        lines = [
            (line.count, line.provenance.computed, line.provenance.source)
            for line in drawn(gang, "Vex").skills
        ]
        assert lines == [(1, False, None), (1, True, "Rebreather kit")]

    def test_the_gang_sheet_draws_the_granted_one_with_its_source(
        self, client, gang, both
    ):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "(x2)" not in body
        assert body.count("Nerves of Steel") >= 2
        assert (
            'Nerves of Steel<span class="sr-only"> (From Rebreather kit (wargear))</span>'
            in body
        )

    def test_the_text_card_writes_both(self, gang, both):
        text = "\n".join(render_model_card(drawn(gang, "Vex")))
        print("\n" + text)

        assert "Skills: Nerves of Steel, Nerves of Steel" in text

    def test_two_grants_of_one_skill_still_read_once(self, gang, fighter, nerves):
        for name in ("Rebreather kit", "Steadying harness"):
            kit = create_wargear(name, price=20)
            modifier(f"{name} steadies", targets_model(), adds(nerves), carried_by=kit)
            assign(kit, miniature=fighter, paid=20)

        (kept,) = drawn(gang, "Vex").skills
        assert (kept.name, kept.count, kept.provenance.computed) == (
            "Nerves of Steel",
            1,
            True,
        )


class TestTheTypeLineReadsASubtypeOnce:
    """Stored and computed copies of a subtype appear once in the type line."""

    def test_a_subtype_both_added_and_granted_reads_once(
        self, gang, fighter, default_pack
    ):
        from n26.tests.sandbox.actions import create_subtype

        mounted = create_subtype("Mounted")
        cutter = create_wargear("Cutter", price=75)
        modifier(
            "Cutter grants Mounted", targets_model(), adds(mounted), carried_by=cutter
        )
        assign(mounted, miniature=fighter)
        assign(cutter, miniature=fighter, paid=75)

        card = drawn(gang, "Vex")
        assert card.type_line == "Fighter (Mounted)"
        assert [line.name for line in card.subtypes] == ["Mounted"]


class TestTwoSkillsOfOneName:
    """Same-named skills from different packs collapse when granted by modifiers."""

    def test_both_granted_read_as_one_skill(
        self, gang, fighter, nerves, other_pack, default_pack
    ):
        twin = create_skill("Nerves of Steel", pack=other_pack)
        assert twin.pk != nerves.pk
        for name, skill in (("Rebreather kit", nerves), ("Steadying harness", twin)):
            kit = create_wargear(name, price=20)
            modifier(f"{name} steadies", targets_model(), adds(skill), carried_by=kit)
            assign(kit, miniature=fighter, paid=20)

        (kept,) = drawn(gang, "Vex").skills
        assert (kept.name, kept.count, kept.provenance.computed) == (
            "Nerves of Steel",
            1,
            True,
        )


class TestWeaponsInTheStash:
    """Stash weapons remain separate because equal names and totals can hide different
    configurations.
    """

    @pytest.fixture
    def lasgun(self, default_pack):
        from n26.tests.sandbox.actions import create_weapon

        return create_weapon("Lasgun", profiles=[("", 0)], price=15)

    def test_two_lasguns_with_equal_totals_but_different_kit_are_two_lines(
        self, gang, lasgun, default_pack
    ):
        from n26.tests.sandbox.actions import attach, create_weapon_accessory

        plain = assign(lasgun, stash=gang.stash, paid=15)
        sighted = assign(lasgun, stash=gang.stash, paid=15)
        attach(sighted, create_weapon_accessory("Iron sights", price=0), paid=0)
        gang.refresh_from_db()

        weapons = [line for line in render_gang(gang).stash if line.kind == "weapon"]
        assert [(line.name, line.rating, line.count) for line in weapons] == [
            ("Lasgun", 15, 1),
            ("Lasgun", 15, 1),
        ]
        assert {line.id for line in weapons} == {str(plain.pk), str(sighted.pk)}

    def test_two_bare_lasguns_are_two_lines_too(self, gang, lasgun):
        assign(lasgun, stash=gang.stash, paid=15)
        assign(lasgun, stash=gang.stash, paid=15)
        gang.refresh_from_db()

        assert [(line.name, line.count) for line in render_gang(gang).stash] == [
            ("Lasgun", 1),
            ("Lasgun", 1),
        ]


class TestKitWhoseHiddenPartBringsAPet:
    """A pet-producing hidden descendant prevents its visible equipment line from
    collapsing.
    """

    def test_two_copies_are_two_lines(
        self, gang, fighter, person_type, gang_type, default_pack
    ):
        from n26.tests.sandbox.actions import create_hidden

        mastiff = Profile.objects.create(
            name="Cyber-mastiff",
            profile_type=person_type,
            gang_type=gang_type,
            price=100,
        )
        tag = create_hidden("The collar's tag brings a mastiff")
        modifier(
            "Collar tag brings a pet",
            targets_model(),
            op_adds_model(mastiff),
            carried_by=tag,
        )
        collar = create_wargear("Mastiff collar", price=100)
        from n26.core.operations import operation

        for _ in range(2):
            held = assign(collar, miniature=fighter, paid=100)
            # Parent the hidden carrier to each collar so its pet belongs to that
            # collar’s subtree.
            with operation(gang, actor=gang.owner) as op:
                op.assign(tag, parent=held, caused_by=held)

        collars = [
            line
            for line in drawn(gang, "Vex").equipment
            if line.name == "Mastiff collar"
        ]
        assert [line.count for line in collars] == [1, 1]
        assert Miniature.objects.filter(name="Cyber-mastiff").count() == 2
