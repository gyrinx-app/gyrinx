"""The Gang Tactics page: how many a gang may hold, and rolling for more.

How many a gang may hold is read off its ranks through the library's
undrawn counter — 2 for a Leader, 1 for a Champion — and never stored.
Each tactic rolled is a row naming the model whose share it spent, and a
result the gang already holds is rolled again. The tables are library
roll tables a gang type's modifier gives its gangs.
"""

import random
import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang, GangTactic, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.core.tactics import allowance, cards, held, tables
from n26.library.models import Picklist, PicklistMember, Subtype

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    return User.objects.create_user("player")


@pytest.fixture
def seeded(default_pack, gang_type):
    """The standard Gang Tactics tables, given to the Escher gang type."""
    from n26.library.standard_content import STANDARD_CONTENT

    STANDARD_CONTENT["gang-tactics-tables"].create()


def found(name, gang_type, owner):
    gang = Gang.objects.create(name=name, owner=owner, gang_type=gang_type)
    with operation(gang, actor=owner) as op:
        op.found(gang_type)
    gang.refresh_from_db()
    return gang


@pytest.fixture
def gang(tester, gang_type, seeded):
    return found("The Ashen Choir", gang_type, tester)


@pytest.fixture
def ranks(default_pack):
    """The two ranks that bring Gang Tactics, as the standard seed says."""
    from n26.library.standard_content import STANDARD_CONTENT

    STANDARD_CONTENT["tactics-contribution"].create()
    return {name: Subtype.objects.get(name=name) for name in ("Leader", "Champion")}


def key(name):
    """A seeded table's key, as the forms send it."""
    return str(Picklist.objects.get(name=name, slot_type__name="Gang Tactic").pk)


@pytest.fixture
def roster(tester, gang, ranks, make_profile, make_statline):
    """A Leader, a Champion and a Ganger, who brings nothing."""
    made = {}
    for name, rank in [("Vex", "Leader"), ("Sura", "Champion"), ("Nix", None)]:
        profile = make_profile(f"{name} entry", price=50)
        make_statline(profile)
        with operation(gang, actor=tester) as op:
            model = op.hire(profile, name)
            if rank:
                op.assign(ranks[rank], miniature=model)
        made[name] = model
    gang.refresh_from_db()
    return made


def page(gang):
    return reverse("n26-gang-tactics", args=[gang.pk])


class TestWhichTables:
    def test_a_gang_gets_the_universal_table_and_its_own(self, gang):
        assert [(one.name, one.dice_label) for one in tables(gang)] == [
            ("Universal", "D66"),
            ("Escher", "D6"),
        ]

    def test_a_house_without_its_own_table_gets_the_universal_one(
        self, tester, default_pack
    ):
        from n26.library.models import GangType
        from n26.library.standard_content import STANDARD_CONTENT

        cawdor = GangType.objects.create(name="Cawdor", pack_id=default_pack.pk)
        STANDARD_CONTENT["gang-tactics-tables"].create()
        gang = found("The Ash Wardens", cawdor, tester)
        assert [one.name for one in tables(gang)] == ["Universal"]

    def test_a_table_staff_author_reaches_the_gang(self, gang, gang_type):
        """The authoring verbs staff use: a pickable, a banded picklist, a
        hidden gang slot and a modifier on the gang type giving it."""
        from n26.library import authoring
        from n26.library.models import SlotType

        slot_type = SlotType.objects.get(name="Gang Tactic")
        table = authoring.create_picklist(
            "Escher Journal", slot_type, dice="d6", roll_selects="band"
        )
        for roll in range(1, 7):
            authoring.add_picklist_member(
                table,
                authoring.create_pickable(f"Journal tactic {roll}", slot_type),
                roll_low=roll,
            )
        slot = authoring.create_slot(
            "Gang Tactics: Escher Journal",
            slot_type,
            table,
            assigned_to="gang",
            hidden=True,
            min_picks=0,
            max_picks=6,
            position=5,
        )
        authoring.modifier(
            "Gang Tactics: Escher Journal table",
            authoring.targets_gang_alone(),
            authoring.ef_adds(slot),
            attach_to=gang_type,
        )
        assert [one.name for one in tables(gang)][-1] == "Escher Journal"


class TestHowManyAGangMayHold:
    def test_a_leader_brings_two_and_a_champion_one(self, gang, roster):
        room = allowance(gang)
        assert (room.available, room.held, room.to_generate) == (3, 0, 3)

    def test_a_leader_who_is_also_a_champion_brings_two(
        self, tester, gang, roster, ranks
    ):
        with operation(gang, actor=tester) as op:
            op.assign(ranks["Champion"], miniature=roster["Vex"])
        assert allowance(gang).available == 3

    def test_adding_and_removing_a_leader_never_stacks_up(
        self, tester, gang, roster, ranks, make_profile, make_statline
    ):
        """Only the ranks on the roster now count, so hiring a Leader and
        removing them again, over and over, leaves the figure where it was."""
        profile = make_profile("Spare Leader entry", price=50)
        make_statline(profile)
        for _ in range(3):
            with operation(gang, actor=tester) as op:
                spare = op.hire(profile, "Spare")
                op.assign(ranks["Leader"], miniature=spare)
            assert allowance(gang).to_generate == 5
            with operation(gang, actor=tester) as op:
                op.remove(spare.membership)
            assert allowance(gang).to_generate == 3

    def test_a_removed_rank_does_not_hand_its_share_to_the_next(
        self, tester, gang, roster, ranks, make_profile, make_statline
    ):
        """Roll a Leader's two, remove them, hire a new Leader: the gang
        still holds the two it rolled, so the new Leader brings none to
        roll."""
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 3)
            op.remove(roster["Vex"].membership)
        profile = make_profile("New Leader entry", price=50)
        make_statline(profile)
        with operation(gang, actor=tester) as op:
            new = op.hire(profile, "Nova")
            op.assign(ranks["Leader"], miniature=new)
        room = allowance(gang)
        assert (room.available, room.held, room.to_generate) == (3, 3, 0)

    def test_a_library_without_the_counter_gives_nothing(self, gang, gang_type):
        assert allowance(gang).available == 0


class TestRolling:
    def test_each_tactic_spends_a_share_biggest_first(self, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            gained = op.roll_tactics(key("Escher"), 3)
        assert [one.source.name for one in gained] == ["Vex", "Vex", "Sura"]
        assert allowance(gang).to_generate == 0

    def test_a_held_result_is_rolled_again(self, tester, gang, roster):
        # Seeded so the dice repeat themselves; the gang still ends up
        # holding three different tactics.
        rng = random.Random(4)  # nosec B311
        with operation(gang, actor=tester) as op:
            gained = op.roll_tactics(key("Escher"), 3, rng=rng)
        assert len({one.pickable_id for one in gained}) == 3

    def test_universal_rolls_land_on_d66_bands(self, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Universal"), 1)
        landed = PicklistMember.objects.get(
            picklist=gained.picklist,
            roll_low__lte=gained.roll,
            roll_high__gte=gained.roll,
        )
        assert landed.pickable_id == gained.pickable_id

    def test_more_than_the_gang_has_left_is_refused(self, tester, gang, roster):
        with pytest.raises(Refusal), operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 4)
        assert not GangTactic.objects.filter(gang=gang).exists()

    def test_another_gangs_table_is_refused(self, tester, gang, roster):
        with pytest.raises(Refusal), operation(gang, actor=tester) as op:
            op.roll_tactics(key("Goliath"), 1)

    def test_each_tactic_goes_in_the_log(self, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 2)
        events = LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.TACTIC_GAINED
        )
        assert events.count() == 2
        assert all(event.dice == "d6" and event.roll for event in events)


class TestThePage:
    def test_anyone_reads_it(self, client, gang, roster):
        response = client.get(page(gang))
        assert response.status_code == 200
        assert response.context["tactics_island"]["toGenerate"] == 3
        assert response.context["tactics_island"]["yours"] is False

    def test_the_owner_rolls_all(self, client, tester, gang, roster):
        client.force_login(tester)
        response = client.post(page(gang), {"table": key("Escher"), "how": "all"})
        assert response.status_code == 302
        assert GangTactic.objects.filter(gang=gang).count() == 3

    def test_the_owner_rolls_a_number(self, client, tester, gang, roster):
        client.force_login(tester)
        client.post(page(gang), {"table": key("Escher"), "how": "some", "count": "2"})
        assert GangTactic.objects.filter(gang=gang).count() == 2

    def test_too_many_keeps_the_form_and_rolls_nothing(
        self, client, tester, gang, roster
    ):
        client.force_login(tester)
        response = client.post(
            page(gang), {"table": key("Escher"), "how": "some", "count": "9"}
        )
        assert response.status_code == 200
        assert "3 tactics to roll for" in response.content.decode()
        assert not GangTactic.objects.filter(gang=gang).exists()

    def test_someone_else_cannot_roll(self, client, gang, roster):
        client.force_login(User.objects.create_user("stranger"))
        client.post(page(gang), {"table": key("Escher"), "how": "all"})
        assert not GangTactic.objects.filter(gang=gang).exists()

    def test_a_held_tactic_shows_as_a_card(self, client, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        response = client.get(page(gang))
        (card,) = response.context["tactics_island"]["cards"]
        assert card["pk"] == str(gained.pk)
        assert card["name"] == gained.pickable.name

    def test_the_menu_links_here(self, client, tester, gang, roster):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert page(gang) in body


class TestDeleting:
    def test_the_owner_deletes_after_saying_yes(self, client, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        at = reverse("n26-delete-gang-tactic", args=[gang.pk, gained.pk])
        asked = client.get(at)
        assert asked.status_code == 200
        assert "Delete tactic" in asked.content.decode()
        client.post(at, {"confirmed": "yes"})
        gained.refresh_from_db()
        assert gained.archived
        assert allowance(gang).to_generate == 3
        assert LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.TACTIC_DISCARDED
        ).exists()

    def test_a_post_without_the_yes_deletes_nothing(self, client, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        client.post(reverse("n26-delete-gang-tactic", args=[gang.pk, gained.pk]))
        gained.refresh_from_db()
        assert not gained.archived

    def test_someone_else_gets_404(self, client, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(User.objects.create_user("stranger"))
        at = reverse("n26-delete-gang-tactic", args=[gang.pk, gained.pk])
        assert client.post(at, {"confirmed": "yes"}).status_code == 404
        gained.refresh_from_db()
        assert not gained.archived


class TestRerolling:
    def test_it_swaps_for_a_different_tactic_on_the_chosen_table(
        self, client, tester, gang, roster
    ):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        at = reverse("n26-reroll-gang-tactic", args=[gang.pk, gained.pk])
        assert client.get(at).status_code == 200
        client.post(at, {"table": key("Universal")})
        gained.refresh_from_db()
        assert gained.archived
        (new,) = GangTactic.objects.filter(gang=gang, archived=False)
        assert new.picklist.name == "Universal"
        assert new.source_id == gained.source_id
        assert LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.TACTIC_REROLLED
        ).exists()

    def test_never_the_tactic_being_replaced(self, tester, gang, roster):
        # Five of the six Escher tactics held, then one re-rolled on the
        # same table: the only result it may land on is the sixth.
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 3)
        tactics = list(GangTactic.objects.filter(gang=gang))
        rng = random.Random(1)  # nosec B311
        for _ in range(2):
            with operation(gang, actor=tester) as op:
                op.reroll_tactic(
                    GangTactic.objects.filter(gang=gang, archived=False).first(),
                    key("Escher"),
                    rng=rng,
                )
        held_now = {
            one.pickable_id
            for one in GangTactic.objects.filter(gang=gang, archived=False)
        }
        replaced = {one.pickable_id for one in tactics} - held_now
        assert len(held_now) == 3
        assert not replaced & held_now

    def test_a_full_table_is_refused(self, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 3)
        # Fill the rest of the Escher table by hand: the gang may hold
        # more than its ranks allow, and a re-roll must still refuse.
        holding = set(GangTactic.objects.values_list("pickable_id", flat=True))
        escher = Picklist.objects.get(pk=key("Escher"))
        for member in escher.members.all():
            if member.pickable_id not in holding:
                GangTactic.objects.create(
                    gang=gang, picklist=escher, pickable=member.pickable, roll=1
                )
        with pytest.raises(Refusal), operation(gang, actor=tester) as op:
            op.reroll_tactic(
                GangTactic.objects.filter(gang=gang).first(), key("Escher")
            )


class TestCampaignFlag:
    @pytest.fixture
    def campaign(self, tester, campaign_type):
        from n26.tests.sandbox.actions import found_campaign

        return found_campaign("Dust Falls", campaign_type, owner=tester)

    def over(self, tester, gang, roster):
        """Roll all three, then lose the Leader: three held, one allowed."""
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 3)
            op.remove(roster["Vex"].membership)

    def test_within_the_allowance_is_not_flagged(self, tester, gang, roster, campaign):
        from n26.core.tactics import too_many_for

        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 3)
        assert not too_many_for(campaign, gang)

    def test_over_the_allowance_before_the_start_is_flagged(
        self, tester, gang, roster, campaign
    ):
        from n26.core.tactics import too_many_for

        self.over(tester, gang, roster)
        assert too_many_for(campaign, gang)

    def test_after_the_start_it_is_not(self, tester, gang, roster, campaign):
        from n26.core.models import Campaign
        from n26.core.tactics import too_many_for

        self.over(tester, gang, roster)
        campaign.status = Campaign.Status.IN_PROGRESS
        assert not too_many_for(campaign, gang)

    def test_joining_warns_and_the_list_shows_a_badge(
        self, client, tester, gang, roster, campaign
    ):
        self.over(tester, gang, roster)
        client.force_login(tester)
        joined = client.post(
            f"/n26/campaigns/{campaign.pk}/gangs/add/",
            {"gang": str(gang.pk)},
            follow=True,
        )
        assert "has 3 Gang Tactics. Its Leader and Champions allow 1." in (
            joined.content.decode()
        )
        response = client.get(f"/n26/campaigns/{campaign.pk}/")
        assert [line.too_many_tactics for line in response.context["sheet"].gangs] == [
            True
        ]
        # The table is drawn by a React island, so the page carries the
        # flag in the island's props rather than the badge's words.
        assert re.search(r'"tooManyTactics":\s*true', response.content.decode())


def notes_file(tmp_path, monkeypatch, table, name, timing, effect):
    """A local tactics notes file with one row, named in the environment."""
    path = tmp_path / "tactics-notes.csv"
    path.write_text(f"table,name,timing,effect\n{table},{name},{timing},{effect}\n")
    monkeypatch.setenv("N26_TACTICS_NOTES", str(path))


class TestSuggestedTacticsNotes:
    def test_off_the_card_gives_the_page_reference(self, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 1)
        (card,) = cards(held(gang), suggest=False)
        assert card.reference == "Page 42 - Underhive Journal: Escher"
        assert card.suggested_notes == ""

    def test_on_the_card_suggests_a_summary_from_the_local_file(
        self, tester, gang, roster, tmp_path, monkeypatch
    ):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        notes_file(
            tmp_path, monkeypatch, "escher", gained.pickable.name, "Now.", "They move."
        )
        (card,) = cards(held(gang), suggest=True)
        assert card.suggested_notes == (
            "<p><strong>Timing:</strong> Now.</p>"
            "<p><strong>Effect:</strong> They move.</p>"
        )

    def test_the_suggestion_is_escaped(
        self, tester, gang, roster, tmp_path, monkeypatch
    ):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        notes_file(
            tmp_path,
            monkeypatch,
            "escher",
            gained.pickable.name,
            "<script>alert(1)</script>",
            "<b>x</b>",
        )
        (card,) = cards(held(gang), suggest=True)
        assert "<script>" not in card.suggested_notes
        assert "&lt;script&gt;" in card.suggested_notes
        assert "<b>" not in card.suggested_notes

    def test_the_page_follows_the_switch(
        self, client, tester, gang, roster, tmp_path, monkeypatch
    ):
        """The reference is always there; the suggestion follows the switch."""
        from gyrinx.site.models import Availability, FeatureFlag
        from n26.flags import TACTICS_NOTES

        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        notes_file(
            tmp_path, monkeypatch, "Escher", gained.pickable.name, "Now.", "They move."
        )
        reference = "Page 42 - Underhive Journal: Escher"
        (card,) = client.get(page(gang)).context["tactics_island"]["cards"]
        assert card["reference"] == reference
        assert card["suggested_notes"] == ""
        FeatureFlag.objects.create(
            slug=TACTICS_NOTES, name="Tactics notes", availability=Availability.EVERYONE
        )
        (card,) = client.get(page(gang)).context["tactics_island"]["cards"]
        assert card["reference"] == reference
        assert "They move." in card["suggested_notes"]

    def test_on_without_a_file_the_card_still_gives_the_reference(
        self, tester, gang, roster, monkeypatch
    ):
        monkeypatch.delenv("N26_TACTICS_NOTES", raising=False)
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 1)
        (card,) = cards(held(gang), suggest=True)
        assert card.suggested_notes == ""
        assert card.reference


def save_notes(client, gang, tactic, notes):
    return client.post(
        reverse("n26-gang-tactic-notes", args=[gang.pk, tactic.pk]), {"notes": notes}
    )


class TestSavingTacticsNotes:
    def test_the_owner_saves_notes_onto_the_card(self, client, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        response = save_notes(client, gang, gained, "<p>Use on <b>turn 2</b>.</p>")
        assert response.status_code == 200
        assert response.json() == {"notes": "<p>Use on <b>turn 2</b>.</p>"}
        (card,) = cards(held(gang), suggest=False)
        assert card.notes == "<p>Use on <b>turn 2</b>.</p>"

    def test_saving_is_logged_without_the_words(self, client, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        save_notes(client, gang, gained, "<p>Secret plan.</p>")
        save_notes(client, gang, gained, "<p>Secret plan.</p>")
        (event,) = LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.TACTIC_NOTES_EDITED
        )
        assert event.note == gained.pickable.name

    def test_everything_but_emphasis_and_lists_is_stripped(
        self, client, tester, gang, roster
    ):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        pasted = (
            '<h1 style="color:red">Big</h1><script>alert(1)</script>'
            '<p onclick="x()" class="y"><a href="javascript:x()">link</a> '
            '<img src="x" onerror="x()"><span style="font-size:90px">'
            "<u>under</u></span></p><table><tr><td>cell</td></tr></table>"
            "<ul><li><em>one</em></li></ul>"
        )
        stored = save_notes(client, gang, gained, pasted).json()["notes"]
        assert stored == (
            "Big<p>link <u>under</u></p>\ncell<ul><li><em>one</em></li></ul>"
        )

    def test_notes_too_long_once_cleaned_are_refused(
        self, client, tester, gang, roster
    ):
        from n26.core.templatetags.richtext import TACTICS_NOTES_MAX_LENGTH

        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        response = save_notes(
            client, gang, gained, "x" * (TACTICS_NOTES_MAX_LENGTH + 1)
        )
        assert response.status_code == 400
        assert "too long" in response.json()["error"]
        assert not gang.tactic_notes.exists()

    def test_markup_that_cleans_away_does_not_count_against_the_length(
        self, client, tester, gang, roster
    ):
        from n26.core.templatetags.richtext import TACTICS_NOTES_MAX_LENGTH

        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        words = TACTICS_NOTES_MAX_LENGTH // 2
        pasted = '<span style="color:red">x</span>' * words
        assert len(pasted) > TACTICS_NOTES_MAX_LENGTH
        response = save_notes(client, gang, gained, pasted)
        assert response.status_code == 200
        assert response.json()["notes"] == "x" * words

    def test_someone_else_cannot_save(self, client, gang, roster, tester):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(User.objects.create_user("stranger"))
        assert save_notes(client, gang, gained, "<p>Mine now.</p>").status_code == 404
        assert not gang.tactic_notes.exists()

    def test_signed_out_cannot_save(self, client, gang, roster, tester):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        response = save_notes(client, gang, gained, "<p>Hello.</p>")
        assert response.status_code == 302
        assert not gang.tactic_notes.exists()

    def test_a_discarded_card_cannot_take_notes(self, client, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
            op.discard_tactic(gained, note="")
        client.force_login(tester)
        assert save_notes(client, gang, gained, "<p>Late.</p>").status_code == 404

    def test_notes_come_back_when_the_tactic_is_rolled_again(
        self, client, tester, gang, roster
    ):
        with operation(gang, actor=tester) as op:
            (gained,) = op.roll_tactics(key("Escher"), 1)
        client.force_login(tester)
        save_notes(client, gang, gained, "<p>Kept.</p>")
        with operation(gang, actor=tester) as op:
            op.discard_tactic(gained, note="")
            op.gain_tactic(
                picklist=gained.picklist,
                pickable=gained.pickable,
                roll=gained.roll,
                dice=gained.picklist.dice,
                source=None,
                note="",
            )
        (card,) = cards(held(gang), suggest=False)
        assert card.pk != str(gained.pk)
        assert card.notes == "<p>Kept.</p>"

    def test_only_the_owner_is_given_the_editor(self, client, tester, gang, roster):
        island = client.get(page(gang)).context["tactics_island"]
        assert island["editorScript"] == ""
        client.force_login(tester)
        island = client.get(page(gang)).context["tactics_island"]
        assert island["editorScript"].endswith("tinymce.min.js")


class TestRerollingSeveral:
    def test_every_selected_card_goes_to_the_chosen_set(
        self, client, tester, gang, roster
    ):
        with operation(gang, actor=tester) as op:
            escher = op.roll_tactics(key("Escher"), 1)
            universal = op.roll_tactics(key("Universal"), 1)
        client.force_login(tester)
        response = client.post(
            reverse("n26-batch-gang-tactics", args=[gang.pk]),
            {
                "action": "reroll",
                "confirmed": "yes",
                "selected": [str(escher[0].pk), str(universal[0].pk)],
                "table": key("Universal"),
            },
            HTTP_ACCEPT="application/json",
        )
        assert response.status_code == 200
        now = GangTactic.objects.filter(gang=gang, archived=False)
        assert [one.picklist.name for one in now] == ["Universal", "Universal"]
        assert not {one.pickable_id for one in now} & {
            escher[0].pickable_id,
            universal[0].pickable_id,
        }


class TestBonusCards:
    def draw(self, client, gang, table, count):
        return client.post(
            reverse("n26-bonus-gang-tactics", args=[gang.pk]),
            {"table": table, "count": str(count)},
            HTTP_ACCEPT="application/json",
        )

    def test_any_set_may_be_drawn_from_even_another_houses(
        self, client, tester, gang, roster
    ):
        client.force_login(tester)
        response = self.draw(client, gang, key("Goliath"), 2)
        assert response.status_code == 200
        drawn = GangTactic.objects.filter(gang=gang, bonus=True)
        assert [one.picklist.name for one in drawn] == ["Goliath", "Goliath"]
        assert all(one.source_id is None for one in drawn)

    def test_bonus_cards_do_not_count_against_the_ranks(
        self, client, tester, gang, roster
    ):
        client.force_login(tester)
        self.draw(client, gang, key("Universal"), 3)
        room = allowance(gang)
        assert (room.available, room.held, room.to_generate) == (3, 0, 3)
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 3)
        assert allowance(gang).to_generate == 0

    def test_a_bonus_never_duplicates_a_held_tactic(self, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            op.roll_tactics(key("Escher"), 3)
            op.roll_bonus_tactics(key("Escher"), 3)
        held_now = GangTactic.objects.filter(gang=gang, archived=False)
        assert len({one.pickable_id for one in held_now}) == 6
        with pytest.raises(Refusal), operation(gang, actor=tester) as op:
            op.roll_bonus_tactics(key("Escher"), 1)

    def test_a_rerolled_bonus_stays_a_bonus_and_may_change_set(
        self, tester, gang, roster
    ):
        with operation(gang, actor=tester) as op:
            (drawn,) = op.roll_bonus_tactics(key("Universal"), 1)
        with operation(gang, actor=tester) as op:
            new = op.reroll_tactic(drawn, key("Goliath"))
        assert new.bonus and new.picklist.name == "Goliath"

    def test_the_card_is_marked(self, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            op.roll_bonus_tactics(key("Universal"), 1)
        (card,) = cards(held(gang), suggest=False)
        assert card.bonus

    def test_someone_else_cannot_draw(self, client, gang, roster):
        client.force_login(User.objects.create_user("stranger"))
        assert self.draw(client, gang, key("Universal"), 1).status_code == 404
        assert not GangTactic.objects.filter(gang=gang).exists()

    def test_a_bad_count_is_refused(self, client, tester, gang, roster):
        client.force_login(tester)
        response = self.draw(client, gang, key("Universal"), 0)
        assert response.status_code == 400
        assert response.json()["error"] == "Draw at least one bonus card."
