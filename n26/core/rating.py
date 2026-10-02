"""A model's recorded rating, split into the hire and grouped additions."""

from dataclasses import dataclass

from n26.core.status import Status


@dataclass(frozen=True)
class RatingContribution:
    label: str
    rating: int

    @property
    def display_rating(self):
        return f"{self.rating:+}¢"


@dataclass(frozen=True)
class RatingReceipt:
    default_rating: int
    override_delta: int
    contributions: tuple[RatingContribution, ...]
    total: int

    @property
    def display_override(self):
        return f"{self.override_delta:+}¢"

    def popover_props(self, name):
        return {
            "name": name,
            "rating": self.total,
            "receipt": {
                "defaultRating": self.default_rating,
                "overrideDelta": self.override_delta,
                "contributions": [
                    {"label": line.label, "rating": line.rating}
                    for line in self.contributions
                ],
                "total": self.total,
            },
        }


def build_rating_receipt(assignments, *, status=""):
    """Fold loaded ledger entries only; library prices and grants add nothing."""
    default = override = 0
    grouped = {}
    for assignment in assignments:
        if assignment.removes:
            continue
        rating = assignment.rating
        if (
            assignment.gang_id
            and assignment.profile_id
            and assignment.miniature_root_id
        ):
            override = getattr(assignment, "base_rating_override_delta", 0)
            default = rating - override
            continue
        if not rating:
            continue
        if getattr(assignment, "rating_from_advancement", False):
            label = "Advancements"
        elif any(
            getattr(assignment, f"{kind}_id")
            for kind in ("weapon", "weapon_profile", "weapon_accessory", "trait")
        ):
            label = "Weapons"
        elif assignment.wargear_id:
            label = "Gear"
        elif assignment.skill_id:
            label = "Skills"
        elif assignment.power_id:
            label = "Powers"
        else:
            label = "Other additions"
        grouped[label] = grouped.get(label, 0) + rating
    contributions = [
        RatingContribution(label, grouped[label])
        for label in (
            "Weapons",
            "Gear",
            "Skills",
            "Powers",
            "Advancements",
            "Other additions",
        )
        if grouped.get(label)
    ]
    total = default + override + sum(line.rating for line in contributions)
    if status == Status.DEAD and total:
        contributions.append(RatingContribution("Dead model", -total))
        total = 0
    return RatingReceipt(default, override, tuple(contributions), total)


def read_rating_receipt(miniature):
    """One narrow assignment read for a receipt refreshed after an edit."""
    from n26.core.card import rating_rows

    return build_rating_receipt(rating_rows(miniature), status=miniature.status)
