"""The Develop Tactics post-cycle action.

Only a Leader or a Champion has it, through a modifier on each rank. Its
one result rolls a Gang Tactic on the table the player picks, when they
confirm, and gives the gang one more tactic for good: the extra stays
with the gang even after the fighter has gone.
"""

import uuid

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.access import actions_for
from n26.core.models import ActionRecord, Gang, GangTactic, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.core.status import Status
from n26.core.tactics import allowance
from n26.library.models import Picklist, Subtype

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("counter_tracking")]


@pytest.fixture
def tester(db):
    return User.objects.create_user("player")


@pytest.fixture
def seeded(default_pack, gang_type):
    from n26.library.standard_content import STANDARD_CONTENT, develop_tactics_action

    STANDARD_CONTENT["tactics-contribution"].create()
    STANDARD_CONTENT["gang-tactics-tables"].create()
    STANDARD_CONTENT["develop-tactics"].create()
    return develop_tactics_action()


@pytest.fixture
def gang(tester, gang_type, seeded):
    gang = Gang.objects.create(
        name="The Ashen Choir", owner=tester, gang_type=gang_type
    )
    with operation(gang, actor=tester) as op:
        op.found(gang_type)
    gang.refresh_from_db()
    return gang


def key(name):
    """A seeded table's key, as the forms send it."""
    return str(Picklist.objects.get(name=name, slot_type__name="Gang Tactic").pk)


@pytest.fixture
def roster(tester, gang, seeded, make_profile, make_statline):
    """A Leader, a Champion and a Ganger."""
    made = {}
    for name, rank in [("Vex", "Leader"), ("Sura", "Champion"), ("Nix", None)]:
        profile = make_profile(f"{name} entry", price=50)
        make_statline(profile)
        with operation(gang, actor=tester) as op:
            model = op.hire(profile, name)
            if rank:
                op.assign(Subtype.objects.get(name=rank), miniature=model)
        made[name] = model
    gang.refresh_from_db()
    return made


def develop(tester, gang, fighter, action, table):
    """Start, choose, review and confirm, as the flow's pages do."""
    with operation(gang, actor=tester) as op:
        record = op.start_action(fighter, action, uuid.uuid4())
    outcome = action.outcomes.get().outcome
    with operation(gang, actor=tester) as op:
        record = op.save_action_choices(record, outcome=outcome, terms={"table": table})
        record = op.review_action(record, outcome=outcome, terms=record.terms)
    with operation(gang, actor=tester) as op:
        return op.complete_action(
            record, revision=record.revision, review=record.review, outcome=outcome
        )


class TestWhoHasIt:
    def test_leaders_and_champions_only(self, roster, seeded):
        def has(name):
            return any(one.action == seeded for one in actions_for(roster[name]))

        assert has("Vex") and has("Sura")
        assert not has("Nix")

    def test_a_model_with_both_ranks_has_it_once(self, tester, gang, roster, seeded):
        with operation(gang, actor=tester) as op:
            op.assign(Subtype.objects.get(name="Champion"), miniature=roster["Vex"])
        found = [one for one in actions_for(roster["Vex"]) if one.action == seeded]
        assert len(found) == 1

    def test_seeding_twice_changes_nothing(self, seeded):
        from n26.library.standard_content import STANDARD_CONTENT

        item = STANDARD_CONTENT["develop-tactics"]
        item.create()
        assert item.check() == (4, 4)


class TestDeveloping:
    def test_it_rolls_a_tactic_on_the_chosen_table(self, tester, gang, roster, seeded):
        record = develop(tester, gang, roster["Sura"], seeded, key("Escher"))
        assert record.state == ActionRecord.State.COMPLETED
        (gained,) = GangTactic.objects.filter(gang=gang)
        assert gained.picklist.name == "Escher"
        assert gained.source == roster["Sura"]
        assert gained.action_record == record
        assert LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.TACTIC_GAINED
        ).exists()

    def test_it_adds_one_to_the_gang_and_spends_it(self, tester, gang, roster, seeded):
        develop(tester, gang, roster["Sura"], seeded, key("Universal"))
        room = allowance(gang)
        assert (room.available, room.held, room.to_generate) == (4, 1, 3)

    def test_the_extra_stays_after_the_fighter_has_gone(
        self, tester, gang, roster, seeded
    ):
        develop(tester, gang, roster["Sura"], seeded, key("Universal"))
        with operation(gang, actor=tester) as op:
            op.remove(roster["Sura"].membership)
        # The Leader's two and the developed one; the Champion's own one went.
        assert allowance(gang).available == 3

    def test_deleting_the_tactic_frees_its_token(self, tester, gang, roster, seeded):
        develop(tester, gang, roster["Sura"], seeded, key("Universal"))
        gained = GangTactic.objects.get(gang=gang)
        with operation(gang, actor=tester) as op:
            op.discard_tactic(gained, note="gone")
        room = allowance(gang)
        assert (room.available, room.to_generate) == (4, 4)

    def test_a_held_result_is_never_rolled(self, tester, gang, roster, seeded):
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 3)
        develop(tester, gang, roster["Sura"], seeded, key("Escher"))
        held = list(GangTactic.objects.filter(gang=gang, picklist__name="Escher"))
        assert len({one.pickable_id for one in held}) == 4

    def test_a_fighter_who_is_not_active_is_refused(self, tester, gang, roster, seeded):
        with operation(gang, actor=tester) as op:
            op.set_status(roster["Sura"], Status.RECOVERY)
        with pytest.raises(Refusal, match="cannot develop tactics"):
            develop(tester, gang, roster["Sura"], seeded, key("Escher"))
        assert not GangTactic.objects.filter(gang=gang).exists()

    def test_another_gangs_table_is_refused(self, tester, gang, roster, seeded):
        with pytest.raises(Refusal):
            develop(tester, gang, roster["Sura"], seeded, key("Goliath"))


class TestThePages:
    def test_the_flow_asks_for_a_table_and_shows_the_tactic(
        self, client, tester, gang, roster, seeded
    ):
        record = develop(tester, gang, roster["Vex"], seeded, key("Escher"))
        client.force_login(tester)
        done = client.get(
            reverse(
                "n26-action-flow",
                args=[roster["Vex"].pk, record.pk, "done"],
            )
        )
        body = done.content.decode()
        gained = GangTactic.objects.get(gang=gang)
        assert gained.pickable.name in body
        assert reverse("n26-gang-tactics", args=[gang.pk]) in body
        # Put right from the tactic's card, not by correcting the action.
        assert "Change result" not in body


class TestTheDevelopedLabel:
    def test_a_developed_tactic_is_marked_and_a_rolled_one_is_not(
        self, tester, gang, roster, seeded
    ):
        from n26.core.tactics import cards, held

        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 1)
        develop(tester, gang, roster["Sura"], seeded, key("Universal"))
        marked = {card.table_name: card.developed for card in cards(held(gang))}
        assert marked == {"Escher": False, "Universal": True}

    def test_a_reroll_keeps_the_mark(self, tester, gang, roster, seeded):
        record = develop(tester, gang, roster["Sura"], seeded, key("Universal"))
        gained = GangTactic.objects.get(gang=gang)
        with operation(gang, actor=tester) as op:
            new = op.reroll_tactic(gained, key("Escher"))
        assert new.action_record == record
        assert allowance(gang).available == 4

    def test_the_card_says_developed(self, client, tester, gang, roster, seeded):
        develop(tester, gang, roster["Sura"], seeded, key("Universal"))
        response = client.get(reverse("n26-gang-tactics", args=[gang.pk]))
        (card,) = response.context["tactics_island"]["cards"]
        assert card["developed"] is True
