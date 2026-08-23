"""Editing a standing gang: name, colour, and the credits budget.

The budget edit is where the money model shows. Its floor is the gang's
wealth, what a raised budget leaves over lands in credits — the budget
less everything actually spent — and a budget set to exactly the gang's
wealth leaves exactly 0¢ in hand.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def gang(tester, gang_type):
    """Founded without a budget — the founding default, and the gang most
    likely to be handed one later, when a campaign fixes it."""
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=None,
        credits=0,
    )


@pytest.fixture
def worth_eighty(tester, gang, make_profile, make_statline):
    """The gang with 80¢ of model on its books."""
    profile = make_profile("Ganger", price=80)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        op.hire(profile, "Vex")
    gang.refresh_from_db()
    assert gang.wealth == 80
    return gang


def edit_url(gang):
    return reverse("n26-edit-gang", args=[gang.pk])


class TestThePage:
    def test_the_sheet_offers_the_way_here(self, client, tester, gang):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert edit_url(gang) in body

    def test_the_form_arrives_filled_with_the_gang(self, client, tester, gang):
        gang.colour = "amber"
        gang.starting_credits = 1000
        gang.credits = 1000
        gang.save()
        client.force_login(tester)
        body = client.get(edit_url(gang)).content.decode()
        assert 'value="The Ashen Choir"' in body
        assert 'value="1000"' in body
        # The type is a fact, not a field: stated, never offered.
        assert "Fixed at founding." in body
        assert 'name="gang_type"' not in body

    def test_a_stranger_gets_a_404(self, client, gang):
        client.force_login(User.objects.create_user("someone-else"))
        assert client.get(edit_url(gang)).status_code == 404
        assert client.post(edit_url(gang), {"name": "Mine Now"}).status_code == 404


class TestRenaming:
    def test_name_and_colour_save(self, client, tester, gang):
        client.force_login(tester)
        response = client.post(
            edit_url(gang), {"name": "The Rust Sermon", "colour": "amber"}
        )
        assert response.status_code == 302
        assert response.url == reverse("n26-gang", args=[gang.pk])
        gang.refresh_from_db()
        assert gang.name == "The Rust Sermon"
        assert gang.colour == "amber"
        # No budget was set, so none appears.
        assert gang.starting_credits is None
        assert gang.credits == 0


class TestTheBudget:
    def test_a_budget_above_wealth_leaves_the_difference_in_hand(
        self, client, tester, worth_eighty
    ):
        gang = worth_eighty
        client.force_login(tester)
        response = client.post(
            edit_url(gang), {"name": gang.name, "starting_credits": "100"}
        )
        assert response.status_code == 302
        gang.refresh_from_db()
        assert gang.starting_credits == 100
        assert gang.credits == 20
        assert gang.wealth == 100
        assert_reconciled(gang)

    def test_a_budget_of_exactly_wealth_leaves_exactly_nothing(
        self, client, tester, worth_eighty
    ):
        """ "I spent all my money": the budget is what the gang is worth,
        and the credit limit is exactly 0."""
        gang = worth_eighty
        client.force_login(tester)
        client.post(edit_url(gang), {"name": gang.name, "starting_credits": "80"})
        gang.refresh_from_db()
        assert gang.starting_credits == 80
        assert gang.credits == 0
        assert not gang.credits_unlimited
        assert_reconciled(gang)

    def test_a_budget_below_wealth_is_refused_and_nothing_changes(
        self, client, tester, worth_eighty
    ):
        gang = worth_eighty
        client.force_login(tester)
        response = client.post(
            edit_url(gang), {"name": "Sneaky Rename", "starting_credits": "79"}
        )
        # Redisplayed with the refusal, and the gang untouched — the name
        # does not save while the budget is refused, because a form is
        # one answer.
        assert response.status_code == 200
        assert "worth 80¢" in response.content.decode()
        gang.refresh_from_db()
        assert gang.name == "The Ashen Choir"
        assert gang.starting_credits is None
        assert_reconciled(gang)

    def test_a_blank_budget_clears_the_limit(self, client, tester, worth_eighty):
        gang = worth_eighty
        gang.starting_credits = 100
        gang.credits = 20
        gang.save()
        client.force_login(tester)
        client.post(edit_url(gang), {"name": gang.name, "starting_credits": ""})
        gang.refresh_from_db()
        assert gang.credits_unlimited
        # No budget: nothing to count down from, pinned to 0 and drawn
        # as "no answer" rather than as a figure.
        assert gang.credits == 0
        assert_reconciled(gang)

    def test_raising_an_existing_budget_raises_the_cash(
        self, client, tester, worth_eighty
    ):
        """The identity every screen shows holds through the edit:
        credits are the budget less everything spent."""
        gang = worth_eighty
        client.force_login(tester)
        client.post(edit_url(gang), {"name": gang.name, "starting_credits": "100"})
        client.post(edit_url(gang), {"name": gang.name, "starting_credits": "150"})
        gang.refresh_from_db()
        assert gang.starting_credits == 150
        assert gang.credits == 70
        assert_reconciled(gang)

    def test_an_untouched_budget_never_blocks_a_rename(self):
        """Discounted buys and granted content can push a gang's worth
        past its budget; the floor binds the change, not the standing
        state, so a rename with the budget left alone must clean."""
        from types import SimpleNamespace

        from n26.core.forms import EditGangForm

        under_water = SimpleNamespace(
            name="The Ashen Choir", starting_credits=100, wealth=104
        )
        unchanged = EditGangForm(
            under_water, data={"name": "Renamed Anyway", "starting_credits": "100"}
        )
        assert unchanged.is_valid()
        lowered = EditGangForm(
            under_water, data={"name": "Renamed Anyway", "starting_credits": "101"}
        )
        assert not lowered.is_valid()
        assert "worth 104¢" in str(lowered.errors["starting_credits"])

    def test_a_budgeted_gang_cannot_shrink_below_its_wealth(
        self, client, tester, worth_eighty
    ):
        gang = worth_eighty
        client.force_login(tester)
        client.post(edit_url(gang), {"name": gang.name, "starting_credits": "100"})
        gang.refresh_from_db()
        assert gang.wealth == 100
        response = client.post(
            edit_url(gang), {"name": gang.name, "starting_credits": "90"}
        )
        assert response.status_code == 200
        assert "worth 100¢" in response.content.decode()
        gang.refresh_from_db()
        assert gang.starting_credits == 100
        assert_reconciled(gang)


def png_upload(name="banner.png"):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (16, 9), "teal").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class TestNotesLoreAndPicture:
    """The gang's own written fields and picture, saved with the rest of
    the form and recorded as acts on the gang itself."""

    def test_notes_and_lore_save_and_are_recorded(self, client, tester, gang):
        client.force_login(tester)
        response = client.post(
            edit_url(gang),
            {
                "act": "story",
                "notes": "<p>Meet at the sump gate.</p>",
                "lore": "<p>Founded on a debt.</p>",
            },
        )
        assert response.status_code == 302
        gang.refresh_from_db()
        assert gang.notes == "<p>Meet at the sump gate.</p>"
        assert gang.lore == "<p>Founded on a debt.</p>"
        recorded = LedgerEvent.objects.filter(gang=gang, miniature=None)
        assert recorded.filter(kind=LedgerEvent.Kind.NOTED).count() == 1
        assert recorded.filter(kind=LedgerEvent.Kind.LORE_EDITED).count() == 1

    def test_an_unchanged_field_writes_no_event(self, client, tester, gang):
        client.force_login(tester)
        words = {"act": "story", "notes": "<p>same</p>", "lore": ""}
        client.post(edit_url(gang), words)
        client.post(edit_url(gang), words)
        assert (
            LedgerEvent.objects.filter(gang=gang, kind=LedgerEvent.Kind.NOTED).count()
            == 1
        )

    def test_the_history_says_what_happened_in_gang_words(self, client, tester, gang):
        client.force_login(tester)
        client.post(
            edit_url(gang),
            {
                "act": "story",
                "notes": "<p>Meet at the sump gate.</p>",
                "lore": "<p>Founded on a debt.</p>",
            },
        )
        body = client.get(reverse("n26-gang-history", args=[gang.pk])).content.decode()
        assert (
            "edited the gang&#x27;s notes" in body or "edited the gang's notes" in body
        )
        assert "edited the gang&#x27;s lore" in body or "edited the gang's lore" in body

    def test_a_form_without_the_boxes_clears_nothing(self, client, tester, gang):
        gang.notes = "<p>Meet at the sump gate.</p>"
        gang.lore = "<p>Founded on a debt.</p>"
        gang.save(update_fields=["notes", "lore"])
        client.force_login(tester)
        client.post(edit_url(gang), {"name": gang.name})
        gang.refresh_from_db()
        assert gang.notes == "<p>Meet at the sump gate.</p>"
        assert gang.lore == "<p>Founded on a debt.</p>"

    def test_the_notes_tab_reads_them_back(self, client, tester, gang):
        gang.notes = "<p>Meet at the sump gate.</p>"
        gang.save(update_fields=["notes"])
        client.force_login(tester)
        general = client.get(edit_url(gang)).content.decode()
        notes_tab = client.get(edit_url(gang) + "?tab=notes").content.decode()
        assert "Meet at the sump gate" not in general
        assert "Meet at the sump gate" in notes_tab
        # The tab strip on both, saying which is current.
        assert "?tab=notes" in general
        assert 'aria-current="page"' in notes_tab

    def test_the_picture_is_stored_removed_and_otherwise_left_be(
        self, client, tester, gang, own_storage
    ):
        client.force_login(tester)
        client.post(edit_url(gang), {"act": "picture", "image": png_upload()})
        gang.refresh_from_db()
        assert gang.image.name.startswith("gang-images/")
        held = gang.image.name

        # A save of the gang's own form never touches the picture.
        client.post(edit_url(gang), {"name": gang.name})
        gang.refresh_from_db()
        assert gang.image.name == held

        client.post(edit_url(gang), {"act": "picture", "remove_image": "on"})
        gang.refresh_from_db()
        assert not gang.image
        recorded = LedgerEvent.objects.filter(gang=gang, miniature=None)
        assert recorded.filter(kind=LedgerEvent.Kind.IMAGE_SET).count() == 1
        assert recorded.filter(kind=LedgerEvent.Kind.IMAGE_CLEARED).count() == 1

    def test_the_crop_dialog_is_told_the_servers_own_shape(self, client, tester, gang):
        """The shape and cap on the file input are str() of the constants
        the server crops with, so the dialog and the store cannot come
        apart."""
        from n26.core.images import LANDSCAPE, MAX_PX

        client.force_login(tester)
        body = client.get(edit_url(gang) + "?tab=notes").content.decode()
        assert f'data-crop="{LANDSCAPE}"' in body
        assert f'data-crop-max="{MAX_PX}"' in body
