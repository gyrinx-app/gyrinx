"""Journal-only ledger events: the gang's history beyond its money.

A rename, a notes edit, a characteristic set by hand price nothing, but
they are part of the gang's story, so each goes through an operation and
writes an event with no entry behind it. These tests pin the contract:
the event stands alone, pinned to its gang, with the actor on it; the
money invariant never sees it; and an act that changes nothing writes
nothing.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse

from n26.core.models import Gang, LedgerEvent
from n26.core.operations import operation

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def gang(tester, gang_type):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def vex(tester, gang, make_profile, make_statline):
    profile = make_profile("Ganger", price=100)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Vex", paid=100)


def journal(gang):
    """The gang's journal-only events, oldest first."""
    return list(
        LedgerEvent.objects.filter(gang=gang, assignment__isnull=True).order_by(
            "created"
        )
    )


class TestTheJournalKeepsTheStory:
    """Acts the books do not price still land in the history."""

    def test_a_rename_writes_an_event_with_both_names_and_the_actor(
        self, tester, gang, vex
    ):
        with operation(gang, actor=tester) as op:
            op.rename(vex, "Mad Vex")
        (event,) = journal(gang)
        assert event.kind == LedgerEvent.Kind.RENAMED
        assert event.note == "Vex → Mad Vex"
        assert event.actor == tester
        assert event.miniature == vex
        assert event.gang == gang
        vex.refresh_from_db()
        assert vex.name == "Mad Vex"

    def test_a_rename_to_the_same_name_writes_nothing(self, tester, gang, vex):
        with operation(gang, actor=tester) as op:
            op.rename(vex, "Vex")
        assert journal(gang) == []

    def test_a_notes_edit_says_it_happened_and_never_what_it_says(
        self, tester, gang, vex
    ):
        with operation(gang, actor=tester) as op:
            op.edit_notes(vex, "<p>Bitten by a sump-croc. Twice.</p>")
        (event,) = journal(gang)
        assert event.kind == LedgerEvent.Kind.NOTED
        assert event.note == ""
        vex.refresh_from_db()
        assert "sump-croc" in vex.notes

    def test_saving_unchanged_notes_writes_nothing(self, tester, gang, vex):
        vex.notes = "steady"
        vex.save(update_fields=["notes"])
        with operation(gang, actor=tester) as op:
            op.edit_notes(vex, "steady")
        assert journal(gang) == []

    def test_every_event_reads_back_in_one_query_off_the_gang(self, tester, gang, vex):
        with operation(gang, actor=tester) as op:
            op.rename(vex, "Mad Vex")
        kinds = [event.kind for event in gang.ledger_events.order_by("created")]
        # The hire's money events and the rename, one stream: the
        # journal is the same log the purchases write to.
        assert LedgerEvent.Kind.RENAMED in kinds
        assert LedgerEvent.Kind.PURCHASED in kinds


class TestTheMoneyInvariantNeverSeesTheJournal:
    """Standalone events have no entry to fold and no deltas to fold in."""

    def test_reconcile_stays_clean_with_journal_events_present(self, tester, gang, vex):
        from n26.core import reconcile

        with operation(gang, actor=tester) as op:
            op.rename(vex, "Mad Vex")
            op.edit_notes(vex, "renamed and annotated in one sitting")
        assert reconcile.check_gang(gang) == []

    def test_total_spent_is_untouched_by_journal_events(self, tester, gang, vex):
        from n26.core.reconcile import total_spent

        before = total_spent(gang)
        with operation(gang, actor=tester) as op:
            op.rename(vex, "Mad Vex")
        assert total_spent(gang) == before

    def test_an_event_about_both_an_assignment_and_a_model_is_refused(
        self, tester, gang, vex
    ):
        membership = vex.membership
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                LedgerEvent.objects.create(
                    assignment=membership,
                    miniature=vex,
                    gang=gang,
                    kind=LedgerEvent.Kind.RENAMED,
                )


class TestCharacteristicsLandInTheHistory:
    """The statline boxes write through the operation, cell by cell."""

    def _form(self, vex, data):
        from n26.core.forms import statline_override_form_for

        form_class = statline_override_form_for(vex.membership.profile)
        form = form_class.opened_on(vex, data)
        assert form.is_valid(), form.errors
        return form

    def test_setting_a_cell_writes_the_override_and_says_the_move(
        self, tester, gang, vex
    ):
        form = self._form(vex, {"statline-weapon_skill": "2+"})
        with operation(gang, actor=tester) as op:
            op.set_stats(vex, form.changes())
        (event,) = journal(gang)
        assert event.kind == LedgerEvent.Kind.STAT_SET
        assert "WS" in event.note and "2+" in event.note
        (override,) = vex.stat_overrides.all()
        assert override.value == "2+"

    def test_clearing_a_cell_removes_the_override_and_says_what_returns(
        self, tester, gang, vex
    ):
        form = self._form(vex, {"statline-weapon_skill": "2+"})
        with operation(gang, actor=tester) as op:
            op.set_stats(vex, form.changes())
        form = self._form(vex, {"statline-weapon_skill": ""})
        with operation(gang, actor=tester) as op:
            op.set_stats(vex, form.changes())
        cleared = journal(gang)[-1]
        assert cleared.kind == LedgerEvent.Kind.STAT_CLEARED
        assert "2+" in cleared.note
        assert vex.stat_overrides.count() == 0

    def test_an_untouched_form_moves_nothing(self, tester, gang, vex):
        form = self._form(vex, {"statline-weapon_skill": "2+"})
        with operation(gang, actor=tester) as op:
            op.set_stats(vex, form.changes())
        form = self._form(vex, {"statline-weapon_skill": "2+"})
        assert form.changes() == []


class TestTheViewsGoThroughTheDoor:
    """The three converted views land their acts in the journal."""

    def test_renaming_through_the_dialog_lands_in_the_journal(
        self, client, tester, gang, vex
    ):
        client.force_login(tester)
        client.post(reverse("n26-rename-fighter", args=[vex.pk]), {"name": "Mad Vex"})
        (event,) = journal(gang)
        assert event.kind == LedgerEvent.Kind.RENAMED
        assert event.actor == tester

    def test_saving_notes_lands_in_the_journal(self, client, tester, gang, vex):
        client.force_login(tester)
        client.post(
            reverse("n26-edit-fighter", args=[vex.pk]),
            {"notes": "keeps to the shadows"},
        )
        (event,) = journal(gang)
        assert event.kind == LedgerEvent.Kind.NOTED

    def test_saving_a_characteristic_lands_in_the_journal(
        self, client, tester, gang, vex
    ):
        client.force_login(tester)
        client.post(
            reverse("n26-edit-fighter", args=[vex.pk]),
            {"act": "statline", "statline-weapon_skill": "2+"},
        )
        (event,) = journal(gang)
        assert event.kind == LedgerEvent.Kind.STAT_SET
