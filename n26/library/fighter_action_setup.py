"""Prepare and attach standard fighter progression without changing player history."""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Prefetch, Q

from n26.library import authoring as a
from n26.library.fighter_action_content import BINDINGS, PROMOTIONS
from n26.library.models import (
    Action,
    AdvancementPromotion,
    Counter,
    GangType,
    Modifier,
    Pickable,
    Picklist,
    Profile,
    RankTable,
    ResolveAdvancement,
    Rule,
    Skill,
    Slot,
    SlotType,
    Subtype,
    Trait,
)
from n26.library.models.pack import get_default_pack
from n26.write_pause import guarded_write

PROGRESSION_RULE = "Fighter progression"
PROMOTION_RULE = "Promotion"
TARGET_KINDS = {"profile": Profile, "gang-type": GangType}


@dataclass(frozen=True)
class ProgressionTarget:
    target: object
    recipe: object
    excluded: str
    attached: bool


def progression_plan():
    from django.core.exceptions import ObjectDoesNotExist

    try:
        definitions = dict(progression_definitions())
    except ObjectDoesNotExist:
        definitions = {}
    result = []
    verified = {}
    scope_model = Modifier._meta.get_field("targets_miniature").related_model
    paths = []
    for relation in scope_model.CONDITIONS:
        path = f"targets_miniature__{relation}"
        paths.append(path)
        condition_model = scope_model._meta.get_field(relation).related_model
        paths.extend(
            f"{path}__{field.name}"
            for field in condition_model._meta.local_many_to_many
        )
    bindings = (
        Modifier.objects.filter(name__startswith="Fighter progression")
        .select_related(
            "targets_miniature",
            "adds_assignable__action",
            "adds_assignable__rank_table",
            "adds_assignable__slot",
            "adds_assignable__rule",
        )
        .prefetch_related(*paths)
    )
    for recipe in BINDINGS:
        targets = (
            TARGET_KINDS[recipe.kind]
            .objects.in_default_pack()
            .unarchived()
            .filter(**recipe.filters)
            .prefetch_related(Prefetch("modifiers", queryset=bindings))
        )
        if recipe.kind == "profile":
            targets = targets.select_related(
                "gang_type", "category__section", "built_ins"
            )
        excluded = {}
        for filters, reason in recipe.exclusions:
            excluded.update(
                (pk, reason)
                for pk in targets.filter(**filters)
                .prefetch_related(None)
                .values_list("pk", flat=True)
            )
        subtypes = (
            list(Subtype.objects.in_default_pack().filter(name__in=recipe.subtypes))
            if recipe.subtypes
            else None
        )
        prefix = _binding_prefix(recipe)
        for target in targets:
            attached = set()
            for modifier in target.modifiers.all():
                label = modifier.name.removeprefix(prefix)
                if modifier.name.startswith(prefix) and label in definitions:
                    key = (recipe.key, modifier.pk)
                    if key not in verified:
                        verified[key] = _modifier_matches(
                            modifier,
                            definitions[label],
                            every=recipe.kind == "gang-type",
                            subtypes=subtypes,
                        )
                    if verified[key]:
                        attached.add(label)
            result.append(
                ProgressionTarget(
                    target,
                    recipe,
                    excluded.get(target.pk, ""),
                    bool(definitions) and len(attached) == len(definitions),
                )
            )
    return result


def _binding_prefix(recipe):
    return (
        "Fighter progression: "
        if recipe.kind == "profile"
        else f"Fighter progression {recipe.key}: "
    )


def _named(model, name, **defaults):
    fields = {field.name for field in model._meta.fields}
    query = {"pack": get_default_pack(), "name__iexact": name}
    if "qualifier" in fields:
        query["qualifier"] = ""
    candidates = model.objects.filter(**query)
    if "slot_type" in defaults:
        row = candidates.filter(slot_type=defaults["slot_type"]).first()
        if row is None and candidates.exists():
            raise RuntimeError(
                f'{model._meta.verbose_name.capitalize()} "{name}" already uses another slot type.'
            )
    else:
        row = candidates.first()
    return row or model.objects.create(name=name, pack=get_default_pack(), **defaults)


def _repair(row, **expected):
    changed = [
        field for field, value in expected.items() if getattr(row, field) != value
    ]
    for field in changed:
        setattr(row, field, expected[field])
    if changed:
        row.save(update_fields=[*changed, "modified"])
    return row


def _modifier_matches(
    modifier,
    thing,
    *,
    remove=False,
    profiles=None,
    subtypes=None,
    every=False,
    with_pick=None,
):
    effect_field = "removes_assignable" if remove else "adds_assignable"
    if not modifier.targets_miniature_id or not getattr(modifier, f"{effect_field}_id"):
        return False
    effect = getattr(modifier, effect_field)
    if effect.thing != thing or getattr(effect, "with_pick_id", None) != getattr(
        with_pick, "pk", None
    ):
        return False
    scope = modifier.targets_miniature
    if scope.reach != ("every_model" if every else "bearer"):
        return False
    expected = {
        "is_profile": ("profiles", profiles),
        "has_subtypes": ("subtypes", subtypes),
    }
    for relation in scope.CONDITIONS:
        rows = list(getattr(scope, relation).all())
        field, values = expected.get(relation, (None, None))
        if values is None:
            if rows:
                return False
        elif (
            len(rows) != 1
            or rows[0].negate
            or {row.pk for row in getattr(rows[0], field).all()}
            != {row.pk for row in values}
        ):
            return False
    return True


def _give_modifier(
    name,
    thing,
    *,
    remove=False,
    profiles=None,
    subtypes=None,
    every=False,
    with_pick=None,
):
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    existing = Modifier.objects.in_default_pack().filter(name=name).first()
    if existing is not None and _modifier_matches(
        existing,
        thing,
        remove=remove,
        profiles=profiles,
        subtypes=subtypes,
        every=every,
        with_pick=with_pick,
    ):
        return existing
    conditions = []
    if profiles is not None:
        if not profiles:
            raise ValueError("An empty profile restriction would apply to everyone.")
        conditions.append(a.is_profile(*profiles))
    if subtypes is not None:
        conditions.append(a.has_subtypes(*subtypes))
    scope = (a.targets_every_model if every else a.targets_model)(*conditions)
    effect = a.ef_removes(thing) if remove else a.ef_adds(thing, with_pick=with_pick)
    if existing is None:
        return a.modifier(name, scope, effect)
    for field in (*SCOPE_FIELDS, *EFFECT_FIELDS):
        setattr(existing, field, None)
    existing.targets_miniature = scope
    setattr(existing, "removes_assignable" if remove else "adds_assignable", effect)
    existing.save(update_fields=[*SCOPE_FIELDS, *EFFECT_FIELDS, "modified"])
    return existing


def _promotion_slot(recipe):
    name = recipe.name
    kind = _named(SlotType, "Promotion", plural_name="Promotions")
    table = _named(Picklist, name, slot_type=kind)
    slot = _named(
        Slot,
        name,
        slot_type=kind,
        picklist=table,
        hidden=True,
        min_picks=1,
        max_picks=1,
    )
    _repair(slot, slot_type=kind, picklist=table, hidden=True, min_picks=1, max_picks=1)
    for position, result in enumerate(recipe.results):
        pick_name = result.name
        pick = _named(
            Pickable, pick_name, slot_type=kind, rating_contribution=result.rating
        )
        _repair(pick, slot_type=kind, rating_contribution=result.rating)
        for subtype in result.removes:
            pick.modifiers.add(
                _give_modifier(
                    f"{pick_name}: remove {subtype}",
                    _named(Subtype, subtype),
                    remove=True,
                )
            )
        for subtype in result.adds:
            pick.modifiers.add(
                _give_modifier(f"{pick_name}: add {subtype}", _named(Subtype, subtype))
            )
        skill = Skill.objects.in_default_pack().get(
            name__iexact=result.skill, qualifier=""
        )
        if result.choice_name:
            choice_type = _named(SlotType, recipe.choice_type)
            chosen = _named(Pickable, result.choice_name, slot_type=choice_type)
            if not any(
                _modifier_matches(modifier, skill)
                for modifier in chosen.modifiers.all()
            ):
                chosen.modifiers.add(
                    _give_modifier(f"{result.choice_name}: skill", skill)
                )
            choices = _named(Picklist, f"{name} choices", slot_type=choice_type)
            if not choices.members.filter(pickable=chosen).exists():
                a.add_picklist_member(choices, chosen, position=position)
            choice_slot = _named(
                Slot,
                f"{name} result",
                slot_type=choice_type,
                picklist=choices,
                hidden=True,
            )
            _repair(choice_slot, slot_type=choice_type, picklist=choices, hidden=True)
            pick.modifiers.add(
                _give_modifier(f"{pick_name}: skill", choice_slot, with_pick=chosen)
            )
        else:
            pick.modifiers.add(_give_modifier(f"{pick_name}: skill", skill))
        for filters in recipe.suppress_slots:
            for replaced in Slot.objects.in_default_pack().filter(**filters):
                pick.modifiers.add(
                    _give_modifier(
                        f"{pick_name}: replaces {replaced}", replaced, remove=True
                    )
                )
        if not table.members.filter(pickable=pick).exists():
            a.add_picklist_member(table, pick, position=position)
        for modifier in Modifier.objects.in_default_pack().filter(
            name__in=recipe.exclude_from_offers,
            offers_choice__isnull=False,
            targets_miniature__isnull=False,
        ):
            conditions = modifier.targets_miniature.has_pickable
            if not conditions.filter(negate=True, pickables=pick).exists():
                condition = conditions.create(negate=True)
                condition.pickables.add(pick)
    return slot


def _matching_profiles(filters):
    query = Q(pk__in=[])
    for match in filters:
        query |= Q(**match)
    return Profile.objects.in_default_pack().filter(query)


@guarded_write
@transaction.atomic
def prepare_fighter_progression():
    from n26.library.standard_content import STANDARD_CONTENT

    if STANDARD_CONTENT["fighter-actions"].status() != "complete":
        STANDARD_CONTENT["fighter-actions"].create()
    promotion_rule = _named(Rule, PROMOTION_RULE, staged=True)
    configured = ResolveAdvancement.objects.get(
        outcome__name="Advancement", pack=get_default_pack()
    )
    for recipe in PROMOTIONS:
        slot = _promotion_slot(recipe)
        promotion, _ = AdvancementPromotion.objects.get_or_create(
            advancement=configured,
            from_subtype=_named(Subtype, recipe.from_subtype),
            threshold=recipe.threshold,
            defaults={
                "slot": slot,
                "replaces_advancement": recipe.replaces_advancement,
                "requires_rule": promotion_rule,
            },
        )
        _repair(
            promotion,
            slot=slot,
            replaces_advancement=recipe.replaces_advancement,
            requires_rule=promotion_rule,
            keep_weapon_trait=_named(Trait, recipe.keep_weapon_trait)
            if recipe.keep_weapon_trait
            else None,
        )
        promotion.optional_profiles.set(_matching_profiles(recipe.optional_profiles))
        promotion.stash_weapons_for.set(_matching_profiles(recipe.stash_weapons_for))
    plan = progression_plan()
    for recipe in BINDINGS:
        rule = _named(Rule, recipe.preview_rule, staged=True)
        eligible = [
            row.target for row in plan if row.recipe == recipe and not row.excluded
        ]
        subtypes = [_named(Subtype, name) for name in recipe.subtypes] or None
        for label, thing in progression_definitions():
            name = f"{recipe.preview_rule} preview: {label}"
            if not eligible:
                rule.modifiers.remove(*rule.modifiers.filter(name=name))
                continue
            rule.modifiers.add(
                _give_modifier(
                    name,
                    thing,
                    every=True,
                    profiles=eligible if recipe.kind == "profile" else None,
                    subtypes=subtypes,
                )
            )
    return Rule.objects.in_default_pack().get(name=PROGRESSION_RULE, qualifier="")


def progression_definitions():
    return (
        (
            "Advancement",
            Action.objects.in_default_pack().get(name="Advancement", qualifier=""),
        ),
        (
            "Standard fighter ranks",
            RankTable.objects.in_default_pack().get(
                name="Standard fighter ranks", qualifier=""
            ),
        ),
        (
            "Advancement slot",
            Slot.objects.in_default_pack().get(name="Advancement", qualifier=""),
        ),
        (
            "Promotion",
            Rule.objects.in_default_pack().get(name=PROMOTION_RULE, qualifier=""),
        ),
    )


@guarded_write
@transaction.atomic
def attach_fighter_progression(*, staged_only=True, target_ids=None):
    prepare_fighter_progression()
    changed = 0
    shared = {}
    for row in progression_plan():
        if row.excluded or (staged_only and not row.target.staged):
            continue
        if target_ids is not None and str(row.target.pk) not in target_ids:
            continue
        recipe = row.recipe
        if recipe.key not in shared:
            subtypes = [_named(Subtype, name) for name in recipe.subtypes] or None
            shared[recipe.key] = [
                _give_modifier(
                    f"{_binding_prefix(recipe)}{label}",
                    thing,
                    every=recipe.kind == "gang-type",
                    subtypes=subtypes,
                )
                for label, thing in progression_definitions()
            ]
        row.target.modifiers.add(*shared[recipe.key])
        for name, amount in recipe.opening_counters:
            counter = Counter.objects.in_default_pack().get(name=name, qualifier="")
            if (
                row.target.built_ins_id is None
                or not row.target.built_ins.members.filter(
                    counter=counter, archived=False
                ).exists()
            ):
                a.add_built_in(row.target, counter, amount=amount)
        changed += not row.attached
    return changed
