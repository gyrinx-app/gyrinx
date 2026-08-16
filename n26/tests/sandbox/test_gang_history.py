"""The gang's history page — the ledger's events told plainly.

The page turns the journal into acts a player can read: a hire is one
line with what came with it folded beneath, an undoing reads as an
undoing, and none of the machinery underneath is ever named. The page
itself is the owner's, because the history says things the roster does
not — when notes were edited, what a model was renamed from.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import history
from n26.core.models import Gang, Reason
from n26.core.operations import operation
from n26.library.authoring import (
    add_built_in,
    create_rule,
    create_subtype,
    create_weapon,
)
from n26.tests.sandbox.actions import found_gang, hire, refund

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("the-owner")


@pytest.fixture
def ganger(make_profile, make_statline):
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    add_built_in(profile, create_subtype("Loner"))
    add_built_in(profile, create_rule("Grit"))
    return profile


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("The Ashen Choir", gang_type, owner=owner, budget=1000)


@pytest.fixture
def vex(gang, ganger, owner):
    return hire(gang, ganger, "Vex", paid=55, actor=owner)


def sentences(gang, viewer=None):
    acts = history.build(Gang.objects.get(pk=gang.pk), viewer=viewer)
    return ["".join(s.text for s in a.spans) for a in acts]


def act_saying(gang, fragment, viewer=None):
    acts = history.build(Gang.objects.get(pk=gang.pk), viewer=viewer)
    for act in acts:
        if fragment in "".join(s.text for s in act.spans):
            return act
    raise AssertionError(
        f"No act says {fragment!r}; the story reads: {sentences(gang)}"
    )


def edit(gang):
    return operation(gang, actor=gang.owner)


@pytest.fixture(autouse=True)
def the_books_stay_honest(gang):
    """Telling the story reads the ledger and must never move it.

    Fetched fresh: operations repin through instances of their own, so
    a cached one would report a drift that is only staleness.
    """
    yield
    from n26.core.reconcile import assert_reconciled

    assert_reconciled(Gang.objects.get(pk=gang.pk))


class TestTheStoryReadsPlainly:
    """Each act is one sentence in the player's words, with what rode
    along folded beneath it."""

    def test_a_hire_is_one_line_with_what_came_with_it_beneath(self, gang, vex):
        act = act_saying(gang, "hired Vex, a Ganger")
        assert {sub.name for sub in act.subs} == {"Loner", "Grit"}
        told = sentences(gang)
        assert not any("Loner" in line or "Grit" in line for line in told)

    def test_the_money_reads_as_the_player_counts_it(self, gang, vex):
        act = act_saying(gang, "hired Vex")
        assert act.credits == -55
        assert act.rating == 55

    def test_a_refund_reads_as_money_coming_back(self, gang, vex):
        refund(vex.membership, actor=gang.owner)
        act = act_saying(gang, "returned Ganger for a refund")
        assert act.credits == 55

    def test_the_founding_folds_what_the_gang_type_brings(self, gang_type, owner):
        add_built_in(gang_type, create_rule("Law of the Blade"))
        gang = found_gang("The Blades", gang_type, owner=owner)
        act = act_saying(gang, "created the gang")
        assert {sub.name for sub in act.subs} == {"Law of the Blade"}

    def test_a_weapons_own_firing_line_earns_no_line(self, gang, vex):
        weapon = create_weapon("Autogun", profiles=[("Rapid fire", 0)], price=30)
        with edit(gang) as op:
            op.assign(weapon, miniature=vex, paid=30)
        act_saying(gang, "bought Autogun")
        acts = history.build(Gang.objects.get(pk=gang.pk))
        told = " ".join(
            "".join(s.text for s in a.spans) + " ".join(sub.name for sub in a.subs)
            for a in acts
        )
        assert "Rapid fire" not in told

    def test_nothing_says_the_machinery_underneath(self, gang, vex):
        with edit(gang) as op:
            op.take_away(vex, create_subtype("Mounted"))
            op.rename(vex, "Vex the Bold")
        told = " ".join(sentences(gang)).casefold()
        for word in ("assignment", "batch", "modifier", "archived"):
            assert word not in told


class TestUndoingReadsAsUndoing:
    """Archiving a taken-away thing restores it, and the story says so —
    the plain record would read as the opposite of what happened."""

    def test_taking_away_and_resetting_read_as_opposites(self, gang, vex):
        mounted = create_subtype("Mounted")
        with edit(gang) as op:
            op.take_away(vex, mounted)
        act_saying(gang, "took Mounted away from Vex")
        with edit(gang) as op:
            op.reset_edits(vex, "subtype")
        act = act_saying(gang, "put Mounted back on Vex")
        assert act.category == "model"

    def test_one_save_of_several_changes_is_one_line(self, gang, vex):
        with edit(gang) as op:
            op.assign(
                create_subtype("Agile"),
                miniature=vex,
                paid=0,
                reason=Reason.EDITED,
            )
            op.assign(
                create_subtype("Wyrd"),
                miniature=vex,
                paid=0,
                reason=Reason.EDITED,
            )
            op.take_away(vex, create_subtype("Mounted"))
        act = act_saying(gang, "changed what Vex is")
        turns = {sub.name: sub.note for sub in act.subs}
        assert turns == {
            "Agile": "added",
            "Wyrd": "added",
            "Mounted": "taken away",
        }

    def test_a_reset_of_several_edits_is_one_line_saying_reset(self, gang, vex):
        with edit(gang) as op:
            op.assign(
                create_subtype("Agile"),
                miniature=vex,
                paid=0,
                reason=Reason.EDITED,
            )
            op.take_away(vex, create_subtype("Mounted"))
        with edit(gang) as op:
            op.reset_edits(vex, "subtype")
        act = act_saying(gang, "reset what Vex is")
        turns = {sub.name: sub.note for sub in act.subs}
        assert turns == {"Agile": "removed", "Mounted": "back"}


class TestWhatAnActSaysAboutItself:
    """Who did it, what it was called before, which cell moved."""

    def test_the_viewer_reads_their_own_acts_as_you(self, gang, vex):
        acts = history.build(gang, viewer=gang.owner)
        assert all(a.actor == "You" for a in acts)
        acts = history.build(gang)
        assert all(a.actor == "the-owner" for a in acts)

    def test_a_rename_keeps_both_names(self, gang, vex):
        with edit(gang) as op:
            op.rename(vex, "Vex the Bold")
        act = act_saying(gang, "renamed Vex to Vex the Bold")
        assert act.note == "Vex → Vex the Bold"

    def test_a_characteristic_says_which_and_to_what(self, gang, vex):
        from n26.core.forms import statline_override_form_for

        form_class = statline_override_form_for(vex.membership.profile)
        form = form_class.opened_on(vex, {"statline-weapon_skill": "2+"})
        assert form.is_valid(), form.errors
        with edit(gang) as op:
            op.set_stats(vex, form.changes())
        act = act_saying(gang, "set Vex's WS to 2+")
        assert "2+" in act.note


class TestThePageIsTheOwners:
    """The history says things the roster does not, so only the owner
    reads it — and every narrowing is an address."""

    def test_the_owner_reads_it(self, client, gang, vex):
        client.force_login(gang.owner)
        response = client.get(reverse("n26-gang-history", args=[gang.pk]))
        assert response.status_code == 200
        page = response.content.decode()
        assert "hired" in page
        assert "Vex" in page

    def test_a_stranger_is_told_nothing_is_here(self, client, gang):
        client.force_login(User.objects.create_user("a-stranger"))
        response = client.get(reverse("n26-gang-history", args=[gang.pk]))
        assert response.status_code == 404

    def test_a_signed_out_reader_is_sent_to_sign_in(self, client, gang):
        response = client.get(reverse("n26-gang-history", args=[gang.pk]))
        assert response.status_code == 302

    def test_the_filters_narrow_and_the_address_says_how(self, client, gang, vex):
        with edit(gang) as op:
            op.rename(vex, "Vex the Bold")
        client.force_login(gang.owner)
        at = reverse("n26-gang-history", args=[gang.pk])
        money = client.get(at, {"kind": "money"}).content.decode()
        assert "hired" in money
        assert "renamed" not in money
        searched = client.get(at, {"q": "renamed"}).content.decode()
        assert "renamed" in searched
        assert "hired" not in searched
