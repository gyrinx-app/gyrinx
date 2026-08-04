"""Smoke tests for the /admin/maintenance/* views (#1825).

Verifies the auth gate (superuser-only), the dry-run rendering, and that POST
applies and creates a Backfill record + per-list audit ListAction.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from n23.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
)
from n23.core.models import Backfill
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.list import ListFighter, ListFighterEquipmentAssignment

User = get_user_model()


_SCENARIO_SEQ = 0


def _setup_scenario(content_house, make_content_fighter, make_list, make_list_fighter):
    global _SCENARIO_SEQ
    _SCENARIO_SEQ += 1
    suffix = f" #{_SCENARIO_SEQ}"
    cat = ContentEquipmentCategory.objects.create(
        name=f"Admin Mut Test{suffix}", group="Gear", persistent=True
    )
    cat.restricted_to.add(content_house)
    eq = ContentEquipment.objects.create(
        name=f"Vast Bulk{suffix}", category=cat, cost=10
    )
    stash_cf = make_content_fighter(
        type="Stash", category="STASH", house=content_house, base_cost=0, is_stash=True
    )
    ganger_cf = make_content_fighter(
        type="Test Ganger", category="GANGER", house=content_house, base_cost=50
    )
    lst = make_list("Admin Test Gang", status="campaign_mode")
    stash = make_list_fighter(lst, "Stash", content_fighter=stash_cf)
    dying = make_list_fighter(
        lst,
        "Bozur",
        content_fighter=ganger_cf,
        injury_state=ListFighter.DEAD,
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash, content_equipment=eq
    )
    ListAction.objects.create(
        list=lst,
        owner=lst.owner,
        applied=True,
        action_type=ListActionType.UPDATE_FIGHTER,
        description=f"{dying.name} was killed (50¢). All equipment transferred to stash.",
        list_fighter=dying,
    )
    return {"list": lst, "stash": stash, "dying": dying, "assignment": assignment}


# ---------------------------------------------------------------- auth gate


@pytest.mark.django_db
def test_anonymous_user_is_redirected_to_admin_login():
    c = Client()
    r = c.get(reverse("admin:maintenance_index"))
    # admin_view redirects anonymous users to the admin login page
    assert r.status_code in (302, 401, 403)


@pytest.mark.django_db
def test_staff_non_superuser_is_forbidden(make_user):
    staff = make_user("staffer", "pw")
    staff.is_staff = True
    staff.save()
    c = Client()
    c.force_login(staff)
    r = c.get(reverse("admin:maintenance_index"))
    assert r.status_code == 403


@pytest.mark.django_db
def test_superuser_can_view_index(make_user):
    su = make_user("superuser", "pw")
    su.is_staff = True
    su.is_superuser = True
    su.save()
    c = Client()
    c.force_login(su)
    r = c.get(reverse("admin:maintenance_index"))
    assert r.status_code == 200
    assert b"Available data repairs" in r.content
    assert b"Migrate persistent stash items" in r.content


# ---------------------------------------------------------------- dry-run


@pytest.mark.django_db
def test_persistent_stash_view_shows_candidates(
    make_user, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    su = make_user("supdry", "pw")
    su.is_staff = True
    su.is_superuser = True
    su.save()
    c = Client()
    c.force_login(su)

    r = c.get(reverse("admin:maintenance_persistent_stash"))
    assert r.status_code == 200
    body = r.content.decode()
    # The would-move table includes our scenario
    assert s["assignment"].content_equipment.name in body
    assert "Bozur" in body
    assert "Admin Test Gang" in body
    # Nothing has changed yet
    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["stash"].id


# ---------------------------------------------------------------- apply


@pytest.mark.django_db
def test_post_applies_creates_backfill_and_moves_assignment(
    make_user, content_house, make_content_fighter, make_list, make_list_fighter
):
    s = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    su = make_user("supapply", "pw")
    su.is_staff = True
    su.is_superuser = True
    su.save()
    c = Client()
    c.force_login(su)

    r = c.post(reverse("admin:maintenance_persistent_stash"), follow=False)
    # Redirect to detail page on success
    assert r.status_code == 302
    assert "/backfill/" in r["Location"]

    # The assignment moved
    s["assignment"].refresh_from_db()
    assert s["assignment"].list_fighter_id == s["dying"].id

    # A backfill row was created
    bf = Backfill.objects.get(triggered_by=su)
    assert bf.status == Backfill.Status.DONE
    assert bf.operation == Backfill.Operation.MIGRATE_PERSISTENT_STASH
    assert bf.summary["moved"] == 1
    assert bf.summary["affected_lists"] == 1

    # And the audit ListAction is recorded on the gang
    assert ListAction.objects.filter(
        list=s["list"], description__icontains="data repair"
    ).exists()

    # Detail page renders
    r = c.get(reverse("admin:maintenance_backfill_detail", args=[bf.pk]))
    assert r.status_code == 200
    assert s["assignment"].content_equipment.name.encode() in r.content


@pytest.mark.django_db
def test_post_scoped_by_list_id_only_touches_that_list(
    make_user, content_house, make_content_fighter, make_list, make_list_fighter
):
    s1 = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    s2 = _setup_scenario(
        content_house, make_content_fighter, make_list, make_list_fighter
    )
    su = make_user("supscope", "pw")
    su.is_staff = True
    su.is_superuser = True
    su.save()
    c = Client()
    c.force_login(su)

    r = c.post(
        reverse("admin:maintenance_persistent_stash"),
        data={"list_id": str(s1["list"].id)},
        follow=False,
    )
    assert r.status_code == 302

    # s1's assignment moved; s2's did not
    s1["assignment"].refresh_from_db()
    s2["assignment"].refresh_from_db()
    assert s1["assignment"].list_fighter_id == s1["dying"].id
    assert s2["assignment"].list_fighter_id == s2["stash"].id

    bf = Backfill.objects.get(triggered_by=su)
    assert str(bf.list_id_scope) == str(s1["list"].id)
    assert bf.summary["moved"] == 1


@pytest.mark.django_db
def test_stat_advancements_preview_changes_nothing(
    make_user, make_list, make_list_fighter
):
    """The dry run must render the plan without writing anything."""
    from n23.core.models import ListFighterAdvancement

    superuser = make_user("statsuper", "pw")
    superuser.is_staff = superuser.is_superuser = True
    superuser.save()

    lst = make_list("Preview Gang")
    fighter = make_list_fighter(lst, "Inert Fighter")
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="toughness",
        uses_mod_system=False,
        xp_cost=5,
        cost_increase=5,
        owner=lst.owner,
    )

    client = Client()
    client.force_login(superuser)
    response = client.get(reverse("admin:maintenance_stat_advancements"))

    assert response.status_code == 200
    assert b"Inert Fighter" in response.content
    # Nothing applied, nothing recorded
    assert ListFighterAdvancement.objects.filter(uses_mod_system=False).exists()
    assert not Backfill.objects.filter(
        operation=Backfill.Operation.FIX_STAT_ADVANCEMENTS
    ).exists()


@pytest.mark.django_db
def test_stat_advancements_apply_records_a_backfill(
    make_user, make_list, make_list_fighter, django_capture_on_commit_callbacks
):
    from n23.core.models import ListFighterAdvancement
    from n23.core.models.notification import Notification

    superuser = make_user("statsuper2", "pw")
    superuser.is_staff = superuser.is_superuser = True
    superuser.save()

    lst = make_list("Apply Gang")
    fighter = make_list_fighter(lst, "Inert Fighter")
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="toughness",
        uses_mod_system=False,
        xp_cost=5,
        cost_increase=5,
        owner=lst.owner,
    )

    client = Client()
    client.force_login(superuser)
    # Messages are deferred to commit, so nobody is told about a change that
    # rolled back; the callbacks have to be run for the test to see them.
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("admin:maintenance_stat_advancements"), {"notify": "on"}
        )

    assert response.status_code == 302
    backfill = Backfill.objects.get(operation=Backfill.Operation.FIX_STAT_ADVANCEMENTS)
    assert backfill.status == Backfill.Status.DONE
    assert backfill.triggered_by == superuser
    assert backfill.summary["changed"] == 1
    assert backfill.summary["visible"] == 1
    backfill.refresh_from_db()
    assert backfill.summary["messages_sent"] == 1

    assert not ListFighterAdvancement.objects.filter(uses_mod_system=False).exists()
    assert Notification.objects.filter(owner=lst.owner).exists()


@pytest.mark.django_db
def test_stat_advancements_refuses_a_second_concurrent_run(make_user):
    """A run in progress must block another starting.

    Idempotency keeps the data safe either way, but two runs would send every
    affected player a duplicate message.
    """
    superuser = make_user("statsuper3", "pw")
    superuser.is_staff = superuser.is_superuser = True
    superuser.save()

    in_progress = Backfill.objects.create(
        operation=Backfill.Operation.FIX_STAT_ADVANCEMENTS,
        status=Backfill.Status.RUNNING,
    )

    client = Client()
    client.force_login(superuser)
    response = client.post(reverse("admin:maintenance_stat_advancements"))

    assert response.status_code == 302
    assert str(in_progress.id) in response["Location"]
    # No second record was started
    assert (
        Backfill.objects.filter(
            operation=Backfill.Operation.FIX_STAT_ADVANCEMENTS
        ).count()
        == 1
    )


def _fighter_statline_type():
    from n23.content.models.statline import (
        ContentStat,
        ContentStatlineType,
        ContentStatlineTypeStat,
    )
    from n23.core.maintenance.statlines import STAT_FIELDS

    statline_type, _ = ContentStatlineType.objects.get_or_create(name="Fighter")
    for position, field_name in enumerate(STAT_FIELDS, start=1):
        ContentStatlineTypeStat.objects.get_or_create(
            statline_type=statline_type,
            stat=ContentStat.objects.get(field_name=field_name),
            defaults={"position": position},
        )
    return statline_type


@pytest.mark.django_db
def test_statline_previews_write_nothing(make_user, content_fighter):
    """Both C1 pages are dry-run on GET."""
    from n23.content.models.statline import ContentStatline

    superuser = make_user("c1super", "pw")
    superuser.is_staff = superuser.is_superuser = True
    superuser.save()
    _fighter_statline_type()

    client = Client()
    client.force_login(superuser)
    for url in (
        "maintenance_normalise_stat_formats",
        "maintenance_materialise_statlines",
    ):
        response = client.get(reverse(f"admin:{url}"))
        assert response.status_code == 200

    assert not ContentStatline.objects.filter(content_fighter=content_fighter).exists()
    assert not Backfill.objects.filter(
        operation__in=[
            Backfill.Operation.NORMALISE_STAT_FORMATS,
            Backfill.Operation.MATERIALISE_STATLINES,
        ]
    ).exists()


@pytest.mark.django_db
def test_materialise_apply_creates_statlines_and_a_record(make_user, content_fighter):
    superuser = make_user("c1super2", "pw")
    superuser.is_staff = superuser.is_superuser = True
    superuser.save()
    _fighter_statline_type()

    client = Client()
    client.force_login(superuser)
    response = client.post(reverse("admin:maintenance_materialise_statlines"))

    assert response.status_code == 302
    record = Backfill.objects.get(operation=Backfill.Operation.MATERIALISE_STATLINES)
    assert record.status == Backfill.Status.DONE
    assert record.triggered_by == superuser
    assert record.summary["created"] >= 1
    content_fighter.refresh_from_db()
    assert content_fighter.custom_statline.stats.count() == 12
