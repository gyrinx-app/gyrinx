"""Verify characteristic editing in the profile authoring form. Derive fields from its
profile type, create a statline when values are entered, format values canonically and
accept symbolic or dice values within storage limits. Clearing a form field removes its
value; omitted set_statline arguments instead preserve existing values.
"""

import pytest
from django.contrib.auth import get_user_model

from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.core.render_text import render_model_card
from n26.library.authoring import create_profile, set_statline
from n26.library.models import Statline, StatlineStat
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):

    user = get_user_model().objects.create_user(
        "statline-author", "statline-author@example.com", "password", is_staff=True
    )
    client.force_login(user)
    return user


@pytest.fixture
def ganger(person_type, gang_type):
    """Profile with distance, roll-target and plain-number characteristics."""
    return create_profile("Ganger", person_type, gang_type, price=50)


def edit(client, profile, statline=None, **overrides):
    """Submit the complete profile edit payload with edit-prefixed fields and
    statline-prefixed characteristics, matching the browser form.
    """
    payload = {
        "act": "edit",
        "edit-name": profile.name,
        "edit-profile_type": str(profile.profile_type_id),
        "edit-gang_type": str(profile.gang_type_id),
        "edit-price": str(profile.price),
        "edit-category": "",
        "edit-qualifier": profile.qualifier,
        "edit-library_author_help": profile.library_author_help,
    }
    for field_name, value in (statline or {}).items():
        payload[f"statline-{field_name}"] = value
    payload.update(overrides)
    return client.post(f"/n26/authoring/profile/{profile.pk}/", payload)


def stored(profile):
    """Read stored characteristic strings keyed by short name."""
    profile.refresh_from_db()
    return {
        stat.short_name: stat.value for stat in profile.statline.stats.select_related()
    }


class TestAProfileWithNoStatline:
    """Render fields from the profile type even before values exist. Create no statline
    when every field remains empty.
    """

    def test_every_characteristic_of_the_type_has_a_box(self, author, client, ganger):
        body = client.get(f"/n26/authoring/profile/{ganger.pk}/").content.decode()

        for field_name in ("movement", "weapon_skill", "toughness"):
            assert f'name="statline-{field_name}"' in body

    def test_the_boxes_suggest_the_kind_of_value_each_takes(
        self, author, client, ganger
    ):
        body = client.get(f"/n26/authoring/profile/{ganger.pk}/").content.decode()

        assert 'placeholder="4&quot;"' in body  # a distance
        assert 'placeholder="3+"' in body  # a roll target

    def test_filling_them_in_founds_the_statline(self, author, client, ganger):
        assert not ganger.has_statline

        response = edit(
            client,
            ganger,
            statline={"movement": "4", "weapon_skill": "3", "toughness": "3"},
        )

        assert response.status_code == 302
        assert stored(ganger) == {"M": '4"', "WS": "3+", "T": "3"}

    def test_a_value_is_stored_as_the_stat_says_it_reads(self, author, client, ganger):
        """Canonicalise values when storing them, using the same path as imports."""
        edit(client, ganger, statline={"movement": "4"})

        assert stored(ganger)["M"] == '4"'

    def test_saving_nothing_at_all_leaves_the_profile_without_one(
        self, author, client, ganger
    ):
        """Avoid creating an empty statline that would add a row of dashes to cards."""
        edit(
            client,
            ganger,
            statline={"movement": "", "weapon_skill": "", "toughness": ""},
        )

        ganger.refresh_from_db()
        assert not ganger.has_statline


class TestChangingAStatlineAlreadyThere:
    """Prefill the same edit form from stored values."""

    @pytest.fixture
    def written(self, ganger):
        set_statline(ganger, movement=4, weapon_skill=3, toughness=3)
        return ganger

    def test_the_boxes_open_on_what_is_stored(self, author, client, written):
        body = client.get(f"/n26/authoring/profile/{written.pk}/").content.decode()

        # Prefill the canonical values, including their distance and target suffixes.
        assert 'value="4&quot;"' in body
        assert 'value="3+"' in body

    def test_changing_some_leaves_the_others_as_they_were(
        self, author, client, written
    ):
        edit(
            client,
            written,
            statline={"movement": "5", "weapon_skill": "3+", "toughness": "3"},
        )

        assert stored(written) == {"M": '5"', "WS": "3+", "T": "3"}

    def test_a_value_resubmitted_untouched_does_not_drift(
        self, author, client, written
    ):
        """Canonical formatting must be idempotent when the form resubmits an already
        formatted value.
        """
        edit(
            client,
            written,
            statline={"movement": '4"', "weapon_skill": "3+", "toughness": "3"},
        )

        assert stored(written)["M"] == '4"'

    def test_a_cleared_box_takes_the_value_off(self, author, client, written):
        """Blank form input clears the value, unlike an omitted set_statline argument.
        Display the missing characteristic as a dash.
        """
        edit(
            client,
            written,
            statline={"movement": "", "weapon_skill": "3+", "toughness": "3"},
        )

        assert stored(written)["M"] == ""
        written.refresh_from_db()
        assert written.stats()["movement"] == "-"

    def test_the_profile_keeps_one_statline_however_often_it_is_saved(
        self, author, client, written
    ):
        for movement in ("5", "6", "7"):
            edit(client, written, statline={"movement": movement})

        assert Statline.objects.filter(profile=written).count() == 1
        assert StatlineStat.objects.filter(statline__profile=written).count() == 3

    def test_the_profiles_own_fields_save_in_the_same_click(
        self, author, client, written
    ):
        """Save profile fields and characteristics through one form submission."""
        edit(
            client,
            written,
            statline={"movement": "6", "weapon_skill": "3+", "toughness": "3"},
            **{"edit-name": "Ganger (Specialist)", "edit-price": "65"},
        )

        written.refresh_from_db()
        assert (written.name, written.price) == ("Ganger (Specialist)", 65)
        assert stored(written)["M"] == '6"'


class TestWhatAnAuthorMayType:
    """Accept symbolic and dice values as well as numbers. Reject values that exceed
    storage limits or contain multiple pasted characteristics.
    """

    def test_a_letter_standing_for_something_survives_as_typed(
        self, author, client, ganger
    ):
        edit(client, ganger, statline={"toughness": "S"})

        assert stored(ganger)["T"] == "S"

    def test_a_dice_roll_survives_as_typed(self, author, client, ganger):
        edit(client, ganger, statline={"toughness": "D6"})

        assert stored(ganger)["T"] == "D6"

    def test_a_value_too_long_to_store_is_refused_in_words(
        self, author, client, ganger
    ):
        response = edit(client, ganger, statline={"movement": "five inches or so"})

        assert response.status_code == 200
        body = response.content.decode()
        assert "Movement" in body
        assert "longer than 10 characters" in body

    def test_a_whole_row_pasted_into_one_box_is_refused_in_words(
        self, author, client, ganger
    ):
        response = edit(client, ganger, statline={"movement": "4,3,3"})

        assert response.status_code == 200
        assert "one characteristic" in response.content.decode()

    def test_a_refusal_writes_nothing_at_all(self, author, client, ganger):
        """Profile and statline changes must commit together or both roll back."""
        response = edit(
            client,
            ganger,
            statline={"movement": "four inches or so", "toughness": "3"},
            **{"edit-name": "Ganger (Specialist)"},
        )

        assert response.status_code == 200
        ganger.refresh_from_db()
        assert ganger.name == "Ganger"
        assert not ganger.has_statline

    def test_what_was_typed_is_shown_back_after_a_refusal(self, author, client, ganger):
        """Preserve rejected input in the form so the error refers to text still visible to
        the author.
        """
        response = edit(client, ganger, statline={"movement": "five inches or so"})

        assert 'value="five inches or so"' in response.content.decode()


class TestTheCardShowsWhatWasAuthored:
    """Model cards read the profile's authored characteristics."""

    def test_a_hired_model_prints_the_edited_statline(
        self, author, client, ganger, gang_type
    ):
        edit(
            client,
            ganger,
            statline={"movement": "4", "weapon_skill": "3", "toughness": "3"},
        )
        gang = found_gang(
            "The Authored",
            gang_type,
            owner=get_user_model().objects.create_user("player"),
            budget=500,
        )
        fighter = hire(gang, ganger, "Yolanda", paid=50)

        text = "\n".join(render_model_card(build_model_card(fighter)))
        print("\n" + text)

        assert '4"' in text  # the Movement, formatted by the stat
        assert "3+" in text  # the Weapon Skill, a roll target
        assert_reconciled(gang)

    def test_a_later_edit_reaches_a_card_already_hired(
        self, author, client, ganger, gang_type
    ):
        """Read characteristic values from library content at render time so corrections
        reach existing fighters.
        """
        edit(client, ganger, statline={"movement": "4"})
        gang = found_gang(
            "The Corrected",
            gang_type,
            owner=get_user_model().objects.create_user("second-player"),
            budget=500,
        )
        fighter = hire(gang, ganger, "Yolanda", paid=50)

        edit(client, ganger, statline={"movement": "6"})

        text = "\n".join(render_model_card(build_model_card(fighter)))
        assert '6"' in text
        assert_reconciled(gang)
