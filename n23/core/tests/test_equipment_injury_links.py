"""Equipment that treats a lasting injury (#1027).

Covers the two modes an equipment-injury link can take:

- ``OFFSET`` — Trading Post bionics. The injury stays live and keeps applying
  its own modifiers; the bionic's +1 is what cancels them out.
- ``SUPPRESS`` — Van Saar Cyberteknika. Nothing offsets the injury, so its
  modifiers have to stop applying.

In both cases the injury row survives, because a lasting injury is a permanent
note on the gang roster.
"""

import pytest
from django.db import IntegrityError
from django.urls import reverse

from n23.content.models import (
    ContentEquipmentInjuryLink,
    ContentInjury,
    ContentInjuryDefaultOutcome,
    ContentModFighterStat,
)
from n23.core.models.list import ListFighterEquipmentAssignment, ListFighterInjury


@pytest.fixture
def eye_injury():
    """Eye Injury: Recovery, and Ballistic Skill down by one."""
    injury = ContentInjury.objects.create(
        name="Eye Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    injury.modifiers.add(
        ContentModFighterStat.objects.create(
            stat="ballistic_skill", mode="worsen", value="1"
        )
    )
    return injury


@pytest.fixture
def bionic_eye(make_equipment):
    """A mundane bionic eye: +1 Ballistic Skill, as printed."""
    equipment = make_equipment("Bionic eye (mundane)", category="Status Items", cost=45)
    equipment.modifiers.add(
        ContentModFighterStat.objects.create(
            stat="ballistic_skill", mode="improve", value="1"
        )
    )
    return equipment


@pytest.fixture
def injured_fighter(list_with_campaign, make_list_fighter, user, eye_injury):
    fighter = make_list_fighter(list_with_campaign, "Injured Fighter")
    ListFighterInjury.objects.create(
        fighter=fighter, injury=eye_injury, owner=user, notes=""
    )
    return fighter


def _assign(fighter, equipment):
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=equipment
    )
    # Statlines and treatments are cached per instance, so callers that assign
    # gear mid-test need a fresh read.
    return type(fighter).objects.get(pk=fighter.pk)


def _stat(fighter, field_name):
    return next(s for s in fighter.statline if s.field_name == field_name).value


def _content_stat(content_fighter, field_name):
    """The printed value of a stat, read from the fighter type's statline."""
    stats = {s["field_name"]: s["value"] for s in content_fighter.statline()}
    return stats[field_name]


@pytest.mark.django_db
def test_untreated_injury_applies_its_modifiers(injured_fighter, content_fighter):
    """Baseline: with no bionic, the injury worsens Ballistic Skill."""
    assert _content_stat(content_fighter, "ballistic_skill") == "5+"
    assert _stat(injured_fighter, "ballistic_skill") == "6+"

    entry = injured_fighter.injuries_display[0]
    assert not entry.is_treated
    assert entry.treated_by == ""


@pytest.mark.django_db
def test_offset_keeps_injury_modifiers_live(
    injured_fighter, bionic_eye, eye_injury, user
):
    """A bionic cancels the injury by arithmetic, not by switching it off.

    Both modifiers stay in play, so the fighter lands back on their printed
    Ballistic Skill — and would keep the +1 even if the injury were removed.
    """
    ContentEquipmentInjuryLink.objects.create(
        equipment=bionic_eye,
        injury=eye_injury,
        mode=ContentEquipmentInjuryLink.Mode.OFFSET,
    )
    fighter = _assign(injured_fighter, bionic_eye)

    assert _stat(fighter, "ballistic_skill") == "5+"
    # The injury's own modifier is still being applied — it is merely cancelled.
    assert any(
        mod.stat == "ballistic_skill" and mod.mode == "worsen" for mod in fighter._mods
    )


@pytest.mark.django_db
def test_suppress_drops_injury_modifiers(injured_fighter, make_equipment, eye_injury):
    """Cyberteknika replaces the injury's effects, so its modifiers stop.

    The implant carries no stat modifier of its own, so if the injury kept
    applying, the fighter would be left worse off than the rules allow.
    """
    cyberteknika = make_equipment(
        "Ocular Cyberteknika", category="Status Items", cost=50
    )
    ContentEquipmentInjuryLink.objects.create(
        equipment=cyberteknika,
        injury=eye_injury,
        mode=ContentEquipmentInjuryLink.Mode.SUPPRESS,
    )
    fighter = _assign(injured_fighter, cyberteknika)

    assert _stat(fighter, "ballistic_skill") == "5+"
    assert not any(
        mod.stat == "ballistic_skill" and mod.mode == "worsen" for mod in fighter._mods
    )


@pytest.mark.django_db
def test_treatment_never_deletes_the_injury(injured_fighter, bionic_eye, eye_injury):
    """The roster note survives treatment — it is only marked as treated."""
    ContentEquipmentInjuryLink.objects.create(equipment=bionic_eye, injury=eye_injury)
    fighter = _assign(injured_fighter, bionic_eye)

    assert ListFighterInjury.objects.filter(fighter=fighter).count() == 1

    entry = fighter.injuries_display[0]
    assert entry.is_treated
    assert entry.treated_by == "Bionic eye (mundane)"


@pytest.mark.django_db
def test_treatment_is_derived_so_selling_the_bionic_reverts_it(
    injured_fighter, bionic_eye, eye_injury
):
    """Removing the gear puts the injury back to untreated, with no cleanup."""
    ContentEquipmentInjuryLink.objects.create(equipment=bionic_eye, injury=eye_injury)
    fighter = _assign(injured_fighter, bionic_eye)
    assert fighter.injuries_display[0].is_treated

    ListFighterEquipmentAssignment.objects.filter(list_fighter=fighter).delete()
    fighter = type(fighter).objects.get(pk=fighter.pk)

    assert not fighter.injuries_display[0].is_treated


@pytest.mark.django_db
def test_link_only_treats_its_own_injury(injured_fighter, make_equipment):
    """A bionic for a different location leaves the injury untreated."""
    hobbled = ContentInjury.objects.create(
        name="Hobbled", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    bionic_leg = make_equipment(
        "Bionic leg (mundane)", category="Status Items", cost=25
    )
    ContentEquipmentInjuryLink.objects.create(equipment=bionic_leg, injury=hobbled)
    fighter = _assign(injured_fighter, bionic_leg)

    assert not fighter.injuries_display[0].is_treated


@pytest.mark.django_db
def test_one_item_can_treat_several_injuries(
    list_with_campaign, make_list_fighter, make_equipment, user
):
    """Cranial Cyberteknika answers either Head Injury or Humiliated."""
    head_injury = ContentInjury.objects.create(
        name="Head Injury", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    humiliated = ContentInjury.objects.create(
        name="Humiliated", phase=ContentInjuryDefaultOutcome.CONVALESCENCE
    )
    cranial = make_equipment("Cranial Cyberteknika", category="Status Items", cost=30)
    for injury in (head_injury, humiliated):
        ContentEquipmentInjuryLink.objects.create(
            equipment=cranial,
            injury=injury,
            mode=ContentEquipmentInjuryLink.Mode.SUPPRESS,
        )

    fighter = make_list_fighter(list_with_campaign, "Cyber Fighter")
    for injury in (head_injury, humiliated):
        ListFighterInjury.objects.create(fighter=fighter, injury=injury, owner=user)
    fighter = _assign(fighter, cranial)

    assert [e.is_treated for e in fighter.injuries_display] == [True, True]


@pytest.mark.django_db
def test_links_are_unique_per_equipment_and_injury(bionic_eye, eye_injury):
    ContentEquipmentInjuryLink.objects.create(equipment=bionic_eye, injury=eye_injury)
    with pytest.raises(IntegrityError):
        ContentEquipmentInjuryLink.objects.create(
            equipment=bionic_eye,
            injury=eye_injury,
            mode=ContentEquipmentInjuryLink.Mode.SUPPRESS,
        )


@pytest.mark.django_db
def test_injuries_edit_page_shows_the_treatment(
    client, injured_fighter, bionic_eye, eye_injury, user
):
    """The edit page names the gear rather than leaving the injury bare."""
    ContentEquipmentInjuryLink.objects.create(equipment=bionic_eye, injury=eye_injury)
    fighter = _assign(injured_fighter, bionic_eye)
    client.force_login(user)

    response = client.get(
        reverse("core:list-fighter-injuries-edit", args=(fighter.list.id, fighter.id))
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Treated by Bionic eye (mundane)" in content
    # The injury is still listed, and still removable by hand.
    assert "Eye Injury" in content
    # The wrench is decorative; the name beside it carries the meaning.
    assert '<i class="bi-wrench-adjustable" aria-hidden="true">' in content


@pytest.mark.django_db
def test_injuries_edit_page_leaves_untreated_injuries_unmarked(
    client, injured_fighter, user
):
    client.force_login(user)

    response = client.get(
        reverse(
            "core:list-fighter-injuries-edit",
            args=(injured_fighter.list.id, injured_fighter.id),
        )
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Eye Injury" in content
    assert "Treated by" not in content


@pytest.mark.django_db
def test_fighter_card_marks_a_treated_injury(
    client, injured_fighter, bionic_eye, eye_injury, user
):
    """The gang page card flags the injury as treated rather than dropping it."""
    ContentEquipmentInjuryLink.objects.create(equipment=bionic_eye, injury=eye_injury)
    fighter = _assign(injured_fighter, bionic_eye)
    client.force_login(user)

    response = client.get(reverse("core:list", args=(fighter.list.id,)))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Eye Injury" in content
    assert "Treated by Bionic eye (mundane)" in content
    # On the card the name is only in a tooltip, so assistive tech needs the
    # visually-hidden label and the icon itself must stay silent.
    assert '<i class="bi-wrench-adjustable" aria-hidden="true">' in content
    assert (
        '<span class="visually-hidden">— treated by Bionic eye (mundane)</span>'
        in content
    )


@pytest.mark.django_db
def test_admin_pages_offer_the_link_inline(
    client, django_user_model, bionic_eye, eye_injury
):
    """Links must be authorable from either end of the relation."""
    admin_user = django_user_model.objects.create_superuser("admin", "a@b.co", "pw")
    client.force_login(admin_user)
    ContentEquipmentInjuryLink.objects.create(equipment=bionic_eye, injury=eye_injury)

    for url, label in (
        (
            reverse("admin:content_contentinjury_change", args=(eye_injury.id,)),
            "Treated by equipment",
        ),
        (
            reverse("admin:content_contentequipment_change", args=(bionic_eye.id,)),
            "Injuries treated",
        ),
    ):
        response = client.get(url)
        assert response.status_code == 200, url
        assert label in response.content.decode(), url


@pytest.mark.django_db
def test_admin_inline_hides_the_parent_side_of_the_link(rf, django_user_model):
    """Only the far end is editable.

    Rendering the parent FK inside its own page is redundant, and lets a link be
    repointed at a different parent by accident.
    """
    from django.contrib.admin.sites import site

    from n23.content.admin import ContentEquipmentInjuryLinkInline
    from n23.content.models import ContentEquipment

    request = rf.get("/")
    request.user = django_user_model.objects.create_superuser("admin", "a@b.co", "pw")

    for parent, expected in (
        (ContentEquipment, ["injury", "mode"]),
        (ContentInjury, ["equipment", "mode"]),
    ):
        inline = ContentEquipmentInjuryLinkInline(parent, site)
        formset = inline.get_formset(request)
        assert list(formset.form.base_fields.keys()) == expected, parent.__name__


@pytest.mark.django_db
def test_uninjured_fighter_never_resolves_treatments(
    list_with_campaign, make_list_fighter, bionic_eye
):
    """Resolving treatments walks every assignment, so skip it with no injuries.

    Asserted on the cache rather than a query count: the point is that the walk
    doesn't happen at all, which a raw number wouldn't pin down.
    """
    fighter = make_list_fighter(list_with_campaign, "Healthy Fighter")
    fighter = _assign(fighter, bionic_eye)

    fighter._mods  # noqa: B018 - touched to force the cached_property to populate

    assert "_injury_treatments" not in fighter.__dict__


@pytest.mark.django_db
def test_classic_print_card_flags_a_treated_injury(
    injured_fighter, bionic_eye, eye_injury
):
    """Paper has no tooltip, so a treated injury has to say so in the text."""
    from n23.core.print_cards import card_from_fighter

    ContentEquipmentInjuryLink.objects.create(equipment=bionic_eye, injury=eye_injury)
    fighter = _assign(injured_fighter, bionic_eye)

    assert card_from_fighter(fighter).injuries == ["Eye Injury (treated)"]


@pytest.mark.django_db
def test_classic_print_card_leaves_an_untreated_injury_bare(injured_fighter):
    from n23.core.print_cards import card_from_fighter

    assert card_from_fighter(injured_fighter).injuries == ["Eye Injury"]


def _stat_display(fighter, field_name):
    return next(s for s in fighter.statline if s.field_name == field_name)


@pytest.mark.django_db
def test_statline_names_the_injury_that_changed_a_stat(injured_fighter):
    """The tooltip should say what moved the stat, not just that something did."""
    bs = _stat_display(injured_fighter, "ballistic_skill")

    assert bs.modded
    assert bs.modded_by == "Eye Injury"


@pytest.mark.django_db
def test_statline_names_every_source_in_application_order(
    injured_fighter, bionic_eye, eye_injury
):
    """An offset stat is touched twice — both sources are named."""
    ContentEquipmentInjuryLink.objects.create(equipment=bionic_eye, injury=eye_injury)
    fighter = _assign(injured_fighter, bionic_eye)

    bs = _stat_display(fighter, "ballistic_skill")

    # Equipment applies before injuries, so it is named first.
    assert bs.modded_by == "Bionic eye (mundane), Eye Injury"


@pytest.mark.django_db
def test_suppressed_injury_is_not_named_as_a_source(
    injured_fighter, make_equipment, eye_injury
):
    """A suppressed injury no longer modifies the stat, so it isn't credited."""
    cyberteknika = make_equipment(
        "Ocular Cyberteknika", category="Status Items", cost=50
    )
    ContentEquipmentInjuryLink.objects.create(
        equipment=cyberteknika,
        injury=eye_injury,
        mode=ContentEquipmentInjuryLink.Mode.SUPPRESS,
    )
    fighter = _assign(injured_fighter, cyberteknika)

    assert "Eye Injury" not in _stat_display(fighter, "ballistic_skill").modded_by


@pytest.mark.django_db
def test_unmodified_stat_has_no_source(injured_fighter):
    assert _stat_display(injured_fighter, "strength").modded_by == ""


@pytest.mark.django_db
def test_statline_tooltip_renders_the_source(client, injured_fighter, user):
    """The gang page shows the specific source rather than the catch-all."""
    client.force_login(user)

    content = client.get(
        reverse("core:list", args=(injured_fighter.list.id,))
    ).content.decode()

    assert 'title="Modified by Eye Injury"' in content
    assert "Modified by equipment, accessories" not in content
