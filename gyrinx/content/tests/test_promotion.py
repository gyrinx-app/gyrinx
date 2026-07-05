"""Phase 1 tests for content-driven promotions (#1596 / #1467 epic).

Covers the ``ContentPromotionCategoryPath`` model and its default seed. See the test matrix
(Group G, plus linchpins A4 and the core/content drift guard) in
``.claude/notes/promotions-epic-design.md``.

These tests are deliberately non-vacuous: each asserts a concrete value/state and names the
regression it guards against.
"""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import ContentHouse, ContentPromotionCategoryPath
from gyrinx.content.models.promotion import (
    DEFAULT_CATEGORY_PROMOTIONS,
    PROMOTION_TARGET_CATEGORIES,
    seed_category_promotions,
)
from gyrinx.models import FighterCategoryChoices


def _make_path(**kwargs):
    defaults = dict(
        name="Promote to Specialist",
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.SPECIALIST,
        xp_cost=6,
    )
    defaults.update(kwargs)
    return ContentPromotionCategoryPath(**defaults)


# --- G1: readable __str__ -------------------------------------------------------------


@pytest.mark.django_db
def test_str_renders_name_and_transition():
    path = _make_path(name="Promote to Specialist")
    # Catches: admin changelist rendering by object id/ctype instead of a readable label (cf #1942).
    assert str(path) == "Promote to Specialist (GANGER → SPECIALIST)"


# --- G2/G3: clean() validation --------------------------------------------------------


@pytest.mark.django_db
def test_clean_rejects_same_from_and_to_category():
    path = _make_path(
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.GANGER,
    )
    # Catches: a no-op "self promotion" being saveable.
    with pytest.raises(ValidationError) as exc:
        path.full_clean()
    assert "to_category" in exc.value.message_dict


@pytest.mark.django_db
def test_clean_rejects_target_outside_allowed_overrides():
    # STASH is a valid FighterCategoryChoices value but NOT a promotable target.
    path = _make_path(
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.STASH,
    )
    # Catches: a promotion whose target category `validate_category_override` would later reject
    # at apply time, i.e. an un-applyable promotion slipping past content validation.
    with pytest.raises(ValidationError) as exc:
        path.full_clean()
    assert "to_category" in exc.value.message_dict


@pytest.mark.django_db
def test_clean_allows_valid_promotion():
    # A sanity anchor so the two reject-tests above can't pass by clean() always raising.
    _make_path().full_clean()  # must not raise


# --- G4: rank ordering (data source for the reversal hierarchy) -----------------------


@pytest.mark.django_db
def test_default_ordering_is_by_rank():
    champion = ContentPromotionCategoryPath.objects.create(
        name="Promote to Champion",
        from_category=FighterCategoryChoices.SPECIALIST,
        to_category=FighterCategoryChoices.CHAMPION,
        rank=2,
        xp_cost=12,
    )
    specialist = ContentPromotionCategoryPath.objects.create(
        name="Promote to Specialist",
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.SPECIALIST,
        rank=1,
        xp_cost=6,
    )
    # Catches: the reversal hierarchy (Champion > Specialist) losing its data ordering.
    assert list(ContentPromotionCategoryPath.objects.all()) == [specialist, champion]


# --- G5: content-level availability gate ----------------------------------------------


@pytest.mark.django_db
def test_is_available_matches_from_category(
    make_content_fighter, make_list, make_list_fighter, content_house
):
    ganger_cf = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    juve_cf = make_content_fighter(
        type="Juve",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=25,
    )
    lst = make_list("Gang")
    ganger = make_list_fighter(lst, "G", content_fighter=ganger_cf)
    juve = make_list_fighter(lst, "J", content_fighter=juve_cf)

    path = ContentPromotionCategoryPath.objects.create(
        name="Promote to Specialist",
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.SPECIALIST,
        xp_cost=6,
    )
    # Catches: category filtering (which Phase 2 depends on) offering a promotion to the wrong
    # category — the exact class of bug behind #1596.
    assert path.is_available_to_fighter(ganger) is True
    assert path.is_available_to_fighter(juve) is False


@pytest.mark.django_db
def test_is_available_respects_house_restriction(
    make_content_fighter, make_list, make_list_fighter, content_house
):
    ganger_cf = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    lst = make_list("Gang")
    ganger = make_list_fighter(lst, "G", content_fighter=ganger_cf)

    other_house = ContentHouse.objects.create(name="Some Other House")
    path = ContentPromotionCategoryPath.objects.create(
        name="Promote to Specialist",
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.SPECIALIST,
        xp_cost=6,
    )

    path.restricted_to_houses.add(other_house)
    # Catches: house restriction being ignored (fighter's own house not in the allow-list).
    assert path.is_available_to_fighter(ganger) is False

    path.restricted_to_houses.add(content_house)
    assert path.is_available_to_fighter(ganger) is True


# --- G6 / seed: the default data --------------------------------------------------------


@pytest.mark.django_db
def test_seed_creates_the_two_default_paths_with_exact_values():
    seed_category_promotions(ContentPromotionCategoryPath)

    by_pair = {
        (p.from_category, p.to_category): p
        for p in ContentPromotionCategoryPath.objects.all()
    }
    assert len(by_pair) == 2

    specialist = by_pair[("GANGER", "SPECIALIST")]
    assert specialist.name == "Promote to Specialist"
    assert specialist.rank == 1
    assert specialist.xp_cost == 6
    assert specialist.cost_increase == 20
    assert specialist.rolls == [2, 12]  # the "also roll 12" fix baked into the seed

    champion = by_pair[("SPECIALIST", "CHAMPION")]
    assert champion.name == "Promote to Champion"
    assert champion.rank == 2
    assert champion.xp_cost == 12
    assert champion.cost_increase == 40

    # Idempotent — re-running never duplicates (the migration may run alongside a prod estate).
    seed_category_promotions(ContentPromotionCategoryPath)
    assert ContentPromotionCategoryPath.objects.count() == 2


# --- A4 (linchpin): seed must reproduce today's hardcoded configs ----------------------


def test_seed_matches_hardcoded_advancement_configs():
    """The seed's cost/XP/rolls must equal the current hardcoded promotion configs.

    This is what makes the Phase 2 refactor cost-NEUTRAL: if anyone edits an
    ``ADVANCEMENT_CONFIGS`` number without the seed (or vice-versa), this fails. No DB needed.
    """
    from gyrinx.core.forms.advancement import AdvancementTypeForm

    configs = AdvancementTypeForm.ADVANCEMENT_CONFIGS
    by_legacy = {e["_legacy_choice"]: e for e in DEFAULT_CATEGORY_PROMOTIONS}

    # Both hardcoded promotion keys must be represented by a seed row.
    assert set(by_legacy) == {"skill_promote_specialist", "skill_promote_champion"}

    for choice, entry in by_legacy.items():
        config = configs[choice]
        assert entry["xp_cost"] == config.xp_cost, choice
        assert entry["cost_increase"] == config.cost_increase, choice
        if config.roll is not None:
            # The scalar hardcoded roll must be among the seed's roll list.
            assert config.roll in entry["rolls"], choice


# --- drift guard: content's promotable targets stay aligned with core's override list ---


def test_promotion_targets_match_core_allowed_overrides():
    """PROMOTION_TARGET_CATEGORIES mirrors core's ALLOWED_CATEGORY_OVERRIDES (content can't
    import core, so the list is duplicated). If core changes its allow-list and this mirror
    isn't updated, a promotion could target a category that fails validation at apply time.
    """
    from gyrinx.core.models.list._common import ALLOWED_CATEGORY_OVERRIDES

    assert list(PROMOTION_TARGET_CATEGORIES) == list(ALLOWED_CATEGORY_OVERRIDES)
