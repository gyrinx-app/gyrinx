import pytest
from django.urls import reverse

from gyrinx.content.models import ContentBattleRole, ContentBattleRoleOption
from gyrinx.core.models import Battle, BattleParticipant
from gyrinx.core.models.state_machine import InvalidStateTransition


@pytest.fixture
def battle_roles(db):
    """The default Attacker/Defender role and its options.

    Seeded via migration in real environments, but tests run with
    ``--nomigrations`` so we create them explicitly here.
    """
    role = ContentBattleRole.objects.create(name="Attacker/Defender")
    attacker = ContentBattleRoleOption.objects.create(role=role, name="Attacker")
    defender = ContentBattleRoleOption.objects.create(role=role, name="Defender")
    return role, attacker, defender


# --- State machine ---------------------------------------------------------


@pytest.mark.django_db
def test_new_battle_starts_pre_battle(user, campaign):
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    assert battle.states.current == Battle.PRE_BATTLE
    assert battle.status == "pre_battle"


@pytest.mark.django_db
def test_state_moves_forward(user, campaign):
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.states.transition_to(Battle.IN_PROGRESS)
    assert battle.states.current == Battle.IN_PROGRESS
    battle.states.transition_to(Battle.POST_BATTLE)
    assert battle.states.current == Battle.POST_BATTLE
    assert battle.states.is_terminal


@pytest.mark.django_db
def test_state_is_forward_only(user, campaign):
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    # Cannot skip a step.
    with pytest.raises(InvalidStateTransition):
        battle.states.transition_to(Battle.POST_BATTLE)
    # Cannot go back.
    battle.states.transition_to(Battle.IN_PROGRESS)
    with pytest.raises(InvalidStateTransition):
        battle.states.transition_to(Battle.PRE_BATTLE)


@pytest.mark.django_db
def test_set_battle_state_view(client, user, campaign, make_list):
    client.force_login(user)
    lst = make_list("Gang 1")
    campaign.lists.add(lst)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([lst])

    url = reverse("core:battle-set-state", args=[battle.id])
    resp = client.post(url, {"status": "in_progress"})
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.status == "in_progress"

    # An invalid (backwards) transition is rejected and leaves state unchanged.
    resp = client.post(url, {"status": "pre_battle"})
    battle.refresh_from_db()
    assert battle.status == "in_progress"


# --- Participants and roles ------------------------------------------------


@pytest.mark.django_db
def test_set_participants_creates_and_removes_through_rows(user, campaign, make_list):
    l1 = make_list("Gang 1")
    l2 = make_list("Gang 2")
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)

    battle.set_participants([l1, l2])
    assert battle.participants.count() == 2
    assert BattleParticipant.objects.filter(battle=battle).count() == 2

    battle.set_participants([l1])
    assert battle.participants.count() == 1
    assert not BattleParticipant.objects.filter(battle=battle, list=l2).exists()


@pytest.mark.django_db
def test_set_participants_preserves_existing_roles(
    user, campaign, make_list, battle_roles
):
    _, attacker, _ = battle_roles
    l1 = make_list("Gang 1")
    l2 = make_list("Gang 2")
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([l1, l2])

    bp = BattleParticipant.objects.get(battle=battle, list=l1)
    bp.role_option = attacker
    bp.save()

    # Re-setting with the same gangs keeps the role.
    battle.set_participants([l1, l2])
    bp.refresh_from_db()
    assert bp.role_option == attacker


@pytest.mark.django_db
def test_participants_grouped_by_role(user, campaign, make_list, battle_roles):
    _, attacker, defender = battle_roles
    l1 = make_list("Gang 1")
    l2 = make_list("Gang 2")
    l3 = make_list("Gang 3")
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([l1, l2, l3])
    BattleParticipant.objects.filter(battle=battle, list=l1).update(
        role_option=attacker
    )
    BattleParticipant.objects.filter(battle=battle, list=l2).update(
        role_option=defender
    )

    groups = battle.participants_grouped_by_role()
    labels = [g["role_option"].name if g["role_option"] else None for g in groups]
    # Named roles first (alphabetical), unassigned last.
    assert labels == ["Attacker", "Defender", None]


@pytest.mark.django_db
def test_edit_battle_roles_view(client, user, campaign, make_list, battle_roles):
    _, attacker, _ = battle_roles
    client.force_login(user)
    lst = make_list("Gang 1")
    campaign.lists.add(lst)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([lst])
    bp = BattleParticipant.objects.get(battle=battle, list=lst)

    url = reverse("core:battle-roles-edit", args=[battle.id])
    resp = client.post(url, {f"role_{bp.pk}": str(attacker.pk)})
    assert resp.status_code == 302
    bp.refresh_from_db()
    assert bp.role_option == attacker


# --- Create / edit views ---------------------------------------------------


@pytest.mark.django_db
def test_create_battle_without_date(client, user, campaign, make_list):
    client.force_login(user)
    l1 = make_list("Gang 1")
    l2 = make_list("Gang 2")
    campaign.lists.add(l1, l2)

    url = reverse("core:battle-new", args=[campaign.id])
    resp = client.post(
        url,
        {"mission": "Ambush", "participants": [str(l1.id), str(l2.id)]},
    )
    assert resp.status_code == 302
    battle = Battle.objects.get()
    assert battle.date is None
    assert battle.status == "pre_battle"
    assert battle.participants.count() == 2


@pytest.mark.django_db
def test_edit_battle_updates_participants_and_winners(
    client, user, campaign, make_list
):
    client.force_login(user)
    l1 = make_list("Gang 1")
    l2 = make_list("Gang 2")
    l3 = make_list("Gang 3")
    campaign.lists.add(l1, l2, l3)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([l1, l2])

    url = reverse("core:battle-edit", args=[battle.id])
    resp = client.post(
        url,
        {
            "mission": "M",
            "participants": [str(l1.id), str(l3.id)],
            "winners": [str(l1.id)],
        },
    )
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert set(battle.participants.values_list("id", flat=True)) == {l1.id, l3.id}
    assert list(battle.winners.values_list("id", flat=True)) == [l1.id]


@pytest.mark.django_db
def test_edit_battle_winner_must_be_participant(client, user, campaign, make_list):
    client.force_login(user)
    l1 = make_list("Gang 1")
    l2 = make_list("Gang 2")
    campaign.lists.add(l1, l2)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([l1])

    url = reverse("core:battle-edit", args=[battle.id])
    resp = client.post(
        url,
        {
            "mission": "M",
            "participants": [str(l1.id)],
            "winners": [str(l2.id)],  # not a participant
        },
    )
    # Form re-renders with an error rather than redirecting.
    assert resp.status_code == 200
    assert battle.winners.count() == 0


# --- Templates -------------------------------------------------------------


@pytest.mark.django_db
def test_battle_page_shows_campaign_header(client, user, campaign):
    client.force_login(user)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    resp = client.get(reverse("core:battle", args=[battle.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert campaign.name in content
    assert reverse("core:campaign", args=[campaign.id]) in content


@pytest.mark.django_db
def test_campaign_page_battles_section_renamed(client, user, campaign):
    client.force_login(user)
    resp = client.get(reverse("core:campaign", args=[campaign.id]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert ">Battles<" in content
    assert "Battle Reports" not in content
