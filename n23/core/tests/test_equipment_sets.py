"""Tests for equipment sets (Tools of the Trade, #1853).

Covers the display filtering, the display-only selected rating, the critical
invariant that set selection never touches the canonical cost/rating, the
manage/switch views, rule gating, and clone behaviour.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n23.content.models import ContentRule
from n23.core.models.list import List, ListFighter, ListFighterEquipmentSet


def refetch(fighter):
    """Re-fetch a fighter with the standard prefetch so caches are fresh."""
    return ListFighter.objects.with_related_data().get(id=fighter.id)


@pytest.fixture
def equipped(make_list, make_list_fighter, make_equipment, make_weapon_profile, user):
    """A fighter with two weapons (30 + 50) and one piece of gear (15).

    Returns a dict of the created objects.
    """
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Ganger")

    lasgun = make_equipment(name="Lasgun", cost=30, category="Basic Weapons")
    make_weapon_profile(lasgun)  # makes it a weapon (has a profile)
    plasma = make_equipment(name="Plasma Gun", cost=50, category="Special Weapons")
    make_weapon_profile(plasma)
    armour = make_equipment(name="Flak Armour", cost=15, category="Armour")

    a_lasgun = fighter.assign(lasgun)
    a_plasma = fighter.assign(plasma)
    a_armour = fighter.assign(armour)

    return {
        "list": lst,
        "fighter": fighter,
        "lasgun": a_lasgun,
        "plasma": a_plasma,
        "armour": a_armour,
    }


def add_tot_rule(fighter):
    rule, _ = ContentRule.objects.get_or_create(name="Tools of the Trade")
    fighter.custom_rules.add(rule)
    return rule


# --- Model / cost layer ------------------------------------------------------


@pytest.mark.django_db
def test_default_card_shows_all_and_selected_equals_max(equipped):
    fighter = refetch(equipped["fighter"])

    assert fighter.active_equipment_set_id is None
    assert fighter.displayed_assignment_ids is None
    # Default card shows the full pool.
    assert len(fighter.displayed_assignments_cached) == len(fighter.assignments_cached)
    assert len(fighter.weapons()) == 2
    # base fighter cost + 30 + 50 + 15
    assert fighter.selected_cost_int == fighter.cost_int_cached
    assert fighter.has_reduced_equipment_selection is False


@pytest.mark.django_db
def test_active_set_hides_excluded_weapon_but_keeps_it_in_pool(equipped):
    fighter = equipped["fighter"]
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="Lasgun only", owner=fighter.owner
    )
    card.assignments.set([equipped["lasgun"], equipped["armour"]])
    fighter.active_equipment_set = card
    fighter.save()

    fighter = refetch(fighter)

    weapon_names = [w.name() for w in fighter.weapons()]
    assert any("Lasgun" in n for n in weapon_names)
    assert not any("Plasma" in n for n in weapon_names)
    # The plasma gun is hidden from display but still in the canonical pool.
    assert len(fighter.weapons()) == 1
    assert len(fighter.assignments_cached) == 3


@pytest.mark.django_db
def test_selected_cost_drops_when_costed_item_excluded(equipped):
    fighter = equipped["fighter"]
    max_cost = refetch(fighter).cost_int_cached

    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="No plasma", owner=fighter.owner
    )
    # Exclude the 50-credit plasma gun.
    card.assignments.set([equipped["lasgun"], equipped["armour"]])
    fighter.active_equipment_set = card
    fighter.save()

    fighter = refetch(fighter)
    assert fighter.selected_cost_int == max_cost - 50
    assert fighter.has_reduced_equipment_selection is True


@pytest.mark.django_db
def test_canonical_cost_unaffected_by_active_set(equipped):
    """The decision-#7 guard: selecting a set must not move the canonical cost."""
    lst = equipped["list"]
    fighter = equipped["fighter"]

    before_fighter_cost = ListFighter.objects.get(id=fighter.id).cost_int()
    before_list_rating = List.objects.get(id=lst.id).facts_from_db(update=False).rating
    before_list_wealth = List.objects.get(id=lst.id).cost_int()
    before_facts_rating = fighter.facts_from_db(update=True).rating

    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="Minimal", owner=fighter.owner
    )
    card.assignments.set([])  # hide everything
    fighter.active_equipment_set = card
    fighter.save()

    assert ListFighter.objects.get(id=fighter.id).cost_int() == before_fighter_cost
    assert (
        List.objects.get(id=lst.id).facts_from_db(update=False).rating
        == before_list_rating
    )
    assert List.objects.get(id=lst.id).cost_int() == before_list_wealth
    # Cached rating_current (feeds credits/audit) is untouched.
    assert (
        ListFighter.objects.get(id=fighter.id).facts_from_db(update=True).rating
        == before_facts_rating
    )


@pytest.mark.django_db
def test_list_selected_rating_reflects_active_sets(equipped):
    lst = equipped["list"]
    fighter = equipped["fighter"]

    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="No plasma", owner=fighter.owner
    )
    card.assignments.set([equipped["lasgun"], equipped["armour"]])
    fighter.active_equipment_set = card
    fighter.save()

    # Fetch with fighters prefetched so selected_rating engages.
    lst = List.objects.with_related_data(with_fighters=True).get(id=lst.id)
    assert lst.has_reduced_equipment_selection is True
    assert lst.selected_rating == lst.facts_from_db(update=False).rating - 50
    # selected and max are on the same basis, so the gap is exactly the hidden gear.
    assert lst.selected_rating == lst.selected_rating_max - 50


@pytest.mark.django_db
def test_default_kit_always_shown_regardless_of_set(
    make_list, make_list_fighter, make_content_fighter, content_house, make_equipment
):
    """Default (template) kit is always shown, even under a set (v1)."""
    from n23.content.models import ContentFighterDefaultAssignment

    cf = make_content_fighter(
        type="Kitted Ganger",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    knife = make_equipment(name="Fighting Knife", cost=0, category="Close Combat")
    ContentFighterDefaultAssignment.objects.create(fighter=cf, equipment=knife)

    lst = make_list("Kit Gang")
    fighter = ListFighter.objects.create(
        list=lst, name="Ganger", content_fighter=cf, owner=lst.owner
    )
    bolter = make_equipment(name="Bolter", cost=35, category="Basic Weapons")
    a_bolter = fighter.assign(bolter)

    # A set that excludes the direct assignment entirely.
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="Empty", owner=fighter.owner
    )
    card.assignments.set([])
    fighter.active_equipment_set = card
    fighter.save()

    fighter = refetch(fighter)
    names = [a.name() for a in fighter.displayed_assignments_cached]
    assert any("Fighting Knife" in n for n in names)  # default kit stays
    assert not any("Bolter" in n for n in names)  # direct assignment hidden
    assert a_bolter.id  # still exists in the pool


@pytest.mark.django_db
def test_has_tools_of_the_trade_detection(equipped):
    fighter = refetch(equipped["fighter"])
    assert fighter.has_tools_of_the_trade is False

    add_tot_rule(equipped["fighter"])
    fighter = refetch(equipped["fighter"])
    assert fighter.has_tools_of_the_trade is True


@pytest.mark.django_db
def test_deleting_active_set_falls_back_to_default(equipped):
    fighter = equipped["fighter"]
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="A", owner=fighter.owner
    )
    fighter.active_equipment_set = card
    fighter.save()

    # Simulate the delete-view side effect.
    fighter.active_equipment_set = None
    fighter.save(update_fields=["active_equipment_set"])
    card.delete()

    fighter = refetch(fighter)
    assert fighter.active_equipment_set_id is None
    assert fighter.displayed_assignment_ids is None


# --- Views -------------------------------------------------------------------


@pytest.mark.django_db
def test_manage_page_owner_ok_other_404(equipped, client, user, make_user):
    lst, fighter = equipped["list"], equipped["fighter"]
    add_tot_rule(fighter)
    url = reverse("core:list-fighter-equipment-sets", args=(lst.id, fighter.id))

    client.force_login(user)
    resp = client.get(url)
    assert resp.status_code == 200
    assert "Create a set" in resp.content.decode()

    other = make_user("intruder", "password")
    client.force_login(other)
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_manage_page_without_rule_shows_message(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]  # no ToT rule
    client.force_login(user)
    html = client.get(
        reverse("core:list-fighter-equipment-sets", args=(lst.id, fighter.id))
    ).content.decode()
    assert "does not have the requisite rule" in html
    # The management UI is not offered.
    assert "Create a set" not in html


@pytest.mark.django_db
def test_edit_page_without_rule_shows_message(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]  # no ToT rule
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="A", owner=user
    )
    client.force_login(user)
    html = client.get(
        reverse(
            "core:list-fighter-equipment-set-edit", args=(lst.id, fighter.id, card.id)
        )
    ).content.decode()
    assert "does not have the requisite rule" in html
    assert 'name="assignment"' not in html


@pytest.mark.django_db
def test_mutation_blocked_without_rule(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]  # no ToT rule
    client.force_login(user)
    resp = client.post(
        reverse("core:list-fighter-equipment-set-create", args=(lst.id, fighter.id)),
        {"name": "Nope"},
    )
    assert resp.status_code == 302
    assert not fighter.equipment_sets.exists()


@pytest.mark.django_db
def test_create_set_seeds_all_direct_assignments(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]
    add_tot_rule(fighter)
    client.force_login(user)

    resp = client.post(
        reverse("core:list-fighter-equipment-set-create", args=(lst.id, fighter.id)),
        {"name": "Loadout A"},
    )
    assert resp.status_code == 302
    card = ListFighterEquipmentSet.objects.get(list_fighter=fighter, name="Loadout A")
    # Seeded with all three direct assignments.
    assert card.assignments.count() == 3


@pytest.mark.django_db
def test_edit_membership_sets_m2m(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]
    add_tot_rule(fighter)
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="A", owner=user
    )
    card.assignments.set(fighter._direct_assignments())
    client.force_login(user)

    resp = client.post(
        reverse(
            "core:list-fighter-equipment-set-edit",
            args=(lst.id, fighter.id, card.id),
        ),
        {"assignment": [str(equipped["lasgun"].id)]},
    )
    assert resp.status_code == 302
    assert set(card.assignments.values_list("id", flat=True)) == {equipped["lasgun"].id}


@pytest.mark.django_db
def test_activate_and_default_views(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]
    add_tot_rule(fighter)
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="A", owner=user
    )
    client.force_login(user)

    # Activated from the manage page: ?next returns there, not to the list.
    manage_url = reverse("core:list-fighter-equipment-sets", args=(lst.id, fighter.id))
    resp = client.post(
        reverse(
            "core:list-fighter-equipment-set-activate",
            args=(lst.id, fighter.id, card.id),
        ),
        {"next": manage_url},
    )
    assert resp.status_code == 302
    assert resp.url == manage_url
    assert ListFighter.objects.get(id=fighter.id).active_equipment_set_id == card.id

    client.post(
        reverse(
            "core:list-fighter-equipment-set-activate-default",
            args=(lst.id, fighter.id),
        )
    )
    assert ListFighter.objects.get(id=fighter.id).active_equipment_set_id is None


@pytest.mark.django_db
def test_rename_and_delete_views(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]
    add_tot_rule(fighter)
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="Old", owner=user
    )
    fighter.active_equipment_set = card
    fighter.save()
    client.force_login(user)

    client.post(
        reverse(
            "core:list-fighter-equipment-set-rename",
            args=(lst.id, fighter.id, card.id),
        ),
        {"name": "New"},
    )
    assert ListFighterEquipmentSet.objects.get(id=card.id).name == "New"

    client.post(
        reverse(
            "core:list-fighter-equipment-set-delete",
            args=(lst.id, fighter.id, card.id),
        )
    )
    assert not ListFighterEquipmentSet.objects.filter(id=card.id).exists()
    # Deleting the active card resets the fighter to the Default card.
    assert ListFighter.objects.get(id=fighter.id).active_equipment_set_id is None


@pytest.mark.django_db
def test_switcher_shown_only_for_tot_fighter(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]
    client.force_login(user)
    url = reverse("core:list", args=(lst.id,))

    # No rule: no switcher entry point.
    html_no_rule = client.get(url).content.decode()
    assert "Manage sets" not in html_no_rule

    add_tot_rule(fighter)
    html_with_rule = client.get(url).content.decode()
    assert "Manage sets" in html_with_rule
    # The switcher dropdown offers the Default card and each named card.
    assert "Default (all equipment)" in html_with_rule
    # The main fighter action dropdown also links to equipment sets (redundancy).
    assert "Equipment sets" in html_with_rule
    assert "Equipment sets" not in html_no_rule

    # Regression: the switcher include's explanatory comment must never leak
    # onto the page as literal text (Django {# #} comments are single-line only;
    # a multi-line one renders verbatim). Checked in both states.
    assert "entry point on the fighter card" not in html_no_rule
    assert "entry point on the fighter card" not in html_with_rule


@pytest.mark.django_db
def test_set_edit_page_renders_checkboxes(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]
    add_tot_rule(fighter)
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="A", owner=user
    )
    card.assignments.set([equipped["lasgun"]])
    client.force_login(user)

    resp = client.get(
        reverse(
            "core:list-fighter-equipment-set-edit",
            args=(lst.id, fighter.id, card.id),
        )
    )
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'name="assignment"' in html
    assert "Lasgun" in html and "Plasma Gun" in html
    # The included assignment renders pre-checked.
    assert "checked" in html
    assert f'value="{equipped["lasgun"].id}"' in html


@pytest.mark.django_db
def test_list_page_shows_selected_max_badges(equipped, client, user):
    """The reduced-selection cost badge and topmatter rating branches render."""
    lst, fighter = equipped["list"], equipped["fighter"]
    add_tot_rule(fighter)
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="No plasma", owner=user
    )
    card.assignments.set([equipped["lasgun"], equipped["armour"]])
    fighter.active_equipment_set = card
    fighter.save()

    client.force_login(user)
    html = client.get(reverse("core:list", args=(lst.id,))).content.decode()
    # Reduced per-fighter cost badge (max shown in brackets via opacity-75 span).
    assert "opacity-75" in html
    # Topmatter reduced rating branch.
    assert "selected equipment sets" in html


@pytest.mark.django_db
def test_url_override_shows_specific_card_without_persisting(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]
    add_tot_rule(fighter)
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="No plasma", owner=user
    )
    card.assignments.set([equipped["lasgun"], equipped["armour"]])
    # Note: NOT activated — persisted default stays Default.
    client.force_login(user)

    url = reverse("core:list", args=(lst.id,)) + f"?set_{fighter.id}={card.id}"
    html = client.get(url).content.decode()
    # The override renders the reduced view...
    assert "opacity-75" in html
    # ...but the persisted default is unchanged.
    assert ListFighter.objects.get(id=fighter.id).active_equipment_set_id is None


@pytest.mark.django_db
def test_post_only_endpoints_reject_get(equipped, client, user):
    lst, fighter = equipped["list"], equipped["fighter"]
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="A", owner=user
    )
    client.force_login(user)
    for name, args in [
        ("core:list-fighter-equipment-set-create", (lst.id, fighter.id)),
        ("core:list-fighter-equipment-set-activate-default", (lst.id, fighter.id)),
        ("core:list-fighter-equipment-set-activate", (lst.id, fighter.id, card.id)),
        ("core:list-fighter-equipment-set-rename", (lst.id, fighter.id, card.id)),
        ("core:list-fighter-equipment-set-delete", (lst.id, fighter.id, card.id)),
    ]:
        assert client.get(reverse(name, args=args)).status_code == 404


# --- Clone -------------------------------------------------------------------


@pytest.mark.django_db
def test_clone_carries_equipment_sets(equipped):
    fighter = equipped["fighter"]
    card = ListFighterEquipmentSet.objects.create(
        list_fighter=fighter, name="Loadout A", owner=fighter.owner
    )
    card.assignments.set([equipped["lasgun"]])
    fighter.active_equipment_set = card
    fighter.save()

    clone = fighter.clone()

    cloned_sets = list(clone.equipment_sets.all())
    assert len(cloned_sets) == 1
    cloned_card = cloned_sets[0]
    assert cloned_card.name == "Loadout A"
    # Membership was remapped to the clone's own assignments.
    member_names = [a.content_equipment.name for a in cloned_card.assignments.all()]
    assert member_names == ["Lasgun"]
    assert all(a.list_fighter_id == clone.id for a in cloned_card.assignments.all())
    # The active card was preserved.
    assert clone.active_equipment_set_id == cloned_card.id


# --- Performance: no N+1 from active sets on the list page -------------------


def _gang(n, with_active_set, make_list, content_fighter, w1, w2, user, name):
    """A list of ``n`` fighters each carrying the same two weapons. When
    ``with_active_set`` is set, every fighter also gets the ToT rule and an
    active equipment set that includes *both* weapons (hides nothing), so the
    rendered card is identical to the plain gang — isolating the set machinery.
    """
    lst = make_list(name)
    rule, _ = ContentRule.objects.get_or_create(name="Tools of the Trade")
    for i in range(n):
        f = ListFighter.objects.create(
            list=lst, name=f"F{i}", content_fighter=content_fighter, owner=user
        )
        a1 = f.assign(w1)
        a2 = f.assign(w2)
        if with_active_set:
            f.custom_rules.add(rule)
            card = ListFighterEquipmentSet.objects.create(
                list_fighter=f, name="Card", owner=user
            )
            card.assignments.set([a1, a2])  # include everything -> no reduction
            f.active_equipment_set = card
            f.save()
    return lst


@pytest.mark.django_db
def test_active_sets_add_no_per_fighter_queries_on_list_page(
    make_list, content_fighter, make_equipment, make_weapon_profile, user, client
):
    """The equipment-set machinery must not add a per-fighter query on the list
    page (#1853) — i.e. no N+1 from resolving each fighter's active set or
    computing the selected rating.

    Measures how the list-page query count grows with fighter count for a plain
    gang vs a gang where every fighter has an active set (including all their
    gear, so cards render identically). Set resolution and the selected rating
    are served from the ``equipment_sets`` / ``equipment_sets__assignments``
    prefetches, so the set gang must grow no faster than the plain baseline.
    (The baseline itself grows because rendering each fighter's weapons issues
    content queries when packs aren't prefetched — that is pre-existing and
    unrelated to equipment sets.)
    """
    client.force_login(user)
    w1 = make_equipment(name="Perf W1", cost=20, category="Basic Weapons")
    make_weapon_profile(w1)
    w2 = make_equipment(name="Perf W2", cost=30, category="Basic Weapons")
    make_weapon_profile(w2)

    def count(lst):
        with CaptureQueriesContext(connection) as q:
            assert client.get(reverse("core:list", args=(lst.id,))).status_code == 200
        return len(q.captured_queries)

    n = 10
    plain = count(_gang(n, False, make_list, content_fighter, w1, w2, user, "Plain"))
    setted = count(_gang(n, True, make_list, content_fighter, w1, w2, user, "Setted"))

    # The set machinery adds only O(1) work: the equipment_sets +
    # equipment_sets__assignments prefetches (a couple of queries per page),
    # never one per fighter. A per-fighter N+1 would put ``setted`` roughly
    # ``n`` queries above ``plain``; the small constant bound catches that while
    # tolerating the couple of bounded prefetch queries.
    assert setted <= plain + 3, (
        f"Active sets add per-fighter queries (N+1): with {n} fighters, "
        f"plain={plain}, setted={setted} (overhead {setted - plain} > 3)."
    )
