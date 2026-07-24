import pytest
from django.urls import reverse

from gyrinx.content.models import ContentBattleRole, ContentBattleRoleOption
from gyrinx.core.models import Battle, BattleParticipant
from gyrinx.core.models.list import List
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
def test_start_and_end_battle_views(client, user, campaign, make_list):
    client.force_login(user)
    lst = make_list("Gang 1")
    campaign.lists.add(lst)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([lst])

    # The confirmation pages render for a manager.
    assert client.get(reverse("core:battle-start", args=[battle.id])).status_code == 200

    # Start: pre-battle -> in-progress.
    resp = client.post(reverse("core:battle-start", args=[battle.id]))
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.status == "in_progress"

    # Starting again is rejected (not a valid transition) and leaves state unchanged.
    client.post(reverse("core:battle-start", args=[battle.id]))
    battle.refresh_from_db()
    assert battle.status == "in_progress"

    # End: in-progress -> post-battle. Ending requires a recorded result.
    resp = client.post(reverse("core:battle-end", args=[battle.id]), {"result": "draw"})
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.status == "post_battle"
    assert battle.result == Battle.RESULT_DRAW

    # A post-battle battle can no longer be started or ended.
    assert battle.can_start() is False
    assert battle.can_end() is False


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


# --- Permissions: manage vs edit -------------------------------------------


@pytest.mark.django_db
def test_participant_can_manage_but_not_edit(user, make_user, campaign, make_list):
    player = make_user("player_pm", "password")
    plist = make_list("Player Gang", owner=player)
    campaign.lists.add(plist)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([plist])

    # A participant gang owner can manage (state + roles + notes) but not edit.
    assert battle.can_manage(player) is True
    assert battle.can_add_notes(player) is True
    assert battle.can_edit(player) is False


@pytest.mark.django_db
def test_participant_manages_via_views(
    client, user, make_user, campaign, make_list, battle_roles
):
    _, attacker, _ = battle_roles
    player = make_user("player_pv", "password")
    plist = make_list("Player Gang", owner=player)
    campaign.lists.add(plist)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([plist])
    bp = BattleParticipant.objects.get(battle=battle, list=plist)

    client.force_login(player)

    # A participant can advance state...
    resp = client.post(reverse("core:battle-start", args=[battle.id]))
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.status == "in_progress"

    # ...and assign roles...
    resp = client.post(
        reverse("core:battle-roles-edit", args=[battle.id]),
        {f"role_{bp.pk}": str(attacker.pk)},
    )
    assert resp.status_code == 302
    bp.refresh_from_db()
    assert bp.role_option == attacker

    # ...but cannot edit the roster or mission.
    client.post(
        reverse("core:battle-edit", args=[battle.id]),
        {"mission": "HACKED", "participants": [str(plist.id)]},
    )
    battle.refresh_from_db()
    assert battle.mission == "M"


@pytest.mark.django_db
def test_non_participant_player_cannot_manage(user, make_user, campaign, make_list):
    other = make_user("other_np", "password")
    other_list = make_list("Other Gang", owner=other)
    campaign.lists.add(other_list)  # in the campaign, but not in this battle
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    assert battle.can_manage(other) is False


# --- Archive ---------------------------------------------------------------


@pytest.mark.django_db
def test_archive_permission_transitions(user, campaign):
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    assert battle.can_edit(user) is True
    assert battle.can_unarchive(user) is False

    battle.archive()
    assert battle.can_edit(user) is False
    assert battle.can_manage(user) is False
    assert battle.can_unarchive(user) is True

    battle.unarchive()
    assert battle.can_edit(user) is True
    assert battle.can_unarchive(user) is False


@pytest.mark.django_db
def test_archive_view_hides_battle_and_blocks_manage(client, user, campaign, make_list):
    client.force_login(user)
    l1 = make_list("G1")
    campaign.lists.add(l1)
    battle = Battle.objects.create(campaign=campaign, mission="Zzsabotage", owner=user)
    battle.set_participants([l1])

    # Archive via the view.
    resp = client.post(
        reverse("core:battle-archive", args=[battle.id]), {"archive": "1"}
    )
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.archived is True
    # Consume the "archived" flash message so it doesn't leak onto later pages.
    client.get(reverse("core:battle", args=[battle.id]))

    # Hidden from the active battle list, visible under ?archived=1.
    battle_link = reverse("core:battle", args=[battle.id])
    active = client.get(reverse("core:campaign-battles", args=[campaign.id]))
    assert battle_link not in active.content.decode()
    archived = client.get(
        reverse("core:campaign-battles", args=[campaign.id]) + "?archived=1"
    )
    assert battle_link in archived.content.decode()

    # Managing an archived battle is blocked.
    client.post(reverse("core:battle-start", args=[battle.id]))
    battle.refresh_from_db()
    assert battle.status == "pre_battle"

    # Unarchive via the view (no archive flag means unarchive).
    resp = client.post(reverse("core:battle-archive", args=[battle.id]))
    assert resp.status_code == 302
    battle.refresh_from_db()
    assert battle.archived is False


@pytest.mark.django_db
def test_participant_cannot_archive(client, user, make_user, campaign, make_list):
    player = make_user("player_arch", "password")
    plist = make_list("Player Gang", owner=player)
    campaign.lists.add(plist)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([plist])

    client.force_login(player)
    client.post(reverse("core:battle-archive", args=[battle.id]), {"archive": "1"})
    battle.refresh_from_db()
    assert battle.archived is False


@pytest.mark.django_db
def test_battle_page_post_battle_prompt(client, user, make_user, campaign, make_list):
    player = make_user("pb_prompt_player", "password")
    mine = make_list("My Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    theirs = make_list(
        "Their Gang", owner=player, status=List.CAMPAIGN_MODE, campaign=campaign
    )
    campaign.lists.add(mine, theirs)
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    battle.set_participants([mine, theirs])

    url = reverse("core:battle", args=[battle.id])
    prompt_mine = (
        f"{reverse('core:list-post-battle', args=[mine.id])}?battle={battle.id}"
    )
    prompt_theirs = (
        f"{reverse('core:list-post-battle', args=[theirs.id])}?battle={battle.id}"
    )

    # Before the battle ends there is nothing to record yet — but crews can
    # still be added.
    client.force_login(user)
    content = client.get(url).content.decode()
    assert prompt_mine not in content
    assert "Add crew" in content

    client.post(reverse("core:battle-start", args=[battle.id]))
    # Ending a battle now records how it finished, so the result is required.
    client.post(reverse("core:battle-end", args=[battle.id]), {"result": "draw"})

    # The arbitrator (campaign owner) is prompted for every participating
    # gang; a finished battle no longer offers to add crews.
    content = client.get(url).content.decode()
    assert prompt_mine in content
    assert prompt_theirs in content
    assert "Add crew" not in content

    # A player is prompted only for their own gang.
    client.force_login(player)
    content = client.get(url).content.decode()
    assert prompt_theirs in content
    assert prompt_mine not in content

    # An unrelated viewer gets no prompt at all.
    outsider = make_user("pb_prompt_outsider", "password")
    client.force_login(outsider)
    content = client.get(url).content.decode()
    assert prompt_mine not in content
    assert prompt_theirs not in content

    # A gang that has left campaign mode no longer gets a button.
    theirs.status = List.LIST_BUILDING
    theirs.save()
    client.force_login(user)
    content = client.get(url).content.decode()
    assert prompt_mine in content
    assert prompt_theirs not in content


# --- Computed name ---------------------------------------------------------


@pytest.mark.django_db
def test_battle_name_has_no_number_when_unambiguous(user, campaign):
    import datetime

    day = datetime.date(2026, 7, 19)
    battle = Battle.objects.create(
        campaign=campaign, mission="Border Dispute", date=day, owner=user
    )
    # A different mission on the same day, and the same mission on another
    # day, are both already distinguishable — no ordinal on any of them.
    other_mission = Battle.objects.create(
        campaign=campaign, mission="The Trap", date=day, owner=user
    )
    other_day = Battle.objects.create(
        campaign=campaign,
        mission="Border Dispute",
        date=datetime.date(2026, 7, 20),
        owner=user,
    )

    assert battle.name == "Border Dispute 2026-07-19"
    assert other_mission.name == "The Trap 2026-07-19"
    assert other_day.name == "Border Dispute 2026-07-20"


@pytest.mark.django_db
def test_battle_name_numbers_only_within_the_colliding_group(user, campaign):
    import datetime

    day = datetime.date(2026, 7, 19)
    # Two battles of the same mission on the same day: these need telling
    # apart, and the ordinal counts within the pair (not across the campaign).
    first = Battle.objects.create(
        campaign=campaign, mission="Border Dispute", date=day, owner=user
    )
    second = Battle.objects.create(
        campaign=campaign, mission="Border Dispute", date=day, owner=user
    )
    # A third battle of another mission does not shift those numbers.
    Battle.objects.create(campaign=campaign, mission="The Trap", date=day, owner=user)

    assert first.name == "Border Dispute 2026-07-19 #1"
    assert second.name == "Border Dispute 2026-07-19 #2"


@pytest.mark.django_db
def test_battle_name_without_date(user, campaign, make_campaign):
    # Undated battles show the mission alone...
    battle = Battle.objects.create(campaign=campaign, mission="Ambush", owner=user)
    assert battle.name == "Ambush"

    # ...and group with each other, not with dated battles.
    import datetime

    Battle.objects.create(
        campaign=campaign,
        mission="Ambush",
        date=datetime.date(2026, 7, 19),
        owner=user,
    )
    assert Battle.objects.get(pk=battle.pk).name == "Ambush"

    second_undated = Battle.objects.create(
        campaign=campaign, mission="Ambush", owner=user
    )
    assert Battle.objects.get(pk=battle.pk).name == "Ambush #1"
    assert second_undated.name == "Ambush #2"


@pytest.mark.django_db
def test_battle_name_does_not_collide_across_campaigns(user, campaign, make_campaign):
    import datetime

    day = datetime.date(2026, 7, 19)
    other_campaign = make_campaign("Other Campaign")
    mine = Battle.objects.create(
        campaign=campaign, mission="Border Dispute", date=day, owner=user
    )
    Battle.objects.create(
        campaign=other_campaign, mission="Border Dispute", date=day, owner=user
    )

    assert mine.name == "Border Dispute 2026-07-19"


@pytest.mark.django_db
def test_battle_name_ordinals_are_distinct_when_created_at_the_same_instant(
    user, campaign
):
    import datetime

    day = datetime.date(2026, 7, 19)
    first = Battle.objects.create(
        campaign=campaign, mission="Border Dispute", date=day, owner=user
    )
    second = Battle.objects.create(
        campaign=campaign, mission="Border Dispute", date=day, owner=user
    )
    # Force identical creation timestamps: the pk breaks the tie, so the two
    # battles still get distinct ordinals rather than both showing "#1".
    Battle.objects.filter(pk__in=[first.pk, second.pk]).update(created=first.created)
    first = Battle.objects.get(pk=first.pk)
    second = Battle.objects.get(pk=second.pk)

    assert {first.name, second.name} == {
        "Border Dispute 2026-07-19 #1",
        "Border Dispute 2026-07-19 #2",
    }
