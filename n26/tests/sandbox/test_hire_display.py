"""Hire delivers priced catalogue facts, not rendered cards or private content."""

import json

import pytest
from django.contrib.auth.models import User
from django.http import QueryDict

from n26.core.hire_display import (
    HireCatalogue,
    catalogue_data,
    confirmation_data,
    figures_data,
)
from n26.core.hire_workflow import UnavailableHire
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import create_option_group, offer_option, revise
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(gang_type):
    owner = User.objects.create_user("hire-display-owner")
    return found_gang("Ashen Choir", gang_type, owner=owner, budget=100)


@pytest.fixture
def profile(make_profile):
    return make_profile("Ganger", price=60)


def entries(data):
    return [
        entry
        for section in data["sections"]
        for category in section["categories"]
        for entry in category["entries"]
    ]


class TestTheDeliveredCatalogue:
    def test_projection_is_query_free_after_the_catalogue_has_been_prepared(
        self, gang, profile, django_assert_num_queries
    ):
        plain = offer_option(profile, "Plain")
        equipped = offer_option(profile, "Equipped", price=25)
        revise(profile, library_author_help="Private author help")
        catalogue = HireCatalogue(gang, gang.owner, "gang")
        _ = catalogue.sections

        with django_assert_num_queries(0):
            data = catalogue_data(catalogue)
            encoded = json.dumps(data)
        (entry,) = entries(data)
        assert entry["name"] == "Ganger"
        assert entry["basePrice"] == 60
        assert entry["groups"][0]["options"] == [
            {
                "key": str(plain.pk),
                "name": "Plain",
                "price": 0,
                "totalPrice": 60,
                "default": True,
            },
            {
                "key": str(equipped.pk),
                "name": "Equipped",
                "price": 25,
                "totalPrice": 85,
                "default": False,
            },
        ]
        assert "Private author help" not in encoded
        assert "library_author_help" not in encoded
        assert "card" not in entry
        assert entry["previewHref"].endswith(f"/preview/{profile.pk}/")

    def test_initial_catalogue_never_draws_preview_cards(
        self, gang, profile, monkeypatch
    ):
        def unexpected(*args, **kwargs):
            raise AssertionError("Initial catalogue drew a preview card")

        monkeypatch.setattr("n26.core.hire.card_to_model_card", unexpected)
        assert entries(catalogue_data(HireCatalogue(gang, gang.owner, "gang")))

    def test_all_profiles_does_not_load_the_gangs_collection_offers(
        self, gang, profile, monkeypatch
    ):
        def unexpected(*args, **kwargs):
            raise AssertionError("All profiles loaded held collections")

        monkeypatch.setattr("n26.core.hire_display.gang_collections", unexpected)
        data = catalogue_data(HireCatalogue(gang, gang.owner, "all"))
        assert any(entry["name"] == profile.name for entry in entries(data))
        assert data["scope"] == "all"
        assert "list=all" in data["listingHref"]


class TestTheConfirmation:
    def test_an_implicit_single_option_is_retained_without_an_unnecessary_choice_label(
        self, profile
    ):
        option = offer_option(profile, "Standard gear", price=10)
        data = confirmation_data(profile, None, str(profile.pk), QueryDict())
        assert data["quote"] == 70
        assert data["selection"] == [str(option.pk)]
        assert data["choices"] == []
        json.dumps(data)

    def test_optional_groups_keep_none_while_required_groups_keep_their_default(
        self, profile
    ):
        main = offer_option(profile, "Plain")
        optional_group = create_option_group(profile, "Equipment", choose="one-or-none")
        offer_option(profile, "Optional gear", price=25, group=optional_group)
        data = confirmation_data(
            profile, None, str(profile.pk), QueryDict("selection=[]")
        )
        assert data["quote"] == 60
        assert data["selection"] == [str(main.pk)]
        assert data["choices"] == []

    def test_a_stable_selection_uses_the_selected_offer_after_reordering(self, profile):
        plain = offer_option(profile, "Plain")
        equipped = offer_option(profile, "Equipped", price=25)
        revise(plain, position=2)
        revise(equipped, position=0)
        incoming = QueryDict(mutable=True)
        incoming["selection"] = json.dumps([str(equipped.pk)])
        data = confirmation_data(profile, None, str(profile.pk), incoming)
        assert data["quote"] == 85
        assert data["choices"] == ["Equipped"]
        assert data["selection"] == [str(equipped.pk)]

    def test_an_option_from_another_profile_never_becomes_a_quote(
        self, profile, make_profile
    ):
        other = make_profile("Other")
        stray = offer_option(other, "Other gear")
        incoming = QueryDict(mutable=True)
        incoming["selection"] = json.dumps([str(stray.pk)])
        with pytest.raises(UnavailableHire):
            confirmation_data(profile, None, str(profile.pk), incoming)


class TestTheDeliveredFigures:
    def test_figures_keep_roster_counts_rating_and_owned_navigation(
        self, gang, profile
    ):
        hire(gang, profile, "Vex", paid=60)
        summary = HireCatalogue(gang, gang.owner, "gang").summary
        data = figures_data(
            gang, summary, trade_points_href="/trade/", credits_href="/credits/"
        )
        assert [item["value"] for item in data["items"]] == [
            "—",
            "60¢",
            "40¢",
            "0¢",
            "100¢",
        ]
        assert data["items"][0]["absent"] == "No Visit Trading Post action open"
        assert data["items"][0]["href"] == "/trade/"
        assert data["items"][2]["href"] == "/credits/"
        assert data["roster"] == {
            "count": 1,
            "rating": 60,
            "groups": [{"profile": "Ganger", "category": "", "count": 1}],
            "models": [{"name": "Vex", "rating": 60}],
        }
        json.dumps(data)
        assert_reconciled(gang)

    def test_zero_credits_are_a_figure_and_unlimited_credits_are_absent(
        self, gang, profile, gang_type
    ):
        hire(gang, profile, "Vex", paid=100)
        limited = figures_data(gang, HireCatalogue(gang, gang.owner, "gang").summary)
        assert limited["items"][2]["value"] == "0¢"
        assert limited["items"][2]["absent"] == ""
        unlimited = found_gang("Unbudgeted", gang_type, owner=gang.owner)
        data = figures_data(
            unlimited, HireCatalogue(unlimited, gang.owner, "gang").summary
        )
        assert data["items"][2]["value"] == "—"
        assert data["items"][2]["absent"] == "Unlimited credits"
        assert_reconciled(gang)
        assert_reconciled(unlimited)
