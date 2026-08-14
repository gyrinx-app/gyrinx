"""Setting a model's characteristics by hand.

A model's characteristics are its entry's, and the rules move them about
from there. An owner may also set one themselves — a campaign advance
nothing in the library carries, a change agreed at the table, an entry
that reads differently from the book.

The rules this file pins:

* What is set replaces the printed value of that cell and nothing else:
  overriding a Toughness leaves the rest of the row following the entry.
* It replaces the **base**, so a rule that improves the characteristic
  improves what was set — a Weapon Skill set to 3+ and improved is 2+.
* An emptied box is an answer: the override goes and the entry prints
  again.
* A card, a print-out and the editor all say the same thing, because
  there is one place the value is folded in.
* None of it is money. Nothing moves a rating, nothing writes a ledger
  row, and a gang still reconciles.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import StatOverride
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.tests.sandbox.actions import (
    assign,
    changes_stat,
    create_subtype,
    found_gang,
    hire,
    modifier,
    targets_model,
)

pytestmark = pytest.mark.django_db

#: What the entry prints, before anyone touches it.
PRINTED = {
    "movement": 5,
    "weapon_skill": 4,
    "toughness": 3,
    "wounds": 1,
    "leadership": 7,
}


@pytest.fixture
def player(db):
    return User.objects.create_user("player")


@pytest.fixture
def ganger(fighter_type, gang_type, make_statline, default_pack):
    """An entry carrying the thirteen real characteristics, five of them
    filled in — enough to show one being taken over while the others
    carry on printing."""
    from n26.library.models import Profile

    profile = Profile.objects.create(
        name="Escher Ganger",
        profile_type=fighter_type,
        gang_type=gang_type,
        price=55,
    )
    make_statline(profile, **PRINTED)
    return profile


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def yolanda(gang, ganger):
    return hire(gang, ganger, "Yolanda", paid=55)


@pytest.fixture
def cell_for(ganger):
    """Look one cell of a statline type up by the name a form posts."""

    def _cell(field_name):
        return next(
            type_stat
            for type_stat in ganger.statline_type.stats.all()
            if type_stat.field_name == field_name
        )

    return _cell


def set_by_hand(miniature, cell_for, **values):
    """Set characteristics the way the page does, without going through it."""
    for field_name, value in values.items():
        StatOverride.objects.update_or_create(
            miniature=miniature,
            statline_type_stat=cell_for(field_name),
            defaults={"value": value},
        )


def card_for(miniature, with_effects=True):
    card = build_card(miniature, with_statlines=True)
    if not with_effects:
        return build_model_card(miniature, card=card)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def values(card):
    """``{short name: what the cell reads}`` for a whole statline."""
    return {cell.short_name: cell.value for cell in card.statline.cells}


def edit_url(miniature):
    return reverse("n26-edit-fighter", args=[miniature.pk])


def box(page, field_name):
    """One characteristic's box, as its attributes read.

    The whole tag, so an assertion about a value or a suggestion is
    about *that* box: a page carrying thirteen of them has a value="4"
    somewhere whatever the one under test says.
    """
    match = re.search(rf"<input[^>]*name=\"statline-{field_name}\"[^>]*>", page)
    assert match, f"no box for {field_name} on the page"
    return match.group(0)


def post_statline(client, miniature, ganger, **values):
    """Save the characteristics form as a browser sends it.

    Every box goes, filled or not — the page draws the whole row, so a
    payload naming one characteristic would prove the view tolerates
    something nobody can produce.
    """
    payload = {"act": "statline"}
    for type_stat in ganger.statline_type.stats.all():
        payload[f"statline-{type_stat.field_name}"] = values.get(
            type_stat.field_name, ""
        )
    return client.post(edit_url(miniature), payload)


class TestWhatTheCardShows:
    """A set characteristic stands in for the printed one, alone."""

    def test_the_cell_reads_what_the_owner_set(self, yolanda, cell_for):
        set_by_hand(yolanda, cell_for, toughness="4")
        assert values(card_for(yolanda))["T"] == "4"

    def test_every_other_cell_still_reads_the_entrys_own(self, yolanda, cell_for):
        set_by_hand(yolanda, cell_for, toughness="4")
        printed = values(card_for(yolanda))
        assert printed["M"] == '5"'
        assert printed["WS"] == "4+"
        assert printed["W"] == "1"
        assert printed["Ld"] == "7"

    def test_the_cell_says_the_owner_set_it(self, yolanda, cell_for):
        """Marked the way a shifted cell is, and naming the same kind of
        cause: a reader should not have to guess why a number differs
        from the book's."""
        set_by_hand(yolanda, cell_for, toughness="4")
        toughness = card_for(yolanda).statline.get("T")
        assert toughness.modified
        assert [source.source for source in toughness.modified_by] == ["the owner"]

    def test_it_is_stored_as_its_stat_reads(self, yolanda, cell_for):
        """A Movement typed as 4 means 4 inches, as it does everywhere
        else, so the box and the card cannot come to print it
        differently."""
        set_by_hand(yolanda, cell_for, movement="4")
        assert StatOverride.objects.get(miniature=yolanda).value == '4"'
        assert values(card_for(yolanda))["M"] == '4"'

    def test_anything_short_may_be_set(self, yolanda, cell_for):
        """The library's own values are free strings, and so are these:
        a characteristic that is rolled, or borrowed, or nonsense the
        owner meant, is theirs to set."""
        set_by_hand(yolanda, cell_for, toughness="2D6")
        assert values(card_for(yolanda))["T"] == "2D6"

    def test_the_entrys_other_models_are_untouched(self, gang, ganger, cell_for):
        """One model's setting is one model's: the entry is shared
        content, and nothing here writes to it."""
        yolanda = hire(gang, ganger, "Yolanda", paid=55)
        donna = hire(gang, ganger, "Mad Donna", paid=55)
        set_by_hand(yolanda, cell_for, toughness="4")
        assert values(card_for(donna))["T"] == "3"
        assert_reconciled(gang)

    def test_a_deleted_model_takes_its_settings_with_it(self, yolanda, cell_for):
        """Nothing a player clicks deletes a model — leaving the roster
        is archiving — but a row that outlived its model would be a
        setting belonging to nobody."""
        set_by_hand(yolanda, cell_for, toughness="4")
        yolanda.delete()
        assert StatOverride.objects.count() == 0


class TestWhatTheRulesDoToIt:
    """The set value is the base the rules then work on."""

    @pytest.fixture
    def keen_eyed(self, fighter_stats):
        """A subtype improving Weapon Skill by one."""
        subtype = create_subtype("Keen-eyed")
        modifier(
            "Keen-eyed sharpens the eye",
            targets_model(),
            changes_stat(fighter_stats["WS"], mode="improve", amount=1),
            carried_by=subtype,
        )
        return subtype

    def test_an_improvement_lands_on_what_the_owner_set(
        self, yolanda, cell_for, keen_eyed
    ):
        """4+ printed, set to 3+, improved once: 2+. Improving the
        printed value instead would read 3+ — the same number the owner
        already set, and the improvement lost."""
        set_by_hand(yolanda, cell_for, weapon_skill="3+")
        assign(keen_eyed, miniature=yolanda)
        assert values(card_for(yolanda))["WS"] == "2+"

    def test_the_cell_names_both_reasons_it_differs(self, yolanda, cell_for, keen_eyed):
        set_by_hand(yolanda, cell_for, weapon_skill="3+")
        assign(keen_eyed, miniature=yolanda)
        skill = card_for(yolanda).statline.get("WS")
        assert [source.source for source in skill.modified_by] == [
            "the owner",
            "Keen-eyed",
        ]

    def test_without_the_setting_the_rule_reads_from_the_entry(
        self, yolanda, keen_eyed
    ):
        assign(keen_eyed, miniature=yolanda)
        assert values(card_for(yolanda))["WS"] == "3+"


class TestTheEditPage:
    """The whole flow through the page an owner uses."""

    def test_the_page_offers_a_box_per_characteristic(
        self, client, player, yolanda, ganger
    ):
        client.force_login(player)
        page = client.get(edit_url(yolanda)).content.decode()
        assert "Save characteristics" in page
        for field_name in ("movement", "weapon_skill", "leadership"):
            assert f'name="statline-{field_name}"' in page

    def test_an_empty_box_suggests_what_the_entry_prints(self, client, player, yolanda):
        """Not an example value — the number that stands if nothing is
        typed, which is what an owner needs to see to decide."""
        client.force_login(player)
        page = client.get(edit_url(yolanda)).content.decode()
        assert 'placeholder="5&quot;"' in box(page, "movement")
        assert 'placeholder="7"' in box(page, "leadership")

    def test_saving_lands_back_here_and_the_values_hold(
        self, client, player, yolanda, ganger
    ):
        client.force_login(player)
        response = post_statline(client, yolanda, ganger, toughness="4", wounds="2")
        assert response.status_code == 302
        assert response.url == edit_url(yolanda)
        shown = values(card_for(yolanda))
        assert (shown["T"], shown["W"]) == ("4", "2")
        # And the boxes read back what was set, beside the ones that
        # stayed empty.
        page = client.get(edit_url(yolanda)).content.decode()
        assert 'value="4"' in box(page, "toughness")
        assert 'value=""' in box(page, "movement")
        # The card on the same page says it too, marked and explained —
        # the boxes and the card are one screen and must agree.
        assert "T changed by the owner" in page

    def test_an_emptied_box_gives_the_entrys_value_back(
        self, client, player, yolanda, ganger
    ):
        client.force_login(player)
        post_statline(client, yolanda, ganger, toughness="4")
        assert values(card_for(yolanda))["T"] == "4"

        post_statline(client, yolanda, ganger)
        assert values(card_for(yolanda))["T"] == "3"
        assert StatOverride.objects.filter(miniature=yolanda).count() == 0

    def test_a_value_too_long_is_refused_in_words(
        self, client, player, yolanda, ganger
    ):
        """The one kind of refusal there is: something that cannot be
        stored. The page comes back with what was typed still in the box
        — a complaint about a value nobody can see is one nobody can act
        on."""
        client.force_login(player)
        response = post_statline(
            client, yolanda, ganger, toughness="four or thereabouts"
        )
        assert response.status_code == 200
        page = response.content.decode()
        assert "Toughness is longer than 10 characters" in page
        assert 'value="four or thereabouts"' in page
        assert StatOverride.objects.filter(miniature=yolanda).count() == 0

    def test_saving_the_notes_leaves_the_settings_alone(
        self, client, player, yolanda, ganger
    ):
        """Two forms on one page: clicking one must not clear the
        other's answers."""
        client.force_login(player)
        post_statline(client, yolanda, ganger, toughness="4")
        client.post(edit_url(yolanda), {"act": "notes", "notes": "<p>Owes Kaine.</p>"})
        assert values(card_for(yolanda))["T"] == "4"

    def test_a_stranger_cannot_set_anything(self, client, yolanda, ganger):
        client.force_login(User.objects.create_user("someone-else"))
        assert post_statline(client, yolanda, ganger, toughness="9").status_code == 404
        assert StatOverride.objects.filter(miniature=yolanda).count() == 0

    def test_none_of_it_is_money(self, client, player, gang, yolanda, ganger):
        from n26.core.models import LedgerEntry

        client.force_login(player)
        gang.refresh_from_db()
        before = (gang.rating, gang.credits, LedgerEntry.objects.count())
        post_statline(client, yolanda, ganger, toughness="9", wounds="4")
        gang.refresh_from_db()
        assert (gang.rating, gang.credits, LedgerEntry.objects.count()) == before
        assert_reconciled(gang)


class TestOnPaper:
    """One seam, so the print-out says what the screen says."""

    def test_the_printed_card_carries_the_set_value(
        self, client, player, gang, yolanda, cell_for
    ):
        set_by_hand(yolanda, cell_for, toughness="12")
        client.force_login(player)
        page = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        # Marked as changed, exactly as the screen marks it: the value
        # alone could be any number on the page.
        assert '<span class="is-modified">12</span>' in page

    def test_the_text_card_carries_it_too(self, yolanda, cell_for):
        from n26.core.render_text import render_model_card

        set_by_hand(yolanda, cell_for, toughness="12")
        text = "\n".join(render_model_card(card_for(yolanda)))
        print("\n" + text)
        assert "12†" in text


class TestTheQueryBudget:
    """Settings are read with the roster, so a gang full of them costs
    what a gang with none costs."""

    def test_a_gang_of_them_costs_what_two_of_them_cost(self, gang, ganger, cell_for):
        """Every model on the sheet has a full row set by hand, so a
        reading that asked each of them separately would show as the
        count climbing with the roster."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.render import render_gang

        def recruit(name):
            miniature = hire(gang, ganger, name, paid=55)
            set_by_hand(
                miniature,
                cell_for,
                movement="6",
                weapon_skill="3+",
                toughness="4",
                wounds="2",
                leadership="8",
            )

        def measure():
            gang.refresh_from_db()
            with CaptureQueriesContext(connection) as captured:
                sheet = render_gang(gang)
                assert all(card.statline.get("T").value == "4" for card in sheet.models)
            return len(captured.captured_queries), len(sheet.models)

        for index in range(2):
            recruit(f"Sister {index}")
        # The first reading pays one-time caches that no later one does.
        measure()
        few, few_models = measure()

        for index in range(2, 8):
            recruit(f"Sister {index}")
        many, many_models = measure()

        assert (few_models, many_models) == (2, 8)
        assert few == many, f"{few} queries for 2 models, {many} for 8"
        assert_reconciled(gang)
