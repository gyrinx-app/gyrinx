"""Reconcile → aggregated user notifications (#1826 + #721).

One notification per affected owner and one per affected arbitrator, each
linking every gang that changed — never one-per-list, so a player with many
gangs isn't buried.
"""

import pytest
from django.urls import reverse

from n23.core.cost.reconcile_notify import notify_lists_reconciled
from n23.core.models.action import ListActionType
from n23.core.models.backfill import Backfill
from n23.core.models.campaign import Campaign
from n23.core.models.list import List, ListFighter
from gyrinx.site.models import Notification, NotificationType
from n23.core.tasks import reconcile_all_lists
from n23.core.tests.test_balance_sheet import buy_equipment, fresh, hire_fighter


# --- notify_lists_reconciled: grouping + de-dupe --------------------------------


@pytest.mark.django_db
def test_one_notification_per_owner_with_links(make_user, make_list):
    alice = make_user("alice", "pw")
    bob = make_user("bob", "pw")
    l1 = make_list("Goliath Bruisers", owner=alice)
    l2 = make_list("Escher Wildcats", owner=alice)
    l3 = make_list("Orlock Arms", owner=bob)

    # [rating_delta, stash_delta] per gang.
    owners, arbs = notify_lists_reconciled(
        {l1.pk: [-10, 0], l2.pk: [5, 3], l3.pk: [-3, 0]}
    )
    assert (owners, arbs) == (2, 0)

    # Alice owns two affected gangs → exactly ONE notification naming both.
    alice_notifs = Notification.objects.filter(owner=alice)
    assert alice_notifs.count() == 1
    n = alice_notifs.get()
    assert n.notification_type == NotificationType.SYSTEM  # background maintenance
    assert "2 of your gangs" in n.subject
    assert n.is_system  # sender defaulted to None → Gyrinx system notification
    assert n.show_as_banner is False
    # Both gangs are linked in the content, each with a summary of what changed.
    assert "Goliath Bruisers" in n.content
    assert "Escher Wildcats" in n.content
    assert reverse("core:list", args=[l1.pk]) in n.content
    assert reverse("core:list", args=[l2.pk]) in n.content
    assert "rating -10¢" in n.content  # Goliath rating dropped by 10
    assert "rating +5¢, stash +3¢" in n.content  # Escher: both moved

    # Bob owns one → singular subject.
    bob_notif = Notification.objects.get(owner=bob)
    assert "A gang of yours was recalculated" == bob_notif.subject


@pytest.mark.django_db
def test_arb_notified_excluding_gangs_they_own(make_user, make_list, make_campaign):
    player = make_user("player", "pw")
    arb = make_user("arb", "pw")
    camp = make_campaign("Turf War", owner=arb, status=Campaign.IN_PROGRESS)
    l_player = make_list(
        "Player Gang", owner=player, status=List.CAMPAIGN_MODE, campaign=camp
    )
    l_arb_own = make_list(
        "Arbs Own Gang", owner=arb, status=List.CAMPAIGN_MODE, campaign=camp
    )

    owners, arbs = notify_lists_reconciled(
        {l_player.pk: [-10, 4], l_arb_own.pk: [5, 0]}
    )
    # Two owners (player, arb — each owns one), one arbitrator (arb, for the
    # player's gang only; their own gang is covered by the owner notification).
    assert (owners, arbs) == (2, 1)

    # The arb receives two: one as owner (their gang), one as arbitrator. Both
    # are SYSTEM notifications, so they're told apart by subject.
    arb_notifs = Notification.objects.filter(owner=arb)
    assert arb_notifs.count() == 2
    arb_camp = arb_notifs.get(subject__icontains="in your campaign")
    # The arbitrator notification links the player's gang, NOT the arb's own
    # (that would double-notify — it's already in their owner notification).
    assert "Player Gang" in arb_camp.content
    assert "Arbs Own Gang" not in arb_camp.content
    assert camp.name in arb_camp.content  # campaign named for context
    assert "rating -10¢, stash +4¢" in arb_camp.content  # both changes summarised

    # The player gets exactly one owner notification.
    assert Notification.objects.filter(owner=player).count() == 1


@pytest.mark.django_db
def test_empty_is_noop():
    assert notify_lists_reconciled({}) == (0, 0)
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_stash_only_move_shows_stash_not_rating(make_user, make_list):
    owner = make_user("stashy", "pw")
    lst = make_list("Stash Mover", owner=owner)
    # Only the stash moved (rating delta 0): summary shows the stash change and
    # omits the rating part rather than printing a meaningless "rating +0¢".
    owners, arbs = notify_lists_reconciled({lst.pk: [0, 5]})
    assert (owners, arbs) == (1, 0)
    n = Notification.objects.get(owner=owner)
    assert "Stash Mover" in n.content
    assert "(stash +5¢)" in n.content
    assert "rating +0¢" not in n.content


@pytest.mark.django_db
def test_non_campaign_list_has_no_arb(make_user, make_list):
    owner = make_user("solo", "pw")
    lst = make_list("Solo Gang", owner=owner)  # list-building mode, no campaign
    owners, arbs = notify_lists_reconciled({lst.pk: [-10, 0]})
    assert (owners, arbs) == (1, 0)


# --- estate reconcile run: single aggregated notification ----------------------


@pytest.mark.django_db
def test_estate_run_notifies_once_per_owner_and_arb(
    make_user, make_list, make_campaign, content_fighter, make_equipment
):
    """A full reconcile_all_lists run over two drifted gangs owned by the same
    player, in a campaign someone else arbitrates, sends the player ONE
    notification and the arb ONE — each naming both gangs.

    The drift here is a pure cache tamper whose ledger head already equals the
    true value, so reconcile moves the cache but writes NO action — proving the
    notification keys off ``ReconcileResult.moved``, not the presence of a
    RECONCILE action.
    """
    admin = make_user("admin", "pw")
    admin.is_staff = admin.is_superuser = True
    admin.save()
    player = make_user("player", "pw")
    arb = make_user("arb", "pw")
    camp = make_campaign("Border War", owner=arb, status=Campaign.IN_PROGRESS)

    lists = []
    for name in ("Gang One", "Gang Two"):
        lst = make_list(name, owner=player, status=List.CAMPAIGN_MODE, campaign=camp)
        # Campaign mode gates hiring on credits — stake some first.
        lst.create_action(
            user=player,
            action_type=ListActionType.UPDATE_CREDITS,
            description="Stake",
            credits_delta=1000,
        )
        lst.apply_credit_delta(1000)
        fighter = hire_fighter(player, lst, content_fighter, name="F")
        buy_equipment(player, lst, fighter, make_equipment("Gun", cost=15))
        true_rating = fresh(lst).rating_current
        fighter = ListFighter.objects.get(pk=fighter.pk)
        # Hidden drift: inflate fighter + list caches, flags clean, ledger head
        # untouched (still equals true) → moved on reconcile, but no action.
        ListFighter.objects.filter(pk=fighter.pk).update(
            rating_current=fighter.rating_current + 10, dirty=False
        )
        List.objects.filter(pk=lst.pk).update(
            rating_current=true_rating + 10, dirty=False
        )
        lists.append((lst, true_rating))

    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        triggered_by=admin,
        status=Backfill.Status.RUNNING,
    )
    reconcile_all_lists.func(
        backfill_id=str(record.id), user_id=admin.pk, batch_size=500
    )

    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    # Caches were actually corrected.
    for lst, true_rating in lists:
        assert fresh(lst).rating_current == true_rating

    # Player: exactly one aggregated owner notification naming both gangs.
    player_notifs = Notification.objects.filter(owner=player)
    assert player_notifs.count() == 1
    pn = player_notifs.get()
    assert pn.notification_type == NotificationType.SYSTEM
    assert "2 of your gangs" in pn.subject
    for lst, _ in lists:
        assert reverse("core:list", args=[lst.pk]) in pn.content
    # Cache was tampered +10 then corrected back down, so each gang shows the
    # rating drop (the stash didn't move here, so no stash part).
    assert "rating -10¢" in pn.content
    assert "stash" not in pn.content

    # Arb: exactly one aggregated campaign notification naming both gangs.
    arb_notifs = Notification.objects.filter(owner=arb)
    assert arb_notifs.count() == 1
    an = arb_notifs.get()
    assert an.notification_type == NotificationType.SYSTEM
    assert "2 gangs in your campaigns" in an.subject


@pytest.mark.django_db
def test_estate_run_no_drift_notifies_nobody(
    make_user, make_list, content_fighter, make_equipment
):
    """A clean run (nothing moved) sends nothing."""
    player = make_user("player", "pw")
    lst = make_list("Clean Gang", owner=player)
    fighter = hire_fighter(player, lst, content_fighter, name="F")
    buy_equipment(player, lst, fighter, make_equipment("Gun", cost=15))

    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        status=Backfill.Status.RUNNING,
    )
    reconcile_all_lists.func(backfill_id=str(record.id), batch_size=500)

    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_completion_notifies_once_even_on_redelivery(
    make_user, make_list, content_fighter, make_equipment
):
    """Pub/Sub is at-least-once: a redelivered final batch re-enters the DONE
    path. Notifications must NOT fire a second time — the completion is gated on
    the real RUNNING->DONE transition."""
    player = make_user("player", "pw")
    lst = make_list("Redelivery Gang", owner=player)
    fighter = hire_fighter(player, lst, content_fighter, name="F")
    buy_equipment(player, lst, fighter, make_equipment("Gun", cost=15))
    true_rating = fresh(lst).rating_current
    List.objects.filter(pk=lst.pk).update(rating_current=true_rating + 10, dirty=False)

    record = Backfill.objects.create(
        operation=Backfill.Operation.RECONCILE_LISTS,
        status=Backfill.Status.RUNNING,
    )
    reconcile_all_lists.func(backfill_id=str(record.id), batch_size=500)
    assert Notification.objects.filter(owner=player).count() == 1

    # Redelivery: same record (now DONE), the gang is already corrected.
    reconcile_all_lists.func(backfill_id=str(record.id), batch_size=500)
    assert Notification.objects.filter(owner=player).count() == 1  # not doubled
