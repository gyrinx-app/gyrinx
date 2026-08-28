from django.db import models
from django.db.models.functions import Lower

from n26.library.models.assignable import (
    Assignable,
    Counter,
    Family,
    Optioned,
    Subtype,
    exclusive_has_no_trade_points,
)
from n26.library.models.base import Content
from n26.library.models.collection import Collection
from n26.library.models.gang_type import GangType
from n26.library.models.statline import StatlineType
from n26.library.offers import Suggest

#: The two Types the rules know. Everything else a model might be
#: called is a Subtype.
TYPE_NAMES = ("Fighter", "Vehicle")


class ProfileType(Content):
    """A model's Type: **Fighter or Vehicle**, and nothing else.

    The rules are closed about this: every model has a Type, which is
    Fighter or Vehicle, plus any number of Subtypes (Beast, Flying,
    Leader, Specialist and the rest). Ganger, Champion and Leader are
    *Subtypes*, and a Chaos Spawn or a sentry gun is a Fighter or a
    Vehicle like anything else. So there are exactly two of these rows,
    created as standard content and never authored by hand.

    Each fixes the shape of the statline its profiles carry.
    """

    family = Family.FOUNDATION

    name = models.CharField(
        max_length=200,
        choices=[(name, name) for name in TYPE_NAMES],
        help_text="Fighter or Vehicle — the rules know no other Type.",
    )
    statline_type = models.ForeignKey(
        StatlineType, on_delete=models.PROTECT, related_name="profile_types"
    )

    class Meta:
        verbose_name = "profile type"
        verbose_name_plural = "profile types"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack", Lower("name"), name="profile_type_unique_per_pack"
            ),
            # The closed set, enforced where it cannot be argued with:
            # everything else a model might be called is a Subtype.
            models.CheckConstraint(
                condition=models.Q(name__in=TYPE_NAMES),
                name="profile_type_is_fighter_or_vehicle",
            ),
        ]

    def __str__(self):
        return self.name


class Profile(Content, Assignable, Optioned):
    """A fighter or vehicle entry — the thing a model is hired as.

    Assignable: hiring is a gang-hosted assignment naming a profile, and
    a Venator's Legacy is a second profile assignment on the model. Its
    statline shape follows its profile type, and it takes option sets.
    """

    family = Family.GANG

    #: What a new profile usually comes with, offered on its create
    #: page as a quick build-out (library/offers.py). The class
    #: reference is the validation: a kind that does not exist cannot
    #: be written down, and one built-ins cannot name fails the guard.
    #: Blank on the form means skipped.
    SUGGESTED_BUILT_INS = (
        Suggest("Starting XP", Counter, named="XP"),
        Suggest("Equipment list", Collection),
        Suggest("Subtypes", Subtype, many=True),
    )

    # The mixin's ``price`` is the fighter alone, before any sets —
    # additive with the sets' prices, so put the whole number here or on
    # ``built_ins``, whichever reads better. Hiring also buys the sets,
    # which is why ``reference_price`` composes rather than reads. One
    # number, not two: a price beside a rating on the same entry would
    # make one of them a lie.

    profile_type = models.ForeignKey(
        ProfileType, on_delete=models.PROTECT, related_name="profiles"
    )
    gang_type = models.ForeignKey(
        GangType,
        on_delete=models.PROTECT,
        related_name="profiles",
        help_text="The kind of gang this profile belongs to. Every profile has one.",
    )
    hireable = models.BooleanField(
        default=True,
        verbose_name="Offered for hire",
        help_text=(
            "Untick for a model nobody hires directly — one that arrives "
            "when something else brings it, a pet behind its collar. An "
            "“adds a model” effect can still bring it in."
        ),
    )
    # ``built_ins`` comes from the Assignable mixin: coming with things is
    # a property of anything acquirable, not of profiles alone. A mount
    # comes with its guns; a gang type comes with its equipment list.

    class Meta:
        verbose_name = "profile"
        verbose_name_plural = "profiles"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                "pack",
                Lower("name"),
                Lower("qualifier"),
                name="profile_unique_per_pack",
            ),
            exclusive_has_no_trade_points("profile"),
        ]

    def __str__(self):
        return self.name

    @property
    def statline_type(self):
        """The statline shape this profile's type calls for."""
        return self.profile_type.statline_type

    @property
    def has_statline(self):
        return hasattr(self, "statline")

    def stats(self):
        """``{field_name: formatted value}``, or ``{}`` if none is defined."""
        return self.statline.as_dict() if self.has_statline else {}
