"""An arbitrator edits the asset types their campaign added itself.

The labels can change at any time. Ownership fixes how every asset of the
type behaves, so it is fixed once the type has any assets. Asset types that
come with the campaign type are library content and are not edited here.
"""

import json

import pytest
from bs4 import BeautifulSoup
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import CampaignEvent
from n26.core.operations import Refusal
from n26.core.views.campaigns import more_actions
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import AssetType, CampaignType, DefaultAssignment
from n26.tests.sandbox.actions import (
    add_campaign_asset_type,
    create_campaign_asset,
    create_campaign_table,
    found_campaign,
    found_gang,
    join_campaign,
)

pytestmark = pytest.mark.django_db

HOLDING = AssetType.Ownership.HOLDING
POSSESSION = AssetType.Ownership.POSSESSION


@pytest.fixture
def core(default_pack):
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="Territory campaign")


@pytest.fixture
def campaign(core):
    owner = User.objects.create_user("arbitrator")
    return found_campaign("Dust Falls", core, owner=owner, budget=1000)


@pytest.fixture
def racket(campaign):
    return add_campaign_asset_type(campaign, "Rakit", plural="Rakits")


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


def edit(campaign, asset_type, label, ownership, plural=""):
    with campaign_operation(campaign, actor=campaign.owner) as act:
        return act.edit_asset_type(asset_type, label, ownership, label_plural=plural)


def edit_url(campaign, asset_type):
    return reverse("n26-campaign-edit-asset-type", args=[campaign.pk, asset_type.pk])


def tab_url(campaign):
    return reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=asset-types"


def props(response):
    page = BeautifulSoup(response.content, "html.parser")
    host = page.select_one('[data-react-name="edit-asset-type"]')
    return json.loads(page.find(id=host["data-react-props"]).string)


def submit(client, target, data, **kwargs):
    page = client.get(target)
    if page.status_code == 200:
        soup = BeautifulSoup(page.content, "html.parser")
        if soup.select_one('[data-react-name="edit-asset-type"]'):
            data = {"snapshot": props(page)["values"]["snapshot"], **data}
    return client.post(target, data, **kwargs)


class TestEditingAnAssetType:
    """The edit is the campaign's own act, logged once for each save that
    changes something. Labels can change at any time; the ownership only
    until the type has an asset or a table. Every decision reads the type
    as it stands under the campaign's line."""

    def test_new_labels_are_saved_and_logged_with_the_old_name(self, campaign, racket):
        edit(campaign, racket, "Racket", HOLDING, plural="Rackets")
        racket.refresh_from_db()
        assert (racket.label_singular, racket.plural) == ("Racket", "Rackets")
        assert campaign.events.last().kind == CampaignEvent.Kind.ASSET_TYPE_EDITED
        assert sentences(campaign_history(campaign))[-1] == (
            "edited the asset type Rakit, now called Racket"
        )

    def test_a_plural_alone_is_logged_under_the_label(self, campaign, racket):
        edit(campaign, racket, "Rakit", HOLDING, plural="Rakitz")
        assert sentences(campaign_history(campaign))[-1] == (
            "edited the asset type Rakit"
        )

    def test_saving_what_is_there_writes_nothing(self, campaign, racket):
        before = campaign.events.count()
        assert edit(campaign, racket, " Rakit ", HOLDING, plural="Rakits") is None
        assert campaign.events.count() == before

    def test_the_log_names_the_label_as_it_stands_not_as_the_page_read_it(
        self, campaign, racket
    ):
        read_earlier = AssetType.objects.get(pk=racket.pk)
        edit(campaign, racket, "Racket", HOLDING)
        edit(campaign, read_earlier, "Rackit", HOLDING)
        assert sentences(campaign_history(campaign))[-1] == (
            "edited the asset type Racket, now called Rackit"
        )

    def test_ownership_changes_while_the_type_has_no_assets(self, campaign, racket):
        edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        racket.refresh_from_db()
        assert racket.ownership == POSSESSION

    def test_ownership_is_fixed_once_the_type_has_an_asset(self, campaign, racket):
        create_campaign_asset(campaign, racket, "Still")
        with pytest.raises(
            Refusal,
            match="You cannot change the ownership now. Dust Falls already has rakits.",
        ):
            edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        racket.refresh_from_db()
        assert racket.ownership == HOLDING
        # The labels still change.
        edit(campaign, racket, "Racket", HOLDING, plural="Rackets")
        racket.refresh_from_db()
        assert racket.label_singular == "Racket"

    def test_ownership_is_fixed_once_the_type_has_a_table(self, campaign, racket):
        create_campaign_table(campaign, racket, "Rakit table")
        with pytest.raises(
            Refusal,
            match=(
                "You cannot change the ownership now. "
                "Dust Falls already has a table of rakits."
            ),
        ):
            edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        racket.refresh_from_db()
        assert racket.ownership == HOLDING

    def test_an_asset_made_from_an_earlier_read_takes_the_ownership_as_it_is(
        self, campaign, racket
    ):
        read_earlier = AssetType.objects.get(pk=racket.pk)
        edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        still = create_campaign_asset(campaign, read_earlier, "Still")
        assert still.asset_type.ownership == POSSESSION
        assert DefaultAssignment.objects.filter(
            default_set_id=campaign.additions.built_ins_id, asset=still
        ).exists()

    def test_a_table_made_from_an_earlier_read_is_refused_once_inherent(
        self, campaign, racket
    ):
        read_earlier = AssetType.objects.get(pk=racket.pk)
        edit(campaign, racket, "Rakit", POSSESSION, plural="Rakits")
        with pytest.raises(Refusal, match="You cannot make a table of Rakits."):
            create_campaign_table(campaign, read_earlier, "Rakit table")

    def test_a_label_the_campaign_already_uses_is_refused(self, campaign, racket):
        with pytest.raises(Refusal, match="already has an asset type called"):
            edit(campaign, racket, "territory", HOLDING)
        add_campaign_asset_type(campaign, "Hideout")
        with pytest.raises(Refusal, match="already has an asset type called hideout"):
            edit(campaign, racket, "hideout", HOLDING)
        # Its own label in another case is its own, not taken.
        edit(campaign, racket, "RAKIT", HOLDING, plural="Rakits")

    def test_a_blank_label_is_refused(self, campaign, racket):
        with pytest.raises(Refusal, match="Give the asset type a label."):
            edit(campaign, racket, "  ", HOLDING)

    def test_a_shared_asset_type_is_not_the_campaigns_to_edit(self, campaign, core):
        territory = core.asset_types.get(label_singular="Territory")
        with pytest.raises(ValueError):
            edit(campaign, territory, "Turf", HOLDING)


class TestTheAssetTypesTab:
    """The tab lists the asset types the campaign added itself, each with
    a link to edit it, and names the shared ones it cannot edit. The More
    actions menu opens it for the arbitrator alone."""

    def test_it_lists_the_campaigns_own_types_and_names_the_shared_ones(
        self, client, campaign, racket
    ):
        add_campaign_asset_type(campaign, "Hideout", ownership=POSSESSION)
        client.force_login(campaign.owner)
        response = client.get(tab_url(campaign))
        assert response.context["tab"] == "asset-types"
        assert response.context["asset_types"] == [
            {
                "label": "Rakit",
                "plural": "Rakits",
                "ownership": "Transferable",
                "href": edit_url(campaign, racket),
            },
            {
                "label": "Hideout",
                "plural": "Hideouts",
                "ownership": "Inherent",
                "href": edit_url(
                    campaign, AssetType.objects.get(label_singular="Hideout")
                ),
            },
        ]
        body = response.content.decode()
        assert (
            "Settlements and Territories come with Territory campaign. "
            "You cannot edit them here."
        ) in body
        assert reverse("n26-campaign-add-asset-type", args=[campaign.pk]) in body
        assert "Save campaign" not in body

    def test_it_says_when_the_campaign_has_none_of_its_own(self, client, campaign):
        client.force_login(campaign.owner)
        body = client.get(tab_url(campaign)).content.decode()
        assert "This campaign has no asset types of its own yet." in body

    def test_the_more_actions_menu_opens_it(self, campaign):
        assert tab_url(campaign) in [
            a.target for a in more_actions(campaign, yours=True)
        ]
        assert tab_url(campaign) not in [
            a.target for a in more_actions(campaign, yours=False)
        ]


class TestTheEditPage:
    """The page opens filled in and saves through the operation. A refusal
    stays on the form. A fixed ownership is stated rather than offered,
    and posting another one changes nothing. Shared types have no page,
    and players reach none of it."""

    def test_it_opens_filled_in_and_saves(self, client, campaign, racket):
        client.force_login(campaign.owner)
        page = client.get(edit_url(campaign, racket))
        assert page.status_code == 200
        data = props(page)
        assert data["values"]["label_singular"] == "Rakit"
        assert data["values"]["label_plural"] == "Rakits"
        assert data["values"]["ownership"] == HOLDING

        response = submit(
            client,
            edit_url(campaign, racket),
            {"label_singular": "Racket", "label_plural": "", "ownership": HOLDING},
            follow=True,
        )
        assert response.redirect_chain[-1][0] == tab_url(campaign)
        assert "Saved the asset type Racket." in response.content.decode()
        racket.refresh_from_db()
        assert racket.plural == "Rackets"

    def test_an_unchanged_save_says_so(self, client, campaign, racket):
        client.force_login(campaign.owner)
        response = submit(
            client,
            edit_url(campaign, racket),
            {"label_singular": "Rakit", "label_plural": "Rakits", "ownership": HOLDING},
            follow=True,
        )
        assert "Nothing changed." in response.content.decode()

    def test_a_refusal_stays_on_the_form(self, client, campaign, racket):
        client.force_login(campaign.owner)
        response = submit(
            client,
            edit_url(campaign, racket),
            {"label_singular": "Territory", "ownership": HOLDING},
        )
        assert response.status_code == 200
        assert props(response)["errors"]["__all__"] == [
            "Dust Falls already has an asset type called Territory."
        ]

    def test_a_fixed_ownership_is_stated_and_cannot_be_posted(
        self, client, campaign, racket
    ):
        create_campaign_asset(campaign, racket, "Still")
        client.force_login(campaign.owner)
        data = props(client.get(edit_url(campaign, racket)))
        assert data["ownerships"] == []
        assert (
            data["ownershipNote"]
            == "Transferable. You cannot change ownership. Dust Falls already has rakits."
        )

        response = submit(
            client,
            edit_url(campaign, racket),
            {"label_singular": "Racket", "ownership": POSSESSION},
        )
        assert response.status_code == 302
        racket.refresh_from_db()
        assert (racket.label_singular, racket.ownership) == ("Racket", HOLDING)

    def test_a_table_fixes_the_ownership_on_the_page_too(
        self, client, campaign, racket
    ):
        create_campaign_table(campaign, racket, "Rakit table")
        client.force_login(campaign.owner)
        data = props(client.get(edit_url(campaign, racket)))
        assert data["ownerships"] == []
        assert (
            data["ownershipNote"]
            == "Transferable. You cannot change ownership. Dust Falls already has a table of rakits."
        )

    def test_a_shared_type_has_no_edit_page(self, client, campaign, core):
        territory = core.asset_types.get(label_singular="Territory")
        client.force_login(campaign.owner)
        assert client.get(edit_url(campaign, territory)).status_code == 404

    def test_the_pages_are_the_arbitrators_alone(
        self, client, campaign, racket, gang_type
    ):
        player = User.objects.create_user("player")
        join_campaign(found_gang("The Ashen Choir", gang_type, owner=player), campaign)
        client.force_login(player)
        assert client.get(tab_url(campaign)).status_code == 404
        assert client.get(edit_url(campaign, racket)).status_code == 404
        response = submit(
            client,
            edit_url(campaign, racket),
            {"label_singular": "Mine", "ownership": HOLDING},
        )
        assert response.status_code == 404
        racket.refresh_from_db()
        assert racket.label_singular == "Rakit"


class TestAssetDisplayGroups:
    @pytest.mark.parametrize("creating", [True, False])
    def test_an_overlong_display_group_shows_its_validation_error(
        self, client, campaign, racket, creating
    ):
        client.force_login(campaign.owner)
        url = (
            reverse("n26-campaign-add-asset-type", args=[campaign.pk])
            if creating
            else edit_url(campaign, racket)
        )
        response = submit(
            client,
            url,
            {
                "label_singular": "Depot",
                "label_plural": "Depots",
                "ownership": HOLDING,
                "display_group": "x" * 201,
            },
        )
        assert response.status_code == 200
        errors = response.context["form"].errors["display_group"]
        assert errors
        if creating:
            text = BeautifulSoup(response.content, "html.parser").get_text(
                " ", strip=True
            )
            assert all(error in text for error in errors)
        else:
            assert props(response)["errors"]["display_group"] == errors
        assert not campaign.additions.asset_types.filter(
            label_singular="Depot"
        ).exists()
        racket.refresh_from_db()
        assert racket.display_group == ""

    def test_arbitrator_can_create_and_change_a_display_group(self, client, campaign):
        client.force_login(campaign.owner)
        response = submit(
            client,
            reverse("n26-campaign-add-asset-type", args=[campaign.pk]),
            {
                "label_singular": "Depot",
                "label_plural": "Depots",
                "ownership": HOLDING,
                "display_group": "Supply sites",
            },
        )
        assert response.status_code == 302
        kind = campaign.additions.asset_types.get(label_singular="Depot")
        assert kind.display_group == "Supply sites"
        response = client.get(edit_url(campaign, kind))
        assert response.context["form"]["display_group"].value() == "Supply sites"
        response = submit(
            client,
            edit_url(campaign, kind),
            {
                "label_singular": "Depot",
                "label_plural": "Depots",
                "ownership": HOLDING,
                "display_group": "Territories",
            },
        )
        assert response.status_code == 302
        kind.refresh_from_db()
        assert kind.display_group == "Territories"
        assert campaign.events.last().kind == CampaignEvent.Kind.ASSET_TYPE_EDITED

    def test_clearing_a_group_restores_a_separate_line(self, campaign, racket):
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.edit_asset_type(
                racket,
                "Rakit",
                HOLDING,
                label_plural="Rakits",
                display_group="Supply sites",
            )
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.edit_asset_type(
                racket, "Rakit", HOLDING, label_plural="Rakits", display_group=""
            )
        racket.refresh_from_db()
        assert racket.display_group == ""


def workflow_data(campaign, kind, **changes):
    from n26.core.asset_type_edit import initial_form

    kind.refresh_from_db()
    return {**initial_form(campaign, kind, campaign.owner).initial, **changes}


@pytest.mark.parametrize("transport", ["html", "json"])
@pytest.mark.parametrize("label", ["Racket", "Territory", "", "x" * 201])
def test_asset_type_transports_share_validation_and_events(
    client, campaign, racket, transport, label
):
    client.force_login(campaign.owner)
    target = (
        edit_url(campaign, racket)
        if transport == "html"
        else reverse(
            "n26-campaign-edit-asset-type-command", args=[campaign.pk, racket.pk]
        )
    )
    data = workflow_data(
        campaign,
        racket,
        label_singular=label,
        label_plural="",
        display_group="Supply sites",
    )
    before = campaign.events.count()
    response = client.post(target, data)
    saved = label == "Racket"
    assert response.status_code == (
        (302 if saved else 200) if transport == "html" else (200 if saved else 422)
    )
    assert campaign.events.count() == before + int(saved)
    racket.refresh_from_db()
    assert racket.label_singular == ("Racket" if saved else "Rakit")
    if saved:
        assert racket.label_plural == "" and racket.plural == "Rackets"
        assert racket.display_group == "Supply sites"
        assert (
            response.url if transport == "html" else response.json()["nextUrl"]
        ) == tab_url(campaign)


def test_asset_type_retries_and_conflicts_use_the_locked_starting_state(
    campaign, racket
):
    from n26.core.asset_type_edit import change

    original = workflow_data(campaign, racket, label_singular="Racket")
    before = campaign.events.count()
    first = change(campaign, racket, campaign.owner, original)
    retry = change(campaign, racket, campaign.owner, original)
    assert first.saved and first.applied
    assert retry.saved and not retry.applied
    assert campaign.events.count() == before + 1
    edit(campaign, racket, "Newer name", HOLDING)
    before = campaign.events.count()
    conflict = change(campaign, racket, campaign.owner, original)
    assert conflict.conflict and not conflict.saved
    assert conflict.current["label_singular"] == "Newer name"
    assert campaign.events.count() == before
    reviewed = workflow_data(campaign, racket, label_singular="Reviewed name")
    assert change(campaign, racket, campaign.owner, reviewed).saved
    assert change(campaign, racket, campaign.owner, original).conflict
    racket.refresh_from_db()
    assert racket.label_singular == "Reviewed name"


@pytest.mark.parametrize("dependency", ["asset", "table"])
def test_new_ownership_constraints_conflict_even_without_a_type_row_change(
    campaign, racket, dependency
):
    from n26.core.asset_type_edit import change

    data = workflow_data(campaign, racket, ownership=POSSESSION)
    version = racket.modified
    if dependency == "asset":
        create_campaign_asset(campaign, racket, "Still")
    else:
        create_campaign_table(campaign, racket, "Rakit table")
    racket.refresh_from_db()
    assert racket.modified == version
    before = campaign.events.count()
    result = change(campaign, racket, campaign.owner, data)
    assert result.conflict and not result.saved
    assert result.current["ownership"] == HOLDING
    assert result.current["fixedReason"]
    assert campaign.events.count() == before


def test_locked_ownership_still_ignores_tampered_input_in_the_shared_workflow(
    campaign, racket
):
    from n26.core.asset_type_edit import change

    create_campaign_asset(campaign, racket, "Still")
    data = workflow_data(
        campaign, racket, label_singular="Racket", ownership=POSSESSION
    )
    result = change(campaign, racket, campaign.owner, data)
    assert result.saved
    racket.refresh_from_db()
    assert racket.ownership == HOLDING and racket.label_singular == "Racket"


def test_type_noop_rechecks_current_owner_before_accepting_a_replay(campaign, racket):
    from n26.core.asset_type_edit import change

    data = workflow_data(campaign, racket)
    owner = campaign.owner
    campaign.owner = User.objects.create_user("new-owner")
    campaign.save(update_fields=["owner"])
    result = change(campaign, racket, owner, data)
    assert not result.saved and result.form.non_field_errors()


def test_wrong_subject_and_tampered_snapshots_cannot_edit_types(campaign, racket):
    from n26.core.asset_type_edit import change

    other = add_campaign_asset_type(campaign, "Other")
    data = workflow_data(campaign, other, label_singular="Changed")
    assert not change(campaign, racket, campaign.owner, data).saved
    data = workflow_data(campaign, racket, label_singular="Changed")
    data["snapshot"] += "tampered"
    assert not change(campaign, racket, campaign.owner, data).saved
    racket.refresh_from_db()
    assert racket.label_singular == "Rakit"


def test_type_command_checks_authentication_csrf_and_subjects(
    client, campaign, racket, core
):
    from django.test import Client

    target = reverse(
        "n26-campaign-edit-asset-type-command", args=[campaign.pk, racket.pk]
    )
    assert client.post(target, {}).status_code == 401
    client.force_login(campaign.owner)
    assert client.get(target).status_code == 405
    protected = Client(enforce_csrf_checks=True)
    protected.force_login(campaign.owner)
    assert (
        protected.post(
            target, workflow_data(campaign, racket), HTTP_ACCEPT="application/json"
        ).status_code
        == 403
    )
    shared = core.asset_types.get(label_singular="Territory")
    shared_url = reverse(
        "n26-campaign-edit-asset-type-command", args=[campaign.pk, shared.pk]
    )
    assert client.post(shared_url, {}).status_code == 404
    bad = reverse("n26-campaign-edit-asset-type-command", args=[campaign.pk, "invalid"])
    assert client.post(bad, {}).status_code == 404


def test_edit_type_queries_do_not_grow_with_assets(client, campaign, racket):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client.force_login(campaign.owner)
    create_campaign_asset(campaign, racket, "First")
    client.get(edit_url(campaign, racket))
    with CaptureQueriesContext(connection) as small:
        assert client.get(edit_url(campaign, racket)).status_code == 200
    for index in range(8):
        create_campaign_asset(campaign, racket, f"Extra {index}")
    with CaptureQueriesContext(connection) as large:
        assert client.get(edit_url(campaign, racket)).status_code == 200
    assert len(small) == len(large)


@pytest.mark.django_db(transaction=True)
def test_simultaneous_type_drafts_cannot_overwrite_each_other(campaign, racket):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connections

    from n26.core.asset_type_edit import change
    from n26.core.models import Campaign

    original = workflow_data(campaign, racket)
    ready = Barrier(2)

    def save(label):
        close_old_connections()
        try:
            current_campaign = Campaign.objects.get(pk=campaign.pk)
            kind = AssetType.objects.get(pk=racket.pk)
            user = User.objects.get(pk=campaign.owner_id)
            ready.wait(timeout=10)
            result = change(
                current_campaign, kind, user, {**original, "label_singular": label}
            )
            return result.saved, result.conflict
        finally:
            connections.close_all()

    before = campaign.events.filter(kind=CampaignEvent.Kind.ASSET_TYPE_EDITED).count()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["First type", "Second type"]))
    assert sorted(results) == [(False, True), (True, False)]
    assert (
        campaign.events.filter(kind=CampaignEvent.Kind.ASSET_TYPE_EDITED).count()
        == before + 1
    )
