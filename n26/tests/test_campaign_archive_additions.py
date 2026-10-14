"""An arbitrator archives a counter or label they added to their campaign.

Archiving takes it off every gang the way leaving the campaign would, for
that one thing: nothing is deleted or set to zero, every gang's history
says what it stood at, and the campaign log shows the archive once.
"""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation, own_addition, own_additions
from n26.core.history import build, campaign_history
from n26.core.models import (
    Assignment,
    CampaignEvent,
    CampaignMembership,
    CounterValue,
    LedgerEvent,
)
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign
from n26.flags import BUILT_IN_PROPAGATION, CAMPAIGNS
from n26.library.authoring import add_built_in, create_counter
from n26.library.models import DefaultAssignment, Pickable
from n26.tests.sandbox.actions import (
    choose,
    ef_contributes_to_counter,
    found_campaign,
    found_gang,
    modifier,
    tally,
    targets_gang_alone,
)

pytestmark = pytest.mark.django_db


def said(act):
    return "".join(span.text for span in act.spans)


def sentences(acts):
    return [said(act) for act in acts]


@pytest.fixture
def table(campaign_type, gang_type):
    """A campaign with a counter and a label of its own, and two gangs in
    it: Rust Kings with Faith at 4 and Lawful picked, Ash Wolves with
    Faith at its opening 1 and nothing picked yet."""
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    add_built_in(campaign_type, create_counter("Reputation"), amount=2)
    arbitrator = User.objects.create_user("arbitrator")
    player = User.objects.create_user("player")
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    with campaign_operation(campaign, actor=arbitrator) as op:
        op.add_counter("Faith", opening=1)
        op.add_label("Alignment", ["Lawful", "Chaotic"])
    kings = found_gang("Rust Kings", gang_type, owner=player)
    wolves = found_gang("Ash Wolves", gang_type, owner=player)
    with campaign_operation(campaign, actor=arbitrator) as op:
        op.add_gang(kings)
        op.add_gang(wolves)
    faith = own_additions(campaign, "counter").get()
    alignment = own_additions(campaign, "slot").get()
    tally(Assignment.objects.get(gang_root=kings, materialised_from=faith), 3)
    question = Assignment.objects.get(gang_root=kings, materialised_from=alignment)
    choose(
        question,
        Pickable.objects.get(slot_type=alignment.slot.slot_type, name="Lawful"),
        slot=alignment.slot,
    )
    return {
        "campaign": campaign,
        "arbitrator": arbitrator,
        "player": player,
        "kings": kings,
        "wolves": wolves,
        "faith": faith,
        "alignment": alignment,
    }


def archive(table, kind):
    campaign = table["campaign"]
    with campaign_operation(campaign, actor=table["arbitrator"]) as op:
        if kind == "counter":
            return op.archive_counter(table["faith"])
        return op.archive_label(table["alignment"])


def copies(member):
    return Assignment.objects.filter(materialised_from=member)


def a_rule_reads_faith(table):
    """A staff-authored rule on the campaign's own type that reads Faith."""
    modifier(
        "Shrines add two Faith",
        targets_gang_alone(),
        ef_contributes_to_counter(table["faith"].counter, 2),
        carried_by=table["campaign"].additions,
    )


def settings_url(campaign):
    return reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=counters-and-labels"


def archive_url(table, kind):
    member = table["faith"] if kind == "counter" else table["alignment"]
    return reverse(
        f"n26-campaign-archive-{kind}", args=[table["campaign"].pk, member.pk]
    )


class TestArchivingACounter:
    """Every gang loses the counter and keeps every value it reached."""

    def test_it_comes_off_every_gang_and_the_values_stay(self, table):
        faith = table["faith"]
        kings_copy = copies(faith).get(gang_root=table["kings"])

        archive(table, "counter")

        assert copies(faith).filter(archived=False).count() == 0
        assert copies(faith).count() == 2
        assert CounterValue.objects.get(assignment=kings_copy).value == 4
        faith.refresh_from_db()
        faith.counter.refresh_from_db()
        assert faith.archived
        assert faith.counter.archived
        for gang in (table["kings"], table["wolves"]):
            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_each_gang_history_says_what_it_stood_at(self, table):
        archive(table, "counter")

        kings = sentences(build(table["kings"]))
        assert "removed Faith (was 4)" in kings
        # The changes that got it there still read as they did.
        assert "changed Faith — +3, now 4" in kings
        assert "removed Faith (was 1)" in sentences(build(table["wolves"]))
        act = next(
            act
            for act in build(table["kings"])
            if said(act).startswith("removed Faith")
        )
        assert act.actor == "arbitrator"
        assert act.note == ""

    def test_the_campaign_log_shows_the_archive_once(self, table):
        archive(table, "counter")

        log = sentences(campaign_history(table["campaign"]))
        assert log.count("archived the counter Faith") == 1
        assert not [line for line in log if line.startswith("removed Faith")]
        event = CampaignEvent.objects.get(kind=CampaignEvent.Kind.COUNTER_ARCHIVED)
        removals = LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.REMOVED, assignment__materialised_from=table["faith"]
        )
        assert {removal.batch for removal in removals} == {event.batch}
        assert {removal.campaign_id for removal in removals} == {table["campaign"].pk}

    def test_the_column_goes_and_a_later_gang_never_gets_it(self, table, gang_type):
        archive(table, "counter")

        sheet = render_campaign(table["campaign"], with_owner_badges=False)
        assert "Faith" not in sheet.counter_columns
        assert "Reputation" in sheet.counter_columns
        late = found_gang("Late Comers", gang_type, owner=table["player"])
        with campaign_operation(table["campaign"], actor=table["arbitrator"]) as op:
            op.add_gang(late)
        assert not copies(table["faith"]).filter(gang_root=late).exists()

    def test_a_gang_that_left_is_not_written_to_again(self, table):
        membership = CampaignMembership.objects.get(
            campaign=table["campaign"], gang=table["wolves"], left__isnull=True
        )
        with campaign_operation(table["campaign"], actor=table["arbitrator"]) as op:
            op.remove_gang(membership)
        before = LedgerEvent.objects.filter(gang=table["wolves"]).count()

        archive(table, "counter")

        assert LedgerEvent.objects.filter(gang=table["wolves"]).count() == before

    def test_one_no_gang_received_is_archived_rather_than_deleted(self, campaign_type):
        arbitrator = User.objects.create_user("lonely-arbitrator")
        campaign = found_campaign("Empty Wastes", campaign_type, owner=arbitrator)
        with campaign_operation(campaign, actor=arbitrator) as op:
            op.add_counter("Dread")
        member = own_additions(campaign, "counter").get()
        with campaign_operation(campaign, actor=arbitrator) as op:
            op.archive_counter(member)
        member.refresh_from_db()
        assert member.archived

    def test_its_tally_address_is_gone(self, client, table):
        held = copies(table["faith"]).get(gang_root=table["kings"])
        client.force_login(table["arbitrator"])
        assert client.get(reverse("n26-tally", args=[held.pk])).status_code == 200

        archive(table, "counter")

        assert client.get(reverse("n26-tally", args=[held.pk])).status_code == 404

    def test_adding_one_by_the_same_name_is_refused_in_words(self, table):
        archive(table, "counter")
        with (
            pytest.raises(Refusal, match="has an archived counter called Faith"),
            campaign_operation(table["campaign"], actor=table["arbitrator"]) as op,
        ):
            op.add_counter("faith")

    def test_one_another_rule_reads_is_refused_and_nothing_changes(self, table):
        a_rule_reads_faith(table)
        with pytest.raises(
            Refusal,
            match="You cannot archive Faith. It is used by “Shrines add two Faith”.",
        ):
            archive(table, "counter")
        table["faith"].refresh_from_db()
        assert not table["faith"].archived
        assert copies(table["faith"]).filter(archived=False).count() == 2

    def test_archiving_it_twice_is_refused_in_words(self, table):
        archive(table, "counter")
        with pytest.raises(Refusal, match="Faith was already archived."):
            archive(table, "counter")

    def test_a_gang_still_waiting_for_its_copy_is_left_as_it_is(self, table, gang_type):
        """A gang whose copy has not reached it yet has nothing taken away
        and no removal written; once archived, nothing grants it later."""
        from n26.core.models import CampaignMembership

        waiting = found_gang("Slow Boat", gang_type, owner=table["player"])
        with campaign_operation(table["campaign"], actor=table["arbitrator"]) as op:
            op.add_gang(waiting)
        copies(table["faith"]).filter(gang_root=waiting).delete()
        assert CampaignMembership.objects.filter(
            gang=waiting, left__isnull=True
        ).exists()

        archive(table, "counter")

        assert not LedgerEvent.objects.filter(
            gang=waiting, kind=LedgerEvent.Kind.REMOVED
        ).exists()
        assert not copies(table["faith"]).filter(gang_root=waiting).exists()


class TestArchivingALabel:
    """Every gang loses the label and the option it picked, and its history
    says which option that was."""

    def test_it_and_its_pick_come_off_every_gang(self, table):
        alignment = table["alignment"]

        archive(table, "label")

        assert copies(alignment).filter(archived=False).count() == 0
        assert not Assignment.objects.filter(
            chosen_for_slot=alignment.slot, archived=False
        ).exists()
        sheet = render_campaign(table["campaign"], with_owner_badges=False)
        assert "Alignment" not in sheet.label_columns
        alignment.refresh_from_db()
        alignment.slot.refresh_from_db()
        assert alignment.archived
        assert alignment.slot.archived
        assert alignment.slot.slot_type.pickables.filter(archived=False).count() == 0
        for gang in (table["kings"], table["wolves"]):
            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_each_gang_history_says_what_it_had_picked(self, table):
        archive(table, "label")

        kings = sentences(build(table["kings"]))
        assert "removed Alignment (was Lawful)" in kings
        assert "removed Lawful" not in kings
        assert "removed Alignment" in sentences(build(table["wolves"]))
        log = sentences(campaign_history(table["campaign"]))
        assert log.count("archived the label Alignment") == 1
        assert not [line for line in log if line.startswith("removed Alignment")]

    def test_adding_one_by_the_same_name_is_refused_in_words(self, table):
        archive(table, "label")
        with (
            pytest.raises(Refusal, match="has an archived label called Alignment"),
            campaign_operation(table["campaign"], actor=table["arbitrator"]) as op,
        ):
            op.add_label("Alignment", ["Good", "Evil"])


class TestWhatTheArbitratorCannotArchive:
    """Only the campaign's own counters and labels can be archived. What
    the shared type gives, another campaign's, and anything already
    archived are not found."""

    def test_only_the_campaigns_own_additions_are_found(self, table, campaign_type):
        campaign = table["campaign"]
        reputation = DefaultAssignment.objects.get(
            default_set_id=campaign_type.built_ins_id, counter__name="Reputation"
        )
        with pytest.raises(ValueError):
            own_addition(campaign, reputation.pk, "counter")
        with pytest.raises(ValueError):
            own_addition(campaign, table["alignment"].pk, "counter")
        with pytest.raises(ValueError):
            own_addition(campaign, "not-a-key", "slot")

        other = found_campaign("Elsewhere", campaign_type, owner=table["arbitrator"])
        with campaign_operation(other, actor=table["arbitrator"]) as op:
            op.add_counter("Faith")
        theirs = own_additions(other, "counter").get()
        with pytest.raises(ValueError):
            own_addition(campaign, theirs.pk, "counter")

        archive(table, "counter")
        with pytest.raises(ValueError):
            own_addition(campaign, table["faith"].pk, "counter")


class TestThePages:
    """The settings tab links to a confirm page for each of the campaign's
    own counters and labels; the confirm page lists what each gang has."""

    def test_the_tab_offers_archive_only_for_the_campaigns_own(self, client, table):
        client.force_login(table["arbitrator"])
        response = client.get(settings_url(table["campaign"]))
        counters = {row["name"]: row for row in response.context["counters"]}
        assert counters["Faith"]["archive_href"] == archive_url(table, "counter")
        assert "archive_href" not in counters["Reputation"]
        (label,) = response.context["labels"]
        assert label["archive_href"] == archive_url(table, "label")
        assert response.context["shared_definitions"] == (
            f"Reputation comes with {table['campaign'].campaign_type}. "
            "You cannot archive it here."
        )
        html = response.content.decode()
        assert archive_url(table, "counter") in html
        assert archive_url(table, "label") in html

    def test_the_confirm_page_lists_each_gang_with_what_it_has(self, client, table):
        client.force_login(table["arbitrator"])
        counter_page = client.get(archive_url(table, "counter"))
        assert counter_page.status_code == 200
        assert counter_page.context["gangs"] == [
            {"gang": "Ash Wolves", "value": "1", "muted": False},
            {"gang": "Rust Kings", "value": "4", "muted": False},
        ]
        assert counter_page.context["refusal"] == ""
        html = counter_page.content.decode()
        assert "Archive counter" in html
        assert "Each gang&#x27;s history keeps every change to Faith" in html
        label_page = client.get(archive_url(table, "label"))
        assert label_page.context["gangs"] == [
            {"gang": "Ash Wolves", "value": "Nothing picked yet", "muted": True},
            {"gang": "Rust Kings", "value": "Lawful", "muted": False},
        ]
        assert "Nothing picked yet" in label_page.content.decode()
        # Reading the page changes nothing.
        assert copies(table["faith"]).filter(archived=False).count() == 2

    @pytest.mark.parametrize("kind", ["counter", "label"])
    def test_posting_archives_and_returns_to_the_tab(self, client, table, kind):
        client.force_login(table["arbitrator"])
        response = client.post(archive_url(table, kind), follow=True)
        assert response.redirect_chain[-1][0] == settings_url(table["campaign"])
        name = "Faith" if kind == "counter" else "Alignment"
        assert f"Archived the {kind} {name}." in response.content.decode()
        member = table["faith"] if kind == "counter" else table["alignment"]
        assert copies(member).filter(archived=False).count() == 0
        assert name not in [row["name"] for row in response.context[f"{kind}s"]]
        # Posting again finds nothing to archive.
        assert client.post(archive_url(table, kind)).status_code == 404

    def test_a_refused_archive_says_why_and_offers_no_button(self, client, table):
        a_rule_reads_faith(table)
        client.force_login(table["arbitrator"])
        page = client.get(archive_url(table, "counter"))
        assert "It is used by “Shrines add two Faith”" in page.context["refusal"]
        assert "Archive counter" not in page.content.decode()
        response = client.post(archive_url(table, "counter"), follow=True)
        assert "It is used by “Shrines add two Faith”" in response.content.decode()
        assert copies(table["faith"]).filter(archived=False).count() == 2

    def test_nobody_else_reaches_it_and_shared_counters_are_not_there(
        self, client, table, campaign_type
    ):
        client.force_login(table["player"])
        assert client.get(archive_url(table, "counter")).status_code == 404
        assert client.post(archive_url(table, "label")).status_code == 404
        client.force_login(table["arbitrator"])
        reputation = DefaultAssignment.objects.get(
            default_set_id=campaign_type.built_ins_id, counter__name="Reputation"
        )
        shared = reverse(
            "n26-campaign-archive-counter", args=[table["campaign"].pk, reputation.pk]
        )
        assert client.get(shared).status_code == 404
        # A label's key is not a counter's.
        wrong_kind = reverse(
            "n26-campaign-archive-counter",
            args=[table["campaign"].pk, table["alignment"].pk],
        )
        assert client.get(wrong_kind).status_code == 404
        assert copies(table["alignment"]).filter(archived=False).count() == 2

    def test_more_gangs_do_not_grow_the_confirm_page_queries(
        self, client, table, gang_type
    ):
        client.force_login(table["arbitrator"])
        small = {}
        for kind in ("counter", "label"):
            client.get(archive_url(table, kind))
            with CaptureQueriesContext(connection) as queries:
                assert client.get(archive_url(table, kind)).status_code == 200
            small[kind] = len(queries)
        with campaign_operation(table["campaign"], actor=table["arbitrator"]) as op:
            for number in range(4):
                op.add_gang(
                    found_gang(f"Gang {number}", gang_type, owner=table["player"])
                )
        for kind in ("counter", "label"):
            client.get(archive_url(table, kind))
            with CaptureQueriesContext(connection) as queries:
                response = client.get(archive_url(table, kind))
            assert len(response.context["gangs"]) == 6
            assert len(queries) <= small[kind]


def unarchive(table, kind):
    campaign = table["campaign"]
    with campaign_operation(campaign, actor=table["arbitrator"]) as op:
        if kind == "counter":
            return op.unarchive_counter(table["faith"])
        return op.unarchive_label(table["alignment"])


def live_pick(table, gang):
    return Assignment.objects.get(
        gang_root=gang, chosen_for_slot=table["alignment"].slot, archived=False
    )


@pytest.fixture
def propagating(db):
    """The running side of built-in propagation sits behind a flag."""
    return FeatureFlag.objects.create(
        slug=BUILT_IN_PROPAGATION,
        name="Built-in propagation",
        availability=Availability.EVERYONE,
    )


class TestUnarchivingACounter:
    """Every gang still in the campaign gets the counter back at the value
    it had; a gang that joined while it was archived gets it new."""

    def test_each_gang_gets_back_the_value_it_had(self, table):
        archive(table, "counter")

        unarchive(table, "counter")

        values = {
            copy.gang_root_id: copy.counter_value.value
            for copy in copies(table["faith"]).filter(archived=False)
        }
        assert values == {table["kings"].pk: 4, table["wolves"].pk: 1}
        table["faith"].refresh_from_db()
        table["faith"].counter.refresh_from_db()
        assert not table["faith"].archived
        assert not table["faith"].counter.archived
        sheet = render_campaign(table["campaign"], with_owner_badges=False)
        assert "Faith" in sheet.counter_columns
        for gang in (table["kings"], table["wolves"]):
            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_each_gang_history_and_the_log_say_so_once(self, table):
        archive(table, "counter")
        unarchive(table, "counter")

        kings = sentences(build(table["kings"]))
        assert "restored Faith (4)" in kings
        assert "removed Faith (was 4)" in kings
        log = sentences(campaign_history(table["campaign"]))
        assert log.count("unarchived the counter Faith") == 1
        assert not [line for line in log if line.startswith("restored")]

    def test_it_can_be_tallied_again(self, client, table):
        archive(table, "counter")
        unarchive(table, "counter")
        held = copies(table["faith"]).get(gang_root=table["kings"])
        client.force_login(table["arbitrator"])
        assert client.get(reverse("n26-tally", args=[held.pk])).status_code == 200

    def test_a_gang_that_left_meanwhile_gets_nothing_back(self, table):
        archive(table, "counter")
        membership = CampaignMembership.objects.get(
            campaign=table["campaign"], gang=table["wolves"], left__isnull=True
        )
        with campaign_operation(table["campaign"], actor=table["arbitrator"]) as op:
            op.remove_gang(membership)

        unarchive(table, "counter")

        assert (
            not copies(table["faith"])
            .filter(gang_root=table["wolves"], archived=False)
            .exists()
        )

    def test_a_gang_that_joined_meanwhile_gets_it_at_its_starting_value(
        self, table, gang_type, propagating, task_queue
    ):
        archive(table, "counter")
        late = found_gang("Late Comers", gang_type, owner=table["player"])
        with campaign_operation(table["campaign"], actor=table["arbitrator"]) as op:
            op.add_gang(late)
        assert not copies(table["faith"]).filter(gang_root=late).exists()

        with task_queue.capture():
            unarchive(table, "counter")
        task_queue.deliver_all()

        fresh = copies(table["faith"]).get(gang_root=late, archived=False)
        assert fresh.counter_value.value == 1
        late.refresh_from_db()
        assert_reconciled(late)

    def test_a_second_archive_and_unarchive_brings_back_the_newer_value(self, table):
        archive(table, "counter")
        unarchive(table, "counter")
        tally(copies(table["faith"]).get(gang_root=table["kings"]), 2)
        archive(table, "counter")

        unarchive(table, "counter")

        kings = copies(table["faith"]).get(gang_root=table["kings"])
        assert not kings.archived
        assert kings.counter_value.value == 6
        assert sentences(build(table["kings"])).count("restored Faith (6)") == 1

    def test_one_that_is_not_archived_is_refused_in_words(self, table):
        with pytest.raises(Refusal, match="Faith is not archived."):
            unarchive(table, "counter")

    def test_adding_its_name_again_points_at_unarchive(self, table):
        archive(table, "counter")
        with (
            pytest.raises(Refusal, match="Unarchive it, or use another name."),
            campaign_operation(table["campaign"], actor=table["arbitrator"]) as op,
        ):
            op.add_counter("Faith")


class TestUnarchivingALabel:
    """Every gang still in the campaign gets the label back with the option
    the archive took from it, and nothing it had already replaced."""

    def test_each_gang_gets_back_the_option_it_had_picked(self, table):
        archive(table, "label")

        unarchive(table, "label")

        assert live_pick(table, table["kings"]).pickable.name == "Lawful"
        assert copies(table["alignment"]).filter(archived=False).count() == 2
        assert not Assignment.objects.filter(
            gang_root=table["wolves"],
            chosen_for_slot=table["alignment"].slot,
            archived=False,
        ).exists()
        sheet = render_campaign(table["campaign"], with_owner_badges=False)
        assert "Alignment" in sheet.label_columns
        for gang in (table["kings"], table["wolves"]):
            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_each_gang_history_and_the_log_say_so_once(self, table):
        archive(table, "label")
        unarchive(table, "label")

        kings = sentences(build(table["kings"]))
        assert "restored Alignment (Lawful)" in kings
        assert "restored Lawful" not in kings
        assert "restored Alignment" in sentences(build(table["wolves"]))
        log = sentences(campaign_history(table["campaign"]))
        assert log.count("unarchived the label Alignment") == 1
        assert not [line for line in log if line.startswith("restored")]

    def test_an_option_replaced_before_the_archive_stays_replaced(self, table):
        from n26.core.operations import operation

        question = copies(table["alignment"]).get(gang_root=table["kings"])
        lawful = live_pick(table, table["kings"])
        chaotic = Pickable.objects.get(
            slot_type=table["alignment"].slot.slot_type, name="Chaotic"
        )
        with operation(table["kings"], actor=table["player"]) as op:
            op.remove(lawful)
            op.choose(question, chaotic, slot=table["alignment"].slot)
        archive(table, "label")

        unarchive(table, "label")

        assert live_pick(table, table["kings"]).pickable.name == "Chaotic"
        lawful.refresh_from_db()
        assert lawful.archived


def unarchive_url(table, kind):
    member = table["faith"] if kind == "counter" else table["alignment"]
    return reverse(
        f"n26-campaign-unarchive-{kind}", args=[table["campaign"].pk, member.pk]
    )


class TestTheUnarchivePages:
    """The settings tab lists what is archived, each with a confirm page
    saying what every gang gets."""

    def test_the_archive_page_says_it_can_be_undone(self, client, table):
        client.force_login(table["arbitrator"])
        page = client.get(archive_url(table, "counter"))
        assert page.context["heading"] == (
            "Archiving removes Faith from every gang in Dust Falls"
        )
        assert "You can unarchive it later" in page.context["consequences"]
        assert "You cannot undo this" not in page.content.decode()

    def test_the_tab_lists_archived_counters_and_labels(self, client, table):
        archive(table, "counter")
        archive(table, "label")
        client.force_login(table["arbitrator"])
        response = client.get(settings_url(table["campaign"]))
        assert response.context["archived_counters"] == [
            {"name": "Faith", "unarchive_href": unarchive_url(table, "counter")}
        ]
        assert response.context["archived_labels"] == [
            {"name": "Alignment", "unarchive_href": unarchive_url(table, "label")}
        ]
        html = response.content.decode()
        assert unarchive_url(table, "counter") in html
        assert unarchive_url(table, "label") in html

    def test_the_confirm_page_lists_what_each_gang_gets(self, client, table, gang_type):
        archive(table, "counter")
        archive(table, "label")
        late = found_gang("Late Comers", gang_type, owner=table["player"])
        with campaign_operation(table["campaign"], actor=table["arbitrator"]) as op:
            op.add_gang(late)
        client.force_login(table["arbitrator"])

        counter_page = client.get(unarchive_url(table, "counter"))
        assert counter_page.status_code == 200
        assert [
            (line.gang, line.value) for line in counter_page.context["returning"]
        ] == [("Ash Wolves", "1"), ("Rust Kings", "4")]
        assert [(line.gang, line.value) for line in counter_page.context["new"]] == [
            ("Late Comers", "1")
        ]
        label_page = client.get(unarchive_url(table, "label"))
        assert [
            (line.gang, line.value) for line in label_page.context["returning"]
        ] == [("Ash Wolves", "Nothing picked yet"), ("Rust Kings", "Lawful")]
        assert "Unarchive label" in label_page.content.decode()

    @pytest.mark.parametrize("kind", ["counter", "label"])
    def test_posting_unarchives_and_returns_to_the_tab(self, client, table, kind):
        archive(table, kind)
        client.force_login(table["arbitrator"])
        response = client.post(unarchive_url(table, kind), follow=True)
        assert response.redirect_chain[-1][0] == settings_url(table["campaign"])
        name = "Faith" if kind == "counter" else "Alignment"
        assert f"Unarchived the {kind} {name}." in response.content.decode()
        member = table["faith"] if kind == "counter" else table["alignment"]
        assert copies(member).filter(archived=False).count() == 2
        assert name in [row["name"] for row in response.context[f"{kind}s"]]
        assert client.post(unarchive_url(table, kind)).status_code == 404

    def test_nobody_else_reaches_it_and_a_live_one_is_not_there(self, client, table):
        client.force_login(table["arbitrator"])
        assert client.get(unarchive_url(table, "counter")).status_code == 404
        archive(table, "counter")
        client.force_login(table["player"])
        assert client.get(unarchive_url(table, "counter")).status_code == 404
        assert client.post(unarchive_url(table, "counter")).status_code == 404

    def test_more_gangs_do_not_grow_the_confirm_page_queries(
        self, client, table, gang_type
    ):
        archive(table, "counter")
        archive(table, "label")
        client.force_login(table["arbitrator"])
        small = {}
        for kind in ("counter", "label"):
            client.get(unarchive_url(table, kind))
            with CaptureQueriesContext(connection) as queries:
                assert client.get(unarchive_url(table, kind)).status_code == 200
            small[kind] = len(queries)
        with campaign_operation(table["campaign"], actor=table["arbitrator"]) as op:
            for number in range(4):
                op.add_gang(
                    found_gang(f"Gang {number}", gang_type, owner=table["player"])
                )
        for kind in ("counter", "label"):
            client.get(unarchive_url(table, kind))
            with CaptureQueriesContext(connection) as queries:
                response = client.get(unarchive_url(table, kind))
            assert len(response.context["new"]) == 4
            assert len(queries) <= small[kind]
