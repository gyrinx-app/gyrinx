"""Phase 1 tests for content-driven promotions (#1596 / #1467 epic).

Covers the ``ContentPromotionPath`` model and its default seed. See the test matrix
(Group G, plus linchpins A4 and the core/content drift guard) in
``.claude/notes/promotions-epic-design.md`` and the rules research in
``.claude/notes/promotions-rules-spec.md``.

These tests are deliberately non-vacuous: each asserts a concrete value/state and names the
regression it guards against.
"""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import ContentHouse, ContentPromotionPath
from gyrinx.content.models.promotion import (
    DEFAULT_PROMOTIONS,
    PROMOTION_TARGET_CATEGORIES,
    seed_default_promotions,
)
from gyrinx.models import FighterCategoryChoices


def _make_path(**kwargs):
    defaults = dict(
        name="Promote to Specialist",
        kind=ContentPromotionPath.Kind.RELABEL,
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.SPECIALIST,
        xp_cost=6,
    )
    defaults.update(kwargs)
    return ContentPromotionPath(**defaults)


# --- G1: readable __str__ -------------------------------------------------------------


def test_str_renders_name_and_transition():
    path = _make_path(name="Promote to Specialist")
    # Catches: admin changelist rendering by object id/ctype instead of a readable label (cf #1942).
    assert str(path) == "Promote to Specialist (GANGER → SPECIALIST)"


def test_str_renders_chosen_type_for_target_driven_paths():
    path = _make_path(
        name="Promotion",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category=FighterCategoryChoices.PROSPECT,
        to_category="",
    )
    # Catches: blank to_category (target decides the category) rendering as "... → )".
    assert str(path) == "Promotion (PROSPECT → chosen type)"


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
def test_clean_relabel_requires_to_category():
    path = _make_path(kind=ContentPromotionPath.Kind.RELABEL, to_category="")
    # Catches: a relabel with no destination — nothing for category_override to apply.
    with pytest.raises(ValidationError) as exc:
        path.full_clean()
    assert "to_category" in exc.value.message_dict


@pytest.mark.django_db
def test_clean_type_change_allows_blank_to_category():
    # Family C paths can promote to targets of differing categories (e.g. Badzone Hive Scum
    # → a Ganger type); the chosen target's category decides, so to_category may be blank.
    path = _make_path(
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category=FighterCategoryChoices.PROSPECT,
        to_category="",
    )
    path.full_clean()  # must not raise


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bad_rolls",
    [[1], [13], [2, "2"], [2, 2], [True]],
    ids=["below-range", "above-range", "non-int", "duplicate", "bool"],
)
def test_clean_rejects_invalid_rolls(bad_rolls):
    path = _make_path(rolls=bad_rolls)
    # Catches: admin-authored rolls JSON that Phase 2's 2d6 prefill would mis-handle.
    with pytest.raises(ValidationError) as exc:
        path.full_clean()
    assert "rolls" in exc.value.message_dict


@pytest.mark.django_db
def test_clean_allows_valid_promotion():
    # A sanity anchor so the reject-tests above can't pass by clean() always raising.
    _make_path(rolls=[2, 12]).full_clean()  # must not raise


@pytest.mark.django_db
def test_clean_target_rejects_stash_and_vehicle(make_content_fighter, content_house):
    stash_cf = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.STASH,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    vehicle_cf = make_content_fighter(
        type="Ridgehauler",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=100,
    )
    ok_cf = make_content_fighter(
        type="Forge Boss",
        category=FighterCategoryChoices.CHAMPION,
        house=content_house,
        base_cost=125,
    )
    # Catches: a promotion turning a fighter into the stash or a vehicle (identity guardrail).
    with pytest.raises(ValidationError):
        ContentPromotionPath.clean_target(stash_cf)
    with pytest.raises(ValidationError):
        ContentPromotionPath.clean_target(vehicle_cf)
    ContentPromotionPath.clean_target(ok_cf)  # must not raise


# --- G4: rank ordering (data source for the reversal hierarchy) -----------------------


@pytest.mark.django_db
def test_default_ordering_is_by_rank():
    champion = ContentPromotionPath.objects.create(
        name="Promote to Champion",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category=FighterCategoryChoices.SPECIALIST,
        to_category=FighterCategoryChoices.CHAMPION,
        rank=2,
        xp_cost=12,
    )
    specialist = ContentPromotionPath.objects.create(
        name="Promote to Specialist",
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.SPECIALIST,
        rank=1,
        xp_cost=6,
    )
    # Catches: the reversal hierarchy (Champion > Specialist) losing its data ordering.
    assert list(ContentPromotionPath.objects.all()) == [specialist, champion]


# --- targets: the "pick Forge Boss or Stimmer" case -----------------------------------


@pytest.mark.django_db
def test_type_change_holds_multiple_targets(make_content_fighter, content_house):
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
        advancements_threshold=5,
        timing=ContentPromotionPath.Timing.DOWNTIME,
    )
    path.targets.set([forge_boss, stimmer])
    # Catches: dual-Champion paths collapsing to a single target (the original #1467 symptom).
    assert set(path.targets.values_list("type", flat=True)) == {"Forge Boss", "Stimmer"}


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

    path = ContentPromotionPath.objects.create(
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
def test_is_available_matches_source_fighter(
    make_content_fighter, make_list, make_list_fighter, content_house
):
    wrecker_cf = make_content_fighter(
        type="Wrecker",
        category=FighterCategoryChoices.PROSPECT,
        house=content_house,
        base_cost=45,
    )
    other_prospect_cf = make_content_fighter(
        type="Neotek",
        category=FighterCategoryChoices.PROSPECT,
        house=content_house,
        base_cost=45,
    )
    lst = make_list("Gang")
    wrecker = make_list_fighter(lst, "W", content_fighter=wrecker_cf)
    other = make_list_fighter(lst, "N", content_fighter=other_prospect_cf)

    path = ContentPromotionPath.objects.create(
        name="Promotion (Road Sergeant or Arms Master)",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category=FighterCategoryChoices.PROSPECT,
        source_fighter=wrecker_cf,
        xp_cost=0,
    )
    # Catches: a house-specific path keyed to one fighter type leaking to every fighter of the
    # same category (both are Prospects; only the Wrecker should see this path).
    assert path.is_available_to_fighter(wrecker) is True
    assert path.is_available_to_fighter(other) is False


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
    path = ContentPromotionPath.objects.create(
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


# --- admin form: rolls as checkboxes, not raw JSON --------------------------------------


def _admin_form_data(**overrides):
    data = {
        "name": "Promote to Specialist",
        "kind": "RELABEL",
        "from_category": "GANGER",
        "to_category": "SPECIALIST",
        "rank": 1,
        "xp_cost": 6,
        "cost_increase": 20,
        "grants_skill": "primary_random",
        "timing": "POST_BATTLE",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_admin_form_rolls_checkboxes_round_trip():
    from django import forms as django_forms

    from gyrinx.content.admin import ContentPromotionPathAdminForm

    # Browsers post checkbox values as strings, in DOM order.
    form = ContentPromotionPathAdminForm(data=_admin_form_data(rolls=["12", "2"]))
    assert form.is_valid(), form.errors
    obj = form.save()
    # Catches: regression to a raw JSON text input — that would store the literal
    # strings (which the model's _clean_rolls rejects) or require hand-typed "[2, 12]".
    assert obj.rolls == [2, 12]  # coerced to ints, stored sorted

    # Editing an existing row pre-ticks the saved totals, via a checkbox widget.
    form2 = ContentPromotionPathAdminForm(instance=obj)
    assert form2.fields["rolls"].initial == [2, 12]
    assert isinstance(form2.fields["rolls"].widget, django_forms.CheckboxSelectMultiple)


@pytest.mark.django_db
def test_admin_form_rolls_rejects_out_of_range_value():
    from gyrinx.content.admin import ContentPromotionPathAdminForm

    form = ContentPromotionPathAdminForm(data=_admin_form_data(rolls=["13"]))
    # Catches: the field losing its 2..12 choice bound (13 is not a 2d6 total).
    assert not form.is_valid()
    assert "rolls" in form.errors


# --- admin lookups: catalog fighters only -----------------------------------------------


@pytest.mark.django_db
def test_admin_fighter_lookups_exclude_pack_fighters(
    admin_client, make_pack_fighter, make_content_fighter, content_house
):
    make_content_fighter(
        type="Catalog Gunner",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    make_pack_fighter(house=content_house, type="Packed Gunner")

    # Catches: user content-pack fighters leaking into the source/targets lookups of
    # globally-visible catalog promotion paths (ContentFighterAdmin serves the
    # autocomplete from all_content(); limit_choices_to must filter it back down).
    for field_name in ("source_fighter", "targets"):
        response = admin_client.get(
            "/admin/autocomplete/",
            {
                "app_label": "content",
                "model_name": "contentpromotionpath",
                "field_name": field_name,
                "term": "Gunner",
            },
        )
        assert response.status_code == 200, field_name
        texts = [r["text"] for r in response.json()["results"]]
        assert any("Catalog Gunner" in t for t in texts), (field_name, texts)
        assert not any("Packed Gunner" in t for t in texts), (field_name, texts)


# --- G6 / seed: the default data --------------------------------------------------------


@pytest.mark.django_db
def test_seed_creates_the_two_default_paths_with_exact_values():
    seed_default_promotions(ContentPromotionPath)

    by_pair = {
        (p.from_category, p.to_category): p for p in ContentPromotionPath.objects.all()
    }
    assert len(by_pair) == 2

    specialist = by_pair[("GANGER", "SPECIALIST")]
    assert specialist.name == "Promote to Specialist"
    assert specialist.kind == ContentPromotionPath.Kind.RELABEL
    assert specialist.rank == 1
    assert specialist.xp_cost == 6
    assert specialist.cost_increase == 20
    assert specialist.rolls == [2, 12]  # rules: a roll of 2 or 12 promotes
    assert specialist.timing == ContentPromotionPath.Timing.POST_BATTLE

    champion = by_pair[("SPECIALIST", "CHAMPION")]
    assert champion.name == "Promote to Champion"
    assert champion.kind == ContentPromotionPath.Kind.TYPE_CHANGE
    assert champion.rank == 2
    assert champion.xp_cost == 12
    assert champion.cost_increase == 40
    assert champion.targets.count() == 0  # per-house champion types are admin-authored

    # Idempotent — re-running never duplicates.
    seed_default_promotions(ContentPromotionPath)
    assert ContentPromotionPath.objects.count() == 2


# --- A4 (linchpin): seed must preserve the original hardcoded promotion values ----------


def test_seed_preserves_original_hardcoded_values():
    """The seed must keep the exact values of the promotions it replaced.

    Until Phase 2, this invariant compared the seed against the (since-deleted) hardcoded
    ``ADVANCEMENT_CONFIGS`` entries; now the expectations are frozen literals here —
    Ganger→Specialist 6 XP +20¢ on 2 or 12, Specialist→Champion 12 XP +40¢, per the
    rulebook's Gaining Experience tables. Editing a seed number breaks cost-neutrality
    for existing gangs and must fail loudly.
    """
    by_legacy = {e["_legacy_choice"]: e for e in DEFAULT_PROMOTIONS}
    assert set(by_legacy) == {"skill_promote_specialist", "skill_promote_champion"}

    specialist = by_legacy["skill_promote_specialist"]
    assert specialist["xp_cost"] == 6
    assert specialist["cost_increase"] == 20
    assert specialist["rolls"] == [2, 12]

    champion = by_legacy["skill_promote_champion"]
    assert champion["xp_cost"] == 12
    assert champion["cost_increase"] == 40


# --- seed ↔ migration snapshot: the frozen inline SEED must match today's constant ------


def test_migration_snapshot_agrees_with_live_seed_constant():
    """Migration 0181 inlines a frozen snapshot of DEFAULT_PROMOTIONS (no app imports, for
    reproducibility). The live constant may gain NEW rows in later phases — but for the rows
    the migration seeded, the two must agree, else fresh installs (migrated) and the test
    suite (seeded from the constant) see different data for the same promotion.
    """
    import importlib.util
    import pathlib

    from gyrinx.content.migrations import __path__ as migrations_path

    spec_path = pathlib.Path(migrations_path[0]) / "0181_seed_promotion_paths.py"
    spec = importlib.util.spec_from_file_location("seed_migration", spec_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    live_by_pair = {
        (e["from_category"], e["to_category"]): e for e in DEFAULT_PROMOTIONS
    }
    for frozen in module.SEED:
        live = live_by_pair[(frozen["from_category"], frozen["to_category"])]
        for key, frozen_value in frozen.items():
            # TextChoices members compare equal to their raw string values.
            assert live[key] == frozen_value, (
                f"{frozen['from_category']}→{frozen['to_category']}: {key}"
            )


# --- drift guard: content's promotable targets stay aligned with core's override list ---


def test_promotion_targets_match_core_allowed_overrides():
    """PROMOTION_TARGET_CATEGORIES mirrors core's ALLOWED_CATEGORY_OVERRIDES (content can't
    import core, so the list is duplicated). If core changes its allow-list and this mirror
    isn't updated, a promotion could target a category that fails validation at apply time.
    """
    from gyrinx.core.models.list._common import ALLOWED_CATEGORY_OVERRIDES

    assert list(PROMOTION_TARGET_CATEGORIES) == list(ALLOWED_CATEGORY_OVERRIDES)


# --- #1468: any-category sources + dynamic targets --------------------------------------


def test_clean_rejects_dynamic_targets_on_relabel():
    path = ContentPromotionPath(
        name="Bad relabel",
        kind=ContentPromotionPath.Kind.RELABEL,
        from_category=FighterCategoryChoices.GANGER,
        to_category=FighterCategoryChoices.SPECIALIST,
        dynamic_targets_category=FighterCategoryChoices.LEADER,
        xp_cost=0,
    )
    with pytest.raises(ValidationError, match="type changes"):
        path.clean()


def test_clean_rejects_blank_source_on_relabel():
    """'Relabel anyone' has no meaning — blank sources are a type-change affordance."""
    path = ContentPromotionPath(
        name="Anyone to Specialist",
        kind=ContentPromotionPath.Kind.RELABEL,
        from_category="",
        to_category=FighterCategoryChoices.SPECIALIST,
        xp_cost=0,
    )
    with pytest.raises(ValidationError, match="source category"):
        path.clean()


def test_clean_rejects_non_overridable_dynamic_target_category():
    path = ContentPromotionPath(
        name="Bad dynamic",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category="",
        dynamic_targets_category=FighterCategoryChoices.STASH,
        xp_cost=0,
    )
    with pytest.raises(ValidationError, match="Dynamic target category"):
        path.clean()


def test_str_renders_any_for_blank_source():
    """Catches: the admin changelist rendering '( → LEADER)' for any-category paths."""
    path = ContentPromotionPath(
        name="Nominate as leader",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category="",
        to_category=FighterCategoryChoices.LEADER,
        xp_cost=0,
    )
    assert str(path) == "Nominate as leader (Any → LEADER)"


def test_leader_migration_snapshot_agrees_with_live_seed_constant():
    """Migration 0187 inlines a frozen snapshot of LEADER_NOMINATION (no app imports).
    The two must agree, else fresh installs (migrated) and the test suite (seeded from
    the constant via the leader_nomination_path fixture) see different data."""
    import importlib.util
    import pathlib

    from gyrinx.content.migrations import __path__ as migrations_path
    from gyrinx.content.models.promotion import LEADER_NOMINATION

    spec_path = pathlib.Path(migrations_path[0]) / "0187_seed_leader_nomination.py"
    spec = importlib.util.spec_from_file_location("leader_seed_migration", spec_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for key, frozen_value in module.SEED.items():
        # TextChoices members compare equal to their raw string values.
        assert LEADER_NOMINATION[key] == frozen_value, key


def test_effective_to_category_falls_back_to_dynamic_category():
    """A dynamic path without an explicit to_category still knows its effective
    category — every dynamically-resolved target shares it by construction. Catches:
    the availability guard treating such a path as category-less."""
    path = ContentPromotionPath(
        name="Dynamic no explicit to",
        kind=ContentPromotionPath.Kind.TYPE_CHANGE,
        from_category="",
        dynamic_targets_category=FighterCategoryChoices.LEADER,
        xp_cost=0,
    )
    assert path.effective_to_category() == FighterCategoryChoices.LEADER
