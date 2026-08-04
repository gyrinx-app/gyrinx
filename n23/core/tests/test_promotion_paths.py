"""Phase 2 tests: the advancement flow driven by ContentPromotionPath.

Covers groups B (Juve — the #1596 fix) and C (roll-driven prefill, including the roll-12
fix) of the promotions test matrix, plus rank-driven reversal across both eras. See
``.claude/notes/promotions-epic-design.md`` and ``promotions-rules-spec.md``.
"""

import pytest
from django.urls import reverse

from n23.content.models import ContentPromotionPath
from n23.core.forms.advancement import AdvancementTypeForm
from n23.core.handlers.fighter.advancement import (
    handle_fighter_advancement,
    handle_fighter_advancement_deletion,
)
from n23.core.models.campaign import CampaignAction
from n23.core.models.list import ListFighter, ListFighterAdvancement
from n23.models import FighterCategoryChoices


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
    from n23.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentFighterEquipmentListItem,
        ContentRule,
        ContentSkillCategory,
    )
    from n23.core.models import ListFighterEquipmentAssignment

    fighter = prospect_setup["fighter"]
    prospect_cf = prospect_setup["prospect_cf"]
    stimmer = prospect_setup["stimmer"]
    path = prospect_setup["path"]

    # Distinct skill trees and special rules per type.
    ferocity, _ = ContentSkillCategory.objects.get_or_create(name="Ferocity")
    cunning, _ = ContentSkillCategory.objects.get_or_create(name="Cunning")
    prospect_cf.primary_skill_categories.set([cunning])
    stimmer.primary_skill_categories.set([ferocity])
    # Fast Learner is promotion scaffolding — shed on promotion; Squat Ancestry is
    # intrinsic and kept (default). Combat Chems Stash is gained from the new type.
    rule_shed = ContentRule.objects.create(name="Fast Learner", shed_on_promotion=True)
    rule_kept = ContentRule.objects.create(name="Squat Ancestry")
    rule_new = ContentRule.objects.create(name="Combat Chems Stash")
    prospect_cf.rules.set([rule_shed, rule_kept])
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
    # Special rules: the new type's are gained, shed-flagged scaffolding is dropped,
    # and intrinsic rules are kept (default-keep).
    rule_names = [r.value for r in fighter.ruleline]
    assert "Combat Chems Stash" in rule_names
    assert "Fast Learner" not in rule_names
    assert "Squat Ancestry" in rule_names
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
    from n23.content.models import (
        ContentEquipment,
        ContentEquipmentCategory,
        ContentFighterEquipmentListItem,
    )
    from n23.core.models import ListFighterEquipmentAssignment

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
    from n23.core.handlers.fighter.hire_clone import (
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


# --- review-driven guards ---------------------------------------------------------------


@pytest.mark.django_db
def test_taken_path_no_longer_offered_and_rebuy_rejected(user, prospect_setup):
    """After promotion the source-pinned path stops matching (category changed) and the
    handler refuses a re-buy — no XP drain / double cost through crafted URLs."""
    from django.core.exceptions import ValidationError

    fighter = prospect_setup["fighter"]
    path = prospect_setup["path"]
    stimmer = prospect_setup["stimmer"]

    assert path.is_available_to_fighter(fighter) is True
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
    # Catches: the source_fighter branch skipping the category check — the taken path
    # stayed offered forever (fighter's content_fighter never changes).
    assert path.is_available_to_fighter(fighter) is False
    form = AdvancementTypeForm(fighter=fighter)
    assert f"promotion_{path.id}" not in dict(form.fields["advancement_choice"].choices)
    with pytest.raises(ValidationError):
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


@pytest.mark.django_db
def test_tampered_target_id_routes_back_to_chooser(
    prospect_setup, make_content_fighter, content_house
):
    """A promotion_target_id that isn't one of the path's targets counts as no choice."""
    from n23.core.views.fighter.advancements import AdvancementFlowParams

    outsider = make_content_fighter(
        type="Outsider",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=100,
    )
    params = AdvancementFlowParams(
        advancement_choice=f"promotion_{prospect_setup['path'].id}",
        promotion_target_id=outsider.id,
    )
    # Catches: presence-only checking letting a tampered/stale id through the confirm
    # gate to an ambiguous apply.
    assert params.promotion_needs_target(prospect_setup["fighter"]) is True
    assert params.promotion_target(prospect_setup["fighter"]) is None


@pytest.mark.django_db
def test_single_target_apply_persists_target_on_row(
    user, make_content_fighter, make_list, make_list_fighter, content_house
):
    """Single-target type-changes pin the resolved target at purchase, so later content
    edits can't rewrite what existing fighters count as."""
    prospect_cf = make_content_fighter(
        type="Wyld Runner",
        category=FighterCategoryChoices.PROSPECT,
        house=content_house,
        base_cost=40,
    )
    matriarch = make_content_fighter(
        type="Matriarch",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=125,
    )
    path = ContentPromotionPath.objects.create(
        name="Promotion (Matriarch)",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category=FighterCategoryChoices.PROSPECT,
        source_fighter=prospect_cf,
        xp_cost=0,
    )
    path.targets.set([matriarch])
    lst = make_list("Single Target Gang")
    fighter = make_list_fighter(lst, "Sable", content_fighter=prospect_cf, xp_current=5)

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
    )
    result.advancement.refresh_from_db()
    # Catches: the row staying target-less, letting an admin's later second target
    # silently rewrite the fighter's counts-as on reversal recalc.
    assert result.advancement.promotion_target == matriarch


@pytest.mark.django_db
def test_higher_rank_relabel_does_not_wipe_pointer(user, prospect_setup, combat_skill):
    """The pointer competes only among promotions WITH targets: recalc triggered by
    deleting a legacy promotion must not let a higher-ranked relabel wipe the counts-as
    of a still-held type change."""
    fighter = prospect_setup["fighter"]
    path = prospect_setup["path"]
    stimmer = prospect_setup["stimmer"]

    # Legacy-era promotion row (rank 1 via the static map) — its deletion triggers recalc.
    legacy = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        advancement_choice="skill_promote_specialist",
        skill=combat_skill,
        xp_cost=0,
        cost_increase=0,
        owner=user,
    )
    legacy.apply_advancement()
    fighter = type(fighter).objects.get(id=fighter.id)
    # Path availability checks category; the legacy relabel moved it to SPECIALIST, so
    # apply the type change directly via the model (rank 2, pointer set)...
    tc = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
        promotion_target=stimmer,
        xp_cost=0,
        cost_increase=0,
        owner=user,
    )
    tc.apply_advancement()
    # ...and a higher-ranked relabel on top (rank 3).
    relabel_path = ContentPromotionPath.objects.create(
        name="Promote to Leader",
        kind=ContentPromotionPath.Kind.RELABEL,
        from_category=FighterCategoryChoices.CHAMPION,
        to_category=FighterCategoryChoices.LEADER,
        rank=3,
        xp_cost=0,
        grants_skill="none",
    )
    relabel = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        advancement_choice=f"promotion_{relabel_path.id}",
        promotion_path=relabel_path,
        xp_cost=0,
        cost_increase=0,
        owner=user,
    )
    relabel.apply_advancement()

    fighter = type(fighter).objects.get(id=fighter.id)
    assert fighter.category_override == FighterCategoryChoices.LEADER
    assert fighter.promoted_content_fighter == stimmer

    handle_fighter_advancement_deletion(user=user, fighter=fighter, advancement=legacy)
    fighter = type(fighter).objects.get(id=fighter.id)
    # Catches: recalc sourcing the pointer from the single best-rank promotion — the
    # rank-3 relabel would have wiped the Stimmer pointer.
    assert fighter.category_override == FighterCategoryChoices.LEADER
    assert fighter.promoted_content_fighter == stimmer


@pytest.mark.django_db
def test_copy_attributes_to_keeps_promotion_resolvable(
    user, prospect_setup, make_list_fighter
):
    """Copied fighters carry resolvable promotion rows, not inert ones that a later
    deletion recalc would resolve to nothing."""
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
    fighter = type(fighter).objects.get(id=fighter.id)
    target_fighter = make_list_fighter(
        prospect_setup["list"], "Copy", content_fighter=prospect_setup["prospect_cf"]
    )
    fighter.copy_attributes_to(target_fighter, include_equipment=False)
    copied = target_fighter.advancements.get()
    # Catches: the copy loop omitting advancement_choice/promotion FKs — inert rows
    # whose recalc would erase the copy's promotion.
    assert copied.promotion_path == path
    assert copied.promotion_target == forge_boss
    assert copied.resolved_promotion().target == forge_boss


# --- shed_on_promotion: rules retained by default, flagged ones dropped -----------------


def _promote_to(user, fighter, path, target):
    handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{path.id}",
        promotion_path=path,
        promotion_target=target,
    )


@pytest.mark.django_db
def test_promotion_keeps_rules_by_default_sheds_flagged(user, prospect_setup):
    """RAW default: a promoted fighter keeps their own rules and gains the new type's;
    only rules flagged shed_on_promotion (the promotion scaffolding) are dropped."""
    from n23.content.models import ContentRule

    fighter = prospect_setup["fighter"]
    prospect_cf = prospect_setup["prospect_cf"]
    stimmer = prospect_setup["stimmer"]

    kept = ContentRule.objects.create(name="Squat Ancestry")
    shed_a = ContentRule.objects.create(
        name="Gang Fighter (Prospect)", shed_on_promotion=True
    )
    shed_b = ContentRule.objects.create(name="Fast Learner", shed_on_promotion=True)
    gained = ContentRule.objects.create(name="Combat Chems Stash")
    prospect_cf.rules.set([kept, shed_a, shed_b])
    stimmer.rules.set([gained])

    before = {r.value for r in fighter.ruleline}
    assert before == {"Squat Ancestry", "Gang Fighter (Prospect)", "Fast Learner"}

    _promote_to(user, fighter, prospect_setup["path"], stimmer)
    fighter = type(fighter).objects.get(id=fighter.id)
    after = {r.value for r in fighter.ruleline}
    # Catches: reverting to the wholesale swap (would drop "Squat Ancestry"), or the flag
    # being ignored (would keep "Gang Fighter (Prospect)"/"Fast Learner").
    assert after == {"Squat Ancestry", "Combat Chems Stash"}


@pytest.mark.django_db
def test_shed_flag_ignored_for_unpromoted_fighter(user, prospect_setup):
    """The flag only bites on promotion — an un-promoted fighter keeps flagged rules."""
    from n23.content.models import ContentRule

    fighter = prospect_setup["fighter"]
    shed = ContentRule.objects.create(name="Fast Learner", shed_on_promotion=True)
    prospect_setup["prospect_cf"].rules.set([shed])
    assert {r.value for r in fighter.ruleline} == {"Fast Learner"}


@pytest.mark.django_db
def test_promotion_ruleline_prefetch_matches_query(user, prospect_setup):
    """The prefetch fast path and the query fallback agree for a promoted fighter."""
    from n23.content.models import ContentRule

    fighter = prospect_setup["fighter"]
    lst = prospect_setup["list"]
    stimmer = prospect_setup["stimmer"]

    prospect_setup["prospect_cf"].rules.set(
        [
            ContentRule.objects.create(name="Squat Ancestry"),
            ContentRule.objects.create(name="Fast Learner", shed_on_promotion=True),
        ]
    )
    stimmer.rules.set([ContentRule.objects.create(name="Combat Chems Stash")])
    _promote_to(user, fighter, prospect_setup["path"], stimmer)

    slow = {r.value for r in ListFighter.objects.get(id=fighter.id).ruleline}
    fast_fighter = ListFighter.objects.with_related_data(packs=lst.packs.all()).get(
        id=fighter.id
    )
    fast = {r.value for r in fast_fighter.ruleline}
    assert fast == slow == {"Squat Ancestry", "Combat Chems Stash"}


# ---------------------------------------------------------------------------
# 'Nominate as leader' (#1468): any-category source, dynamic Leader targets,
# LEADER_DEATH trigger gate, and the fighter-card affordance.
# ---------------------------------------------------------------------------


def _offered_path_names(fighter):
    from n23.core.forms.advancement import available_promotion_paths

    return {p.name for p in available_promotion_paths(fighter)}


@pytest.fixture
def leaderless_gang(
    campaign, make_content_fighter, make_list, make_list_fighter, content_house
):
    """A campaign-mode gang whose leader is dead, in a house with two Leader types."""
    from n23.core.models.list import List

    queen = make_content_fighter(
        type="Queen",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=150,
    )
    matriarch = make_content_fighter(
        type="Matriarch",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=160,
    )
    ganger_cf = make_content_fighter(
        type="Sisterhood Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    juve_cf = make_content_fighter(
        type="Sisterhood Juve",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=25,
    )
    lst = make_list("Leaderless Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    dead_leader = make_list_fighter(
        lst, "Old Queen", content_fighter=queen, injury_state=ListFighter.DEAD
    )
    ganger = make_list_fighter(
        lst, "Successor", content_fighter=ganger_cf, xp_current=0
    )
    return {
        "list": lst,
        "dead_leader": dead_leader,
        "ganger": ganger,
        "queen": queen,
        "matriarch": matriarch,
        "ganger_cf": ganger_cf,
        "juve_cf": juve_cf,
    }


@pytest.mark.django_db
def test_nomination_offered_to_any_category_when_leader_dead(
    leaderless_gang, leader_nomination_path, make_list_fighter
):
    """Any fighter — ganger AND juve — sees the path once the leader is dead, at 0 XP
    and 0 cost. Catches: the SQL prefilter or the availability gate dropping blank
    from_category rows, or the seeded costs drifting."""
    ganger = leaderless_gang["ganger"]
    juve = make_list_fighter(
        leaderless_gang["list"], "Junior", content_fighter=leaderless_gang["juve_cf"]
    )
    assert "Nominate as leader" in _offered_path_names(ganger)
    assert "Nominate as leader" in _offered_path_names(juve)

    form = AdvancementTypeForm(fighter=ganger)
    key = f"promotion_{leader_nomination_path.id}"
    assert key in [choice for choice, _ in form.fields["advancement_choice"].choices]
    assert form.advancement_configs[key].xp_cost == 0
    assert form.advancement_configs[key].cost_increase == 0


@pytest.mark.django_db
def test_nomination_hidden_while_leader_lives(leaderless_gang, leader_nomination_path):
    """Catches: the LEADER_DEATH trigger degrading to always-on."""
    dead_leader = leaderless_gang["dead_leader"]
    dead_leader.injury_state = ListFighter.ACTIVE
    dead_leader.save()
    assert "Nominate as leader" not in _offered_path_names(leaderless_gang["ganger"])


@pytest.mark.django_db
def test_nomination_hidden_outside_campaign_mode(
    leader_nomination_path,
    make_content_fighter,
    make_list,
    make_list_fighter,
    content_house,
):
    """A leaderless list-building gang must NOT see the path (campaign-only)."""
    make_content_fighter(
        type="Building Leader",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=150,
    )
    ganger_cf = make_content_fighter(
        type="Building Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    lst = make_list("Building Gang")
    fighter = make_list_fighter(lst, "Hopeful", content_fighter=ganger_cf)
    assert "Nominate as leader" not in _offered_path_names(fighter)


@pytest.mark.django_db
def test_nomination_hidden_when_house_has_no_leader_types(
    campaign,
    leader_nomination_path,
    make_content_fighter,
    make_list,
    make_list_fighter,
    house,
):
    """A dynamic type change with nothing to become is not on offer."""
    from n23.core.models.list import List

    ganger_cf = make_content_fighter(
        type="Outcast Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    lst = make_list(
        "No Leader Types Gang",
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    fighter = make_list_fighter(lst, "Nobody", content_fighter=ganger_cf)
    assert "Nominate as leader" not in _offered_path_names(fighter)


@pytest.mark.django_db
def test_nomination_hidden_for_out_of_fight_or_type_changed_fighter(
    leaderless_gang, leader_nomination_path
):
    """A dead fighter can't be nominated; nor can one already holding a type change.
    Catches: the any-category path losing its 'already taken' protection (category
    change can't provide it here)."""
    ganger = leaderless_gang["ganger"]

    ganger.injury_state = ListFighter.DEAD
    ganger.save()
    assert "Nominate as leader" not in _offered_path_names(ganger)

    ganger.injury_state = ListFighter.ACTIVE
    ganger.promoted_content_fighter = leaderless_gang["queen"]
    ganger.save()
    ganger = ListFighter.objects.get(id=ganger.id)
    assert "Nominate as leader" not in _offered_path_names(ganger)

    # The dead leader themselves is never offered succession.
    assert "Nominate as leader" not in _offered_path_names(
        leaderless_gang["dead_leader"]
    )


@pytest.mark.django_db
def test_dynamic_targets_resolve_to_gang_house_leaders(
    leaderless_gang, leader_nomination_path, make_content_fighter, house
):
    """Resolution keys off the gang's house: both of its Leader types, and never
    another house's."""
    make_content_fighter(
        type="Foreign Boss",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    resolved = set(leader_nomination_path.resolve_targets(leaderless_gang["ganger"]))
    assert resolved == {leaderless_gang["queen"], leaderless_gang["matriarch"]}


@pytest.mark.django_db
def test_nomination_apply_and_reverse_invariants(
    user, leaderless_gang, leader_nomination_path
):
    """Apply: LEADER category, pointer to the chosen type, base cost and rating and XP
    all unchanged (free, access-only). Reverse: exact symmetry. Catches: the nomination
    bleeding into cost, or reversal leaving the pointer/category behind."""
    ganger = leaderless_gang["ganger"]
    lst = leaderless_gang["list"]
    queen = leaderless_gang["queen"]
    lst.refresh_from_db()
    rating_before = lst.rating_current

    result = handle_fighter_advancement(
        user=user,
        fighter=ganger,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{leader_nomination_path.id}",
        promotion_path=leader_nomination_path,
        promotion_target=queen,
    )

    fighter = ListFighter.objects.get(id=ganger.id)
    assert fighter.category_override == FighterCategoryChoices.LEADER
    assert fighter.get_category() == FighterCategoryChoices.LEADER
    assert fighter.promoted_content_fighter == queen
    assert fighter._base_cost_int == 50
    assert fighter.xp_current == 0
    lst.refresh_from_db()
    assert lst.rating_current == rating_before

    handle_fighter_advancement_deletion(
        user=user, fighter=fighter, advancement=result.advancement
    )
    fighter = ListFighter.objects.get(id=ganger.id)
    assert fighter.category_override is None
    assert fighter.promoted_content_fighter is None
    assert fighter.xp_current == 0
    lst.refresh_from_db()
    assert lst.rating_current == rating_before


@pytest.mark.django_db
def test_nomination_reversal_falls_back_to_prior_promotion(
    user, leaderless_gang, leader_nomination_path, default_promotions
):
    """A Specialist ganger nominated leader falls back to SPECIALIST when the
    nomination is undone — rank 3 must not clear the whole promotion history."""
    ganger = leaderless_gang["ganger"]
    ganger.xp_current = 6
    ganger.save()
    spec_path = default_promotions[
        (FighterCategoryChoices.GANGER, FighterCategoryChoices.SPECIALIST)
    ]

    handle_fighter_advancement(
        user=user,
        fighter=ganger,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=6,
        cost_increase=20,
        advancement_choice=f"promotion_{spec_path.id}",
        promotion_path=spec_path,
    )
    fighter = ListFighter.objects.get(id=ganger.id)
    assert fighter.get_category() == FighterCategoryChoices.SPECIALIST

    nomination = handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{leader_nomination_path.id}",
        promotion_path=leader_nomination_path,
        promotion_target=leaderless_gang["queen"],
    )
    fighter = ListFighter.objects.get(id=ganger.id)
    assert fighter.get_category() == FighterCategoryChoices.LEADER

    handle_fighter_advancement_deletion(
        user=user, fighter=fighter, advancement=nomination.advancement
    )
    fighter = ListFighter.objects.get(id=ganger.id)
    # Catches: rank-driven recalc collapsing to None (or staying LEADER).
    assert fighter.category_override == FighterCategoryChoices.SPECIALIST
    assert fighter.promoted_content_fighter is None


@pytest.mark.django_db
def test_sole_leader_type_infers_target(
    user,
    campaign,
    leader_nomination_path,
    make_content_fighter,
    make_list,
    make_list_fighter,
    house,
):
    """A house with exactly one Leader type: apply with no stored choice resolves and
    persists that sole dynamic target. Catches: dynamic paths (empty targets M2M)
    applying category-only and never setting the pointer."""
    from n23.core.models.list import List

    boss = make_content_fighter(
        type="Sole Boss",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=120,
    )
    ganger_cf = make_content_fighter(
        type="Lone Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=45,
    )
    lst = make_list(
        "Sole Leader Gang",
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    fighter = make_list_fighter(lst, "Stepper", content_fighter=ganger_cf)

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
        xp_cost=0,
        cost_increase=0,
        advancement_choice=f"promotion_{leader_nomination_path.id}",
        promotion_path=leader_nomination_path,
    )
    result.advancement.refresh_from_db()
    fighter = ListFighter.objects.get(id=fighter.id)
    assert fighter.promoted_content_fighter == boss
    assert result.advancement.promotion_target == boss


@pytest.mark.django_db
def test_nomination_gains_gang_leader_rule_and_sheds_scaffolding(
    user, leaderless_gang, leader_nomination_path
):
    """The 'Gang Leader' special rule arrives via the type-change pointer's rules — no
    bespoke rule-granting code — while the old type's scaffolding (Gang Fighter (X),
    Promotion (…), flagged shed_on_promotion by migration 0188) drops away and
    unflagged house rules are kept. Catches: rules resolution not following the
    dynamically-resolved pointer, or the shed flag being ignored for nominations."""
    from n23.content.models import ContentRule

    gang_leader = ContentRule.objects.create(name="Gang Leader")
    leaderless_gang["queen"].rules.set([gang_leader])
    # Mirror the base-type ruleset of a real ganger row, flagged as 0188 flags them.
    leaderless_gang["ganger_cf"].rules.set(
        [
            ContentRule.objects.create(
                name="Gang Fighter (Ganger)", shed_on_promotion=True
            ),
            ContentRule.objects.create(
                name="Promotion (Specialist)", shed_on_promotion=True
            ),
            ContentRule.objects.create(name="Spirit Bond"),
        ]
    )

    _promote_to(
        user,
        leaderless_gang["ganger"],
        leader_nomination_path,
        leaderless_gang["queen"],
    )
    fighter = ListFighter.objects.get(id=leaderless_gang["ganger"].id)
    assert {r.value for r in fighter.ruleline} == {"Gang Leader", "Spirit Bond"}


@pytest.mark.django_db
def test_handler_rejects_nomination_outside_campaign(
    user,
    leader_nomination_path,
    make_content_fighter,
    make_list,
    make_list_fighter,
    content_house,
):
    """A crafted confirm URL must not apply a nomination to a list-building gang."""
    from django.core.exceptions import ValidationError

    make_content_fighter(
        type="Crafted Leader",
        category=FighterCategoryChoices.LEADER,
        house=content_house,
        base_cost=150,
    )
    ganger_cf = make_content_fighter(
        type="Crafted Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    lst = make_list("Crafted Gang")
    fighter = make_list_fighter(lst, "Chancer", content_fighter=ganger_cf)

    with pytest.raises(ValidationError, match="not available"):
        handle_fighter_advancement(
            user=user,
            fighter=fighter,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_PROMOTION,
            xp_cost=0,
            cost_increase=0,
            advancement_choice=f"promotion_{leader_nomination_path.id}",
            promotion_path=leader_nomination_path,
        )


@pytest.mark.django_db
def test_leader_nomination_offer_and_card_property(
    leaderless_gang, leader_nomination_path
):
    """The gang-level affordance points multi-target gangs at the chooser step, closes
    while a leader lives, and the per-fighter property tracks eligibility."""
    from n23.core.models.list import List

    lst = List.objects.get(id=leaderless_gang["list"].id)
    offer = lst.leader_nomination_offer
    assert offer is not None
    assert offer["path"] == leader_nomination_path
    assert offer["url_name"] == "core:list-fighter-advancement-select"
    assert f"promotion_{leader_nomination_path.id}" in offer["query"]

    assert leaderless_gang["ganger"].can_be_nominated_leader is True
    assert leaderless_gang["dead_leader"].can_be_nominated_leader is False

    # A living leader closes the offer (fresh instance: the property is cached).
    dead_leader = leaderless_gang["dead_leader"]
    dead_leader.injury_state = ListFighter.ACTIVE
    dead_leader.save()
    assert List.objects.get(id=lst.id).leader_nomination_offer is None


@pytest.mark.django_db
def test_nomination_wizard_end_to_end(
    client, user, leaderless_gang, leader_nomination_path
):
    """Deep link → target chooser (both leader types offered) → confirm → applied.
    The whole flow is URL-driven; this catches the wizard rejecting dynamic-target
    paths at any of its three gates."""
    client.force_login(user)
    lst = leaderless_gang["list"]
    ganger = leaderless_gang["ganger"]
    queen = leaderless_gang["queen"]
    params = f"advancement_choice=promotion_{leader_nomination_path.id}&xp_cost=0&cost_increase=0"

    select_url = reverse(
        "core:list-fighter-advancement-select", args=(lst.id, ganger.id)
    )
    response = client.get(f"{select_url}?{params}")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Queen" in content
    assert "Matriarch" in content

    response = client.post(f"{select_url}?{params}", {"target": str(queen.id)})
    assert response.status_code == 302
    confirm_url = response.url
    assert "promotion_target_id" in confirm_url

    response = client.post(confirm_url)
    assert response.status_code == 302
    fighter = ListFighter.objects.get(id=ganger.id)
    assert fighter.get_category() == FighterCategoryChoices.LEADER
    assert fighter.promoted_content_fighter == queen


@pytest.mark.django_db
def test_leader_nomination_seed_shape(leader_nomination_path):
    """The seeded row IS the feature's content contract — free, skill-less, dynamic
    Leader targets, LEADER_DEATH trigger, rank above Champion."""
    path = leader_nomination_path
    assert path.kind == ContentPromotionPath.Kind.TYPE_CHANGE
    assert path.from_category == ""
    assert path.to_category == FighterCategoryChoices.LEADER
    assert path.dynamic_targets_category == FighterCategoryChoices.LEADER
    assert path.rank == 3
    assert path.xp_cost == 0
    assert path.cost_increase == 0
    assert path.rolls == []
    assert path.grants_skill == "none"
    assert path.timing == ContentPromotionPath.Timing.LEADER_DEATH


@pytest.mark.django_db
def test_nomination_hidden_for_child_fighter(
    leaderless_gang,
    leader_nomination_path,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """An exotic beast (child fighter) can never be nominated, even though beasts can
    otherwise take advancements. Catches: the any-category gate stopping at
    stash/vehicle and letting equipment-spawned fighters through."""
    from n23.core.models.list import ListFighterEquipmentAssignment

    beast_cf = make_content_fighter(
        type="Gnasher",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=leaderless_gang["ganger_cf"].house,
        base_cost=30,
    )
    beast = make_list_fighter(
        leaderless_gang["list"], "Gnasher", content_fighter=beast_cf
    )
    collar = make_equipment("Beast Collar", category="Status Items", cost=0)
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=leaderless_gang["ganger"],
        content_equipment=collar,
        child_fighter=beast,
    )
    beast = ListFighter.objects.get(id=beast.id)
    assert "Nominate as leader" not in _offered_path_names(beast)
