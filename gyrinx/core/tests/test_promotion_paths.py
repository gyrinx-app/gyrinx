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


# --- Phase 4 gate: multi-target paths are not yet offered -------------------------------


@pytest.mark.django_db
def test_multi_target_paths_gated_until_selection_exists(
    juve_fighter, make_content_fighter, content_house
):
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
        from_category=FighterCategoryChoices.JUVE,
        xp_cost=0,
    )
    path.targets.set([forge_boss, stimmer])

    form = AdvancementTypeForm(fighter=juve_fighter)
    choices = dict(form.fields["advancement_choice"].choices)
    # Catches: offering a two-target promotion with no way to pick the target — the
    # player's "which type?" decision (the heart of #1467) would be silently dropped.
    assert f"promotion_{path.id}" not in choices
