"""Finish the live Spyrer tier launch without rewriting fighter history.

The Malcadon rig's empty slot is withdrawn from future acquisitions and
removed from its existing copies. Yeld Tier 2 receives its retained movement
effect and a named conditional rule. Older Hunt Masters receive the recruitment
use that hire grants now, while their paid actions remain untouched.
"""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from n26.core.access import actions_for
from n26.core.counter_tracking import is_active
from n26.core.models import ActionAllowance, Assignment, Gang, Miniature, SlotSelection
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library.models import (
    Action,
    ContentPack,
    DefaultAssignment,
    Pickable,
    Profile,
    Rule,
    Wargear,
)


class Refused(Exception):
    pass


@dataclass(frozen=True)
class Plan:
    gangs: tuple = ()
    empty_slots: int = 0
    missing_uses: int = 0
    detach_malcadon: bool = False
    repair_yeld: bool = False
    problems: tuple = ()

    @property
    def ok(self):
        return not self.problems

    @property
    def nothing_here(self):
        return not any(
            (self.gangs, self.detach_malcadon, self.repair_yeld, self.problems)
        )

    def preview(self):
        yield f"Detach the unfinished Malcadon rig slot: {'yes' if self.detach_malcadon else 'already detached'}."
        yield f"Remove {self.empty_slots} empty Malcadon slot(s) from existing gear."
        yield f"Repair Yeld rig Tier 2: {'yes' if self.repair_yeld else 'already repaired'}."
        yield f"Grant {self.missing_uses} missing Hunt Master recruitment use(s)."
        yield "Keep selected tiers, paid action uses and their history."


def _one(model, **lookups):
    rows = list(model.objects.filter(**lookups)[:2])
    if len(rows) != 1:
        raise Refused(
            f"Expected one {model._meta.verbose_name} for {lookups}; found {len(rows)}."
        )
    return rows[0]


def _content():
    pack = _one(ContentPack, slug=settings.DEFAULT_CONTENT_PACK_SLUG)
    rig = _one(Wargear, pack=pack, name__iexact="Malcadon hunting rig")
    profile = _one(Profile, pack=pack, name__iexact="Hunt Master")
    action = _one(Action, pack=pack, name__iexact="Recruitment augmentation")
    tier1 = _one(
        Pickable, pack=pack, name__iexact="Tier 1", qualifier__iexact="Yeld hunting rig"
    )
    tier2 = _one(
        Pickable, pack=pack, name__iexact="Tier 2", qualifier__iexact="Yeld hunting rig"
    )
    if rig.built_ins_id is None:
        raise Refused("The Malcadon hunting rig has no built-in set.")
    members = list(
        DefaultAssignment.objects.filter(
            default_set_id=rig.built_ins_id,
            slot__name__iexact="Malcadon hunting rig augmentation",
        )[:2]
    )
    if len(members) > 1:
        raise Refused("The Malcadon rig has more than one augmentation slot member.")
    if action.recruitment_allowance_rule_id is None:
        raise Refused("Recruitment augmentation has no recruitment allowance rule.")
    return rig, members[0] if members else None, profile, action, tier1, tier2


def _movement(tier1):
    modifiers = list(
        tier1.modifiers.filter(
            changes_stat__stat__short_name="M",
            changes_stat__mode="improve",
            changes_stat__amount=1,
        )[:2]
    )
    if len(modifiers) != 1:
        raise Refused("Yeld rig Tier 1 must have one Movement +1 modifier.")
    return modifiers[0]


def _rule(tier2):
    rules = list(
        Rule.objects.filter(
            pack=tier2.pack,
            name="Chameleonic protection",
            qualifier="Yeld hunting rig Tier 2",
        )[:2]
    )
    if len(rules) > 1:
        raise Refused("Yeld Tier 2 has duplicate chameleonic rules.")
    if (
        rules
        and rules[0].annotation
        != "Ranged attacks targeting this model suffer −1 to hit, even after it moves."
    ):
        raise Refused("Yeld Tier 2's chameleonic rule has changed.")
    return rules[0] if rules else None


def _needs_yeld(tier1, tier2):
    movement = _movement(tier1)
    rule = _rule(tier2)
    has_movement = tier2.modifiers.filter(pk=movement.pk).exists()
    has_rule = bool(
        rule and tier2.modifiers.filter(adds_assignable__rule=rule).exists()
    )
    return not (has_movement and has_rule)


def _slot_assignments(member):
    if member is None:
        return Assignment.objects.none()
    return Assignment.objects.filter(materialised_from=member, archived=False)


def _missing_hunt_masters(profile, action):
    return (
        Miniature.objects.filter(
            membership__profile=profile,
            membership__archived=False,
            membership__gang__archived=False,
        )
        .exclude(
            action_allowances__action=action,
            action_allowances__source_kind=ActionAllowance.Source.RECRUITMENT,
        )
        .distinct()
    )


def _slot_problems(rig, member, gang=None):
    if member is None:
        return ()
    slots = _slot_assignments(member)
    if gang is not None:
        slots = slots.filter(gang_root=gang)
    if slots.exclude(materialised_for__wargear=rig).exists():
        return ("A Malcadon rig slot is not attached to its original rig.",)
    if slots.exclude(
        ledger_entry__paid=0,
        ledger_entry__trade_points=0,
        ledger_entry__rating_contribution=0,
    ).exists():
        return ("A Malcadon rig slot has a non-zero ledger value.",)
    if Assignment.objects.filter(
        Q(caused_by__in=slots) | Q(chosen_for__in=slots)
    ).exists():
        return ("A Malcadon rig slot has a dependent assignment or a selected tier.",)
    if SlotSelection.objects.filter(slot_assignment__in=slots).exists():
        return ("A Malcadon rig slot appears in recorded action history.",)
    tier_history = SlotSelection.objects.filter(
        intended_pick__in=member.slot.picklist.members.values("pickable_id")
    )
    if gang is not None:
        tier_history = tier_history.filter(action_record__gang=gang)
    if tier_history.exists():
        return ("A Malcadon rig tier appears in recorded action history.",)
    if (
        gang is None
        and Assignment.objects.filter(
            slot=member.slot, archived=False, materialised_from__isnull=True
        ).exists()
    ):
        return (
            "A Malcadon augmentation slot was assigned outside the rig's built-ins.",
        )
    return ()


def find():
    try:
        rig, member, profile, action, tier1, tier2 = _content()
        problems = list(_slot_problems(rig, member))
        slots = _slot_assignments(member)
        hunters = _missing_hunt_masters(profile, action)
        missing_uses = hunters.count()
        if missing_uses and not is_active():
            problems.append(
                "Activate counter history before granting recruitment uses."
            )
        gang_ids = set(slots.values_list("gang_root_id", flat=True))
        gang_ids.update(hunters.values_list("membership__gang_id", flat=True))
        return Plan(
            gangs=tuple((pk,) for pk in sorted(gang_ids - {None}, key=str)),
            empty_slots=slots.count(),
            missing_uses=missing_uses,
            detach_malcadon=bool(member and not member.archived),
            repair_yeld=_needs_yeld(tier1, tier2),
            problems=tuple(problems),
        )
    except Refused as exc:
        return Plan(problems=(str(exc),))


@transaction.atomic
def prepare():
    """Repair library content before walking existing gangs."""
    from n26.library import authoring

    plan = find()
    if not plan.ok:
        raise Refused("; ".join(plan.problems))
    if plan.nothing_here:
        return plan
    _, member, _, _, tier1, tier2 = _content()
    if member is not None and not member.archived:
        authoring.remove_default_member(member)
    movement = _movement(tier1)
    if not tier2.modifiers.filter(pk=movement.pk).exists():
        authoring.attach_modifiers_to(tier2, [movement])
    rule = _rule(tier2)
    if rule is None:
        rule = authoring.create_rule(
            "Chameleonic protection",
            annotation="Ranged attacks targeting this model suffer −1 to hit, even after it moves.",
            qualifier="Yeld hunting rig Tier 2",
            pack=tier2.pack,
        )
    if not tier2.modifiers.filter(adds_assignable__rule=rule).exists():
        authoring.modifier(
            "Yeld rig: chameleonic protection after moving",
            authoring.targets_model(),
            authoring.ef_adds(rule),
            attach_to=tier2,
            pack=tier2.pack,
        )
    return plan


def apply_one(gang_id):
    from n26.core.allowances import grant_recruitment_allowances

    gang = Gang.objects.get(pk=gang_id)
    rig, member, profile, action, _, _ = _content()
    removed = granted = 0
    with transaction.atomic():
        with operation(gang, actor=None) as op:
            assert_reconciled(gang)
            slots = list(_slot_assignments(member).filter(gang_root=gang))
            problems = _slot_problems(rig, member, gang)
            if problems:
                raise Refused("; ".join(problems))
            for slot in slots:
                op.remove(slot, note="Unfinished Malcadon rig augmentation withdrawn.")
                removed += 1
            for fighter in _missing_hunt_masters(profile, action).filter(
                membership__gang=gang
            ):
                if action.pk not in {
                    access.action.pk for access in actions_for(fighter)
                }:
                    raise Refused(f"{fighter} has no Recruitment augmentation access.")
                allowances = grant_recruitment_allowances(op, fighter)
                if any(allowance.action_id != action.pk for allowance in allowances):
                    raise Refused(f"{fighter} has an unrelated recruitment action use.")
                if len(allowances) != 1:
                    raise Refused(f"{fighter} did not receive a recruitment use.")
                granted += len(allowances)
        gang.refresh_from_db()
        assert_reconciled(gang)
    return f"{gang}: removed {removed} empty Malcadon slot(s); granted {granted} recruitment use(s)."
