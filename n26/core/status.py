"""Model statuses shared by content effects and player-data operations.

Keep the enum independent of models so library effects can reference it.
Lasting-effect results may update the model's stored status.
"""

from django.db import models


class Status(models.TextChoices):
    ACTIVE = "active", "Active"
    #: Misses the rest of the campaign cycle; cleared by Clean House.
    RECOVERY = "recovery", "In Recovery"
    #: Dies unless a Doc treats them this cycle. A vehicle reads
    #: "Critically Damaged", which is not fatal — the Chop Shop repairs it.
    CRITICAL = "critical", "Critically Injured"
    #: Taken by the enemy; the Escape table decides what happens next.
    CAPTURED = "captured", "Captured"
    #: Held for D6×10 credits, paid now or the model dies.
    RANSOMED = "ransomed", "Ransomed"
    DEAD = "dead", "Dead"


#: The statuses under which a model takes no part in a battle.
OUT_OF_ACTION = frozenset(
    {Status.RECOVERY, Status.CRITICAL, Status.CAPTURED, Status.RANSOMED, Status.DEAD}
)


def label_for(status, vehicle=False):
    """The status as a card says it — a vehicle is damaged, not injured."""
    if status == Status.CRITICAL and vehicle:
        return "Critically Damaged"
    if status == Status.DEAD and vehicle:
        return "Destroyed"
    return Status(status).label


def explains(status, vehicle=False):
    """One sentence under the badge: what the status means for the model."""
    match Status(status):
        case Status.ACTIVE:
            return "Takes part in battles as normal."
        case Status.RECOVERY:
            return "Misses the rest of the cycle. Cleared by Clean House."
        case Status.CRITICAL:
            if vehicle:
                return "Cannot fight until repaired at the Chop Shop."
            return "Dies unless the Doc treats them this cycle."
        case Status.CAPTURED:
            return "Roll on the Escape table."
        case Status.RANSOMED:
            return "Pay the ransom now, or they die."
        case Status.DEAD:
            return "Adds nothing to the gang's rating."
    return ""


#: Neutral for Active, warning for Recovery, and danger for other statuses.
#: Dead cards also fade.
_COLOURS = {
    Status.ACTIVE: "ink",
    Status.RECOVERY: "amber",
    Status.CRITICAL: "red",
    Status.CAPTURED: "red",
    Status.RANSOMED: "red",
    Status.DEAD: "red",
}


def status_colour(status):
    """The badge colour for a status. An empty status reads as active."""
    return _COLOURS[Status(status or Status.ACTIVE)]
