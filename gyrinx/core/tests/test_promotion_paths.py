"""Phase 2 tests: the advancement flow driven by ContentPromotionPath.

Covers groups B (Juve — the #1596 fix) and C (roll-driven prefill, including the roll-12
fix) of the promotions test matrix, plus rank-driven reversal across both eras. See
``.claude/notes/promotions-epic-design.md`` and ``promotions-rules-spec.md``.
"""

import pytest
from django.urls import reverse

from gyrinx.content.models import ContentPromotionPath
from gyrinx.core.forms.advancement import AdvancementTypeForm
from gyrinx.core.handlers.fighter.advancement import (
    handle_fighter_advancement,
    handle_fighter_advancement_deletion,
)
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighterAdvancement
from gyrinx.models import FighterCategoryChoices


@pytest.fixture
def ganger_with_xp(make_content_fighter, make_list, make_list_fighter, content_house):
    ganger_cf = make_content_fighter(
        type="Sister",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    lst = make_list("Roll Test Gang")
    return make_list_fighter(lst, "Ganger", content_fighter=ganger_cf, xp_current=30)


@pytest.fixture
def combat_skill(make_content_skill):
    return make_content_skill("Counter-attack", category="Combat")


@pytest.fixture
def juve_fighter(make_content_fighter, make_list, make_list_fighter, content_house):
    juve_cf = make_content_fighter(
        type="Little Sister",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=25,
    )
    lst = make_list("Promotion Test Gang")
    return make_list_fighter(lst, "Juve", content_fighter=juve_cf, xp_current=10)


@pytest.fixture
def juve_promotion_path(juve_fighter):
    """A house-style Juve → Specialist path: no skill, Downtime, threshold 5 (RAW)."""
    return ContentPromotionPath.objects.create(
        name="Promotion (Specialist)",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category=FighterCategoryChoices.JUVE,
        to_category=FighterCategoryChoices.SPECIALIST,
        rank=1,
        xp_cost=0,
        cost_increase=15,
        grants_skill="none",
        advancements_threshold=5,
        timing=ContentPromotionPath.Timing.DOWNTIME,
    )


# --- B1: a Juve is offered its authored promotion (the #1596 fix) -----------------------


@pytest.mark.django_db
def test_juve_sees_authored_promotion(juve_fighter, juve_promotion_path):
    form = AdvancementTypeForm(fighter=juve_fighter)
    choices = dict(form.fields["advancement_choice"].choices)
    # Catches: the reported #1596 bug — Juves offered no promotion at all.
    assert f"promotion_{juve_promotion_path.id}" in choices
    assert choices[f"promotion_{juve_promotion_path.id}"] == "Promotion (Specialist)"


# --- B2: applying the Juve promotion is label-only (RAW) --------------------------------


@pytest.mark.django_db
def test_juve_promotion_wizard_flow_is_label_only(
    client, user, juve_fighter, juve_promotion_path
):
    lst = juve_fighter.list
    base_cost_before = juve_fighter._base_cost_int
    cost_before = juve_fighter.cost_int()
    key = f"promotion_{juve_promotion_path.id}"

    client.force_login(user)
    type_url = reverse(
        "core:list-fighter-advancement-type", args=[lst.id, juve_fighter.id]
    )
    # Skill-less promotion: type → confirm directly (no selection step).
    response = client.post(
        type_url,
        {"advancement_choice": key, "xp_cost": 0, "cost_increase": 15},
        follow=True,
    )
    assert response.status_code == 200
    assert "advancements/new/confirm" in response.request["PATH_INFO"]

    confirm_url = f"{response.request['PATH_INFO']}?{response.request['QUERY_STRING']}"
    response = client.post(confirm_url, follow=True)
    assert response.status_code == 200

    juve_fighter.refresh_from_db()
    fighter = type(juve_fighter).objects.get(id=juve_fighter.id)
    # Category relabelled per the path...
    assert fighter.get_category() == FighterCategoryChoices.SPECIALIST
    # ...but RAW-faithful: base cost NEVER changes; only the flat cost_increase applies.
    assert fighter._base_cost_int == base_cost_before
    assert fighter.cost_int() == cost_before + 15
    # The stored row is a promotion advancement carrying the path FK.
    advancement = fighter.advancements.get()
    assert advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_PROMOTION
    assert advancement.promotion_path == juve_promotion_path
    assert advancement.skill is None


# --- C1/C2: roll-driven prefill, including the roll-12 fix ------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("dice_total", [2, 12])
def test_roll_prefills_promotion(default_promotions, ganger_with_xp, dice_total):
    """Rulebook Ganger 2D6 table: a roll of 2 OR 12 promotes to Specialist (+20¢).

    The 12 case is the fixed latent bug — the old hardcoded config only implemented 2,
    so a rolled 12 fell through to Willpower.
    """
    specialist_path = default_promotions[("GANGER", "SPECIALIST")]
    action = CampaignAction(dice_total=dice_total)
    initial = AdvancementTypeForm.get_initial_for_action(action, ganger_with_xp)
    assert initial["advancement_choice"] == f"promotion_{specialist_path.id}"
    assert initial["cost_increase"] == 20
    assert initial["xp_cost"] == 6


@pytest.mark.django_db
def test_roll_still_prefills_stats(default_promotions, ganger_with_xp):
    # A non-promotion roll keeps its stat mapping (10 → Leadership/Cool row).
    action = CampaignAction(dice_total=10)
    initial = AdvancementTypeForm.get_initial_for_action(action, ganger_with_xp)
    assert initial["advancement_choice"] == "stat_leadership"


# --- rank-driven reversal across eras ---------------------------------------------------


@pytest.mark.django_db
def test_reversal_falls_back_by_rank_data_driven(
    user, ganger_with_xp, default_promotions
):
    """Delete the Champion promotion: the fighter falls back to SPECIALIST (rank 1), not
    None — driven by ContentPromotionPath.rank, not a hardcoded hierarchy."""
    specialist_path = default_promotions[("GANGER", "SPECIALIST")]
    champion_path = default_promotions[("SPECIALIST", "CHAMPION")]

    handle_fighter_advancement(
        user=user,
        fighter=ganger_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=6,
        cost_increase=20,
        advancement_choice=f"promotion_{specialist_path.id}",
        promotion_path=specialist_path,
    )
    result = handle_fighter_advancement(
        user=user,
        fighter=ganger_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=12,
        cost_increase=40,
        advancement_choice=f"promotion_{champion_path.id}",
        promotion_path=champion_path,
    )
    ganger_with_xp.refresh_from_db()
    assert ganger_with_xp.category_override == FighterCategoryChoices.CHAMPION

    handle_fighter_advancement_deletion(
        user=user, fighter=ganger_with_xp, advancement=result.advancement
    )
    ganger_with_xp.refresh_from_db()
    # Catches: the rank ordering breaking when the hierarchy moved from code to data.
    assert ganger_with_xp.category_override == FighterCategoryChoices.SPECIALIST


@pytest.mark.django_db
def test_reversal_mixed_eras(user, ganger_with_xp, default_promotions, combat_skill):
    """A legacy-era Specialist promotion (stored string, no FK) still anchors the
    fallback when a data-driven Champion promotion is deleted."""
    champion_path = default_promotions[("SPECIALIST", "CHAMPION")]

    legacy = ListFighterAdvancement.objects.create(
        fighter=ganger_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        advancement_choice="skill_promote_specialist",
        skill=combat_skill,
        xp_cost=6,
        cost_increase=20,
    )
    legacy.apply_advancement()

    result = handle_fighter_advancement(
        user=user,
        fighter=ganger_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=12,
        cost_increase=40,
        advancement_choice=f"promotion_{champion_path.id}",
        promotion_path=champion_path,
    )
    handle_fighter_advancement_deletion(
        user=user, fighter=ganger_with_xp, advancement=result.advancement
    )
    ganger_with_xp.refresh_from_db()
    # Catches: the legacy static map being dropped — historical rows must keep anchoring
    # the category fallback forever.
    assert ganger_with_xp.category_override == FighterCategoryChoices.SPECIALIST


# --- D group: multi-target type-change promotions (#1467) -------------------------------


@pytest.fixture
def prospect_setup(make_content_fighter, make_list, make_list_fighter, content_house):
    """A Prospect with a two-target promotion path (the Forge-born case)."""
    prospect_cf = make_content_fighter(
        type="Forge-born",
        category=FighterCategoryChoices.PROSPECT,
        house=content_house,
        base_cost=50,
    )
    forge_boss = make_content_fighter(
        type="Forge Boss",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=125,
    )
    stimmer = make_content_fighter(
        type="Stimmer",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=125,
    )
    path = ContentPromotionPath.objects.create(
        name="Promotion (Forge Boss or Stimmer)",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category=FighterCategoryChoices.PROSPECT,
        source_fighter=prospect_cf,
        xp_cost=0,
        cost_increase=0,
        grants_skill="none",
        advancements_threshold=5,
        timing=ContentPromotionPath.Timing.DOWNTIME,
        rank=2,
    )
    path.targets.set([forge_boss, stimmer])
    lst = make_list("Type-change Test Gang")
    fighter = make_list_fighter(lst, "Krag", content_fighter=prospect_cf, xp_current=10)
    return {
        "fighter": fighter,
        "list": lst,
        "path": path,
        "prospect_cf": prospect_cf,
        "forge_boss": forge_boss,
        "stimmer": stimmer,
    }


@pytest.mark.django_db
def test_multi_target_path_now_offered(prospect_setup):
    """Phase 4 lifts the multi-target gate: the two-target path appears in choices."""
    form = AdvancementTypeForm(fighter=prospect_setup["fighter"])
    choices = dict(form.fields["advancement_choice"].choices)
    # Catches: the #1467 symptom — dual-Champion prospects offered nothing.
    assert f"promotion_{prospect_setup['path'].id}" in choices


@pytest.mark.django_db
def test_type_change_wizard_flow_end_to_end(client, user, prospect_setup):
    """Full wizard: type → target choice (both offered) → confirm → applied per RAW."""
    fighter = prospect_setup["fighter"]
    lst = prospect_setup["list"]
    path = prospect_setup["path"]
    stimmer = prospect_setup["stimmer"]
    base_cost_before = fighter._base_cost_int
    key = f"promotion_{path.id}"

    client.force_login(user)
    type_url = reverse("core:list-fighter-advancement-type", args=[lst.id, fighter.id])
    response = client.post(
        type_url,
        {"advancement_choice": key, "xp_cost": 0, "cost_increase": 0},
        follow=True,
    )
    # Multi-target promotion routes to the select step for the target choice.
    assert response.status_code == 200
    assert "advancements/new/select" in response.request["PATH_INFO"]
    target_field = response.context["form"].fields["target"]
    # Catches: the choice collapsing — BOTH champion types must be offered.
    assert set(target_field.queryset.values_list("type", flat=True)) == {
        "Forge Boss",
        "Stimmer",
    }

    select_url = f"{response.request['PATH_INFO']}?{response.request['QUERY_STRING']}"
    response = client.post(select_url, {"target": str(stimmer.id)}, follow=True)
    assert response.status_code == 200
    assert "advancements/new/confirm" in response.request["PATH_INFO"]

    confirm_url = f"{response.request['PATH_INFO']}?{response.request['QUERY_STRING']}"
    response = client.post(confirm_url, follow=True)
    assert response.status_code == 200

    fighter = type(fighter).objects.get(id=fighter.id)
    # The fighter now counts as the CHOSEN type...
    assert fighter.promoted_content_fighter == stimmer
    assert fighter.get_category() == FighterCategoryChoices.CHAMPION
    # ...RAW-faithful: statline/base cost stay with the original type.
    assert fighter.content_fighter == prospect_setup["prospect_cf"]
    assert fighter._base_cost_int == base_cost_before
    advancement = fighter.advancements.get()
    assert advancement.promotion_target == stimmer
    assert advancement.promotion_path == path


@pytest.mark.django_db
def test_type_change_reversal_clears_pointer(user, prospect_setup):
    """D4: deleting the promotion clears the pointer and category symmetrically."""
    fighter = prospect_setup["fighter"]
    path = prospect_setup["path"]
    forge_boss = prospect_setup["forge_boss"]

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
        promotion_target=forge_boss,
    )
    fighter.refresh_from_db()
    assert fighter.promoted_content_fighter == forge_boss
    assert fighter.category_override == FighterCategoryChoices.CHAMPION

    handle_fighter_advancement_deletion(
        user=user, fighter=fighter, advancement=result.advancement
    )
    fighter.refresh_from_db()
    # Catches: asymmetric reversal — the pointer or label surviving deletion.
    assert fighter.promoted_content_fighter is None
    assert fighter.category_override is None


@pytest.mark.django_db
def test_promotion_target_cannot_be_stash(
    user, prospect_setup, make_content_fighter, content_house
):
    """F3: a promotion must never turn a fighter into the stash."""
    from django.core.exceptions import ValidationError

    stash_cf = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.STASH,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    path = prospect_setup["path"]
    with pytest.raises(ValidationError):
        handle_fighter_advancement(
            user=user,
            fighter=prospect_setup["fighter"],
            advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
            xp_cost=0,
            cost_increase=0,
            advancement_choice=f"promotion_{path.id}",
            promotion_path=path,
            promotion_target=stash_cf,
        )


# --- F group: access follows the promoted type; statline/cost never do ------------------


@pytest.mark.django_db
def test_access_follows_promoted_type(user, prospect_setup, make_content_skill):
    """Skill access and special rules come from the promoted type; equipment-list
    pricing prefers the promoted type's row over base."""
    from gyrinx.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentFighterEquipmentListItem,
        ContentRule,
        ContentSkillCategory,
    )
    from gyrinx.core.models import ListFighterEquipmentAssignment

    fighter = prospect_setup["fighter"]
    prospect_cf = prospect_setup["prospect_cf"]
    stimmer = prospect_setup["stimmer"]
    path = prospect_setup["path"]

    # Distinct skill trees and special rules per type.
    ferocity, _ = ContentSkillCategory.objects.get_or_create(name="Ferocity")
    cunning, _ = ContentSkillCategory.objects.get_or_create(name="Cunning")
    prospect_cf.primary_skill_categories.set([cunning])
    stimmer.primary_skill_categories.set([ferocity])
    rule_old = ContentRule.objects.create(name="Fast Learner")
    rule_new = ContentRule.objects.create(name="Combat Chems Stash")
    prospect_cf.rules.set([rule_old])
    stimmer.rules.set([rule_new])

    # An equipment-list price only the Stimmer gets.
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Test Gear", defaults={"group": "Gear"}
    )
    equipment = ContentEquipment.objects.create(
        name="Chem Rig", category=category, cost="100"
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=stimmer, equipment=equipment, cost=40
    )

    # Promote to Stimmer.
    handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
        promotion_target=stimmer,
    )
    fighter = type(fighter).objects.get(id=fighter.id)

    # Skill access follows the promoted type (replaced, not merged).
    assert fighter.get_primary_skill_categories() == {ferocity}
    # Special rules swap wholesale to the promoted type's set.
    rule_names = [r.value for r in fighter.ruleline]
    assert "Combat Chems Stash" in rule_names
    assert "Fast Learner" not in rule_names
    # New purchases price against the promoted type's equipment list.
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=equipment
    )
    assert assignment.base_cost_int() == 40
    # Statline identity and base cost NEVER follow the pointer.
    assert fighter.content_fighter_cached == prospect_cf
    assert fighter._base_cost_int == 50


@pytest.mark.django_db
def test_legacy_beats_promotion_for_equipment_pricing(
    user, prospect_setup, make_content_fighter, content_house
):
    """F1: when legacy, promoted, and base all price the same item, legacy wins."""
    from gyrinx.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentFighterEquipmentListItem,
    )
    from gyrinx.core.models import ListFighterEquipmentAssignment

    fighter = prospect_setup["fighter"]
    stimmer = prospect_setup["stimmer"]
    path = prospect_setup["path"]

    legacy_cf = make_content_fighter(
        type="Old Mentor",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=60,
        can_be_legacy=True,
    )
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Test Gear", defaults={"group": "Gear"}
    )
    equipment = ContentEquipment.objects.create(
        name="Shiv", category=category, cost="100"
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=legacy_cf, equipment=equipment, cost=30
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=stimmer, equipment=equipment, cost=50
    )

    handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
        promotion_target=stimmer,
    )
    fighter = type(fighter).objects.get(id=fighter.id)
    fighter.legacy_content_fighter = legacy_cf
    fighter.save()
    fighter = type(fighter).objects.get(id=fighter.id)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=equipment
    )
    # Catches: the three-way tie-break ordering regressing (legacy > promoted > base).
    assert assignment.base_cost_int() == 30


# --- Phase 5: promotion state survives fighter copies -----------------------------------


@pytest.mark.django_db
def test_clone_carries_promotion_state(user, prospect_setup):
    """Cloning (the mechanism behind campaign entry) keeps the label AND the pointer.

    Also covers the pre-existing category_override gap: before this, a promoted
    fighter lost their badge when their list was cloned into a campaign.
    """
    fighter = prospect_setup["fighter"]
    path = prospect_setup["path"]
    stimmer = prospect_setup["stimmer"]

    handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
        promotion_target=stimmer,
    )
    fighter.refresh_from_db()

    clone = fighter.clone(name="Krag's Twin")
    # Catches: the hand-maintained clone field list dropping promotion state — the
    # clone would arrive in the campaign as an unpromoted Prospect.
    assert clone.category_override == FighterCategoryChoices.CHAMPION
    assert clone.promoted_content_fighter == stimmer


@pytest.mark.django_db
def test_duplicate_handler_promotion_follows_caller_choice(user, prospect_setup):
    """The duplicate-fighter handler carries promotion state only when asked —
    mirroring the form's "Clone as {promoted category}" checkbox semantics."""
    from gyrinx.core.handlers.fighter.hire_clone import (
        FighterCloneParams,
        handle_fighter_clone,
    )

    fighter = prospect_setup["fighter"]
    path = prospect_setup["path"]
    forge_boss = prospect_setup["forge_boss"]

    handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
        promotion_target=forge_boss,
    )
    fighter.refresh_from_db()

    # Checkbox unticked: promotion cleared on the copy.
    result = handle_fighter_clone(
        user=user,
        source_fighter=fighter,
        clone_params=FighterCloneParams(
            name="Fresh Copy",
            content_fighter=fighter.content_fighter,
            target_list=prospect_setup["list"],
        ),
    )
    assert result.fighter.category_override is None
    assert result.fighter.promoted_content_fighter is None

    # Checkbox ticked: label and pointer travel together.
    result = handle_fighter_clone(
        user=user,
        source_fighter=fighter,
        clone_params=FighterCloneParams(
            name="Promoted Copy",
            content_fighter=fighter.content_fighter,
            target_list=prospect_setup["list"],
            category_override=fighter.category_override,
            promoted_content_fighter=fighter.promoted_content_fighter,
        ),
    )
    assert result.fighter.category_override == FighterCategoryChoices.CHAMPION
    assert result.fighter.promoted_content_fighter == forge_boss


@pytest.mark.django_db
def test_multi_target_promotion_without_stored_choice_resolves_no_target(
    user, prospect_setup
):
    """A programmatically-created multi-target promotion row with no stored target must
    NOT resolve to an arbitrary pick — it applies only what is unambiguous."""
    fighter = prospect_setup["fighter"]
    path = prospect_setup["path"]

    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter,
        owner=user,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
        xp_cost=0,
        cost_increase=0,
    )
    resolved = advancement.resolved_promotion()
    # Catches: resolved_promotion falling back to targets.first() and silently picking
    # Forge Boss vs Stimmer on the player's behalf.
    assert resolved.target is None
    advancement.apply_advancement()
    fighter.refresh_from_db()
    assert fighter.promoted_content_fighter is None
