import pytest

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_model_card
from n26.library.forms import generate_form
from n26.library.models import (
    Action,
    ChangesStat,
    Modifier,
    OffersChoice,
    Picklist,
    RankTable,
    Slot,
    SlotType,
)
from n26.library.specs import specs
from n26.library.standard_content import (
    FIGHTER_ADVANCEMENTS,
    FIGHTER_RANK_THRESHOLDS,
    STANDARD_CONTENT,
)
from n26.tests.sandbox.actions import (
    assign,
    choose,
    create_profile,
    found_gang,
    hire,
    set_statline,
)

pytestmark = pytest.mark.django_db


def test_fighter_action_content_is_complete_and_idempotent():
    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    content.create()
    assert content.check() == (42, 42)
    table = Picklist.objects.get(name="Fighter advancement table")
    assert table.dice == "2d6"
    assert table.roll_selects == "threshold"
    assert list(
        table.members.values_list(
            "pickable__name", "roll_low", "pickable__rating_contribution"
        )
    ) == list(FIGHTER_ADVANCEMENTS)
    ranks = RankTable.objects.get(name="Standard fighter ranks")
    assert (
        tuple(ranks.thresholds.values_list("threshold", flat=True))
        == FIGHTER_RANK_THRESHOLDS
    )
    actions = {
        action.name: action
        for action in Action.objects.prefetch_related("use_price", "outcomes")
    }
    assert set(actions) >= {
        "Suit Evolution",
        "Suit Maintenance",
        "Recruitment augmentation",
        "Advancement",
    }
    assert [
        (p.resource, p.payer, p.amount, str(p.counter) if p.counter else None)
        for p in actions["Suit Evolution"].use_price.all()
    ] == [("counter", "fighter", 4, "Kill Count")]
    assert [
        (p.resource, p.payer, p.amount)
        for p in actions["Suit Maintenance"].use_price.all()
    ] == [("credits", "gang", 100)]
    assert actions["Recruitment augmentation"].recruitment_allowance_rule_id
    assert actions["Advancement"].rank_allowance_rule.counter == ranks.counter
    assert {
        name: (action.timing, [member.outcome.name for member in action.outcomes.all()])
        for name, action in actions.items()
        if name
        in {
            "Suit Evolution",
            "Suit Maintenance",
            "Recruitment augmentation",
            "Advancement",
        }
    } == {
        "Suit Evolution": (
            "post_cycle",
            ["Hunting Rig Augmentation", "Clear glitches"],
        ),
        "Suit Maintenance": ("post_cycle", ["Clear glitches"]),
        "Recruitment augmentation": (
            "recruitment",
            ["Hunting Rig Augmentation"],
        ),
        "Advancement": ("post_cycle", ["Advancement"]),
    }
    offers = {
        modifier.name.removeprefix("Advancement: "): modifier.effect
        for modifier in Modifier.objects.filter(name__startswith="Advancement: ")
        if isinstance(modifier.effect, OffersChoice)
    }
    assert {
        (name, offer.mode, offer.from_section.name if offer.from_section else "any")
        for name, offer in offers.items()
    } == {
        ("Random Primary skill", "random", "Primary"),
        ("Select Primary skill", "select", "Primary"),
        ("Random Secondary skill", "random", "Secondary"),
        ("Select Secondary skill", "select", "Secondary"),
        ("Select any skill", "select", "any"),
    }
    assert not Action.objects.filter(name__icontains="Power Boost").exists()
    changes = {
        modifier.name.removeprefix("Advancement: "): modifier.effect
        for modifier in Modifier.objects.filter(name__startswith="Advancement: ")
        if isinstance(modifier.effect, ChangesStat)
    }
    characteristic_names = {
        name
        for name, _, _ in FIGHTER_ADVANCEMENTS
        if not name.startswith(("Random", "Select"))
    }
    assert set(changes) == characteristic_names
    assert {
        (name, effect.stat.full_name, effect.mode, effect.amount)
        for name, effect in changes.items()
    } == {(name, name, ChangesStat.Mode.IMPROVE, 1) for name in characteristic_names}
    advancement_slot = Slot.objects.get(name="Advancement")
    assert advancement_slot.hidden is True
    clear = actions["Suit Maintenance"].outcomes.get().outcome.apply_changes
    assert [
        change.remove_picks.slot_type.name
        for change in clear.changes.select_related("remove_picks")
        if change.remove_picks_id
    ] == ["Spyrer Hunting Rig Glitch"]


def test_homebrew_names_do_not_stand_in_for_standard_fighter_content(default_pack):
    from n26.library.models import (
        Collection,
        CollectionSection,
        ContentPack,
        Counter,
        Pickable,
        PicklistMember,
        RankThreshold,
    )

    homebrew = ContentPack.objects.create(name="Homebrew", slug="homebrew-actions")
    skill_collection = Collection.objects.create(pack=homebrew, name="Skills & Powers")
    for position, name in enumerate(("Primary", "Secondary")):
        CollectionSection.objects.create(
            pack=homebrew,
            collection=skill_collection,
            name=name,
            position=position,
        )
    advancement_type = SlotType.objects.create(pack=homebrew, name="Advancement")
    table = Picklist.objects.create(
        pack=homebrew,
        name="Fighter advancement table",
        slot_type=advancement_type,
        dice="d6",
        roll_selects="threshold",
    )
    for position, (name, roll, _) in enumerate(FIGHTER_ADVANCEMENTS):
        pick = Pickable.objects.create(
            pack=homebrew,
            name=name,
            slot_type=advancement_type,
            rating_contribution=99,
        )
        PicklistMember.objects.create(
            picklist=table,
            pickable=pick,
            position=position,
            roll_low=roll,
            roll_high=roll,
        )
    xp = Counter.objects.create(pack=homebrew, name="XP")
    ranks = RankTable.objects.create(
        pack=homebrew, name="Standard fighter ranks", counter=xp
    )
    for threshold in FIGHTER_RANK_THRESHOLDS:
        RankThreshold.objects.create(rank_table=ranks, threshold=threshold)
    for name in (
        "Suit Evolution",
        "Suit Maintenance",
        "Recruitment augmentation",
        "Advancement",
    ):
        Action.objects.create(
            pack=homebrew, name=name, timing=Action.Timing.RECRUITMENT
        )

    content = STANDARD_CONTENT["fighter-actions"]
    assert content.check() == (0, 42)
    content.create()
    content.create()

    assert content.check() == (42, 42)
    assert Picklist.objects.get(pack=homebrew, name=table.name).dice == "d6"
    assert (
        Pickable.objects.get(pack=homebrew, name="Leadership").rating_contribution == 99
    )
    default_table = Picklist.objects.get(
        pack=default_pack, name="Fighter advancement table"
    )
    assert default_table.dice == "2d6"
    assert default_table.members.count() == len(FIGHTER_ADVANCEMENTS)
    assert (
        Pickable.objects.get(pack=default_pack, name="Leadership").rating_contribution
        == 5
    )
    assert RankTable.objects.get(
        pack=default_pack, name="Standard fighter ranks"
    ).thresholds.count() == len(FIGHTER_RANK_THRESHOLDS)
    assert (
        Action.objects.filter(
            pack=default_pack,
            name__in=(
                "Suit Evolution",
                "Suit Maintenance",
                "Recruitment augmentation",
                "Advancement",
            ),
        ).count()
        == 4
    )
    offers = Modifier.objects.filter(
        pack=default_pack,
        name__in=(
            "Advancement: Random Primary skill",
            "Advancement: Select Primary skill",
            "Advancement: Random Secondary skill",
            "Advancement: Select Secondary skill",
        ),
    )
    assert {offer.effect.from_section.collection_id for offer in offers} == {
        Collection.objects.get(pack=default_pack, name="Skills & Powers").pk
    }


def test_reseeding_repairs_the_old_broad_glitch_cleanup():
    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    clear = Action.objects.get(name="Suit Maintenance").outcomes.get().outcome
    removal = clear.apply_changes.changes.get(remove_picks__isnull=False).remove_picks
    removal.slot_type = SlotType.objects.get(name="Augmentation")
    removal.save(update_fields=["slot_type", "modified"])

    content.create()

    removal.refresh_from_db()
    assert removal.slot_type.name == "Spyrer Hunting Rig Glitch"
    assert clear.apply_changes.changes.filter(remove_picks__isnull=False).count() == 1


@pytest.mark.parametrize(
    ("result", "field", "before", "after"),
    [("Movement", "movement", "5", '6"'), ("Weapon Skill", "weapon_skill", "4+", "3+")],
)
def test_seeded_characteristic_results_change_the_drawn_card(
    owner, gang_type, result, field, before, after
):
    from n26.library.models import ProfileType

    STANDARD_CONTENT["fighter-actions"].create()
    profile = create_profile(
        f"{result} candidate", ProfileType.objects.get(name="Fighter"), gang_type
    )
    set_statline(profile, **{field: before})
    gang = found_gang(f"{result} test", gang_type, owner=owner, budget=1000)
    fighter = hire(gang, profile, "Candidate", paid=0)
    slot = Slot.objects.get(name="Advancement")
    anchor = assign(slot, miniature=fighter)
    choose(anchor, slot.picklist.members.get(pickable__name=result).pickable, slot=slot)

    card = build_card(fighter, with_statlines=True)
    computed = compute(
        card, build_modifier_index(node.assignable for node in card.all_nodes())
    )
    drawn = build_model_card(fighter, card=card, computed=computed)
    values = {cell.full_name: cell.value for cell in drawn.statline.cells}
    assert values[result] == after
    assert drawn.choices == []


def test_choice_authoring_form_preserves_random_mode_and_select_default():
    form_class = generate_form(specs()["ef_offers_choice"])
    assert "mode" in form_class().fields
    random = specs()["ef_offers_choice"].compile({"model": "skill", "mode": "random"})
    selected = specs()["ef_offers_choice"].compile({"model": "skill"})
    assert random.mode == OffersChoice.Mode.RANDOM
    assert selected.mode == OffersChoice.Mode.SELECT
