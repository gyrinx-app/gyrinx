"""Owners edit the hire's rating while equipment and advancements keep adding."""

import json
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.history import build as build_history
from n26.core.models import Assignment, LedgerEvent, Miniature
from n26.core.operations import Refusal, operation
from n26.core.rating import read_rating_receipt
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.core.status import Status
from n26.tests.sandbox.actions import (
    buy,
    create_default_set,
    create_rule,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire_with_option,
    offer_option,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(gang_type):
    owner = User.objects.create_user("player")
    return found_gang("The Ashen Choir", gang_type, owner=owner, budget=1000)


@pytest.fixture
def vex(gang, make_profile, make_statline):
    profile = make_profile("Ganger", price=100)
    make_statline(profile)
    miniature = hire_with_option(gang, profile, "Vex", paid=80, rating=100)
    buy(miniature, thing=create_wargear("Armour", price=20))
    return miniature


def rating_url(miniature):
    return reverse("n26-base-rating", args=[miniature.pk])


def edit_url(miniature):
    return reverse("n26-edit-fighter", args=[miniature.pk])


class TestTheRatingPencil:
    def test_the_pencil_is_immediately_right_of_the_rating_on_edit(
        self, client, gang, vex
    ):
        client.force_login(gang.owner)
        response = client.get(edit_url(vex))
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        pencil = soup.find("a", attrs={"aria-label": "Override Vex's base rating"})
        assert pencil["href"] == rating_url(vex)
        assert pencil["hx-get"] == rating_url(vex)
        assert pencil["hx-swap"] == "none"
        assert "120¢" in pencil.find_previous_sibling("div").get_text()

    @pytest.mark.parametrize("route", ["n26-gang", "n26-equip", "n26-fighter-options"])
    def test_other_screens_do_not_offer_the_pencil(self, client, gang, vex, route):
        client.force_login(gang.owner)
        response = client.get(
            reverse(route, args=[gang.pk if route == "n26-gang" else vex.pk])
        )
        assert response.status_code == 200
        assert "Override Vex&#x27;s base rating" not in response.content.decode()
        assert rating_url(vex) not in response.content.decode()

    def test_a_partial_card_update_keeps_the_pencil(self, client, gang, vex):
        from n26.core.views.edit import render_card_update

        client.force_login(gang.owner)
        request = client.get(edit_url(vex)).wsgi_request
        response = render_card_update(request, vex, edit_url(vex))
        assert rating_url(vex) in response.content.decode()

    def test_the_form_opens_with_base_rating_rather_than_total(self, client, gang, vex):
        client.force_login(gang.owner)
        response = client.get(rating_url(vex))
        assert response.status_code == 200
        assert response.context["form"].initial["rating"] == 100
        assert 'value="100"' in response.content.decode()
        assert_reconciled(gang)


class TestTheRatingDialog:
    def test_open_query_count_does_not_grow_with_models_or_equipment(
        self, client, gang, vex, make_profile
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(gang.owner)

        def queries():
            client.get(rating_url(vex), HTTP_HX_REQUEST="true")
            with CaptureQueriesContext(connection) as captured:
                response = client.get(rating_url(vex), HTTP_HX_REQUEST="true")
                assert response.status_code == 200
            return len(captured)

        before = queries()
        profile = make_profile("More fighters", price=100)
        for number in range(5):
            hire_with_option(gang, profile, f"Extra {number}", paid=100, rating=100)
            buy(vex, thing=create_wargear(f"Extra armour {number}", price=20))
        assert queries() <= before

    def test_open_is_only_a_dialog_with_the_hire_contribution(self, client, gang, vex):
        client.force_login(gang.owner)
        response = client.get(rating_url(vex), HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        assert response["HX-Replace-Url"] == f"{edit_url(vex)}?rating=1"
        props = response.context["rating_dialog"]
        assert props["value"] == "100"
        assert "name" not in props
        assert props["csrfToken"]
        assert props["errors"] == []
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id="n26-rating-dialog-host")["hx-swap-oob"] == "true"
        assert soup.find("html") is None
        assert "n26-model-card-host" not in response.content.decode()

    def test_reload_keeps_the_dialog_open(self, client, gang, vex):
        client.force_login(gang.owner)
        response = client.get(edit_url(vex), {"rating": "1"})
        assert response.context["rating_dialog"]["value"] == "100"

    def test_invalid_rating_redraws_bound_errors(self, client, gang, vex):
        client.force_login(gang.owner)
        response = client.post(
            rating_url(vex), {"rating": "1.5"}, HTTP_HX_REQUEST="true"
        )
        props = response.context["rating_dialog"]
        assert props["value"] == "1.5"
        assert props["errors"]
        assert response.status_code == 200
        assert "n26-gang-wealth" not in response.content.decode()
        vex.refresh_from_db()
        assert vex.rating == 120

    def test_save_updates_only_numbers_and_closes_dialog(self, client, gang, vex):
        client.force_login(gang.owner)
        response = client.post(rating_url(vex), {"rating": 150}, HTTP_HX_REQUEST="true")
        soup = BeautifulSoup(response.content, "html.parser")
        rating = soup.find(id=f"n26-model-rating-{vex.pk}")
        assert "170¢" in rating.get_text()
        assert rating["hx-swap-oob"] == "true"
        pencil = rating.find("a", attrs={"aria-label": "Override Vex's base rating"})
        assert pencil["hx-get"] == rating_url(vex)
        assert soup.find(id="n26-gang-figures")["hx-swap-oob"] == "true"
        assert "170¢" in soup.find(id="n26-gang-wealth").get_text()
        assert not soup.find(id="n26-rating-dialog-host").get_text(strip=True)
        assert soup.find(id="n26-model-card-host") is None
        assert soup.find("textarea") is None
        assert response["HX-Replace-Url"] == edit_url(vex)
        assert "Base rating saved." in response["HX-Trigger"]
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_htmx_save_still_requires_csrf(self, gang, vex):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(gang.owner)
        response = client.post(rating_url(vex), {"rating": 0}, HTTP_HX_REQUEST="true")
        # The project's CSRF failure view redirects to the homepage.
        assert response.status_code == 302
        assert response.url == "/"
        assert not gang.ledger_events.filter(kind=LedgerEvent.Kind.RATING_SET).exists()
        vex.refresh_from_db()
        assert vex.rating == 120


class TestSavingBaseRating:
    def test_removing_an_override_restores_the_recorded_hire_rating(
        self, client, gang, vex
    ):
        client.force_login(gang.owner)
        client.post(rating_url(vex), {"rating": 150})
        client.post(rating_url(vex), {"rating": 175})
        opened = client.get(rating_url(vex), HTTP_HX_REQUEST="true")
        assert opened.context["rating_dialog"]["defaultRating"] == 100
        assert opened.context["rating_dialog"]["hasOverride"]
        response = client.post(
            rating_url(vex),
            {"act": "remove-override", "rating": "invalid"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert "Base rating override removed." in response["HX-Trigger"]
        vex.refresh_from_db()
        gang.refresh_from_db()
        assert vex.rating == 120
        assert vex.membership.ledger_entry.rating_contribution == 100
        assert vex.membership.ledger_entry.paid == 80
        act = build_history(gang, viewer=gang.owner)[-1]
        assert "".join(span.text for span in act.spans) == "reset Vex's base rating"
        assert act.actor == "You"
        assert act.rating == -75
        assert (
            gang.ledger_events.order_by("created", "pk").last().kind
            == LedgerEvent.Kind.RATING_RESET
        )
        assert "rating-tooltip" in response.content.decode()
        assert_reconciled(gang)
        opened = client.get(rating_url(vex), HTTP_HX_REQUEST="true")
        assert not opened.context["rating_dialog"]["hasOverride"]

    def test_repeated_removal_writes_no_extra_event(self, client, gang, vex):
        client.force_login(gang.owner)
        client.post(rating_url(vex), {"rating": 150})
        client.post(rating_url(vex), {"act": "remove-override"})
        before = gang.ledger_events.count()
        client.post(rating_url(vex), {"act": "remove-override"})
        assert gang.ledger_events.count() == before
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_removal_keeps_later_hire_option_changes(self, gang, vex):
        from n26.core.models import LedgerEvent

        # A later option change moves the hire's underlying contribution.
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(vex, 150)
            membership = vex.membership
            entry = membership.ledger_entry
            entry.refresh_from_db()
            entry.rating_contribution += 30
            entry.save(update_fields=["rating_contribution", "modified"])
            op.event(membership, LedgerEvent.Kind.AMENDED, rating_delta=30)
            op.touched(vex)
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(vex, None)
        vex.refresh_from_db()
        assert vex.membership.ledger_entry.rating_contribution == 130
        assert vex.rating == 150
        assert_reconciled(gang)

    @pytest.mark.parametrize("rating", [150, 50, 0, -10])
    def test_only_the_hire_rating_changes(self, client, gang, vex, rating):
        client.force_login(gang.owner)
        before_credits = gang.credits
        before_entries = list(gang.ledger_events.values_list("pk", flat=True))
        response = client.post(rating_url(vex), {"rating": rating})
        assert response.status_code == 302
        assert response.url == edit_url(vex)
        vex.refresh_from_db()
        gang.refresh_from_db()
        entry = vex.membership.ledger_entry
        assert entry.rating_contribution == rating
        assert entry.paid == 80
        assert entry.list_price == 80
        assert entry.discount == 0
        assert vex.rating == rating + 20
        assert gang.rating == rating + 20
        assert gang.credits == before_credits
        event = gang.ledger_events.exclude(pk__in=before_entries).get()
        assert event.kind == LedgerEvent.Kind.RATING_SET
        assert event.assignment == vex.membership
        assert event.actor == gang.owner
        assert event.rating_delta == rating - 100
        assert event.credits_delta == 0
        assert event.trade_points_delta == 0
        assert_reconciled(gang)

    def test_later_equipment_and_advancements_still_add_to_rating(self, gang, vex):
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(vex, 150)
            op.assign(create_rule("Strength advancement"), miniature=vex, rating=30)
        buy(vex, thing=create_wargear("Respirator", price=10))
        vex.refresh_from_db()
        gang.refresh_from_db()
        assert vex.rating == 210
        assert gang.rating == 210
        assert_reconciled(gang)

    def test_history_names_the_model_and_base_rating(self, client, gang, vex):
        client.force_login(gang.owner)
        client.post(rating_url(vex), {"rating": 150})
        act = build_history(gang, viewer=gang.owner)[-1]
        assert "".join(span.text for span in act.spans) == "changed Vex's base rating"
        assert act.category == "model"
        assert act.rating == 50
        assert act.credits == 0
        assert act.note == "Base rating 100¢ → 150¢"

    def test_repeated_saves_with_stale_objects_write_once(self, gang, vex):
        stale = Miniature.objects.select_related("membership__ledger_entry").get(
            pk=vex.pk
        )
        with operation(gang, actor=gang.owner) as op:
            assert op.set_base_rating(vex, 150)
        with operation(gang, actor=gang.owner) as op:
            assert not op.set_base_rating(stale, 150)
        assert gang.ledger_events.filter(kind=LedgerEvent.Kind.RATING_SET).count() == 1
        assert_reconciled(gang)

    @pytest.mark.parametrize("rating", ["", "1.5", "text", str(2**31), str(-(2**31))])
    def test_invalid_values_show_errors_without_writing(
        self, client, gang, vex, rating
    ):
        client.force_login(gang.owner)
        response = client.post(rating_url(vex), {"rating": rating})
        assert response.status_code == 200
        assert "rating" in response.context["form"].errors
        assert not gang.ledger_events.filter(kind=LedgerEvent.Kind.RATING_SET).exists()
        vex.refresh_from_db()
        assert vex.rating == 120
        assert_reconciled(gang)

    def test_a_change_larger_than_a_ledger_delta_is_refused(self, gang, vex):
        with pytest.raises(Refusal, match="too large"):
            with operation(gang, actor=gang.owner) as op:
                op.set_base_rating(vex, -(2**31) + 1)
        assert_reconciled(gang)

    @pytest.mark.parametrize("overflow", ["model", "gang"])
    @pytest.mark.parametrize("status", [Status.ACTIVE, Status.DEAD])
    def test_a_base_rating_that_overflows_a_total_is_refused_without_writing(
        self, client, gang, vex, make_profile, overflow, status
    ):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(vex, status)
        rating = 2**31 - 1
        if overflow == "gang":
            hire_with_option(
                gang, make_profile("Extra", price=100), "Extra", paid=100, rating=100
            )
            rating -= 20
        client.force_login(gang.owner)
        response = client.post(
            rating_url(vex), {"rating": rating}, HTTP_HX_REQUEST="true"
        )
        assert response.status_code == 200
        assert "too large" in response.context["rating_dialog"]["formErrors"][0]
        assert not gang.ledger_events.filter(kind=LedgerEvent.Kind.RATING_SET).exists()
        vex.refresh_from_db()
        assert vex.rating == (0 if status == Status.DEAD else 120)
        assert vex.membership.ledger_entry.rating_contribution == 100
        assert_reconciled(gang)

        with operation(gang, actor=gang.owner) as op:
            op.set_status(vex, Status.ACTIVE)
        vex.refresh_from_db()
        assert vex.rating == 120
        assert_reconciled(gang)

    def test_a_safe_override_on_a_dead_model_is_kept_when_reactivated(self, gang, vex):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(vex, Status.DEAD)
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(vex, 150)
        vex.refresh_from_db()
        assert vex.rating == 0
        assert_reconciled(gang)
        with operation(gang, actor=gang.owner) as op:
            op.set_status(vex, Status.ACTIVE)
        vex.refresh_from_db()
        assert vex.rating == 170
        assert_reconciled(gang)


class TestRatingSettlement:
    def test_the_lowest_accepted_override_can_still_be_refunded(
        self, gang, make_profile
    ):
        model = hire_with_option(gang, make_profile("Ganger", price=100), "Vex")
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(model, -(2**31) + 100)
        with pytest.raises(Refusal, match="Enter a whole number"):
            with operation(gang, actor=gang.owner) as op:
                op.set_base_rating(model, -(2**31))
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(model, -(2**31) + 1)
        with operation(gang, actor=gang.owner) as op:
            op.refund(model.membership)
        gang.refresh_from_db()
        assert gang.rating == 0
        assert gang.credits == 1000
        refunded = gang.ledger_events.get(kind=LedgerEvent.Kind.REFUNDED)
        assert refunded.rating_delta == 2**31 - 1
        assert_reconciled(gang)

    @pytest.mark.parametrize("direction", [1, -1])
    def test_an_option_cannot_push_an_override_past_the_refundable_range(
        self, gang, make_profile, direction
    ):
        profile = make_profile("Ganger", price=100)
        standard = create_default_set("Standard", price=0)
        upgrade = create_default_set("Upgrade", price=1)
        offer_option(profile, "Standard", default_set=standard, position=0)
        offer_option(profile, "Upgrade", default_set=upgrade, position=1)
        model = hire_with_option(
            gang, profile, "Vex", option=standard if direction == 1 else upgrade
        )
        boundary = direction * (2**31 - 1)
        if direction == -1:
            with operation(gang, actor=gang.owner) as op:
                op.set_base_rating(model, -(2**31) + 101)
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(model, boundary)
        credits = gang.credits
        events = gang.ledger_events.count()
        with pytest.raises(Refusal, match="resulting base rating"):
            with operation(gang, actor=gang.owner) as op:
                op.rechoose(
                    model.membership, option=upgrade if direction == 1 else standard
                )
        gang.refresh_from_db()
        model.membership.ledger_entry.refresh_from_db()
        assert model.membership.ledger_entry.rating_contribution == boundary
        assert gang.credits == credits
        assert gang.ledger_events.count() == events
        assert model.membership.chosen_options.get().default_set == (
            standard if direction == 1 else upgrade
        )
        assert_reconciled(gang)

    @pytest.mark.parametrize("overflow", ["model", "gang", "stash"])
    def test_a_later_purchase_that_overflows_rating_rolls_back(
        self, gang, vex, make_profile, overflow
    ):
        holder = vex
        if overflow == "stash":
            holder = gang.stash
            with operation(gang, actor=gang.owner) as op:
                op.assign(create_wargear("Stored gear"), stash=holder, rating=2**31 - 1)
        else:
            base = 2**31 - 21
            if overflow == "gang":
                holder = hire_with_option(
                    gang,
                    make_profile("Extra", price=100),
                    "Extra",
                    paid=100,
                    rating=100,
                )
                base -= 100
            with operation(gang, actor=gang.owner) as op:
                op.set_base_rating(vex, base)
        gear = create_wargear("Extra gear", price=1)
        credits = gang.credits
        events = gang.ledger_events.count()
        with pytest.raises(Refusal, match="resulting rating"):
            buy(holder, thing=gear)
        gang.refresh_from_db()
        vex.refresh_from_db()
        holder.refresh_from_db()
        assert gang.credits == credits
        assert gang.ledger_events.count() == events
        assert not Assignment.objects.filter(gang_root=gang, wargear=gear).exists()
        assert_reconciled(gang)

    def test_a_dead_model_cannot_be_reactivated_after_the_gang_rating_grows(
        self, gang, vex, make_profile
    ):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(vex, Status.DEAD)
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(vex, 2**31 - 21)
        hire_with_option(
            gang, make_profile("Extra", price=100), "Extra", paid=100, rating=100
        )
        events = gang.ledger_events.count()
        with pytest.raises(Refusal, match="resulting rating"):
            with operation(gang, actor=gang.owner) as op:
                op.set_status(vex, Status.ACTIVE)
        gang.refresh_from_db()
        vex.refresh_from_db()
        assert vex.status == Status.DEAD
        assert vex.rating == 0
        assert gang.rating == 100
        assert gang.ledger_events.count() == events
        assert_reconciled(gang)


class TestRatingOverrideMarker:
    def test_marker_uses_the_recorded_rating_and_keeps_equipment_separate(
        self, gang, vex
    ):
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(vex, 150)
        # A later library edit must not rewrite the explanation of a purchase.
        profile = vex.membership.profile
        profile.price = 500
        profile.save(update_fields=["price"])
        vex.refresh_from_db()
        assert build_model_card(vex).rating_override == {
            "name": "Vex",
            "rating": 170,
            "baseRating": 150,
            "defaultBaseRating": 100,
        }

    @pytest.mark.parametrize("route", ["n26-gang", "n26-equip", "n26-fighter-options"])
    def test_override_is_explained_wherever_a_model_card_appears(
        self, client, gang, vex, route
    ):
        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(vex, 150)
        client.force_login(gang.owner)
        response = client.get(
            reverse(route, args=[gang.pk if route == "n26-gang" else vex.pk])
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        rating = soup.find(id=f"n26-model-rating-{vex.pk}")
        assert rating.find(class_="decoration-dashed")
        props = json.loads(rating.find("script", type="application/json").string)
        assert props == {
            "name": "Vex",
            "rating": 170,
            "baseRating": 150,
            "defaultBaseRating": 100,
        }

    def test_save_refreshes_the_receipt_and_reset_removes_the_override_line(
        self, client, gang, vex
    ):
        client.force_login(gang.owner)
        saved = client.post(rating_url(vex), {"rating": 150}, HTTP_HX_REQUEST="true")
        soup = BeautifulSoup(saved.content, "html.parser")
        rating = soup.find(id=f"n26-model-rating-{vex.pk}")
        assert rating["hx-swap-oob"] == "true"
        props = json.loads(rating.find("script", type="application/json").string)
        assert props["receipt"]["overrideDelta"] == 50
        assert props["receipt"]["total"] == 170
        renamed = client.post(
            reverse("n26-rename-fighter", args=[vex.pk]) + "?back=edit",
            {"name": "Karn"},
            HTTP_HX_REQUEST="true",
        )
        soup = BeautifulSoup(renamed.content, "html.parser")
        assert soup.find("a", attrs={"aria-label": "Override Karn's base rating"})
        reset = client.post(
            rating_url(vex), {"act": "remove-override"}, HTTP_HX_REQUEST="true"
        )
        rating = BeautifulSoup(reset.content, "html.parser").find(
            id=f"n26-model-rating-{vex.pk}"
        )
        assert rating.find(class_="decoration-dashed")
        props = json.loads(rating.find("script", type="application/json").string)
        assert props["name"] == "Karn"
        assert props["receipt"]["overrideDelta"] == 0
        assert props["receipt"]["total"] == 120
        vex.refresh_from_db()
        assert not build_model_card(vex).rating_override
        assert_reconciled(gang)

    def test_override_query_count_stays_flat_as_the_roster_grows(
        self, client, gang, vex, make_profile
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(gang.owner)

        def queries():
            client.get(reverse("n26-gang", args=[gang.pk]))
            with CaptureQueriesContext(connection) as captured:
                response = client.get(reverse("n26-gang", args=[gang.pk]))
                assert response.status_code == 200
            return len(captured)

        with operation(gang, actor=gang.owner) as op:
            op.set_base_rating(vex, 150)
        before = queries()
        profile = make_profile("More fighters", price=100)
        for number in range(5):
            miniature = hire_with_option(
                gang, profile, f"Extra {number}", paid=100, rating=100
            )
            with operation(gang, actor=gang.owner) as op:
                op.set_base_rating(miniature, 110)
        assert queries() <= before


class TestTheRatingReceipt:
    @pytest.mark.parametrize("override", [None, 150, 70])
    def test_edit_always_marks_the_rating_and_provides_a_breakdown_popover(
        self, client, gang, vex, override
    ):
        if override is not None:
            with operation(gang, actor=gang.owner) as op:
                op.set_base_rating(vex, override)
        client.force_login(gang.owner)
        response = client.get(edit_url(vex))
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id=f"n26-rating-receipt-{vex.pk}") is None
        assert "Rating receipt" not in response.content.decode()
        rating = soup.find(id=f"n26-model-rating-{vex.pk}")
        assert rating.find(class_="decoration-dashed")
        props = json.loads(rating.find("script", type="application/json").string)
        assert props["receipt"] == {
            "defaultRating": 100,
            "overrideDelta": (override - 100) if override is not None else 0,
            "contributions": [{"label": "Gear", "rating": 20}],
            "total": (override if override is not None else 100) + 20,
        }
        assert "rating-tooltip" in response.content.decode()
        assert_reconciled(gang)

    def test_contributions_are_grouped_and_add_to_the_total(self, gang, vex):
        give_weapon(vex, create_weapon("Autogun", price=25), paid=25)
        buy(vex, thing=create_wargear("Respirator", price=10))
        with operation(gang, actor=gang.owner) as op:
            op.assign(create_rule("Rating adjustment"), miniature=vex, rating=-5)
            op.set_base_rating(vex, 150)
        vex.refresh_from_db()
        receipt = read_rating_receipt(vex)
        assert receipt.default_rating == 100
        assert receipt.override_delta == 50
        assert [(line.label, line.rating) for line in receipt.contributions] == [
            ("Weapons", 25),
            ("Gear", 30),
            ("Other additions", -5),
        ]
        assert receipt.total == vex.rating == 200
        assert build_model_card(vex).rating_receipt == receipt
        assert_reconciled(gang)

    def test_card_updates_refresh_the_receipt(self, client, gang, vex):
        from n26.core.views.edit import render_card_update

        client.force_login(gang.owner)
        request = client.get(edit_url(vex)).wsgi_request
        buy(vex, thing=create_wargear("Respirator", price=10))
        vex.refresh_from_db()
        response = render_card_update(request, vex, edit_url(vex))
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id="n26-model-card-host")["hx-swap-oob"] == "true"
        rating = soup.find(id=f"n26-model-rating-{vex.pk}")
        props = json.loads(rating.find("script", type="application/json").string)
        assert props["receipt"]["contributions"] == [{"label": "Gear", "rating": 30}]
        assert props["receipt"]["total"] == 130
        assert_reconciled(gang)

    def test_receipt_save_query_count_does_not_grow_with_equipment(
        self, client, gang, vex
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(gang.owner)

        def queries():
            client.post(rating_url(vex), {"rating": 150}, HTTP_HX_REQUEST="true")
            with CaptureQueriesContext(connection) as captured:
                response = client.post(
                    rating_url(vex), {"rating": 150}, HTTP_HX_REQUEST="true"
                )
                assert response.status_code == 200
            return len(captured)

        before = queries()
        for number in range(5):
            buy(vex, thing=create_wargear(f"More gear {number}", price=10))
        assert queries() <= before
        assert_reconciled(gang)


class TestRatingPermissions:
    @pytest.mark.parametrize("method", ["get", "post"])
    def test_a_stranger_cannot_read_or_change_rating(self, client, gang, vex, method):
        client.force_login(User.objects.create_user("stranger"))
        response = getattr(client, method)(rating_url(vex), {"rating": 0})
        assert response.status_code == 404
        vex.refresh_from_db()
        assert vex.rating == 120
        assert_reconciled(gang)

    def test_anonymous_readers_are_sent_to_login(self, client, vex):
        assert client.get(rating_url(vex)).status_code == 302

    def test_a_removed_model_cannot_be_edited(self, client, gang, vex):
        with operation(gang, actor=gang.owner) as op:
            op.remove(vex.membership)
        client.force_login(gang.owner)
        assert client.post(rating_url(vex), {"rating": 150}).status_code == 404
        assert_reconciled(gang)

    def test_an_operation_cannot_change_another_gangs_model(self, gang, vex, gang_type):
        other = found_gang("Other gang", gang_type, owner=gang.owner, budget=1000)
        with pytest.raises(Refusal):
            with operation(other, actor=gang.owner) as op:
                op.set_base_rating(vex, 150)
        assert_reconciled(gang)
        assert_reconciled(other)


class TestDialogPageState:
    @pytest.mark.parametrize("dialog", ["rating", "rename"])
    def test_open_errors_cancel_reload_and_save_keep_the_edit_page_state(
        self, client, gang, vex, dialog
    ):
        client.force_login(gang.owner)
        back = f"{edit_url(vex)}?skills=all-sets&dismissed=show"
        page = client.get(back)
        soup = BeautifulSoup(page.content, "html.parser")
        label = "Override Vex's base rating" if dialog == "rating" else "Rename Vex"
        pencil = soup.find("a", attrs={"aria-label": label})
        endpoint = pencil["hx-get"]
        assert parse_qs(urlsplit(endpoint).query)["at"] == [back]
        opened = client.get(endpoint, HTTP_HX_REQUEST="true")
        props = opened.context[f"{dialog}_dialog"]
        assert props["cancelUrl"] == back
        assert props["actionUrl"] == endpoint
        opened_url = opened["HX-Replace-Url"]
        if dialog == "rename":
            assert client.get(pencil["href"]).url == opened_url
        assert parse_qs(urlsplit(opened_url).query) == {
            "skills": ["all-sets"],
            "dismissed": ["show"],
            dialog: ["1" if dialog == "rating" else str(vex.pk)],
        }
        reloaded = client.get(opened_url)
        assert reloaded.context[f"{dialog}_dialog"]["cancelUrl"] == back
        invalid = {"rating": "1.5"} if dialog == "rating" else {"name": " "}
        refused = client.post(endpoint, invalid, HTTP_HX_REQUEST="true")
        assert refused.context[f"{dialog}_dialog"]["cancelUrl"] == back
        assert refused["HX-Replace-Url"] == opened_url
        values = {"rating": 150} if dialog == "rating" else {"name": "Karn"}
        saved = client.post(endpoint, values, HTTP_HX_REQUEST="true")
        assert saved["HX-Replace-Url"] == back
        updated = BeautifulSoup(saved.content, "html.parser")
        pencil = updated.find(id=f"n26-rating-pencil-{vex.pk}")
        assert parse_qs(urlsplit(pencil["hx-get"]).query)["at"] == [back]
        if dialog == "rename":
            pencil = updated.find(id=f"n26-name-pencil-{vex.pk}")
            assert parse_qs(urlsplit(pencil["hx-get"]).query)["at"] == [back]
        gang.refresh_from_db()
        assert_reconciled(gang)

    @pytest.mark.parametrize("dialog", ["rating", "rename"])
    @pytest.mark.parametrize(
        "at",
        ["https://example.com/elsewhere", "/n26/fighters/other/edit/?skills=all-sets"],
    )
    def test_unrecognised_return_pages_fall_back_to_this_models_edit_page(
        self, client, gang, vex, dialog, at
    ):
        client.force_login(gang.owner)
        endpoint = (
            rating_url(vex) + "?" + urlencode({"at": at})
            if dialog == "rating"
            else reverse("n26-rename-fighter", args=[vex.pk])
            + "?"
            + urlencode({"back": "edit", "at": at})
        )
        response = client.get(endpoint, HTTP_HX_REQUEST="true")
        assert response.context[f"{dialog}_dialog"]["cancelUrl"] == edit_url(vex)
