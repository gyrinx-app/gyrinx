"""Outcomes and fixed costs for recorded Ganger advancement rolls."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError

from n23.content.models import ContentPromotionPath
from n23.models import FighterCategoryChoices

GRANTS_SKILL_LABELS = {
    "primary_random": "Random Primary Skill",
    "primary_chosen": "Chosen Primary Skill",
    "secondary_random": "Random Secondary Skill",
    "secondary_chosen": "Chosen Secondary Skill",
    "any_random": "Random Skill (Any Set)",
}


def promotion_choice_key(path) -> str:
    return f"promotion_{path.id}"


def promotion_choice_label(path) -> str:
    suffix = GRANTS_SKILL_LABELS.get(path.grants_skill)
    return f"{path.name} ({suffix})" if suffix else path.name


@dataclass(frozen=True)
class AdvancementRoll:
    choices: tuple[tuple[str, str], ...]
    cost_increase: int
    xp_cost: int = 6

    def validate_choice(self, choice):
        if choice not in dict(self.choices):
            raise ValidationError("Select one of the advancements for this roll.")


# Each band offers a choice; the individual stat purchase prices do not apply.
STAT_ROLL_BANDS = (
    (
        (3, 4),
        (("weapon_skill", "Weapon skill"), ("ballistic_skill", "Ballistic skill")),
        20,
    ),
    ((5, 6), (("strength", "Strength"), ("toughness", "Toughness")), 30),
    ((7,), (("movement", "Movement"), ("initiative", "Initiative")), 10),
    ((8, 9), (("willpower", "Willpower"), ("intelligence", "Intelligence")), 5),
    ((10, 11), (("leadership", "Leadership"), ("cool", "Cool")), 10),
)


def resolve_advancement_roll(total, fighter=None) -> AdvancementRoll:
    paths = ContentPromotionPath.objects.filter(rolls__contains=total).prefetch_related(
        "targets", "restricted_to_houses"
    )
    for path in paths:
        if fighter and not path.is_available_to_fighter(fighter):
            continue
        return AdvancementRoll(
            choices=((promotion_choice_key(path), promotion_choice_label(path)),),
            cost_increase=path.cost_increase,
        )

    for totals, stats, cost_increase in STAT_ROLL_BANDS:
        if total in totals:
            return AdvancementRoll(
                choices=tuple((f"stat_{key}", label) for key, label in stats),
                cost_increase=cost_increase,
            )

    if total in (2, 12):
        raise ValidationError("No promotion is available for this roll.")

    raise ValidationError("The advancement roll must total between 2 and 12.")


def validate_advancement_roll(action, fighter) -> AdvancementRoll:
    if (
        action.list_id != fighter.list_id
        or action.campaign_id != fighter.list.campaign_id
        or action.user_id != fighter.list.owner_id
    ):
        raise ValidationError("This advancement roll belongs to another gang.")
    if fighter.get_category() not in (
        FighterCategoryChoices.GANGER,
        FighterCategoryChoices.EXOTIC_BEAST,
    ):
        raise ValidationError(
            "Only gangers and exotic beasts can roll for advancements."
        )
    if (
        action.dice_count != 2
        or len(action.dice_results) != 2
        or any(type(die) is not int or not 1 <= die <= 6 for die in action.dice_results)
        or sum(action.dice_results) != action.dice_total
    ):
        raise ValidationError(
            "This action does not contain a valid 2D6 advancement roll."
        )
    return resolve_advancement_roll(action.dice_total, fighter)
