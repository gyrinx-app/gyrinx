"""Verify owner overrides of model characteristics. Overrides replace individual base
values before modifiers apply; clearing a field restores the profile value. Keep editor,
screen, print and text output consistent without changing ratings, credits or purchase
ledger entries.
"""

import re

import pytest
from bs4 import BeautifulSoup
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

#: Baseline profile values before overrides or modifiers.
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
    """Standard Fighter characteristics with five stored values for override and fallback
    comparisons.
    """
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
    """Resolve a characteristic definition by its posted field name."""

    def _cell(field_name):
        return next(
            type_stat
            for type_stat in ganger.statline_type.stats.all()
            if type_stat.field_name == field_name
        )

    return _cell


def set_by_hand(miniature, cell_for, **values):
    """Write model-specific overrides directly for display fixtures."""
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
    """Return displayed characteristic values keyed by short name."""
    return {cell.short_name: cell.value for cell in card.statline.cells}


def edit_url(miniature):
    return reverse("n26-edit-fighter", args=[miniature.pk])


def box(page, field_name):
    """Return the specific input tag so assertions cannot accidentally match another
    characteristic's value or placeholder.
    """
    match = re.search(rf"<input[^>]*name=\"statline-{field_name}\"[^>]*>", page)
    assert match, f"no box for {field_name} on the page"
    return match.group(0)


def post_statline(client, miniature, ganger, **values):
    """Submit every characteristic field, including empty inputs, matching the browser
    form.
    """
    payload = {"act": "statline"}
    for type_stat in ganger.statline_type.stats.all():
        payload[f"statline-{type_stat.field_name}"] = values.get(
            type_stat.field_name, ""
        )
    return client.post(edit_url(miniature), payload)


class TestWhatTheCardShows:
    """Replace only the overridden characteristic and preserve profile values elsewhere."""

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
        """Mark the cell as modified and attribute the change to the owner."""
        set_by_hand(yolanda, cell_for, toughness="4")
        toughness = card_for(yolanda).statline.get("T")
        assert toughness.modified
        assert [source.source for source in toughness.modified_by] == ["the owner"]

    def test_it_is_stored_as_its_stat_reads(self, yolanda, cell_for):
        """Canonicalise stored override values using the characteristic's display rules."""
        set_by_hand(yolanda, cell_for, movement="4")
        assert StatOverride.objects.get(miniature=yolanda).value == '4"'
        assert values(card_for(yolanda))["M"] == '4"'

    def test_anything_short_may_be_set(self, yolanda, cell_for):
        """Allow symbolic and dice strings within storage limits."""
        set_by_hand(yolanda, cell_for, toughness="2D6")
        assert values(card_for(yolanda))["T"] == "2D6"

    def test_the_entrys_other_models_are_untouched(self, gang, ganger, cell_for):
        """Store overrides on the model without changing its shared profile."""
        yolanda = hire(gang, ganger, "Yolanda", paid=55)
        donna = hire(gang, ganger, "Mad Donna", paid=55)
        set_by_hand(yolanda, cell_for, toughness="4")
        assert values(card_for(donna))["T"] == "3"
        assert_reconciled(gang)

    def test_a_deleted_model_takes_its_settings_with_it(self, yolanda, cell_for):
        """Cascade override rows when the model is deleted."""
        set_by_hand(yolanda, cell_for, toughness="4")
        yolanda.delete()
        assert StatOverride.objects.count() == 0


class TestWhatTheRulesDoToIt:
    """Apply modifiers to the overridden base value."""

    @pytest.fixture
    def keen_eyed(self, fighter_stats):

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
        """Override printed 4+ with 3+, then apply the improvement to reach 2+."""
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
    """Verify owner editing, validation, clearing and unrelated notes submissions."""

    def test_the_page_offers_a_box_per_characteristic(
        self, client, player, yolanda, ganger
    ):
        client.force_login(player)
        page = client.get(edit_url(yolanda)).content.decode()
        assert "Save characteristics" in page
        for field_name in ("movement", "weapon_skill", "leadership"):
            assert f'name="statline-{field_name}"' in page

    def test_an_empty_box_suggests_what_the_entry_prints(self, client, player, yolanda):
        """Use the current profile value as the override field's placeholder."""
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
        # Prefill overridden fields and leave the others empty.
        page = client.get(edit_url(yolanda)).content.decode()
        assert 'value="4"' in box(page, "toughness")
        assert 'value=""' in box(page, "movement")
        # Show override attribution on the card beside the form.
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
        """Reject values beyond the storage limit and retain the rejected text beside its
        error.
        """
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
        """Submitting notes must not clear the separate characteristic form."""
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
    """Use the same overridden values in print and text cards."""

    def test_the_printed_card_carries_the_set_value(
        self, client, player, gang, yolanda, cell_for
    ):
        set_by_hand(yolanda, cell_for, toughness="12")
        client.force_login(player)
        response = client.get(reverse("n26-print", args=[gang.pk]))
        assert response.status_code == 200
        document = BeautifulSoup(response.content, "html.parser")
        headings = document.find_all("th", string="T")
        assert len(headings) == 1
        heading = headings[0]
        index = heading.parent.find_all("th").index(heading)
        cells = heading.parent.find_next_sibling("tr").find_all("td")
        assert cells[index].get_text(" ", strip=True) == "12"

    def test_the_text_card_carries_it_too(self, yolanda, cell_for):
        from n26.core.render_text import render_model_card

        set_by_hand(yolanda, cell_for, toughness="12")
        text = "\n".join(render_model_card(card_for(yolanda)))
        print("\n" + text)
        assert "12†" in text


class TestTheQueryBudget:
    """Batch model overrides with the roster so query counts do not grow per fighter."""

    def test_a_gang_of_them_costs_what_two_of_them_cost(self, gang, ganger, cell_for):
        """Give every compared model overrides so per-model reads would appear as query
        growth.
        """
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
        # Warm one-off caches before comparing query counts.
        measure()
        few, few_models = measure()

        for index in range(2, 8):
            recruit(f"Sister {index}")
        many, many_models = measure()

        assert (few_models, many_models) == (2, 8)
        assert few == many, f"{few} queries for 2 models, {many} for 8"
        assert_reconciled(gang)
