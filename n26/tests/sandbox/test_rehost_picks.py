"""Moving a gang's picks off the model they were written on.

A slot that says the gang holds its pick was, for a while, saying the
bearer, so the picks made then sit on the Leader. Setting the slot back
steers only new picks. The repair moves the ones already written onto
the gang, keeping everything that says which question they answer and
why they exist, and proves each gang's books whole before it commits.

The fault is planted the way it happened: the slot is granted to the
Leader by a modifier on their profile, says the bearer when the pick is
made through the page, and says the gang afterwards.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled, check_gang
from n26.core.rehost_picks import Refused, apply, find
from n26.core.render import render_gang
from n26.core.views.choose import link_slots
from n26.library.authoring import (
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    ef_adds,
    modifier,
    targets_model,
)
from n26.maintenance import Operation, rehost_gang_picks_view
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db

LEADER_PRICE = 120
GANGER_PRICE = 50


@pytest.fixture
def owner(db):
    return User.objects.create_user("rehost-player")


@pytest.fixture
def slot_type(default_pack):
    return create_slot_type("Archetype", allows_repeats=False)


@pytest.fixture
def archetypes(slot_type):
    return {name: create_pickable(name, slot_type) for name in ("Brawler", "Wyrd")}


@pytest.fixture
def gang_slot(slot_type, archetypes):
    """The Leader is asked. Which host the pick lands on is set by the
    test, because the fault is the slot changing its mind."""
    return create_slot(
        "Gang archetype",
        slot_type,
        create_picklist("Archetypes", slot_type, members=list(archetypes.values())),
        label="Archetype",
        assigned_to="bearer",
    )


@pytest.fixture
def leader_profile(person_type, gang_type, gang_slot):
    """The slot reaches the Leader through a modifier on their profile,
    so the assignment that asks is their membership."""
    profile = create_profile(
        "Outcast Leader", person_type, gang_type, price=LEADER_PRICE
    )
    modifier(
        "Leader: the gang is asked its Archetype",
        targets_model(),
        ef_adds(gang_slot),
        attach_to=profile,
    )
    return profile


@pytest.fixture
def ganger_profile(person_type, gang_type):
    return create_profile("Hive Scum", person_type, gang_type, price=GANGER_PRICE)


@pytest.fixture
def gang(owner, gang_type):
    return found_gang("The Unhosted", gang_type, owner=owner, budget=1000)


@pytest.fixture
def leader(gang, leader_profile):
    return hire(gang, leader_profile, "Leader", paid=LEADER_PRICE)


@pytest.fixture
def scum(gang, ganger_profile):
    return hire(gang, ganger_profile, "Scum", paid=GANGER_PRICE)


@pytest.fixture
def reader(client, owner):
    client.force_login(owner)
    return client


def _says(slot, host):
    slot.assigned_to = host
    slot.save(update_fields=["assigned_to"])


def card_of(gang, name):
    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    return next(card for card in sheet.models if card.name == name)


def chosen_on(gang, name):
    (line,) = card_of(gang, name).questions
    return line.chosen


def choose(reader, gang, name, pickable):
    """Settle the one choice on this model's card, through the page."""
    (line,) = card_of(gang, name).questions
    response = reader.post(line.href, {"thing": f"library.pickable:{pickable.pk}"})
    assert response.status_code == 302, response.content.decode()
    return Assignment.objects.get(pickable=pickable, archived=False)


@pytest.fixture
def astray(reader, gang, leader, scum, gang_slot, archetypes):
    """A pick written while the slot said the bearer, under a slot that
    now says the gang."""
    pick = choose(reader, gang, "Leader", archetypes["Brawler"])
    assert pick.miniature == leader
    assert pick.caused_by == leader.membership
    _says(gang_slot, "gang")
    gang.refresh_from_db()
    assert_reconciled(gang)
    return pick


class TestFindingWhatSitsOnAModel:
    def test_a_pick_the_gang_already_holds_is_not_named(
        self, reader, gang, leader, gang_slot, archetypes
    ):
        _says(gang_slot, "gang")
        pick = choose(reader, gang, "Leader", archetypes["Brawler"])
        assert pick.gang == gang

        assert find().nothing_here

    def test_a_pick_of_a_bearer_slot_is_not_named(
        self, reader, gang, leader, gang_slot, archetypes
    ):
        pick = choose(reader, gang, "Leader", archetypes["Brawler"])
        assert pick.miniature == leader

        assert find().nothing_here

    def test_the_plan_names_the_gang_and_its_pick(self, gang, astray):
        plan = find()

        assert plan.ok
        assert plan.gangs == ((gang.pk, (astray.pk,)),)
        assert f"gang {gang.pk}: move 1 pick off its models onto the gang" in (
            plan.preview()
        )

    def test_an_archived_pick_is_counted_and_not_named(self, gang, astray):
        astray.archived = True
        astray.save(update_fields=["archived"])

        plan = find()

        assert plan.nothing_here
        assert plan.archived == 1
        assert "1 archived pick on a model, left alone" in plan.preview()

    def test_a_pick_on_a_model_outside_its_gang_refuses(
        self, gang, astray, owner, gang_type
    ):
        elsewhere = found_gang("Elsewhere", gang_type, owner=owner, budget=1000)
        Assignment.objects.filter(pk=astray.pk).update(gang_root=elsewhere)

        plan = find()

        assert not plan.ok
        with pytest.raises(Refused):
            apply(plan)
        astray.refresh_from_db()
        assert astray.miniature is not None


class TestMovingThePick:
    def test_the_pick_lands_on_the_gang_and_keeps_its_links(
        self, gang, leader, astray, gang_slot
    ):
        before = (astray.caused_by_id, astray.chosen_for_id, astray.chosen_for_slot_id)

        report = apply(find())

        astray.refresh_from_db()
        assert (astray.gang, astray.miniature) == (gang, None)
        assert (astray.gang_root_id, astray.miniature_root_id) == (gang.pk, None)
        assert (
            astray.caused_by_id,
            astray.chosen_for_id,
            astray.chosen_for_slot_id,
        ) == before
        assert astray.caused_by == leader.membership
        assert f"gang {gang.pk}: moved 1 pick onto the gang" in report
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_leaders_card_still_reads_it_as_chosen(self, gang, astray):
        apply(find())

        assert chosen_on(gang, "Leader") == "Brawler"

    def test_what_the_pick_caused_stays_where_it_is(
        self, gang, leader, astray, default_pack
    ):
        """A power taken through what the pick offered is hosted on the
        Leader in its own right: it goes with the pick, not onto the gang."""
        from n26.library.authoring import create_rule

        below = Assignment.objects.create(
            rule=create_rule("Freeze Time"),
            miniature=leader,
            caused_by=astray,
        )

        apply(find())

        below.refresh_from_db()
        assert below.miniature == leader
        assert below.caused_by_id == astray.pk

    def test_the_pick_still_goes_with_the_leader(self, gang, leader, astray):
        from n26.tests.sandbox.actions import remove

        apply(find())

        remove(leader.membership)
        astray.refresh_from_db()
        assert astray.archived

    def test_a_second_run_finds_nothing(self, astray):
        apply(find())

        assert find().nothing_here

    def test_a_clean_gang_applies_to_nothing(self, gang, leader, scum):
        report = apply(find())

        assert report == [
            "nothing to move — every live pick of a slot the gang holds sits on the gang"
        ]
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestTheConsole:
    def test_the_operation_is_registered_and_named(self):
        from gyrinx.maintenance.registry import operations, resolve_operation

        assert Operation.REHOST_GANG_PICKS.value in {
            op.operation for op in operations()
        }
        assert (
            resolve_operation(Operation.REHOST_GANG_PICKS.value).view
            is rehost_gang_picks_view
        )

    def test_its_page_shows_the_plan_and_writes_nothing(self, client, gang, astray):
        from gyrinx.maintenance.models import Backfill

        superuser = User.objects.create_superuser("root", "root@example.com", "x")
        client.force_login(superuser)

        page = client.get(
            reverse("admin:maintenance_n26_rehost_gang_picks")
        ).content.decode()

        assert f"gang {gang.pk}: move 1 pick off its models onto the gang" in page
        assert not Backfill.objects.exists()
        astray.refresh_from_db()
        assert astray.miniature is not None
        assert not check_gang(gang)

    def test_applying_from_the_page_records_a_run_and_moves_the_pick(
        self, client, gang, astray
    ):
        from gyrinx.maintenance.models import Backfill

        superuser = User.objects.create_superuser("root", "root@example.com", "x")
        client.force_login(superuser)

        response = client.post(reverse("admin:maintenance_n26_rehost_gang_picks"))

        assert response.status_code == 302
        (run,) = Backfill.objects.all()
        assert run.status == Backfill.Status.DONE, run.error
        assert f"gang {gang.pk}: moved 1 pick onto the gang" in run.summary["report"]
        astray.refresh_from_db()
        assert astray.gang == gang
