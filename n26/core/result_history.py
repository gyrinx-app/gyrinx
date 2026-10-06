"""Historical table results, separate from a model's current injuries."""

from dataclasses import dataclass
from datetime import datetime

from n26.core.models import Assignment


@dataclass(frozen=True)
class ResultRecord:
    name: str
    kind: str
    when: datetime
    removed: bool


def result_history(miniature):
    """Read a bounded history in one query, including corrected records."""
    rows = (
        Assignment.objects.filter(
            miniature_root=miniature, pickable__record_only=True, removes=False
        )
        .select_related("pickable__slot_type")
        .order_by("-created", "-pk")[:20]
    )
    return [
        ResultRecord(
            row.pickable.name, row.pickable.slot_type.name, row.created, row.archived
        )
        for row in rows
    ]
