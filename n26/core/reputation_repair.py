"""Raise active campaign Reputation balances to their authored minimum."""

from dataclasses import dataclass

from django.conf import settings
from django.db.models import F

from n26.core.models import Assignment, CampaignMembership, Gang
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library.core_campaign import REPUTATION


@dataclass(frozen=True)
class Plan:
    gangs: tuple
    problems: tuple = ()

    @property
    def nothing_here(self):
        return not self.gangs

    @property
    def ok(self):
        return not self.problems

    def preview(self):
        return [
            f"{len(self.gangs)} gang(s) have campaign reputation below its minimum.",
            *(
                f"{name}: raise recorded reputation to its minimum."
                for _, name in self.gangs
            ),
        ]


def candidates(gang=None):
    carriers = CampaignMembership.objects.filter(
        left=None, campaign__archived=False
    ).values("type_carrier_id")
    assignments = Assignment.objects.filter(
        archived=False,
        removes=False,
        gang_root__archived=False,
        caused_by_id__in=carriers,
        counter__pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG,
        counter__name__iexact=REPUTATION,
        counter__qualifier="",
        counter_value__value__lt=F("counter__minimum"),
    ).select_related("counter", "counter_value")
    return assignments.filter(gang_root=gang) if gang is not None else assignments


def find():
    return Plan(
        tuple(
            candidates()
            .order_by("gang_root_id")
            .values_list("gang_root_id", "gang_root__name")
            .distinct()
        )
    )


def apply_one(gang_id):
    gang = Gang.objects.filter(pk=gang_id, archived=False).first()
    if gang is None:
        return f"Gang {gang_id}: skipped because it was archived or removed."
    repaired = 0
    with operation(gang, actor=None) as op:
        assert_reconciled(gang)
        for assignment in candidates(gang):
            op.tally(
                assignment,
                assignment.counter.minimum - assignment.counter_value.value,
                note="Reputation minimum correction",
            )
            repaired += 1
        assert_reconciled(gang)
    return f"{gang}: corrected {repaired} reputation counter(s)."
