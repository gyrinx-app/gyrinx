"""Authors copy advancement tables without duplicating result definitions."""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from n26.library import authoring as a
from n26.library.models import Modifier, Pickable, Picklist
from n26.library.standard_content import STANDARD_CONTENT

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(default_pack):
    kind = a.create_slot_type("Advancement")
    table = a.create_picklist("Standard", kind, dice="2d6", roll_selects="threshold")
    for index, threshold in enumerate([2, 6, 9]):
        pick = a.create_pickable(f"Result {index}", kind)
        a.modifier(
            f"Extra rule {index}",
            a.targets_model(),
            a.ef_adds(a.create_rule(f"Rule {index}")),
            attach_to=pick,
        )
        a.add_picklist_member(
            table,
            pick,
            position=index * 2,
            roll_low=threshold,
            label_override=f"Label {index}",
            level=index + 1,
        )
    return table


def membership_values(table):
    return list(
        table.members.values_list(
            "pickable_id",
            "position",
            "label_override",
            "roll_low",
            "roll_high",
            "level",
        )
    )


def test_the_copy_keeps_settings_and_memberships_but_shares_results(table):
    before = Pickable.objects.count(), Modifier.objects.count()
    copy = a.clone_picklist(table, "Orlock")
    assert (copy.slot_type, copy.dice, copy.roll_selects, copy.pack) == (
        table.slot_type,
        "2d6",
        "threshold",
        table.pack,
    )
    assert membership_values(copy) == membership_values(table)
    assert set(copy.members.values_list("pk", flat=True)).isdisjoint(
        table.members.values_list("pk", flat=True)
    )
    assert (Pickable.objects.count(), Modifier.objects.count()) == before
    for roll in range(2, 13):
        assert [m.pickable_id for m in copy.landing(roll)] == [
            m.pickable_id for m in table.landing(roll)
        ]


def test_a_legendary_name_at_six_and_membership_edits_leave_the_original_unchanged(
    table,
):
    original = membership_values(table)
    copy = a.clone_picklist(table, "Orlock")
    name = a.create_pickable("Legendary name", table.slot_type)
    a.add_picklist_member(copy, name, roll_low=6)
    assert name.pk not in [m.pickable_id for m in copy.landing(5)]
    assert name.pk in [m.pickable_id for m in copy.landing(6)]
    assert len(copy.landing(6)) == len(table.landing(6)) + 1
    a.remove_picklist_member(copy.members.first())
    a.revise(copy.members.first(), position=20, label_override="New label")
    assert membership_values(table) == original


def test_inactive_members_remain_inactive_in_the_copy(table):
    a.revise(table.members.first(), staged=True)
    a.revise(table.members.last(), archived=True)
    copy = a.clone_picklist(table, "Orlock")
    assert list(copy.members.values_list("staged", "archived")) == list(
        table.members.values_list("staged", "archived")
    )


def test_duplicate_or_blank_names_leave_no_partial_copy(table):
    before = Picklist.objects.count()
    for name in ["standard", "   "]:
        with pytest.raises(ValidationError):
            a.clone_picklist(table, name)
    assert Picklist.objects.count() == before


def test_an_author_can_clone_the_seeded_fighter_advancement_table(client, default_pack):
    STANDARD_CONTENT["fighter-actions"].create()
    table = Picklist.objects.get(name="Fighter advancement table")
    client.force_login(User.objects.create_user("author", is_staff=True))
    url = reverse("authoring-picklist-clone", args=[table.pk])
    detail = client.get(reverse("authoring-detail", args=["picklist", table.pk]))
    assert url in detail.content.decode()
    assert client.get(url).status_code == 200
    response = client.post(url, {"name": "Orlock advancement table"})
    copy = Picklist.objects.get(name="Orlock advancement table")
    assert response.status_code == 302
    assert response.url == reverse("authoring-detail", args=["picklist", copy.pk])
    assert membership_values(copy) == membership_values(table)
    response = client.post(url, {"name": "Orlock advancement table"})
    assert response.status_code == 200
    assert response.context["form"].errors


def test_cloning_is_staff_only_and_get_does_not_write(client, table):
    url = reverse("authoring-picklist-clone", args=[table.pk])
    before = Picklist.objects.count()
    assert client.post(url, {"name": "Blocked"}).status_code == 302
    client.force_login(User.objects.create_user("player"))
    assert client.post(url, {"name": "Blocked"}).status_code == 302
    client.force_login(User.objects.create_user("author", is_staff=True))
    assert client.get(url).status_code == 200
    assert Picklist.objects.count() == before
