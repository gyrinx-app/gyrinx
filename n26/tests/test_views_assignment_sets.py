"""Named model cards are owner-only display preferences, not equipment trades."""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.assignment_sets import equipment_for, save_model_card
from n26.core.models import Assignment, AssignmentSet, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.flags import CAMPAIGNS
from n26.library.authoring import (
    add_rank_threshold,
    create_counter,
    create_rank_table,
    create_skill,
    create_subtype,
    create_wargear,
    create_weapon,
    ef_adds,
    modifier,
    targets_model,
)
from n26.tests.sandbox.actions import assign, found_gang, give_weapon, hire, sell

pytestmark = pytest.mark.django_db


@pytest.fixture
def flag():
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def model(client, owner, gang_type, make_profile, default_pack):
    client.force_login(owner)
    gang = found_gang("The Bad Girls", gang_type, owner=owner, budget=1000)
    miniature = hire(gang, make_profile("Escher Ganger"), "Yolanda", paid=55)
    give_weapon(
        miniature,
        create_weapon("Combat shotgun", profiles=[("Salvo", 0)]),
        paid=35,
    )
    give_weapon(
        miniature,
        create_weapon("Stiletto knife", profiles=[("Blade", 0)]),
        paid=20,
    )
    cutter = create_wargear("Cutter")
    modifier(
        "Cutter grants Mounted",
        targets_model(),
        ef_adds(create_subtype("Mounted")),
        attach_to=cutter,
    )
    assign(cutter, miniature=miniature, paid=75)
    assign(create_skill("Nerves of Steel"), miniature=miniature)
    assert_reconciled(gang)
    return miniature


@pytest.fixture
def kit(model):
    return {str(row.weapon or row.wargear): row for row in equipment_for(model)}


@pytest.fixture
def named(model, kit):
    return save_model_card(
        model, name="Long range", assignments=[kit["Combat shotgun"]]
    )


def address(model, suffix=""):
    return f"/n26/gangs/{model.gang.pk}/models/{model.pk}/cards/{suffix}"


def fields(name="Long range", assignments=(), revision=None):
    data = {"name": name, "assignments": [str(row.pk) for row in assignments]}
    if revision is not None:
        data["revision"] = revision
    return data


class TestManagingModelCards:
    """Named selections replace the standard option and leave the books alone."""

    def test_the_standard_card_shows_all_equipment(self, client, model, flag):
        response = client.get(address(model))
        assert response.status_code == 200
        cards = response.context["cards"]
        assert len(cards) == 1
        assert cards[0].name == "Standard"
        assert not cards[0].id
        assert [weapon.name for weapon in cards[0].card.weapons] == [
            "Combat shotgun",
            "Stiletto knife",
        ]
        assert cards[0].card.type_line == "Fighter (Mounted)"
        assert "Add model card" in response.content.decode()

    def test_new_cards_start_with_all_equipment_selected(
        self, client, model, kit, flag
    ):
        response = client.get(address(model, "new/"))
        form = response.context["form"]
        assert set(form.initial["assignments"]) == {row.pk for row in kit.values()}
        assert set(form.fields["assignments"].queryset) == set(kit.values())
        assert response.content.decode().count(" checked") == 3

    def test_saving_a_named_card_changes_no_equipment_or_history(
        self, client, model, kit, flag
    ):
        events = LedgerEvent.objects.count()
        equipment = list(Assignment.objects.values_list("pk", flat=True))
        response = client.post(
            address(model, "new/"),
            fields("  Long range  ", [kit["Combat shotgun"]]),
        )
        assert response.status_code == 302
        assert response.url == address(model)
        named = AssignmentSet.objects.get(miniature=model)
        assert named.name == "Long range"
        assert set(named.assignments.all()) == {kit["Combat shotgun"]}
        assert LedgerEvent.objects.count() == events
        assert list(Assignment.objects.values_list("pk", flat=True)) == equipment
        assert_reconciled(model.gang)

    def test_named_cards_have_no_phantom_standard_card_and_keep_full_rating(
        self, client, model, kit, named, flag
    ):
        save_model_card(
            model,
            name="Riding kit",
            assignments=[kit["Cutter"], kit["Stiletto knife"]],
        )
        response = client.get(address(model))
        cards = response.context["cards"]
        assert [row.name for row in cards] == ["Long range", "Riding kit"]
        shooting, riding = [row.card for row in cards]
        assert shooting.rating == riding.rating == 185
        assert shooting.type_line == "Fighter"
        assert riding.type_line == "Fighter (Mounted)"
        assert [weapon.name for weapon in shooting.weapons] == ["Combat shotgun"]
        assert [weapon.name for weapon in riding.weapons] == ["Stiletto knife"]
        assert [skill.name for skill in shooting.skills] == ["Nerves of Steel"]
        assert [skill.name for skill in riding.skills] == ["Nerves of Steel"]
        assert shooting.id == riding.id == ""
        assert shooting.model_cards_href == riding.model_cards_href == ""

    def test_an_empty_equipment_selection_is_valid(self, client, model, flag):
        response = client.post(address(model, "new/"), fields("No weapons"))
        assert response.status_code == 302
        card = client.get(response.url).context["cards"][0].card
        assert card.weapons == []
        assert card.rating == 185
        assert [skill.name for skill in card.skills] == ["Nerves of Steel"]

    def test_editing_changes_the_name_and_selection(
        self, client, model, kit, named, flag
    ):
        url = address(model, f"{named.pk}/edit/")
        initial = client.get(url).context["form"].initial
        assert initial["name"] == "Long range"
        assert initial["assignments"] == [kit["Combat shotgun"].pk]
        response = client.post(
            url,
            fields("Close quarters", [kit["Stiletto knife"]], initial["revision"]),
        )
        assert response.status_code == 302
        named.refresh_from_db()
        assert named.name == "Close quarters"
        assert set(named.assignments.all()) == {kit["Stiletto knife"]}
        assert named.modified.isoformat() != initial["revision"]

    def test_names_are_unique_ignoring_case_and_whitespace(
        self, client, model, kit, named, flag
    ):
        response = client.post(
            address(model, "new/"), fields(" LONG RANGE ", [kit["Stiletto knife"]])
        )
        assert response.status_code == 200
        assert "already has a card with that name" in response.content.decode()
        assert "name" in response.context["form"].errors
        assert response.content.decode().count(" checked") == 1
        assert model.assignment_sets.count() == 1

    def test_get_remove_only_asks_the_question(self, client, model, named, flag):
        response = client.get(address(model, f"{named.pk}/remove/"))
        assert response.status_code == 200
        assert AssignmentSet.objects.filter(pk=named.pk).exists()
        assert "return to one standard card" in response.content.decode()

    def test_removing_the_last_card_restores_the_standard_option(
        self, client, model, named, flag
    ):
        events = LedgerEvent.objects.count()
        response = client.post(
            address(model, f"{named.pk}/remove/"),
            {"revision": named.modified.isoformat()},
        )
        assert response.status_code == 302
        assert not model.assignment_sets.exists()
        assert client.get(response.url).context["cards"][0].name == "Standard"
        assert LedgerEvent.objects.count() == events
        assert equipment_for(model).count() == 3

    def test_removing_one_card_keeps_the_other_card(self, client, model, named, flag):
        other = save_model_card(model, name="Close quarters", assignments=[])
        response = client.post(
            address(model, f"{named.pk}/remove/"),
            {"revision": named.modified.isoformat()},
        )
        assert response.status_code == 302
        assert [row.id for row in client.get(response.url).context["cards"]] == [
            str(other.pk)
        ]

    def test_a_card_name_is_escaped_in_the_page(self, client, model, flag):
        save_model_card(model, name="<script>alert(1)</script>", assignments=[])
        drawn = client.get(address(model)).content.decode()
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in drawn
        assert "<script>alert(1)</script>" not in drawn


class TestStaleAndInvalidSelections:
    """A stale form cannot replace newer preferences or select another model's kit."""

    @pytest.mark.parametrize("suffix", ["edit/", "remove/"])
    def test_a_stale_revision_does_not_overwrite_a_card(
        self, client, model, named, flag, suffix
    ):
        revision = named.modified.isoformat()
        updated = save_model_card(
            model,
            name="Newer name",
            assignments=[],
            assignment_set=named,
            revision=revision,
        )
        response = client.post(
            address(model, f"{named.pk}/{suffix}"),
            fields("Older name", revision=revision),
        )
        assert response.status_code == 200
        assert "This model card changed." in response.content.decode()
        updated.refresh_from_db()
        assert updated.name == "Newer name"
        assert updated.assignments.count() == 0

    @pytest.mark.parametrize("suffix", ["edit/", "remove/"])
    def test_the_revision_is_required(self, client, model, named, flag, suffix):
        response = client.post(
            address(model, f"{named.pk}/{suffix}"), fields("No revision")
        )
        assert response.status_code == 200
        assert "revision" in response.context["form"].errors
        named.refresh_from_db()
        assert named.name == "Long range"

    @pytest.mark.parametrize("kind", ["profile", "skill", "weapon_profile"])
    def test_non_equipment_roots_and_weapon_children_are_not_selectable(
        self, client, model, flag, kind
    ):
        row = Assignment.objects.filter(
            miniature_root=model, **{f"{kind}__isnull": False}
        ).first()
        assert row is not None
        response = client.post(address(model, "new/"), fields(assignments=[row]))
        assert response.status_code == 200
        assert "assignments" in response.context["form"].errors
        assert not model.assignment_sets.exists()

    def test_another_models_equipment_is_not_selectable(
        self, client, model, make_profile, flag
    ):
        other = hire(model.gang, make_profile("Other profile"), "Donna")
        stolen = give_weapon(other, create_weapon("Stub gun", profiles=[("Shot", 0)]))
        response = client.post(address(model, "new/"), fields(assignments=[stolen]))
        assert response.status_code == 200
        assert "assignments" in response.context["form"].errors
        assert not model.assignment_sets.exists()

    def test_equipment_sold_after_form_validation_is_rechecked_under_lock(
        self, model, kit
    ):
        shotgun = kit["Combat shotgun"]
        sell(shotgun)
        with pytest.raises(ValidationError, match="no longer on this model"):
            save_model_card(model, name="Old selection", assignments=[shotgun])
        assert not model.assignment_sets.exists()
        model.gang.refresh_from_db()
        assert_reconciled(model.gang)

    def test_sold_equipment_is_not_offered(self, client, model, kit, flag):
        shotgun = kit["Combat shotgun"]
        sell(shotgun)
        response = client.get(address(model, "new/"))
        assert shotgun not in response.context["form"].fields["assignments"].queryset
        model.gang.refresh_from_db()
        assert_reconciled(model.gang)


class TestModelCardPermissions:
    """Every route requires this live model's owner and the campaigns flag."""

    @pytest.mark.parametrize("suffix", ["", "new/", "edit/", "remove/"])
    def test_flag_off_blocks_get_and_post(self, client, model, named, flag, suffix):
        flag.availability = Availability.OFF
        flag.save()
        path = f"{named.pk}/{suffix}" if suffix in {"edit/", "remove/"} else suffix
        for method in (client.get, client.post):
            assert method(address(model, path)).status_code == 404

    @pytest.mark.parametrize("suffix", ["", "new/", "edit/", "remove/"])
    def test_other_players_cannot_read_or_change_cards(
        self, client, model, named, flag, suffix
    ):
        client.force_login(User.objects.create_user("other-player"))
        path = f"{named.pk}/{suffix}" if suffix in {"edit/", "remove/"} else suffix
        for method in (client.get, client.post):
            assert method(address(model, path)).status_code == 404

    def test_anonymous_readers_cannot_reach_the_feature(self, client, model, flag):
        client.logout()
        response = client.get(address(model))
        assert response.status_code == 404

    def test_the_model_must_belong_to_the_addressed_gang(
        self, client, model, gang_type, flag
    ):
        other = found_gang("Other gang", gang_type, owner=model.gang.owner)
        url = address(model).replace(str(model.gang.pk), str(other.pk))
        assert client.get(url).status_code == 404
        assert client.post(f"{url}new/", fields()).status_code == 404

    def test_a_card_must_belong_to_the_addressed_model(
        self, client, model, make_profile, named, flag
    ):
        other = hire(model.gang, make_profile("Other profile"), "Donna")
        for suffix in ("edit/", "remove/"):
            url = address(other, f"{named.pk}/{suffix}")
            assert client.get(url).status_code == 404
            assert client.post(url, fields()).status_code == 404

    @pytest.mark.parametrize("target", ["gang", "model", "card"])
    def test_malformed_ids_return_404(self, client, model, named, flag, target):
        ids = {
            "gang": str(model.gang.pk),
            "model": str(model.pk),
            "card": str(named.pk),
        }
        url = address(model, f"{named.pk}/edit/").replace(ids[target], "bad-id")
        assert client.get(url).status_code == 404

    def test_archived_models_cannot_be_managed(self, client, model, flag):
        model.membership.archive()
        assert client.get(address(model)).status_code == 404
        assert client.post(address(model, "new/"), fields()).status_code == 404

    def test_archived_gangs_cannot_be_managed(self, client, model, flag):
        model.gang.archive()
        assert client.get(address(model)).status_code == 404
        assert client.post(address(model, "new/"), fields()).status_code == 404

    @pytest.mark.parametrize("screen", ["gang", "model"])
    def test_only_flagged_owners_see_the_layers_action(
        self, client, model, flag, screen
    ):
        url = (
            f"/n26/gangs/{model.gang.pk}/"
            if screen == "gang"
            else f"/n26/fighters/{model.pk}/edit/"
        )
        drawn = client.get(url).content.decode()
        assert f'href="{address(model)}"' in drawn
        assert 'aria-label="Model cards"' in drawn
        flag.availability = Availability.OFF
        flag.save()
        drawn = client.get(url).content.decode()
        assert f'href="{address(model)}"' not in drawn
        assert 'aria-label="Model cards"' not in drawn

    def test_other_readers_never_see_card_management(self, client, model, flag):
        client.force_login(User.objects.create_user("visitor"))
        url = f"/n26/gangs/{model.gang.pk}/"
        response = client.get(url)
        assert response.status_code == 200
        assert f'href="{address(model)}"' not in response.content.decode()
        assert 'aria-label="Model cards"' not in response.content.decode()


class TestModelCardQueryGrowth:
    """More named cards reuse the hydrated equipment and modifier index."""

    def test_more_cards_do_not_add_queries(self, client, model, named, kit, flag):
        xp = create_counter("XP")
        ranks = create_rank_table("Fighter ranks", xp, initial_title="Rookie")
        add_rank_threshold(ranks, 4, title="Rookie")
        with operation(model.gang, actor=model.gang.owner) as op:
            op.assign(ranks, miniature=model)
            counter = op.assign(xp, miniature=model)
            op.open_counter(counter, 0)
        # Hold content shape constant: the Cutter's modifier needs hydration
        # that a shotgun-only card does not. Only the number of cards grows.
        save_model_card(
            model,
            name=named.name,
            assignments=list(kit.values()),
            assignment_set=named,
            revision=named.modified.isoformat(),
        )

        def count():
            client.get(address(model))
            with CaptureQueriesContext(connection) as captured:
                response = client.get(address(model))
                assert response.status_code == 200
            return len(captured)

        small = count()
        for number in range(6):
            save_model_card(
                model,
                name=f"Selection {number}",
                assignments=list(kit.values()),
            )
        assert count() <= small
        assert len(client.get(address(model)).context["cards"]) == 7
