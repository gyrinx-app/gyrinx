import pytest
from django.forms import ValidationError

from gyrinx.content.models import (
    ContentFighterPsykerDisciplineAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentRule,
)
from gyrinx.core.models import ListFighter, ListFighterPsykerPowerAssignment


@pytest.mark.django_db
def test_psyker(content_fighter, make_list, make_list_fighter):
    psyker, _ = ContentRule.objects.get_or_create(name="Psyker")
    non_sanctioned_psyker, _ = ContentRule.objects.get_or_create(
        name="Non-sanctioned Psyker"
    )
    sanctioned_psyker, _ = ContentRule.objects.get_or_create(name="Sanctioned Psyker")

    biomancy, _ = ContentPsykerDiscipline.objects.get_or_create(
        name="Biomancy",
        generic=True,
    )

    arachnosis, _ = ContentPsykerPower.objects.get_or_create(
        name="Arachnosis",
        discipline=biomancy,
    )

    chronomancy, _ = ContentPsykerDiscipline.objects.get_or_create(
        name="Chronomancy",
    )

    freeze_time, _ = ContentPsykerPower.objects.get_or_create(
        name="Freeze Time",
        discipline=chronomancy,
    )

    # You can't assign a generic discipline
    assign = ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=content_fighter,
        discipline=biomancy,
    )
    with pytest.raises(ValidationError):
        assign.full_clean()
    assign.delete()

    # You can't assign a discipline if the ContentFighter is not a psyker
    assign = ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=content_fighter,
        discipline=chronomancy,
    )
    with pytest.raises(ValidationError):
        assign.full_clean()
    assign.delete()

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    assert fighter.psyker_powers.count() == 0

    # You can't assign a psyker power if the ContentFighter is not a psyker
    # TODO: Find a way to build this generically, rather than special-casing it
    assign = ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=fighter,
        psyker_power=arachnosis,
    )
    with pytest.raises(ValidationError):
        assign.full_clean()
    assign.delete()

    content_fighter.rules.add(psyker)

    # You can assign a psyker power from a generic discipline
    ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=fighter,
        psyker_power=arachnosis,
    )

    assert fighter.psyker_powers.count() == 1
    assert len(fighter.psyker_default_powers()) == 0
    assert len(fighter.psyker_assigned_powers()) == 1

    # You can't assign a psyker power from a non-generic discipline if the ContentFighter is not assigned that discipline
    assign = ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=fighter,
        psyker_power=freeze_time,
    )
    with pytest.raises(ValidationError):
        assign.full_clean()
    assign.delete()

    # You can assign a discipline to a content fighter so they can use powers from that discipline
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=content_fighter,
        discipline=chronomancy,
    )

    # You can assign a psyker power from a discipline that the ContentFighter is assigned
    ft_assign = ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=fighter,
        psyker_power=freeze_time,
    )

    assert fighter.psyker_powers.count() == 2
    assert len(fighter.psyker_default_powers()) == 0
    assert len(fighter.psyker_assigned_powers()) == 2

    ft_assign.delete()

    assert fighter.psyker_powers.count() == 1
    assert len(fighter.psyker_default_powers()) == 0
    assert len(fighter.psyker_assigned_powers()) == 1

    # The above also applies to non-sanctioned psykers
    content_fighter.rules.add(non_sanctioned_psyker)
    content_fighter.rules.remove(psyker)

    ft_assign = ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=fighter,
        psyker_power=freeze_time,
    )

    assert fighter.psyker_powers.count() == 2
    assert len(fighter.psyker_default_powers()) == 0
    assert len(fighter.psyker_assigned_powers()) == 2

    ft_assign.delete()

    assert fighter.psyker_powers.count() == 1
    assert len(fighter.psyker_default_powers()) == 0
    assert len(fighter.psyker_assigned_powers()) == 1

    # The above also applies to sanctioned psykers
    content_fighter.rules.add(sanctioned_psyker)
    content_fighter.rules.remove(non_sanctioned_psyker)

    ft_assign = ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=fighter,
        psyker_power=freeze_time,
    )

    assert fighter.psyker_powers.count() == 2
    assert len(fighter.psyker_default_powers()) == 0
    assert len(fighter.psyker_assigned_powers()) == 2

    ft_assign.delete()

    assert fighter.psyker_powers.count() == 1
    assert len(fighter.psyker_default_powers()) == 0
    assert len(fighter.psyker_assigned_powers()) == 1


@pytest.mark.django_db
def test_psyker_default_power(content_fighter, make_list, make_list_fighter):
    psyker, _ = ContentRule.objects.get_or_create(name="Psyker")

    biomancy, _ = ContentPsykerDiscipline.objects.get_or_create(
        name="Biomancy",
        generic=True,
    )

    arachnosis, _ = ContentPsykerPower.objects.get_or_create(
        name="Arachnosis",
        discipline=biomancy,
    )

    # You can't assign a default psyker power if the ContentFighter is not a psyker
    assign = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=content_fighter,
        psyker_power=arachnosis,
    )
    with pytest.raises(ValidationError):
        assign.full_clean()
    assign.delete()

    # This content fighter is a psyker
    content_fighter.rules.add(psyker)
    content_fighter.save()

    # And they have a default psyker power
    default_assign = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=content_fighter,
        psyker_power=arachnosis,
    )
    default_assign.save()

    assert content_fighter.default_psyker_powers.count() == 1

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(
        lst, "Test Fighter", content_fighter=content_fighter
    )

    assert len(fighter.powers()) == 1
    assert len(fighter.psyker_default_powers()) == 1
    assert len(fighter.psyker_assigned_powers()) == 0

    # You can't assign a power that is already assigned as a default
    assign = ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=fighter,
        psyker_power=arachnosis,
    )
    with pytest.raises(ValidationError):
        assign.full_clean()
    assign.delete()

    # You can disable a default psyker power
    fighter.disabled_pskyer_default_powers.add(default_assign)
    fighter.save()

    assert len(fighter.psyker_default_powers()) == 0
    assert len(fighter.psyker_assigned_powers()) == 0
    assert len(fighter.powers()) == 0
    assert len(fighter.disabled_pskyer_default_powers.all()) == 1

    # You can re-enable a default psyker power
    fighter.disabled_pskyer_default_powers.remove(default_assign)
    fighter.save()

    assert len(fighter.psyker_default_powers()) == 1
    assert len(fighter.psyker_assigned_powers()) == 0
    assert len(fighter.powers()) == 1
    assert len(fighter.disabled_pskyer_default_powers.all()) == 0
