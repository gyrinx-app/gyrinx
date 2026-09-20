import pytest

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_model_card
from n26.library import authoring
from n26.library.forms import generate_form
from n26.library.models import (
    Action,
    ChangesStat,
    Modifier,
    OffersChoice,
    Pickable,
    Picklist,
    PicklistMember,
    RankTable,
    Skill,
    Slot,
    SlotType,
    Stat,
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
        ProfileType,
        RankThreshold,
        Stat,
        StatlineType,
    )

    homebrew = ContentPack.objects.create(name="Homebrew", slug="homebrew-actions")
    Stat.objects.create(
        pack=homebrew,
        short_name="M",
        full_name="Movement",
    )
    model_shape = StatlineType.objects.create(pack=homebrew, name="Model")
    ProfileType.objects.create(pack=homebrew, name="Fighter", statline_type=model_shape)
    ProfileType.objects.create(pack=homebrew, name="Vehicle", statline_type=model_shape)
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
    assert Stat.objects.filter(pack=default_pack, full_name="Movement").exists()
    assert StatlineType.objects.filter(pack=default_pack, name="Model").exists()
    assert ProfileType.objects.filter(pack=default_pack, name="Fighter").exists()
    assert ProfileType.objects.filter(pack=default_pack, name="Vehicle").exists()
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


def test_qualified_skills_collection_is_not_used_as_the_standard_collection(
    default_pack,
):
    from n26.library.models import Collection, Counter

    custom = Collection.objects.create(
        pack=default_pack,
        name="Skills & Powers",
        qualifier="Custom",
    )
    advancement_type = SlotType.objects.create(pack=default_pack, name="Advancement")
    table = Picklist.objects.create(
        pack=default_pack,
        name="Fighter advancement table",
        slot_type=advancement_type,
        dice="2d6",
        roll_selects="threshold",
    )
    custom_slot = Slot.objects.create(
        pack=default_pack,
        name="Advancement",
        qualifier="Custom",
        slot_type=advancement_type,
        picklist=table,
        min_picks=3,
        max_picks=3,
    )
    lower_standard_slot = Slot.objects.create(
        pack=default_pack,
        name="advancement",
        qualifier="",
        slot_type=advancement_type,
        picklist=table,
        min_picks=4,
        max_picks=4,
    )
    xp = Counter.objects.create(pack=default_pack, name="XP", qualifier="")
    custom_ranks = RankTable.objects.create(
        pack=default_pack,
        name="Standard fighter ranks",
        qualifier="Custom",
        counter=xp,
    )

    content = STANDARD_CONTENT["fighter-actions"]
    assert content.status() == "incomplete"
    content.create()

    standard = Collection.objects.get(
        pack=default_pack,
        name="Skills & Powers",
        qualifier="",
    )
    assert standard != custom
    assert custom.sections.count() == 0
    assert custom.selectors.count() == 0
    assert (
        Slot.objects.get(pack=default_pack, name__iexact="Advancement", qualifier="")
        == lower_standard_slot
    )
    lower_standard_slot.refresh_from_db()
    assert (lower_standard_slot.min_picks, lower_standard_slot.max_picks) == (1, 1)
    assert lower_standard_slot.hidden is True
    custom_slot.refresh_from_db()
    assert (custom_slot.min_picks, custom_slot.max_picks) == (3, 3)
    assert (
        RankTable.objects.get(
            pack=default_pack, name="Standard fighter ranks", qualifier=""
        )
        != custom_ranks
    )
    assert custom_ranks.thresholds.count() == 0
    assert content.status() == "complete"


def test_qualified_skill_section_does_not_satisfy_fighter_action_completeness(
    default_pack,
):
    from n26.library.models import Collection, CollectionSection

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    custom = Collection.objects.create(
        pack=default_pack,
        name="Skills & Powers",
        qualifier="Custom",
    )
    wrong_primary = CollectionSection.objects.create(
        pack=default_pack,
        collection=custom,
        name="Primary",
    )
    result = Pickable.objects.get(name="Random Primary skill", qualifier="")
    offer = result.modifiers.get().effect
    offer.from_section = wrong_primary
    offer.save(update_fields=["from_section"])

    assert content.status() == "incomplete"
    content.create()

    repaired = result.modifiers.get().effect
    assert repaired.from_section.collection.qualifier == ""
    assert content.status() == "complete"


@pytest.mark.parametrize("result_name", ["Movement", "Random Primary skill"])
def test_homebrew_modifier_does_not_satisfy_advancement_completeness(
    default_pack,
    result_name,
):
    from n26.library.models import ContentPack

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    result = Pickable.objects.get(name=result_name, qualifier="")
    modifier = result.modifiers.get()
    homebrew = ContentPack.objects.create(
        name=f"Homebrew {result_name}",
        slug=f"homebrew-{result_name.lower().replace(' ', '-')}",
    )
    Modifier.objects.filter(pk=modifier.pk).update(pack=homebrew)

    assert content.status() == "incomplete"
    content.create()

    assert result.modifiers.filter(pack=default_pack).exists()
    assert content.status() == "complete"


def test_same_named_picklist_for_another_slot_type_is_left_untouched(default_pack):
    other_type = SlotType.objects.create(pack=default_pack, name="Other advancement")
    other_table = Picklist.objects.create(
        pack=default_pack,
        slot_type=other_type,
        name="Fighter advancement table",
        dice="d6",
        roll_selects="threshold",
    )

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()

    other_table.refresh_from_db()
    assert other_table.slot_type == other_type
    assert other_table.dice == "d6"
    assert content.status() == "complete"
    assert (
        Picklist.objects.filter(
            pack=default_pack, name="Fighter advancement table"
        ).count()
        == 2
    )


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


def test_reseeding_repairs_missing_action_and_result_links():
    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    action = Action.objects.get(name="Suit Maintenance", qualifier="")
    action.outcomes.all().delete()
    result = (
        Picklist.objects.get(name="Fighter advancement table")
        .members.get(pickable__name="Movement")
        .pickable
    )
    result.modifiers.clear()

    assert content.status() == "incomplete"
    content.create()

    assert content.status() == "complete"
    assert action.outcomes.get().outcome.name == "Clear glitches"
    assert isinstance(result.modifiers.get().effect, ChangesStat)


def test_reseeding_replaces_a_same_named_homebrew_action_outcome():
    from n26.library.models import ActionOutcome, ContentPack

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    action = Action.objects.get(name="Advancement", qualifier="")
    correct = action.outcomes.get().outcome
    homebrew = ContentPack.objects.create(name="Homebrew", slug="homebrew-outcome")
    wrong = authoring.create_outcome(
        "Advancement",
        authoring.apply_changes(),
        pack=homebrew,
    )
    action.outcomes.all().delete()
    ActionOutcome.objects.create(action=action, outcome=wrong)

    assert content.status() == "incomplete"
    content.create()

    linked = action.outcomes.get().outcome
    assert linked == correct
    assert linked.pack != homebrew
    assert content.status() == "complete"


def test_reseeding_repairs_the_advancement_rank_counter():
    from n26.library.models import Counter

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    action = Action.objects.get(name="Advancement", qualifier="")
    action.rank_allowance_rule.counter = Counter.objects.create(name="Wrong counter")
    action.rank_allowance_rule.save(update_fields=["counter", "modified"])

    assert content.status() == "incomplete"
    content.create()

    action.refresh_from_db()
    assert action.rank_allowance_rule.counter.name == "XP"
    assert content.status() == "complete"


def test_reseeding_repairs_the_rank_table_to_default_pack_xp(default_pack):
    from n26.library.models import ContentPack, Counter

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    homebrew = ContentPack.objects.create(name="Homebrew", slug="homebrew-xp")
    ranks = RankTable.objects.get(name="Standard fighter ranks")
    ranks.counter = Counter.objects.create(pack=homebrew, name="XP")
    ranks.save(update_fields=["counter", "modified"])

    assert content.status() == "incomplete"
    content.create()

    ranks.refresh_from_db()
    assert ranks.counter.pack == default_pack
    assert content.status() == "complete"


def test_reseeding_replaces_the_wrong_advancement_allowance_kind():
    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    action = Action.objects.get(name="Advancement", qualifier="")
    action.rank_allowance_rule = None
    action.recruitment_allowance_rule = authoring.recruitment_allowance_rule()
    action.save(
        update_fields=[
            "rank_allowance_rule",
            "recruitment_allowance_rule",
            "modified",
        ]
    )

    assert content.status() == "incomplete"
    content.create()

    action.refresh_from_db()
    assert action.recruitment_allowance_rule_id is None
    assert action.rank_allowance_rule.counter.name == "XP"
    assert content.status() == "complete"


def test_reseeding_repairs_advancement_modifiers_to_bearer_scope():
    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    result = (
        Picklist.objects.get(name="Fighter advancement table")
        .members.get(pickable__name="Random Primary skill")
        .pickable
    )
    modifier = result.modifiers.get()
    modifier.targets_miniature.reach = modifier.targets_miniature.Reach.EVERY_MODEL
    modifier.targets_miniature.save(update_fields=["reach"])

    assert content.status() == "incomplete"
    content.create()

    modifier.refresh_from_db()
    assert modifier.targets_miniature.reach == (modifier.targets_miniature.Reach.BEARER)
    assert content.status() == "complete"


def test_reseeding_repairs_the_advancement_outcome_operation():
    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    action = Action.objects.get(name="Advancement", qualifier="")
    outcome = action.outcomes.get().outcome
    wrong = authoring.apply_changes(
        authoring.remove_picks(SlotType.objects.get(name="Augmentation"))
    )
    type(outcome).objects.filter(pk=outcome.pk).update(
        resolve_advancement=None,
        apply_changes=wrong,
    )

    assert content.status() == "incomplete"
    content.create()

    outcome.refresh_from_db()
    assert outcome.resolve_advancement.slot == Slot.objects.get(name="Advancement")
    assert content.status() == "complete"


def test_reseeding_repairs_a_skill_offer_for_the_wrong_kind():
    from django.contrib.contenttypes.models import ContentType

    from n26.library.models import Subtype

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    result = (
        Picklist.objects.get(name="Fighter advancement table")
        .members.get(pickable__name="Random Primary skill")
        .pickable
    )
    modifier = result.modifiers.get()
    offer = modifier.effect
    offer.of_kind = ContentType.objects.get_for_model(Subtype)
    offer.save(update_fields=["of_kind"])

    assert content.status() == "incomplete"
    content.create()

    modifier.refresh_from_db()
    assert isinstance(modifier.effect, OffersChoice)
    assert modifier.effect.of_kind.model_class() is Skill
    assert content.status() == "complete"


def test_clearing_imported_content_preserves_advancement_modifiers():
    from n26.library.ingest import clear_imported

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()

    clear_imported()

    assert content.status() == "complete"
    assert Modifier.objects.filter(
        library_pickable_set__listed_on__picklist__name=("Fighter advancement table")
    ).count() == len(FIGHTER_ADVANCEMENTS)


def test_clearing_imported_content_does_not_spare_a_same_named_other_table(
    default_pack,
):
    from n26.library.ingest import clear_imported

    content = STANDARD_CONTENT["fighter-actions"]
    content.create()
    other_type = SlotType.objects.create(pack=default_pack, name="Other advancement")
    other_table = Picklist.objects.create(
        pack=default_pack,
        slot_type=other_type,
        name="Fighter advancement table",
    )
    other_pick = Pickable.objects.create(
        pack=default_pack,
        name="Imported lookalike result",
        slot_type=other_type,
    )
    PicklistMember.objects.create(picklist=other_table, pickable=other_pick)
    lookalike = authoring.modifier(
        "Imported lookalike advancement",
        authoring.targets_model(),
        authoring.ef_changes_stat(
            Stat.objects.get(pack=default_pack, full_name="Movement"),
            mode="improve",
            amount=1,
        ),
    )
    other_pick.modifiers.add(lookalike)

    clear_imported()

    assert not Modifier.objects.filter(pk=lookalike.pk).exists()
    assert content.status() == "complete"


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
