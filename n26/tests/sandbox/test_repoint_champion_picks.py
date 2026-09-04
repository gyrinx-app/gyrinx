"""Moving a pick onto the pickable its slot's picklist now offers.

A slot draws from a picklist, and pointing the slot at a different list
moves nothing already picked: the pick goes on naming what was picked,
which the list the slot now reads need not hold at all. The repair
points such a pick at the pickable of the same name on the slot's own
list, keeping everything that says which choice it settles and why it
exists, and proves each gang's books whole before it commits.

The fault is planted in the shape it takes: one picklist serves a
Champion's own Archetype choice, the pick is made through the page, and
the slot is then pointed at a list of Champion archetypes carrying the
same names.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled, check_gang
from n26.core.render import render_gang
from n26.core.repoint_champion_picks import Refused, apply, find
from n26.core.views.choose import link_slots
from n26.library.authoring import (
    add_picklist_member,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    ef_adds,
    modifier,
    targets_model,
)
from n26.maintenance import Operation, repoint_champion_picks_view
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db

CHAMPION_PRICE = 90
GANGER_PRICE = 50

#: The names the two lists share — a pick made from one has to land on
#: the same name on the other.
NAMES = ("Brawler", "Wyrd")


@pytest.fixture
def owner(db):
    return User.objects.create_user("repoint-player")


@pytest.fixture
def slot_type(default_pack):
    return create_slot_type("Archetype", allows_repeats=False)


#: What the Champion's own archetype gives the model that picked it.
PAYLOAD = "Duellist"


@pytest.fixture
def shared(slot_type):
    """The archetypes as one list held them, serving both choices."""
    return {
        name: create_pickable(name, slot_type, qualifier="Archetype") for name in NAMES
    }


@pytest.fixture
def shared_list(slot_type, shared):
    return create_picklist(
        "Archetypes", slot_type, members=[shared[name] for name in NAMES]
    )


@pytest.fixture
def champion_archetypes(slot_type):
    """The Champion's own five, under the same names."""
    made = {
        name: create_pickable(name, slot_type, qualifier="Champion Archetype")
        for name in NAMES
    }
    modifier(
        f"Brawler: {PAYLOAD}",
        targets_model(),
        ef_adds(create_rule(PAYLOAD)),
        attach_to=made["Brawler"],
    )
    return made


@pytest.fixture
def champion_list(slot_type, champion_archetypes):
    return create_picklist(
        "Champion Archetypes",
        slot_type,
        members=[champion_archetypes[name] for name in NAMES],
    )


@pytest.fixture
def champion_slot(slot_type, shared_list):
    """The Champion is asked and the Champion holds the pick. Which list
    it draws from is set by each test, because the fault is a slot
    pointed at one list and then the other."""
    return create_slot(
        "Archetype (Champion)",
        slot_type,
        shared_list,
        label="Archetype",
        min_picks=0,
        assigned_to="bearer",
    )


@pytest.fixture
def champion_profile(person_type, gang_type, champion_slot):
    """The slot reaches the Champion through a modifier on their profile,
    so the assignment that asks is their membership."""
    profile = create_profile("Champion", person_type, gang_type, price=CHAMPION_PRICE)
    modifier(
        "Champion: the model is asked its Archetype",
        targets_model(),
        ef_adds(champion_slot),
        attach_to=profile,
    )
    return profile


@pytest.fixture
def ganger_profile(person_type, gang_type):
    return create_profile("Hive Scum", person_type, gang_type, price=GANGER_PRICE)


@pytest.fixture
def gang(owner, gang_type):
    return found_gang("The Unlisted", gang_type, owner=owner, budget=1000)


@pytest.fixture
def champion(gang, champion_profile):
    return hire(gang, champion_profile, "Champion", paid=CHAMPION_PRICE)


@pytest.fixture
def scum(gang, ganger_profile):
    return hire(gang, ganger_profile, "Scum", paid=GANGER_PRICE)


@pytest.fixture
def reader(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def console(db):
    """The maintenance console, as a superuser sees it. Its own client,
    because the player's is signed in as the gang's owner."""
    from django.test import Client

    superuser = User.objects.create_superuser("root", "root@example.com", "x")
    client = Client()
    client.force_login(superuser)
    return client


def _point_slot_at(slot, picklist):
    slot.picklist = picklist
    slot.save(update_fields=["picklist"])


def rules_on(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return [line.name for line in compute(card, index).rules]


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
    return Assignment.objects.get(pickable=pickable, gang_root=gang, archived=False)


@pytest.fixture
def adrift(reader, gang, champion, champion_slot, shared, champion_list):
    """A pick made from the shared list, under a slot that now draws
    from the Champion's own."""
    pick = choose(reader, gang, "Champion", shared["Brawler"])
    assert pick.miniature == champion
    assert pick.caused_by == champion.membership
    _point_slot_at(champion_slot, champion_list)
    gang.refresh_from_db()
    assert_reconciled(gang)
    return pick


class TestFindingWhatIsOffTheList:
    def test_a_pick_the_list_still_offers_is_not_named(
        self, reader, gang, champion, shared
    ):
        pick = choose(reader, gang, "Champion", shared["Brawler"])
        assert pick.pickable == shared["Brawler"]

        assert find().nothing_here

    def test_a_pick_of_a_slot_that_hands_the_gang_the_pick_is_not_named(
        self, reader, gang, champion, champion_slot, shared, champion_list
    ):
        """Where the gang holds the pick, moving it is the gang's own
        repair and not this one."""
        choose(reader, gang, "Champion", shared["Brawler"])
        champion_slot.assigned_to = "gang"
        champion_slot.save(update_fields=["assigned_to"])
        _point_slot_at(champion_slot, champion_list)

        assert find().nothing_here

    def test_the_plan_names_the_gang_and_its_pick(
        self, gang, adrift, champion_archetypes
    ):
        plan = find()

        assert plan.ok
        assert plan.gangs == (
            (gang.pk, ((adrift.pk, champion_archetypes["Brawler"].pk),)),
        )
        assert (
            f"gang {gang.pk}: move 1 pick onto the pickable of the same name "
            "on its slot's picklist" in plan.preview()
        )

    def test_an_archived_pick_is_counted_and_not_named(self, gang, adrift):
        adrift.archived = True
        adrift.save(update_fields=["archived"])

        plan = find()

        assert plan.nothing_here
        assert plan.archived == 1
        assert (
            "1 archived pick naming something off the list, left alone"
            in plan.preview()
        )

    def test_a_pick_with_no_match_on_the_list_refuses(
        self, reader, gang, champion, champion_slot, shared, slot_type
    ):
        """Nothing of that name to move to is not this fault, and the
        move cannot run at all while one stands."""
        pick = choose(reader, gang, "Champion", shared["Wyrd"])
        _point_slot_at(
            champion_slot,
            create_picklist(
                "Champion Archetypes",
                slot_type,
                members=[create_pickable("Brawler", slot_type, qualifier="Champion")],
            ),
        )

        plan = find()

        assert not plan.ok
        assert any("nothing of that name is on its slot" in p for p in plan.problems)
        with pytest.raises(Refused):
            apply(plan)
        pick.refresh_from_db()
        assert pick.pickable == shared["Wyrd"]

    def test_a_pick_with_two_of_its_name_on_the_list_refuses(
        self, gang, adrift, champion_list, slot_type
    ):
        add_picklist_member(
            champion_list,
            create_pickable("Brawler", slot_type, qualifier="Second Champion"),
        )

        plan = find()

        assert not plan.ok
        assert any("cannot be read" in p for p in plan.problems)
        with pytest.raises(Refused):
            apply(plan)


class TestMovingThePick:
    def test_the_pick_names_the_champions_own_and_keeps_its_links(
        self, gang, champion, adrift, champion_archetypes
    ):
        before = (adrift.caused_by_id, adrift.chosen_for_id, adrift.chosen_for_slot_id)

        report = apply(find())

        adrift.refresh_from_db()
        assert adrift.pickable == champion_archetypes["Brawler"]
        assert (adrift.miniature, adrift.gang) == (champion, None)
        assert (
            adrift.caused_by_id,
            adrift.chosen_for_id,
            adrift.chosen_for_slot_id,
        ) == before
        assert adrift.caused_by == champion.membership
        assert f"gang {gang.pk}: moved 1 pick onto its slot's own pickables" in report
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_champions_card_still_reads_it_as_chosen(self, gang, adrift):
        apply(find())

        assert chosen_on(gang, "Champion") == "Brawler"

    def test_the_champion_now_reads_its_own_archetype(self, gang, champion, adrift):
        """What the repair is for: until the pick names the Champion's
        own pickable, what that pickable says reaches nobody."""
        assert PAYLOAD not in rules_on(champion)

        apply(find())

        assert PAYLOAD in rules_on(champion)

    def test_what_the_pick_caused_stays_where_it_is(self, gang, champion, adrift):
        below = Assignment.objects.create(
            rule=create_rule("Freeze Time"),
            miniature=champion,
            caused_by=adrift,
        )

        apply(find())

        below.refresh_from_db()
        assert below.miniature == champion
        assert below.caused_by_id == adrift.pk

    def test_the_pick_still_goes_with_the_champion(self, gang, champion, adrift):
        from n26.tests.sandbox.actions import remove

        apply(find())

        remove(champion.membership)
        adrift.refresh_from_db()
        assert adrift.archived

    def test_a_second_run_finds_nothing(self, adrift):
        apply(find())

        assert find().nothing_here

    def test_a_clean_gang_applies_to_nothing(self, gang, champion, scum):
        report = apply(find())

        assert report == [
            "nothing to move — every live pick names something its slot's "
            "picklist offers"
        ]
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestAGangThatCannotBeMadeWhole:
    """A gang is moved in its own transaction and proved before it
    commits. One that does not reconcile, or whose picks changed while
    the plan stood, is left exactly as it was and named on the report."""

    def test_a_gang_that_does_not_reconcile_is_rolled_back(
        self, gang, champion, adrift, shared, monkeypatch
    ):
        monkeypatch.setattr(
            "n26.core.reconcile.check_gang", lambda g: ["the books disagree"]
        )

        report = apply(find())

        adrift.refresh_from_db()
        assert adrift.pickable == shared["Brawler"]
        assert any(
            line.startswith(f"gang {gang.pk}: skipped — does not reconcile")
            for line in report
        )

    def test_a_gang_whose_picks_changed_since_the_plan_is_skipped(
        self, gang, champion, adrift, shared
    ):
        from n26.tests.sandbox.actions import remove

        plan = find()
        remove(champion.membership)

        report = apply(plan)

        assert (
            f"gang {gang.pk}: skipped — its picks changed since the plan was "
            "read; read it again" in report
        )
        adrift.refresh_from_db()
        assert adrift.archived
        assert adrift.pickable == shared["Brawler"]


class TestSeveralGangsAndSeveralPicks:
    """Each gang is its own line and its own transaction, and a gang
    with two Champions moves both picks."""

    @pytest.fixture
    def crowd(
        self,
        reader,
        gang,
        champion,
        champion_slot,
        shared,
        champion_list,
        owner,
        gang_type,
        champion_profile,
    ):
        first = choose(reader, gang, "Champion", shared["Brawler"])
        hire(gang, champion_profile, "Second", paid=CHAMPION_PRICE)
        second = choose(reader, gang, "Second", shared["Wyrd"])
        other = found_gang("The Others", gang_type, owner=owner, budget=1000)
        hire(other, champion_profile, "Champion", paid=CHAMPION_PRICE)
        third = choose(reader, other, "Champion", shared["Brawler"])
        _point_slot_at(champion_slot, champion_list)
        return {"gang": gang, "other": other, "picks": (first, second, third)}

    def test_the_plan_names_each_gang_and_counts_the_whole(
        self, crowd, champion_archetypes
    ):
        plan = find()

        assert plan.gangs == tuple(
            sorted(
                [
                    (
                        crowd["gang"].pk,
                        (
                            (
                                crowd["picks"][0].pk,
                                champion_archetypes["Brawler"].pk,
                            ),
                            (crowd["picks"][1].pk, champion_archetypes["Wyrd"].pk),
                        ),
                    ),
                    (
                        crowd["other"].pk,
                        ((crowd["picks"][2].pk, champion_archetypes["Brawler"].pk),),
                    ),
                ]
            )
        )
        assert (
            f"gang {crowd['gang'].pk}: move 2 picks onto the pickable of the "
            "same name on its slot's picklist" in plan.preview()
        )
        assert "3 picks across 2 gangs" in plan.preview()

    def test_the_plan_can_be_read_for_one_gang_alone(self, crowd, champion_archetypes):
        narrowed = find(crowd["other"].pk)

        assert narrowed.gangs == (
            (
                crowd["other"].pk,
                ((crowd["picks"][2].pk, champion_archetypes["Brawler"].pk),),
            ),
        )

    def test_every_pick_lands_on_the_name_it_had(self, crowd, champion_archetypes):
        report = apply(find())

        for pick, name in zip(
            crowd["picks"], ("Brawler", "Wyrd", "Brawler"), strict=True
        ):
            pick.refresh_from_db()
            assert pick.pickable == champion_archetypes[name]
        assert (
            f"gang {crowd['gang'].pk}: moved 2 picks onto its slot's own pickables"
            in report
        )
        assert (
            f"gang {crowd['other'].pk}: moved 1 pick onto its slot's own pickables"
            in report
        )
        for g in (crowd["gang"], crowd["other"]):
            g.refresh_from_db()
            assert_reconciled(g)
        assert find().nothing_here


class TestTheConsole:
    def test_the_operation_is_registered_and_named(self):
        from gyrinx.maintenance.registry import operations, resolve_operation

        assert Operation.REPOINT_CHAMPION_PICKS.value in {
            op.operation for op in operations()
        }
        assert (
            resolve_operation(Operation.REPOINT_CHAMPION_PICKS.value).view
            is repoint_champion_picks_view
        )

    def test_its_page_shows_the_plan_and_writes_nothing(
        self, console, gang, adrift, shared
    ):
        from gyrinx.maintenance.models import Backfill

        page = console.get(
            reverse("admin:maintenance_n26_repoint_champion_picks")
        ).content.decode()

        assert f"gang {gang.pk}: move 1 pick onto the pickable" in page
        assert not Backfill.objects.exists()
        adrift.refresh_from_db()
        assert adrift.pickable == shared["Brawler"]
        assert not check_gang(gang)

    def test_applying_from_the_page_records_a_run_and_moves_the_pick(
        self, console, gang, adrift, champion_archetypes
    ):
        from gyrinx.maintenance.models import Backfill

        response = console.post(reverse("admin:maintenance_n26_repoint_champion_picks"))

        assert response.status_code == 302
        (run,) = Backfill.objects.all()
        assert run.status == Backfill.Status.DONE, run.error
        assert (
            f"gang {gang.pk}: moved 1 pick onto its slot's own pickables"
            in run.summary["report"]
        )
        adrift.refresh_from_db()
        assert adrift.pickable == champion_archetypes["Brawler"]
