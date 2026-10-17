"""Built-in visit discovery is authored; contribution rules remain content."""

from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.built_in_actions import trading_post_visit_relevant
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.trading import visitors
from n26.library.authoring import (
    configure_trading_post_visit,
    create_gang_type,
    create_pack,
    create_subtype,
    revise,
)
from n26.library.models import BuiltInAction, HasSubtypes, Subtype
from n26.library.standard_content import STANDARD_CONTENT
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(gang_type):
    return found_gang(
        "The Lanterns", gang_type, owner=User.objects.create_user("player"), budget=1000
    )


@pytest.fixture
def author(client):
    person = User.objects.create_user("author", is_staff=True)
    client.force_login(person)
    return person


def settings_url():
    return reverse("authoring-trading-post-visit")


def visit_url(gang):
    return reverse("n26-gang-trade-points", args=[gang.pk])


class TestAuthoring:
    def test_only_staff_can_configure_the_action(self, client, gang):
        client.force_login(gang.owner)
        assert client.get(settings_url()).status_code == 302
        assert client.post(settings_url(), {}).status_code == 302
        assert not BuiltInAction.objects.exists()

    def test_actions_link_to_the_protected_built_in(self, client, author):
        body = client.get(reverse("authoring-leaf", args=["action"])).content.decode()
        assert settings_url() in body
        assert "Built-in actions" in body

    def test_a_new_library_type_is_selectable_and_can_be_cleared(self, client, author):
        added = create_gang_type("Lantern seekers")
        response = client.get(settings_url())
        choices = response.context["form"].fields["excluded_gang_types"].queryset
        assert added in choices
        response = client.post(settings_url(), {"excluded_gang_types": [str(added.pk)]})
        assert response.status_code == 302
        action = BuiltInAction.objects.get()
        assert list(action.excluded_gang_types.all()) == [added]
        assert client.post(settings_url(), {}).status_code == 302
        assert not action.excluded_gang_types.exists()
        assert BuiltInAction.objects.count() == 1

    def test_a_type_from_an_owned_library_pack_can_be_selected(self, client, author):
        pack = create_pack("Owned library", owner=author)
        added = create_gang_type("Authored list", pack=pack)
        response = client.get(settings_url())
        assert added in response.context["form"].fields["excluded_gang_types"].queryset
        response = client.post(settings_url(), {"excluded_gang_types": [str(added.pk)]})
        assert response.status_code == 302
        assert list(BuiltInAction.objects.get().excluded_gang_types.all()) == [added]

    def test_a_selected_archived_type_remains_editable(self, client, author):
        selected = create_gang_type("Archived list")
        configure_trading_post_visit([selected])
        selected.archived = True
        selected.save(update_fields=["archived"])
        choices = (
            client.get(settings_url())
            .context["form"]
            .fields["excluded_gang_types"]
            .queryset
        )
        assert selected in choices
        assert (
            client.post(
                settings_url(), {"excluded_gang_types": [str(selected.pk)]}
            ).status_code
            == 302
        )

    def test_campaign_private_types_are_neither_offered_nor_accepted(
        self, client, author
    ):
        from n26.library.authoring import create_campaign_type
        from n26.tests.sandbox.actions import found_campaign

        campaign = found_campaign(
            "Private campaign", create_campaign_type("Test campaign"), owner=author
        )
        private = create_gang_type("Private list", pack=campaign.pack)
        choices = (
            client.get(settings_url())
            .context["form"]
            .fields["excluded_gang_types"]
            .queryset
        )
        assert private not in choices
        response = client.post(
            settings_url(), {"excluded_gang_types": [str(private.pk)]}
        )
        assert response.status_code == 200
        assert response.context["form"].errors
        assert not BuiltInAction.objects.exists()

    def test_listing_queries_do_not_grow_with_gang_types(self, client, author):
        create_gang_type("First list")
        client.get(settings_url())
        with CaptureQueriesContext(connection) as small:
            assert client.get(settings_url()).status_code == 200
        for number in range(20):
            create_gang_type(f"Additional list {number}")
        with CaptureQueriesContext(connection) as large:
            assert client.get(settings_url()).status_code == 200
        assert len(large) == len(small)


class TestOwnerDiscovery:
    def test_missing_configuration_and_new_types_show_setup_normally(self, gang):
        assert trading_post_visit_relevant(gang)
        configure_trading_post_visit([create_gang_type("Excluded list")])
        assert trading_post_visit_relevant(gang)

    def test_renaming_a_selected_type_preserves_its_configuration(self, gang):
        configure_trading_post_visit([gang.gang_type])
        revise(gang.gang_type, name="Renamed list")
        assert not trading_post_visit_relevant(gang)

    def test_excluded_setup_is_in_other_actions_and_still_usable(self, client, gang):
        configure_trading_post_visit([gang.gang_type])
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        other = reverse("n26-gang-other-actions", args=[gang.pk])
        assert other in body
        assert f'href="{visit_url(gang)}"' not in body
        assert visit_url(gang) in client.get(other).content.decode()
        assert (
            "house rules or an exception"
            in client.get(visit_url(gang)).content.decode()
        )
        response = client.post(visit_url(gang), {"brought": "4"})
        assert response.status_code == 302
        gang.refresh_from_db()
        assert gang.visiting_trading_post
        assert gang.trade_points_left == 4
        assert_reconciled(gang)

    def test_an_open_visit_stays_visible_and_can_finish_after_a_change(
        self, client, gang
    ):
        with operation(gang, actor=gang.owner) as op:
            op.visit_trading_post([], brought=3)
        configure_trading_post_visit([gang.gang_type])
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert f'href="{visit_url(gang)}"' in body
        assert "Complete action" in client.get(visit_url(gang)).content.decode()
        assert client.post(visit_url(gang), {"act": "finish"}).status_code == 302
        gang.refresh_from_db()
        assert not gang.visiting_trading_post
        assert_reconciled(gang)

    def test_exceptions_do_not_grant_strangers_access(self, client, gang):
        configure_trading_post_visit([gang.gang_type])
        client.force_login(User.objects.create_user("stranger"))
        other = reverse("n26-gang-other-actions", args=[gang.pk])
        assert client.get(other).status_code == 404
        assert client.post(visit_url(gang), {"brought": "4"}).status_code == 404


class TestStandardContent:
    def test_foundations_defaults_exclude_spyre_and_preserve_author_changes(
        self, default_pack
    ):
        seed = STANDARD_CONTENT["built-in-actions"]
        seed.create()
        action = BuiltInAction.objects.get()
        assert list(action.excluded_gang_types.values_list("name", flat=True)) == [
            "Spyre Hunters"
        ]
        configure_trading_post_visit([])
        seed.create()
        assert not action.excluded_gang_types.exists()
        assert seed.status() == "complete"

    @pytest.mark.parametrize("spyrer", [False, True])
    def test_rank_contributions_exclude_spyrers_but_preserve_ordinary_ranks(
        self, gang, make_profile, spyrer
    ):
        STANDARD_CONTENT["visit-contribution"].create()
        ranks = {
            name: Subtype.objects.get(name=name)
            for name in ("Leader", "Champion", "Spyrer")
        }
        for number, names in enumerate(
            [("Leader",), ("Champion",), ("Leader", "Champion")]
        ):
            model = hire(
                gang, make_profile(f"Entry {number}", price=0), f"Visitor {number}"
            )
            with operation(gang, actor=gang.owner) as op:
                for name in names + (("Spyrer",) if spyrer else ()):
                    op.assign(ranks[name], miniature=model)
        offered = visitors(gang)
        assert sorted(visitor.trade_points for visitor in offered) == (
            [] if spyrer else [1, 2, 2]
        )
        assert_reconciled(gang)

    def test_migration_preserves_conditions_and_is_idempotent(self, default_pack):
        STANDARD_CONTENT["visit-contribution"].create()
        spyrer = Subtype.objects.get(name="Spyrer")
        HasSubtypes.objects.filter(subtypes=spyrer).delete()
        champion = Subtype.objects.get(name="Champion")
        scope = champion.modifiers.get().targets_miniature
        original = set(scope.has_subtypes.values_list("pk", flat=True))
        marker = create_subtype("Another condition")
        extra = HasSubtypes.objects.create(scope=scope, negate=True)
        extra.subtypes.add(marker)
        migrate = import_module(
            "n26.library.migrations.0126_built_in_trading_post_action"
        ).configure_visits
        editor = SimpleNamespace(connection=connection)
        migrate(apps, editor)
        configure_trading_post_visit([])
        migrate(apps, editor)
        assert original | {extra.pk} <= set(
            scope.has_subtypes.values_list("pk", flat=True)
        )
        assert HasSubtypes.objects.filter(negate=True, subtypes=spyrer).count() == 2
        assert not BuiltInAction.objects.get().excluded_gang_types.exists()

    @pytest.mark.parametrize("qualified_only", [False, True])
    def test_migration_resolves_case_and_qualified_variants(
        self, default_pack, qualified_only
    ):
        spyre = create_gang_type(
            "SPYRE HUNTERS", qualifier="A" if qualified_only else ""
        )
        spyrer = create_subtype("SPYRER", qualifier="A" if qualified_only else "")
        create_gang_type("Spyre Hunters", qualifier="Other list")
        create_subtype("Spyrer", qualifier="Other rules")
        migrate = import_module(
            "n26.library.migrations.0126_built_in_trading_post_action"
        ).configure_visits
        migrate(apps, SimpleNamespace(connection=connection))
        action = BuiltInAction.objects.get()
        assert list(action.excluded_gang_types.all()) == [spyre]
        assert Subtype.objects.filter(name__iexact="Spyrer").count() == 2
        assert Subtype.objects.get(pk=spyrer.pk).name == "SPYRER"
