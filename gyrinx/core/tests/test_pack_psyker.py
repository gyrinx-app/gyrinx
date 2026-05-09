"""Tests for pack support for psyker disciplines and powers.

A pack-authored discipline / power should:

- Be creatable from the pack edit UI
- Appear in the pack detail page
- Be assignable to a pack fighter (discipline) or as a default power on a pack
  fighter
- Be visible to subscribed lists in the powers-edit view + ListFighter helpers
- Stay invisible to unsubscribed lists

Tests are written red-first.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.psyker import (
    ContentFighterPsykerDisciplineAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerDiscipline,
    ContentPsykerPower,
)
from gyrinx.content.models.metadata import ContentRule
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


# --- Fixtures -----------------------------------------------------------------


@pytest.fixture
def pack_owner(user):
    return user


@pytest.fixture
def pack(pack_owner):
    return CustomContentPack.objects.create(
        name="Psyker Test Pack", owner=pack_owner, listed=True
    )


@pytest.fixture
def psyker_rule():
    """The "Psyker" content rule that drives ``is_psyker``."""
    rule, _ = ContentRule.objects.get_or_create(name="Psyker")
    return rule


@pytest.fixture
def base_discipline():
    """A base-library (non-pack) discipline so we can verify pack queries
    include base content alongside pack content."""
    return ContentPsykerDiscipline.objects.create(
        name="Base Telekinesis", generic=False
    )


@pytest.fixture
def base_power(base_discipline):
    return ContentPsykerPower.objects.create(
        name="Base Mind Lock", discipline=base_discipline
    )


@pytest.fixture
def pack_discipline(pack):
    discipline = ContentPsykerDiscipline.objects.create(
        name="Pack Pyromancy", generic=False
    )
    ct = ContentType.objects.get_for_model(ContentPsykerDiscipline)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=discipline.pk, owner=pack.owner
    )
    return discipline


@pytest.fixture
def pack_generic_discipline(pack):
    discipline = ContentPsykerDiscipline.objects.create(
        name="Pack Generic Tradition", generic=True
    )
    ct = ContentType.objects.get_for_model(ContentPsykerDiscipline)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=discipline.pk, owner=pack.owner
    )
    return discipline


@pytest.fixture
def pack_power(pack, pack_discipline):
    power = ContentPsykerPower.objects.create(
        name="Pack Inferno", discipline=pack_discipline
    )
    ct = ContentType.objects.get_for_model(ContentPsykerPower)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=power.pk, owner=pack.owner
    )
    return power


@pytest.fixture
def pack_psyker_fighter(pack, pack_owner, content_house, psyker_rule):
    """A pack-authored psyker fighter."""
    fighter = ContentFighter.objects.create(
        type="Pack Wyrd",
        category="GANGER",
        house=content_house,
        base_cost=80,
    )
    fighter.rules.add(psyker_rule)
    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=fighter.pk, owner=pack_owner
    )
    return fighter


@pytest.fixture
def pack_non_psyker_fighter(pack, pack_owner, content_house):
    fighter = ContentFighter.objects.create(
        type="Pack Mundane",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=fighter.pk, owner=pack_owner
    )
    return fighter


# --- Pack creation UI ---------------------------------------------------------


@pytest.mark.django_db
def test_pack_detail_shows_psyker_powers_section(client, pack_owner, pack):
    """The merged section header reads "Psyker Powers" — disciplines are
    rendered as group headers within this section, not as a separate
    section."""
    client.force_login(pack_owner)
    response = client.get(reverse("core:pack", args=[pack.id]))
    assert response.status_code == 200
    assert b"Psyker Powers" in response.content


@pytest.mark.django_db
def test_pack_detail_does_not_show_separate_disciplines_section(
    client, pack_owner, pack
):
    """The dedicated "Psyker Disciplines" section header is suppressed —
    disciplines render inline inside the Psyker Powers section."""
    client.force_login(pack_owner)
    response = client.get(reverse("core:pack", args=[pack.id]))
    assert response.status_code == 200
    body = response.content.decode()
    # Section header (h2) should not exist for disciplines.
    assert ">Psyker Disciplines<" not in body


@pytest.mark.django_db
def test_pack_detail_renders_discipline_group_headers(
    client, pack_owner, pack, pack_discipline, pack_power
):
    """Each pack-authored discipline appears as a group header inside the
    Psyker Powers section (mirrors skill trees)."""
    client.force_login(pack_owner)
    response = client.get(reverse("core:pack", args=[pack.id]))
    body = response.content.decode()
    assert "Pack Pyromancy" in body
    assert "Pack Inferno" in body
    # Discipline-level Edit / Archive controls live in the merged section.
    assert "Edit discipline" in body
    assert "Archive discipline" in body
    assert "Add power" in body


@pytest.mark.django_db
def test_create_pack_discipline(client, pack_owner, pack):
    client.force_login(pack_owner)
    url = reverse("core:pack-add-item", args=[pack.id, "psyker-discipline"])
    response = client.post(
        url,
        {"name": "Custom Telepathy", "generic": "", "description": "Mind reading."},
    )
    assert response.status_code == 302, response.content[:500]
    discipline = ContentPsykerDiscipline.objects.all_content().get(
        name="Custom Telepathy"
    )
    assert discipline.generic is False
    assert discipline.description == "Mind reading."


@pytest.mark.django_db
def test_create_pack_discipline_generic(client, pack_owner, pack):
    client.force_login(pack_owner)
    url = reverse("core:pack-add-item", args=[pack.id, "psyker-discipline"])
    response = client.post(
        url, {"name": "Custom Tradition", "generic": "on", "description": ""}
    )
    assert response.status_code == 302
    discipline = ContentPsykerDiscipline.objects.all_content().get(
        name="Custom Tradition"
    )
    assert discipline.generic is True


@pytest.mark.django_db
def test_create_pack_power(client, pack_owner, pack, pack_discipline):
    client.force_login(pack_owner)
    url = reverse("core:pack-add-item", args=[pack.id, "psyker-power"])
    response = client.post(
        url,
        {
            "name": "Custom Bolt",
            "discipline": str(pack_discipline.pk),
            "description": "Hurls a bolt of energy.",
        },
    )
    assert response.status_code == 302, response.content[:500]
    power = ContentPsykerPower.objects.all_content().get(name="Custom Bolt")
    assert power.description == "Hurls a bolt of energy."


@pytest.mark.django_db
def test_create_pack_power_disciplines_grouped(
    client, pack_owner, pack, pack_discipline, base_discipline
):
    """Power form discipline dropdown groups Custom (pack) vs Default (base)."""
    client.force_login(pack_owner)
    url = reverse("core:pack-add-item", args=[pack.id, "psyker-power"])
    response = client.get(url)
    assert response.status_code == 200
    body = response.content.decode()
    assert "Pack Pyromancy" in body
    assert "Base Telekinesis" in body
    assert "Custom" in body
    assert "Default" in body


# --- Pack fighter form: discipline assignments --------------------------------


@pytest.mark.django_db
def test_pack_fighter_form_lists_non_generic_disciplines(
    client,
    pack_owner,
    pack,
    pack_psyker_fighter,
    pack_discipline,
    pack_generic_discipline,
):
    """The discipline picker on the pack fighter form should list non-generic
    pack disciplines (and base disciplines) — generic disciplines must not
    appear because they cannot be assigned to a fighter."""
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse("core:pack-edit-item", args=[pack.id, pack_item.id])
    response = client.get(url)
    assert response.status_code == 200
    body = response.content.decode()
    assert "Pack Pyromancy" in body
    assert "Pack Generic Tradition" not in body


@pytest.mark.django_db
def test_pack_fighter_form_save_creates_discipline_assignment(
    client, pack_owner, pack, pack_psyker_fighter, pack_discipline, content_house
):
    """Submitting the pack fighter form with a discipline checked should
    create a ContentFighterPsykerDisciplineAssignment AND register it as a
    CustomContentPackItem so subscribed lists can see it."""
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse("core:pack-edit-item", args=[pack.id, pack_item.id])
    # Submit the bare minimum: type/category/house/base_cost/psyker_disciplines.
    response = client.post(
        url,
        {
            "type": pack_psyker_fighter.type,
            "category": pack_psyker_fighter.category,
            "house": str(pack_psyker_fighter.house_id),
            "base_cost": str(pack_psyker_fighter.base_cost),
            "psyker_disciplines": [str(pack_discipline.pk)],
        },
    )
    assert response.status_code == 302, response.content[:1000]
    assignment = ContentFighterPsykerDisciplineAssignment.objects.all_content().get(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=ct, object_id=assignment.pk, archived=False
    ).exists()


@pytest.mark.django_db
def test_pack_fighter_form_save_removes_unselected_discipline(
    client, pack_owner, pack, pack_psyker_fighter, pack_discipline
):
    """Unchecking a discipline should archive the assignment + its pack item."""
    # Pre-existing assignment.
    assignment = ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    pack_item_for_assignment = CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=assignment.pk, owner=pack_owner
    )

    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse("core:pack-edit-item", args=[pack.id, pack_item.id])
    response = client.post(
        url,
        {
            "type": pack_psyker_fighter.type,
            "category": pack_psyker_fighter.category,
            "house": str(pack_psyker_fighter.house_id),
            "base_cost": str(pack_psyker_fighter.base_cost),
            "psyker_disciplines": [],
        },
    )
    assert response.status_code == 302
    assert (
        not ContentFighterPsykerDisciplineAssignment.objects.all_content()
        .filter(pk=assignment.pk)
        .exists()
    )
    # The row is removed entirely (deleted, not archived) when the user
    # unchecks the discipline. The associated CustomContentPackItem is also
    # removed alongside it.
    assert not CustomContentPackItem.objects.filter(
        pk=pack_item_for_assignment.pk
    ).exists()


# --- Pack fighter default-powers page -----------------------------------------


@pytest.mark.django_db
def test_default_powers_page_visible_for_psyker_fighter(
    client, pack_owner, pack, pack_psyker_fighter
):
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse(
        "core:pack-fighter-default-psyker-powers", args=[pack.id, pack_item.id]
    )
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_default_powers_page_hidden_for_non_psyker_fighter(
    client, pack_owner, pack, pack_non_psyker_fighter
):
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_non_psyker_fighter.pk,
    )
    url = reverse(
        "core:pack-fighter-default-psyker-powers", args=[pack.id, pack_item.id]
    )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_default_powers_page_only_shows_powers_from_assigned_or_generic_disciplines(
    client,
    pack_owner,
    pack,
    pack_psyker_fighter,
    pack_discipline,
    pack_power,
    pack_generic_discipline,
):
    """The picker shows powers from disciplines that are: (a) assigned to
    the fighter, or (b) generic. Other powers (from disciplines the fighter
    can't access) must not appear."""
    # Assign pack_discipline to fighter so its powers are accessible.
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    # Generic discipline + power; should also appear.
    generic_power = ContentPsykerPower.objects.create(
        name="Pack Generic Bolt", discipline=pack_generic_discipline
    )
    ct = ContentType.objects.get_for_model(ContentPsykerPower)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=generic_power.pk, owner=pack_owner
    )
    # Inaccessible: power in a non-generic, non-assigned discipline.
    other_discipline = ContentPsykerDiscipline.objects.create(
        name="Pack Other", generic=False
    )
    ct_d = ContentType.objects.get_for_model(ContentPsykerDiscipline)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct_d, object_id=other_discipline.pk, owner=pack_owner
    )
    other_power = ContentPsykerPower.objects.create(
        name="Pack Other Bolt", discipline=other_discipline
    )
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=other_power.pk, owner=pack_owner
    )

    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse(
        "core:pack-fighter-default-psyker-powers", args=[pack.id, pack_item.id]
    )
    response = client.get(url)
    body = response.content.decode()
    assert "Pack Inferno" in body  # assigned discipline
    assert "Pack Generic Bolt" in body  # generic discipline
    assert "Pack Other Bolt" not in body  # inaccessible


@pytest.mark.django_db
def test_default_powers_add_creates_assignment_and_pack_item(
    client, pack_owner, pack, pack_psyker_fighter, pack_discipline, pack_power
):
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse(
        "core:pack-fighter-default-psyker-power-add", args=[pack.id, pack_item.id]
    )
    response = client.post(url, {"psyker_power": str(pack_power.pk)})
    assert response.status_code == 302, response.content[:500]
    assignment = ContentFighterPsykerPowerDefaultAssignment.objects.all_content().get(
        fighter=pack_psyker_fighter, psyker_power=pack_power
    )
    ct = ContentType.objects.get_for_model(ContentFighterPsykerPowerDefaultAssignment)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=ct, object_id=assignment.pk, archived=False
    ).exists()


@pytest.mark.django_db
def test_default_powers_remove(
    client, pack_owner, pack, pack_psyker_fighter, pack_discipline, pack_power
):
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    assignment = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=pack_psyker_fighter, psyker_power=pack_power
    )
    ct = ContentType.objects.get_for_model(ContentFighterPsykerPowerDefaultAssignment)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=assignment.pk, owner=pack_owner
    )

    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse(
        "core:pack-fighter-default-psyker-power-remove",
        args=[pack.id, pack_item.id, assignment.pk],
    )
    response = client.post(url)
    assert response.status_code == 302
    assert (
        not ContentFighterPsykerPowerDefaultAssignment.objects.all_content()
        .filter(pk=assignment.pk)
        .exists()
    )


# --- Pack-aware reads: subscribed lists ---------------------------------------


def _make_subscribed_list(user, content_house, pack, fighter, name="Sub List"):
    lst = List.objects.create(name=name, owner=user, content_house=content_house)
    lst.packs.add(pack)
    lf = ListFighter.objects.create(
        name="Sub Fighter",
        content_fighter=fighter,
        list=lst,
        owner=user,
    )
    return lst, lf


@pytest.mark.django_db
def test_subscribed_list_sees_pack_power_in_powers_edit(
    client,
    user,
    pack,
    pack_psyker_fighter,
    pack_discipline,
    pack_power,
    content_house,
):
    """The /list/X/fighter/Y/powers page must surface pack-defined powers
    when the list subscribes to the pack."""
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    # Register the assignment as a pack item so subscribed lists see it.
    ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    assignment = ContentFighterPsykerDisciplineAssignment.objects.all_content().get(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=assignment.pk, owner=pack.owner
    )

    lst, lf = _make_subscribed_list(user, content_house, pack, pack_psyker_fighter)
    client.force_login(user)
    url = reverse("core:list-fighter-powers-edit", args=[lst.id, lf.id])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Pack Inferno" in response.content


@pytest.mark.django_db
def test_subscribed_list_sees_archived_pack_power_in_powers_edit(
    client,
    user,
    pack,
    pack_psyker_fighter,
    pack_discipline,
    pack_power,
    content_house,
):
    """Archiving the CustomContentPackItem for a pack power must NOT hide it
    from a list already subscribed to the pack (see #1742).
    """
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    assignment = ContentFighterPsykerDisciplineAssignment.objects.all_content().get(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=assignment.pk, owner=pack.owner
    )

    # Archive the pack power's pack item — should still be visible to subscribers.
    power_item = CustomContentPackItem.objects.get(pack=pack, object_id=pack_power.pk)
    power_item.archived = True
    power_item.save()

    lst, lf = _make_subscribed_list(user, content_house, pack, pack_psyker_fighter)
    client.force_login(user)
    url = reverse("core:list-fighter-powers-edit", args=[lst.id, lf.id])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Pack Inferno" in response.content


@pytest.mark.django_db
def test_unsubscribed_list_hides_pack_power_in_powers_edit(
    client,
    user,
    pack,
    pack_psyker_fighter,
    pack_discipline,
    pack_power,
    content_house,
):
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    assignment = ContentFighterPsykerDisciplineAssignment.objects.all_content().get(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=assignment.pk, owner=pack.owner
    )
    # Note: the list is created but does NOT subscribe to the pack.
    # Using a base-content fighter to avoid pack-content visibility issues
    # on the fighter itself.
    lst = List.objects.create(name="No Sub", owner=user, content_house=content_house)
    lf = ListFighter.objects.create(
        name="Lone", content_fighter=pack_psyker_fighter, list=lst, owner=user
    )
    client.force_login(user)
    url = reverse("core:list-fighter-powers-edit", args=[lst.id, lf.id])
    response = client.get(url)
    assert response.status_code == 200
    # Either pack power is hidden, or the page renders without it.
    assert b"Pack Inferno" not in response.content


@pytest.mark.django_db
def test_listfighter_get_available_psyker_disciplines_includes_pack_assignments(
    user, pack, pack_psyker_fighter, pack_discipline, content_house
):
    """ListFighter.get_available_psyker_disciplines must include disciplines
    assigned via a pack-authored assignment row."""
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    assignment = ContentFighterPsykerDisciplineAssignment.objects.all_content().get(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=assignment.pk, owner=pack.owner
    )

    lst, lf = _make_subscribed_list(user, content_house, pack, pack_psyker_fighter)
    available = lf.get_available_psyker_disciplines()
    assert pack_discipline in available


@pytest.mark.django_db
def test_listfighter_psyker_default_powers_includes_pack_defaults(
    user, pack, pack_psyker_fighter, pack_discipline, pack_power, content_house
):
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    assignment = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=pack_psyker_fighter, psyker_power=pack_power
    )
    ct_d = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    da = ContentFighterPsykerDisciplineAssignment.objects.all_content().get(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct_d, object_id=da.pk, owner=pack.owner
    )
    ct_p = ContentType.objects.get_for_model(ContentFighterPsykerPowerDefaultAssignment)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct_p, object_id=assignment.pk, owner=pack.owner
    )

    lst, lf = _make_subscribed_list(user, content_house, pack, pack_psyker_fighter)
    # ``name`` returns a string with discipline parens — match by substring.
    default_labels = [p.name() for p in lf.psyker_default_powers()]
    assert any("Pack Inferno" in label for label in default_labels)


# --- Archive / restore cascade ------------------------------------------------


@pytest.mark.django_db
def test_archiving_discipline_cascades_to_powers(
    client, pack_owner, pack, pack_discipline, pack_power
):
    """Archiving a pack discipline must archive its powers' pack items so
    subscribed lists don't see orphaned powers with no accessible discipline."""
    client.force_login(pack_owner)
    discipline_pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentPsykerDiscipline),
        object_id=pack_discipline.pk,
    )
    power_pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentPsykerPower),
        object_id=pack_power.pk,
    )
    response = client.post(
        reverse("core:pack-delete-item", args=(pack.id, discipline_pack_item.id))
    )
    assert response.status_code == 302
    discipline_pack_item.refresh_from_db()
    power_pack_item.refresh_from_db()
    assert discipline_pack_item.archived
    assert power_pack_item.archived


@pytest.mark.django_db
def test_archiving_discipline_cascades_to_assignments(
    client, pack_owner, pack, pack_psyker_fighter, pack_discipline
):
    """Archiving a pack discipline must archive any pack-authored
    ContentFighterPsykerDisciplineAssignment rows that reference it."""
    assignment = ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    a_ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    a_pack_item = CustomContentPackItem.objects.create(
        pack=pack, content_type=a_ct, object_id=assignment.pk, owner=pack_owner
    )
    discipline_pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentPsykerDiscipline),
        object_id=pack_discipline.pk,
    )
    client.force_login(pack_owner)
    response = client.post(
        reverse("core:pack-delete-item", args=(pack.id, discipline_pack_item.id))
    )
    assert response.status_code == 302
    a_pack_item.refresh_from_db()
    assert a_pack_item.archived


@pytest.mark.django_db
def test_restoring_discipline_cascades_to_powers(
    client, pack_owner, pack, pack_discipline, pack_power
):
    discipline_pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentPsykerDiscipline),
        object_id=pack_discipline.pk,
    )
    power_pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentPsykerPower),
        object_id=pack_power.pk,
    )
    # Archive both first.
    client.force_login(pack_owner)
    client.post(
        reverse("core:pack-delete-item", args=(pack.id, discipline_pack_item.id))
    )
    discipline_pack_item.refresh_from_db()
    power_pack_item.refresh_from_db()
    assert discipline_pack_item.archived and power_pack_item.archived

    # Restoring the discipline restores the power too.
    response = client.post(
        reverse("core:pack-restore-item", args=(pack.id, discipline_pack_item.id))
    )
    assert response.status_code == 302
    discipline_pack_item.refresh_from_db()
    power_pack_item.refresh_from_db()
    assert not discipline_pack_item.archived
    assert not power_pack_item.archived


# --- Permission checks --------------------------------------------------------


@pytest.mark.django_db
def test_default_powers_page_403_for_non_owner(
    client, make_user, pack, pack_psyker_fighter
):
    other = make_user("other_psyker_user", "password")
    client.force_login(other)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse(
        "core:pack-fighter-default-psyker-powers", args=[pack.id, pack_item.id]
    )
    response = client.get(url)
    # `_get_pack_for_edit` raises Http404 for non-editors.
    assert response.status_code == 404


@pytest.mark.django_db
def test_default_powers_add_403_for_non_owner(
    client, make_user, pack, pack_psyker_fighter, pack_discipline, pack_power
):
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    other = make_user("other_psyker_user", "password")
    client.force_login(other)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    url = reverse(
        "core:pack-fighter-default-psyker-power-add", args=[pack.id, pack_item.id]
    )
    response = client.post(url, {"psyker_power": str(pack_power.pk)})
    assert response.status_code == 404
    assert (
        not ContentFighterPsykerPowerDefaultAssignment.objects.all_content()
        .filter(fighter=pack_psyker_fighter, psyker_power=pack_power)
        .exists()
    )


# --- Fighter preview card on edit page ----------------------------------------


@pytest.mark.django_db
def test_pack_fighter_edit_card_shows_assigned_disciplines_and_default_powers(
    client, pack_owner, pack, pack_psyker_fighter, pack_discipline, pack_power
):
    """The preview card on the pack-fighter edit page must show the
    same psyker information as the card on the pack detail page."""
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=pack_psyker_fighter, psyker_power=pack_power
    )
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    response = client.get(reverse("core:pack-edit-item", args=[pack.id, pack_item.id]))
    body = response.content.decode()
    assert "Pack Pyromancy" in body  # discipline name in card
    assert "Pack Inferno" in body  # default power name in card


@pytest.mark.django_db
def test_pack_fighter_edit_card_links_to_equipment_tab(
    client, pack_owner, pack, pack_psyker_fighter
):
    """The preview card on the pack-fighter edit page must surface a link
    to the equipment tab (Gear / Weapons "Edit" link), so users can find
    the equipment management UI from the fighter edit page."""
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    response = client.get(reverse("core:pack-edit-item", args=[pack.id, pack_item.id]))
    body = response.content.decode()
    equipment_url = reverse("core:pack-item-equipment", args=[pack.id, pack_item.id])
    assert f'href="{equipment_url}"' in body


@pytest.mark.django_db
def test_fighter_card_psyker_link_text_is_edit(
    client, pack_owner, pack, pack_psyker_fighter
):
    """The psyker link in the fighter preview card reads "Edit"."""
    client.force_login(pack_owner)
    response = client.get(reverse("core:pack", args=[pack.id]))
    body = response.content.decode()
    # Card row label is "Psyker"; link text is "Edit".
    assert "Default powers</a>" not in body  # old wording is gone
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
    )
    psyker_url = reverse(
        "core:pack-fighter-default-psyker-powers", args=[pack.id, pack_item.id]
    )
    assert f'href="{psyker_url}"' in body


# --- Multi-pack scoping (same content registered in two packs) ---------------


@pytest.fixture
def other_pack(pack_owner):
    """A second pack used to verify cross-pack isolation."""
    return CustomContentPack.objects.create(
        name="Other Psyker Pack", owner=pack_owner, listed=True
    )


@pytest.mark.django_db
def test_unchecking_discipline_does_not_remove_assignment_from_other_pack(
    client, pack_owner, pack, other_pack, pack_psyker_fighter, pack_discipline
):
    """If two packs both register the same fighter+discipline assignment,
    one pack unchecking the discipline must not remove the other pack's
    link OR delete the shared assignment row."""
    assignment = ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    a_ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    pack_a_link = CustomContentPackItem.objects.create(
        pack=pack, content_type=a_ct, object_id=assignment.pk, owner=pack_owner
    )
    pack_b_link = CustomContentPackItem.objects.create(
        pack=other_pack, content_type=a_ct, object_id=assignment.pk, owner=pack_owner
    )
    # Register the discipline in `other_pack` too so it's pack-visible there.
    d_ct = ContentType.objects.get_for_model(ContentPsykerDiscipline)
    CustomContentPackItem.objects.create(
        pack=other_pack,
        content_type=d_ct,
        object_id=pack_discipline.pk,
        owner=pack_owner,
    )

    # Now uncheck the discipline on PACK A.
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
        pack=pack,
    )
    response = client.post(
        reverse("core:pack-edit-item", args=[pack.id, pack_item.id]),
        {
            "type": pack_psyker_fighter.type,
            "category": pack_psyker_fighter.category,
            "house": str(pack_psyker_fighter.house_id),
            "base_cost": str(pack_psyker_fighter.base_cost),
            "psyker_disciplines": [],
        },
    )
    assert response.status_code == 302
    # Pack A's link is gone …
    assert not CustomContentPackItem.objects.filter(pk=pack_a_link.pk).exists()
    # … but pack B's link remains, and the shared assignment row is untouched.
    assert CustomContentPackItem.objects.filter(pk=pack_b_link.pk).exists()
    assert (
        ContentFighterPsykerDisciplineAssignment.objects.all_content()
        .filter(pk=assignment.pk)
        .exists()
    )


@pytest.mark.django_db
def test_checking_discipline_reuses_assignment_from_other_pack(
    client, pack_owner, pack, other_pack, pack_psyker_fighter, pack_discipline
):
    """If pack B already created the assignment row, pack A should reuse
    it (linking via a new CustomContentPackItem) rather than crashing on
    the (fighter, discipline) unique constraint."""
    assignment = ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    a_ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    CustomContentPackItem.objects.create(
        pack=other_pack, content_type=a_ct, object_id=assignment.pk, owner=pack_owner
    )
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
        pack=pack,
    )
    response = client.post(
        reverse("core:pack-edit-item", args=[pack.id, pack_item.id]),
        {
            "type": pack_psyker_fighter.type,
            "category": pack_psyker_fighter.category,
            "house": str(pack_psyker_fighter.house_id),
            "base_cost": str(pack_psyker_fighter.base_cost),
            "psyker_disciplines": [str(pack_discipline.pk)],
        },
    )
    assert response.status_code == 302, response.content[:500]
    # Same assignment row, but now also linked to pack A.
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=a_ct, object_id=assignment.pk
    ).exists()
    # Only one assignment row exists.
    assert (
        ContentFighterPsykerDisciplineAssignment.objects.all_content()
        .filter(fighter=pack_psyker_fighter, discipline=pack_discipline)
        .count()
        == 1
    )


@pytest.mark.django_db
def test_remove_default_power_does_not_delete_other_pack_link(
    client,
    pack_owner,
    pack,
    other_pack,
    pack_psyker_fighter,
    pack_discipline,
    pack_power,
):
    """Removing a default power from pack A must not touch pack B's link
    or delete the shared assignment row."""
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    assignment = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=pack_psyker_fighter, psyker_power=pack_power
    )
    dp_ct = ContentType.objects.get_for_model(
        ContentFighterPsykerPowerDefaultAssignment
    )
    CustomContentPackItem.objects.create(
        pack=pack, content_type=dp_ct, object_id=assignment.pk, owner=pack_owner
    )
    pack_b_link = CustomContentPackItem.objects.create(
        pack=other_pack, content_type=dp_ct, object_id=assignment.pk, owner=pack_owner
    )

    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
        pack=pack,
    )
    response = client.post(
        reverse(
            "core:pack-fighter-default-psyker-power-remove",
            args=[pack.id, pack_item.id, assignment.pk],
        )
    )
    assert response.status_code == 302
    assert CustomContentPackItem.objects.filter(pk=pack_b_link.pk).exists()
    assert (
        ContentFighterPsykerPowerDefaultAssignment.objects.all_content()
        .filter(pk=assignment.pk)
        .exists()
    )


@pytest.mark.django_db
def test_add_default_power_when_assignment_exists_in_other_pack(
    client,
    pack_owner,
    pack,
    other_pack,
    pack_psyker_fighter,
    pack_discipline,
    pack_power,
):
    """If pack B already authored the (fighter, power) default, adding it
    in pack A should reuse the row (no IntegrityError) and create a new
    CustomContentPackItem for pack A."""
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    assignment = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=pack_psyker_fighter, psyker_power=pack_power
    )
    dp_ct = ContentType.objects.get_for_model(
        ContentFighterPsykerPowerDefaultAssignment
    )
    CustomContentPackItem.objects.create(
        pack=other_pack, content_type=dp_ct, object_id=assignment.pk, owner=pack_owner
    )
    client.force_login(pack_owner)
    pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=pack_psyker_fighter.pk,
        pack=pack,
    )
    response = client.post(
        reverse(
            "core:pack-fighter-default-psyker-power-add", args=[pack.id, pack_item.id]
        ),
        {"psyker_power": str(pack_power.pk)},
    )
    assert response.status_code == 302, response.content[:500]
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=dp_ct, object_id=assignment.pk
    ).exists()


# --- Disabled defaults pack-aware ---------------------------------------------


@pytest.mark.django_db
def test_disabled_pack_default_power_excluded_from_default_powers(
    user, pack, pack_psyker_fighter, pack_discipline, pack_power, content_house
):
    """Disabling a pack-authored default power on a list fighter must
    actually remove it from ``psyker_default_powers()``. The disabled set
    is read through the default ContentManager which would otherwise
    silently exclude pack-authored rows."""
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    default_assignment = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=pack_psyker_fighter, psyker_power=pack_power
    )
    a_ct = ContentType.objects.get_for_model(ContentFighterPsykerDisciplineAssignment)
    da = ContentFighterPsykerDisciplineAssignment.objects.all_content().get(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    CustomContentPackItem.objects.create(
        pack=pack, content_type=a_ct, object_id=da.pk, owner=pack.owner
    )
    dp_ct = ContentType.objects.get_for_model(
        ContentFighterPsykerPowerDefaultAssignment
    )
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=dp_ct,
        object_id=default_assignment.pk,
        owner=pack.owner,
    )

    lst, lf = _make_subscribed_list(user, content_house, pack, pack_psyker_fighter)
    # Sanity: power appears as a default before disabling.
    assert any("Pack Inferno" in p.name() for p in lf.psyker_default_powers())
    # Disable the pack-authored default.
    lf.disabled_pskyer_default_powers.add(default_assignment)
    # Now it must NOT come back as a default.
    assert not any("Pack Inferno" in p.name() for p in lf.psyker_default_powers())


# --- Discipline cascade reaches default-power assignments ---------------------


@pytest.mark.django_db
def test_archiving_discipline_cascades_to_default_power_assignments(
    client,
    pack_owner,
    pack,
    pack_psyker_fighter,
    pack_discipline,
    pack_power,
):
    """Archiving a pack discipline must also archive
    ContentFighterPsykerPowerDefaultAssignment pack items whose power
    belongs to that discipline."""
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=pack_psyker_fighter, discipline=pack_discipline
    )
    default_assignment = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=pack_psyker_fighter, psyker_power=pack_power
    )
    dp_ct = ContentType.objects.get_for_model(
        ContentFighterPsykerPowerDefaultAssignment
    )
    dp_pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=dp_ct,
        object_id=default_assignment.pk,
        owner=pack_owner,
    )
    discipline_pack_item = CustomContentPackItem.objects.get(
        content_type=ContentType.objects.get_for_model(ContentPsykerDiscipline),
        object_id=pack_discipline.pk,
    )

    client.force_login(pack_owner)
    response = client.post(
        reverse("core:pack-delete-item", args=(pack.id, discipline_pack_item.id))
    )
    assert response.status_code == 302
    dp_pack_item.refresh_from_db()
    assert dp_pack_item.archived


# --- Description rendering ----------------------------------------------------


@pytest.mark.django_db
def test_discipline_description_shown_on_pack_detail(
    client, pack_owner, pack, pack_discipline
):
    pack_discipline.description = "A discipline of fire and rage."
    pack_discipline.save()
    client.force_login(pack_owner)
    response = client.get(reverse("core:pack", args=[pack.id]))
    assert b"A discipline of fire and rage." in response.content


@pytest.mark.django_db
def test_power_description_shown_on_pack_detail(client, pack_owner, pack, pack_power):
    pack_power.description = "Wreathes the target in flames."
    pack_power.save()
    client.force_login(pack_owner)
    response = client.get(reverse("core:pack", args=[pack.id]))
    assert b"Wreathes the target in flames." in response.content
