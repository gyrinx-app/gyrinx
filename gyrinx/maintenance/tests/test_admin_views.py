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


def _fighter_statline_type():
    from n23.content.models.statline import (
        ContentStat,
        ContentStatlineType,
        ContentStatlineTypeStat,
    )
    from n23.core.maintenance.statlines import STAT_FIELDS

    # Metadata mirrors content.0156 — divergent hand-mirrors are a trap for
    # any future display assertion added in this file.
    highlighted = {"leadership", "cool", "willpower", "intelligence"}
    statline_type, _ = ContentStatlineType.objects.get_or_create(name="Fighter")
    for position, field_name in enumerate(STAT_FIELDS, start=1):
        ContentStatlineTypeStat.objects.get_or_create(
            statline_type=statline_type,
            stat=ContentStat.objects.get(field_name=field_name),
            defaults={
                "position": position,
                "is_highlighted": field_name in highlighted,
                "is_first_of_group": field_name == "leadership",
            },
        )
    return statline_type
