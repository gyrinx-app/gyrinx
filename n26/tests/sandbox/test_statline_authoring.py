"""Typing a fighter's characteristics on the page that authors it.

A profile's statline is a row of small numbers, and it is edited where the
rest of the profile is edited: same page, same form, same Save. The shape
of that form is content — it comes from the statline type the profile's
Type calls for — so no spec describes it and nothing generates it.

The rules this file pins:

* A profile with no statline still shows every box, and filling them in is
  how a statline comes to exist.
* An author types the bare thing and the stored value is canonical: 4 for
  a Movement is held, and shown back, as ``4"``.
* Almost nothing is refused. ``S`` for the wielder's Strength and ``D6``
  are as real as ``4``; only what cannot be stored is turned away.
* An empty box means no value — the one place this parts company with
  ``set_statline``, which leaves a characteristic it is not told about
  alone.
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
    """Staff, because the authoring pages sit behind the admin gate."""
    user = get_user_model().objects.create_user(
        "statline-author", "statline-author@example.com", "password", is_staff=True
    )
    client.force_login(user)
    return user


@pytest.fixture
def ganger(person_type, gang_type):
    """A profile carrying the three-stat shape: a distance, a roll target
    and a plain number, which is one of each display rule."""
    return create_profile("Ganger", person_type, gang_type, price=50)


def edit(client, profile, statline=None, **overrides):
    """Post the profile's page the way the browser does.

    The whole form goes every time — its own fields prefixed ``edit`` and
    the characteristics prefixed ``statline`` — because that is what a
    click of Save sends, and a payload naming only the field under test
    would prove the view tolerates something no browser produces.
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
    """``{short name: the stored string}`` — what a page would read back."""
    profile.refresh_from_db()
    return {
        stat.short_name: stat.value for stat in profile.statline.stats.select_related()
    }


class TestAProfileWithNoStatline:
    """The case that matters most, because it is how one gets created.

    Nothing is missing when a profile has no statline: the shape is known
    from the profile's Type, so every box is there and empty, and filling
    them in founds the row.
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
        """An author types 4 for a Movement and it lands as 4", because
        every surface should agree without each one remembering to
        format. The form does not do this — the value does, on the way
        into the database, by the same path an importer takes."""
        edit(client, ganger, statline={"movement": "4"})

        assert stored(ganger)["M"] == '4"'

    def test_saving_nothing_at_all_leaves_the_profile_without_one(
        self, author, client, ganger
    ):
        """A profile whose page was opened and saved with the statline
        untouched has still not been given one — an empty statline of
        empty values would print a row of dashes on every card."""
        edit(
            client,
            ganger,
            statline={"movement": "", "weapon_skill": "", "toughness": ""},
        )

        ganger.refresh_from_db()
        assert not ganger.has_statline


class TestChangingAStatlineAlreadyThere:
    """Editing is the same form, opened on what is stored."""

    @pytest.fixture
    def written(self, ganger):
        set_statline(ganger, movement=4, weapon_skill=3, toughness=3)
        return ganger

    def test_the_boxes_open_on_what_is_stored(self, author, client, written):
        body = client.get(f"/n26/authoring/profile/{written.pk}/").content.decode()

        # The canonical value, quote mark and all — the same string the
        # card prints, so the author is never left wondering whose mark
        # it is.
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
        """The box shows 4" and posts 4" back. Formatting a value that is
        already formatted has to be a no-op, or every save would add
        another quote mark."""
        edit(
            client,
            written,
            statline={"movement": '4"', "weapon_skill": "3+", "toughness": "3"},
        )

        assert stored(written)["M"] == '4"'

    def test_a_cleared_box_takes_the_value_off(self, author, client, written):
        """The one place this parts company with ``set_statline``. That
        verb leaves a characteristic it is not told about alone, which is
        right for a spreadsheet with an absent column and wrong for a
        person looking at a box: an author who cannot empty one is stuck
        with a typo forever. A card prints the absence as a dash."""
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
        """One form, one Save. The statline is not a second thing to
        remember to submit."""
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
    """Almost anything, and the exceptions are about storage, not taste.

    A characteristic is not always a number: a weapon's Strength can be
    the wielder's own, a value can be rolled. Refusing those would make
    the editor turn away content the spreadsheet importer accepts.
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

        assert response.status_code == 200  # back on the page, not a 500
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
        """Both halves of the form save together or not at all — a page
        that took the new name and dropped the statline would leave the
        author unsure which of the two clicks had landed."""
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
        """The box keeps the rejected text. Redrawn from the database it
        would show the old value, and the author would be reading a
        complaint about something not on the screen."""
        response = edit(client, ganger, statline={"movement": "five inches or so"})

        assert 'value="five inches or so"' in response.content.decode()


class TestTheCardShowsWhatWasAuthored:
    """The point of all of it: what the author typed is what a player's
    card prints."""

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
        """Statlines are read from the library at render time, not copied
        onto the model at hire. Correcting a profile's characteristics is
        therefore a correction to every fighter hired from it."""
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
