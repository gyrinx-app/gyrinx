"""Gear stored twice, merged back into one weapon.

Builds the shape production holds — a grenade kept both as wargear and
as the weapon carrying its firing line, listed on an equipment list and
bought by gangs — and proves the repair's whole discipline: the
duplicate stops listing twice, every purchase follows onto the weapon
and starts printing a statline, no gang's numbers move, the money keeps
its provenance, a second run does nothing, and anything that is not
plainly one thing is reported and left exactly as it was.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import TRADING_POST, browse
from n26.core.models import Assignment, LedgerEntry
from n26.core.reconcile import assert_reconciled, recomputed_rating
from n26.library.models import StatlineType, StatlineTypeStat, Wargear, Weapon
from n26.library.repair import Refused, apply, find_candidates
from n26.tests.sandbox.actions import (
    add_entry,
    allows_at_most,
    buy,
    create_category,
    create_collection,
    create_default_set,
    create_gang_type,
    create_option_group,
    create_profile,
    create_rule,
    create_stat,
    create_trading_post,
    create_wargear,
    create_weapon,
    ef_adds,
    found_gang,
    hire,
    modifier,
    offer_option,
    remove,
    set_statline,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def weapon_shape(db):
    """SR / LR / Str / AP / L — the shape every weapon profile prints in."""
    shape = StatlineType.objects.create(name="Weapon")
    for position, (short, full, flags) in enumerate(
        [
            ("SR", "Short Range", {"is_inches": True}),
            ("LR", "Long Range", {"is_inches": True}),
            ("Str", "Weapon Strength", {}),
            ("AP", "Armour Piercing", {"is_modifier": True}),
            ("L", "Lethality", {}),
        ]
    ):
        StatlineTypeStat.objects.create(
            statline_type=shape,
            stat=create_stat(short, full, **flags),
            position=position,
            is_first_of_group=(position == 0),
        )
    return shape


@pytest.fixture
def grenades(default_pack, weapon_shape):
    """A grenade as production holds it: a wargear row left over from
    before it had a firing line, and the weapon that now carries one.
    Both priced, both homed under Grenades."""
    category = create_category("Wargear", "Grenades", 0)
    stray = create_wargear(
        "Frag grenades", price=30, trade_point_price=2, category=category
    )
    weapon = create_weapon(
        "Frag grenades",
        profiles=[("", 0)],
        slots=0,
        price=30,
        trade_point_price=2,
        category=category,
        statline_type=weapon_shape,
    )
    set_statline(
        weapon.profiles.get(),
        short_range="6",
        long_range="",
        weapon_strength="3",
        armour_piercing="-1",
        lethality="4+",
    )
    return stray, weapon


@pytest.fixture
def gang_type(db):
    return create_gang_type("Escher", starting_credits=1000)


@pytest.fixture
def fighter(gang_type, person_type):
    return create_profile("Ganger", person_type, gang_type, price=50)


@pytest.fixture
def equipment_list(grenades, fighter):
    """The fighter's own list, offering the stray — which is how every
    one of these was bought."""
    stray, _ = grenades
    listing = create_collection("Escher equipment")
    add_entry(listing, stray)
    fighter.built_ins = create_default_set("Ganger kit", members=[])
    fighter.save()
    return listing


@pytest.fixture
def armed(grenades, gang_type, fighter, equipment_list, owner):
    """A gang whose model bought the grenade through its equipment list."""
    stray, _ = grenades
    gang = found_gang("The Wild Ones", gang_type, owner=owner, budget=1000)
    model = hire(gang, fighter, "Scarred", paid=50)
    entry = equipment_list.entries.get()
    bought = buy(model, thing=stray, entry=entry)
    yield gang, model, bought
    # Whatever the test did, the gang's books must still fold — including
    # where the repair refused and unwound.
    gang.refresh_from_db()
    assert_reconciled(gang)


class TestWhatItFinds:
    def test_a_grenade_kept_as_both_is_one_thing_to_merge(self, grenades):
        stray, weapon = grenades

        found = find_candidates()

        assert len(found) == 1
        assert found[0].merges
        assert found[0].wargear == stray
        assert found[0].weapon == weapon

    def test_it_counts_what_would_move(self, armed, equipment_list):
        found = find_candidates()

        assert found[0].entries == 1
        assert found[0].assignments == 1
        assert found[0].gangs == 1

    def test_a_name_shared_with_a_weapon_that_has_no_firing_line_is_not_a_pair(
        self, default_pack
    ):
        category = create_category("Wargear", "Field gear", 0)
        create_wargear("Bedroll", price=10, category=category)
        create_weapon("Bedroll", price=10, category=category)

        found = find_candidates()

        assert [c.decision for c in found] == ["no_firing_line"]


class TestTheMerge:
    def test_the_wargear_goes_and_the_weapon_stays(self, grenades):
        stray, weapon = grenades

        apply()

        assert not Wargear.objects.filter(pk=stray.pk).exists()
        assert Weapon.objects.filter(pk=weapon.pk).exists()

    def test_the_equipment_list_offers_the_weapon_instead(
        self, armed, equipment_list, grenades
    ):
        _, weapon = grenades

        apply()

        entry = equipment_list.entries.get()
        assert entry.assignable == weapon

    def test_a_purchase_follows_onto_the_weapon(self, armed, grenades):
        _, weapon = grenades
        _, _, bought = armed

        apply()

        bought.refresh_from_db()
        assert bought.assignable == weapon
        assert bought.wargear_id is None

    def test_the_ledger_now_names_the_weapon_too(self, armed, grenades):
        _, weapon = grenades
        _, _, bought = armed

        apply()

        entry = LedgerEntry.objects.get(assignment=bought)
        assert entry.assignable == weapon

    def test_the_money_keeps_its_provenance(self, armed, equipment_list):
        _, _, bought = armed
        was = LedgerEntry.objects.get(assignment=bought).bought_from_id

        apply()

        entry = LedgerEntry.objects.get(assignment=bought)
        assert entry.bought_from_id == was
        assert entry.bought_from == equipment_list.entries.get()

    def test_a_sold_grenade_follows_too(self, armed, grenades):
        """An archived purchase is still part of the gang's story, so it
        must name the row that survives."""
        _, weapon = grenades
        _, _, bought = armed
        remove(bought)

        apply()

        bought.refresh_from_db()
        assert bought.archived
        assert bought.assignable == weapon

    def test_the_grenade_starts_printing_its_statline(self, armed):
        """The whole point: bought as wargear it was a bare name, because
        a firing line can hang off nothing but a weapon."""
        from n26.core.render import build_model_card

        _, model, _ = armed
        before = build_model_card(model)
        assert [line.name for line in before.weapons] == []
        assert "Frag grenades" in [str(line.name) for line in before.equipment]

        apply()

        after = build_model_card(model)
        (grenade,) = after.weapons
        assert str(grenade.name) == "Frag grenades"
        assert grenade.slots == 0
        assert grenade.profiles[0].statline is not None

    def test_the_firing_line_is_written_onto_the_purchase(self, armed, grenades):
        """The statline is not a property of the weapon alone: its free
        lines are assignments, and a purchase made against the wargear
        row never had any."""
        _, weapon = grenades
        _, _, bought = armed

        result = apply()

        assert result.lines_granted == 1
        (line,) = Assignment.objects.filter(parent=bought)
        assert line.assignable == weapon.profiles.get()
        assert line.caused_by_id == bought.pk

    def test_a_sold_grenade_gets_its_line_sold_too(self, armed):
        """A line on a weapon that has gone must not come back live."""
        _, _, bought = armed
        remove(bought)

        apply()

        (line,) = Assignment.objects.filter(parent=bought)
        assert line.archived

    def test_a_granted_line_is_worth_nothing(self, armed):
        """A weapon's own line is free, so it moves no rating — and the
        ledger has to say so, or the gang stops balancing."""
        gang, _, bought = armed

        apply()

        line = Assignment.objects.get(parent=bought)
        entry = LedgerEntry.objects.get(assignment=line)
        assert (entry.paid, entry.rating_contribution, entry.list_price) == (0, 0, 0)
        assert line.ledger_events.count() == 0

    def test_no_gang_numbers_move(self, armed):
        gang, _, _ = armed
        before = (gang.rating, gang.credits, recomputed_rating(gang))

        apply()

        gang.refresh_from_db()
        assert (gang.rating, gang.credits, recomputed_rating(gang)) == before
        assert_reconciled(gang)

    def test_it_says_what_it_did(self, armed):
        result = apply()

        assert result.entries_moved == 1
        assert result.assignments_moved == 1
        assert result.gangs == 1
        assert result.gangs_proved == 1
        assert [row["name"] for row in result.merged] == ["Frag grenades"]

    def test_a_gang_already_drifting_is_counted_but_not_proved(
        self, armed, monkeypatch
    ):
        """Books that did not balance before the run are not this repair's
        to answer for — so it neither refuses over them nor claims to have
        proved them."""
        from n26.core import reconcile

        monkeypatch.setattr(
            reconcile, "check_gang", lambda gang: ["rating pinned 100, ledger sums 130"]
        )

        result = apply()

        assert result.gangs == 1
        assert result.gangs_proved == 0
        assert result.merged
        # The real check has to be back before the gang is held to it.
        monkeypatch.undo()

    def test_running_it_again_does_nothing(self, armed):
        apply()

        again = apply()

        assert again.merged == []
        assert again.assignments_moved == 0


class TestTheTradingPost:
    def test_the_grenade_listed_twice_now_lists_once(self, grenades, default_pack):
        post = create_trading_post()
        before = [line.name for line in browse(post, TRADING_POST).all_lines()]
        assert before.count("Frag grenades") == 2

        apply()

        after = [line.name for line in browse(post, TRADING_POST).all_lines()]
        assert after.count("Frag grenades") == 1


class TestWhatItLeavesAlone:
    def test_gear_homed_in_a_different_category_is_reported_not_merged(
        self, default_pack
    ):
        """Two things may share a name. Where the books file them apart,
        that is the sheet saying they are not one thing."""
        mutations = create_category("Wargear", "Mutations", 0)
        natural = create_category("Close combat weapons", "Natural weapons", 0)
        stray = create_wargear("Tentacles", price=0, category=mutations)
        create_weapon("Tentacles", profiles=[("", 0)], price=0, category=natural)

        result = apply()

        assert result.merged == []
        assert result.skipped[0]["decision"] == "different_category"
        assert Wargear.objects.filter(pk=stray.pk).exists()

    def test_gear_the_two_price_differently_is_reported_not_merged(self, default_pack):
        category = create_category("Wargear", "Grenades", 0)
        stray = create_wargear("Krak grenades", price=45, category=category)
        create_weapon("Krak grenades", profiles=[("", 0)], price=50, category=category)

        result = apply()

        assert result.skipped[0]["decision"] == "different_price"
        assert Wargear.objects.filter(pk=stray.pk).exists()

    def test_wargear_offering_options_is_reported_not_merged(self, grenades):
        """A weapon cannot hold option groups, and they cascade — so a
        careless merge would empty them in silence."""
        stray, _ = grenades
        group = create_option_group(stray, "Choose a fuse")
        offer_option(stray, "Timed", group=group)

        result = apply()

        assert result.merged == []
        assert result.skipped[0]["decision"] == "carries_options"
        assert Wargear.objects.filter(pk=stray.pk).exists()
        assert stray.option_groups.count() == 1

    def test_wargear_carrying_a_modifier_is_reported_not_merged(self, grenades):
        stray, _ = grenades
        modifier(
            "the model: gains Blast",
            targets_model(),
            ef_adds(create_rule("Blast")),
            carried_by=stray,
        )

        result = apply()

        assert result.skipped[0]["decision"] == "carries_rules"
        assert Wargear.objects.filter(pk=stray.pk).exists()

    def test_wargear_with_a_ceiling_on_it_is_reported_not_merged(self, grenades):
        """How many may be held can name a wargear and nothing else, so
        merging would leave the ceiling nowhere to go."""
        stray, _ = grenades
        modifier(
            "the model: at most two",
            targets_model(),
            allows_at_most(2, stray),
        )

        result = apply()

        assert result.skipped[0]["decision"] == "spoken_for"
        assert Wargear.objects.filter(pk=stray.pk).exists()

    def test_a_skip_writes_nothing_at_all(self, armed, grenades):
        """A pair left alone keeps every purchase it had."""
        stray, _ = grenades
        _, _, bought = armed
        create_option_group(stray, "Choose a fuse")

        apply()

        bought.refresh_from_db()
        assert bought.assignable == stray


class TestTheConsoleDoor:
    """The console is the platform's and the repair is ours; what is
    proven here is that the two meet."""

    URL = "admin:maintenance_n26_merge_wargear_into_weapon"

    @pytest.fixture
    def superuser(self, db):
        return User.objects.create_superuser("boss", "boss@example.com", "password")

    @pytest.fixture
    def staffer(self, db):
        return User.objects.create_user("assistant", is_staff=True)

    def test_only_a_superuser_may_reach_it(self, client, staffer):
        from django.urls import reverse

        client.force_login(staffer)

        assert client.get(reverse(self.URL)).status_code == 403

    def test_it_shows_what_it_would_do_and_writes_nothing(
        self, client, superuser, armed, grenades
    ):
        from django.urls import reverse

        from gyrinx.maintenance.models import Backfill

        stray, _ = grenades
        client.force_login(superuser)

        response = client.get(reverse(self.URL))

        assert response.status_code == 200
        assert b"Frag grenades" in response.content
        assert Wargear.objects.filter(pk=stray.pk).exists()
        assert not Backfill.objects.exists()

    def test_applying_records_what_happened(self, client, superuser, armed, grenades):
        from django.urls import reverse

        from gyrinx.maintenance.models import Backfill

        stray, _ = grenades
        client.force_login(superuser)

        response = client.post(reverse(self.URL))

        assert response.status_code == 302
        assert not Wargear.objects.filter(pk=stray.pk).exists()
        record = Backfill.objects.get()
        assert record.status == Backfill.Status.DONE
        assert record.summary["assignments_moved"] == 1
        assert record.summary["gangs"] == 1

    def test_a_run_with_nothing_to_do_records_nothing(self, client, superuser):
        from django.urls import reverse

        from gyrinx.maintenance.models import Backfill

        client.force_login(superuser)

        client.post(reverse(self.URL))

        assert not Backfill.objects.exists()


class TestWhenItRefuses:
    def test_a_gang_whose_numbers_move_unwinds_the_whole_run(
        self, armed, grenades, monkeypatch
    ):
        """The proof is not decoration: if a gang stops balancing, nothing
        lands — not even the moves that were fine."""
        from n26.core import reconcile

        stray, _ = grenades
        asked = []

        def drifting(gang):
            # Balanced the first time it is asked and broken the second,
            # so the pre-check passes and the proof afterwards does not.
            asked.append(gang.pk)
            if asked.count(gang.pk) == 1:
                return []
            return ["rating pinned 100, ledger sums to 130"]

        monkeypatch.setattr(reconcile, "check_gang", drifting)

        with pytest.raises(Refused):
            apply()

        assert Wargear.objects.filter(pk=stray.pk).exists()
        assert Assignment.objects.filter(wargear=stray).count() == 1
        # The real check has to be back before the gang is held to it — an
        # unwound run must leave the books exactly as it found them.
        monkeypatch.undo()
