"""Several of one thing read once, with the count the book writes.

A fighter carrying two respirators, a fighter who selected the same skill
twice, a stash holding two of one item: each is drawn as one line with
``(x2)`` after the name, wherever the line carries nothing to click —
the gang sheet, the print page, the text card, a hire preview. The
model's own page keeps one line per assignment, because each line there
carries a menu naming that assignment; so does the owner's stash on the
gang sheet. Two things that only look alike stay apart: one bought and
one granted, two pinned at different figures, and kit that brought a pet
with it, which is one line per pet however many are alike.

The same count format is the one a several-pick slot and a stat tooltip
already use, so ``Enfeebled (x5)`` and ``Respirator (x2)`` read as one
rule.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.hire import preview_model_card
from n26.core.models import Miniature
from n26.core.render import build_model_card, render_gang
from n26.core.render_text import gang_to_text, render_model_card
from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    adds,
    assign,
    create_default_set,
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
    """The card the gang sheet draws for one model, effects folded in."""
    return next(card for card in render_gang(gang).models if card.name == name)


class TestGearOnTheCard:
    """Two of one wargear on a fighter are one gear line counting two."""

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

        assert "Equipment: Respirator (x2)" in text

    def test_one_bought_and_one_granted_stay_apart(self, gang, fighter, respirator):
        """A line saying "from Rebreather kit" of a respirator that was
        paid for would lie about it, so the two keep their own lines."""
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
    """The rows a kind files itself into stack the same way gear does."""

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
    """Two of one item in the stash are one line counting two, with the
    rating of one beside it — except on the owner's sheet, where each
    line carries a menu naming its own assignment."""

    @pytest.fixture
    def stashed(self, gang, respirator):
        assign(respirator, stash=gang.stash, paid=15)
        assign(respirator, stash=gang.stash, paid=15)
        gang.refresh_from_db()
        return gang

    def test_the_sheet_holds_one_line_with_one_items_rating(self, stashed):
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

    def test_the_print_page_writes_the_count_and_one_items_rating(
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
    """A profile whose built-in kit holds two of one thing previews as
    one line counting two, as the card it becomes will draw it."""

    def test_two_of_one_built_in_are_one_line(self, profile, respirator):
        profile.built_ins = create_default_set("Kit", members=[respirator, respirator])
        profile.save()

        (kept,) = preview_model_card(profile).equipment
        assert (kept.name, kept.count) == ("Respirator", 2)
