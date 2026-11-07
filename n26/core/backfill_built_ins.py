"""Repair built-in provenance and reconcile missing grants, one gang per operation.

First, match untagged DEFAULT assignments caused by a carrier to its set
members. Claim option sets newest selection first, then built-ins. Pair
newest copies to matching members one at a time, subtracting already tagged
copies. Exclude free weapon profiles, which are not set members. Report
unmatched or ambiguous copies without tagging them.

Tagging changes only provenance. Then reconcile live carriers, skipping a
carrier's own missing member when its host already holds that content from
another source. Nested grants created during catch-up use ordinary provenance
rules rather than this backfill-only duplicate avoidance.

Tag archived grants too so removed equipment remains satisfied. Each gang
must reconcile before commit; repeating the backfill creates no new grants.
"""

from dataclasses import dataclass, field

from django.db.models import Count, Q

from n26.core.builtins import plan_defaults
from n26.core.models import Assignment, Gang, LedgerEvent, Reason
from n26.core.operations import operation
from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS

#: Set member kinds eligible for provenance repair, excluding included
#: weapon profiles.
TAGGABLE_KINDS = tuple(
    kind for kind in DEFAULT_ASSIGNABLE_FIELDS if kind != "weapon_profile"
)

#: Grants written before provenance existed, in the shape that says so.
LEGACY_SHAPE = {
    "materialised_from__isnull": True,
    "ledger_entry__reason": Reason.DEFAULT,
    "removes": False,
}


@dataclass
class GangOutcome:
    """What the backfill did to one gang, in counts, plus the carriers
    it left holding a member's thing some other way."""

    gang_id: str
    #: Legacy grants given their provenance.
    tagged: int = 0
    #: Legacy grants whose member is already accounted for by a tagged
    #: copy — a live copy for the pair stood, so no second was tagged.
    already: int = 0
    #: Legacy grants with more copies than the set has members.
    ambiguous: int = 0
    #: Legacy grants whose member no set of their carrier names.
    unmatched: int = 0
    #: Members materialised as caught up.
    granted: int = 0
    #: Members reconcile could not place — ammo with no gun.
    skipped: int = 0
    #: Sentences, one per member skipped because the carrier's model
    #: already holds the thing another way.
    held_another_way: list = field(default_factory=list)

    def counts(self):
        return {
            "tagged": self.tagged,
            "already": self.already,
            "ambiguous": self.ambiguous,
            "unmatched": self.unmatched,
            "granted": self.granted,
            "skipped": self.skipped,
            "held_another_way": len(self.held_another_way),
        }


def catch_up(gang_id):
    """Settle one gang: tag its legacy grants, then catch every live
    carrier up with its sets. One operation, committing on its own."""
    gang = Gang.objects.get(pk=gang_id)
    outcome = GangOutcome(gang_id=str(gang_id))
    with operation(gang, actor=None) as op:
        _tag_legacy_grants(gang, outcome)
        # Uncaused grants have no carrier to match. Count them as unmatched so
        # the report accounts for every untagged assignment.
        outcome.unmatched += (
            Assignment.objects.filter(
                gang_root=gang, caused_by__isnull=True, **LEGACY_SHAPE
            )
            .filter(_of_kinds(TAGGABLE_KINDS))
            .count()
        )
        _catch_up_carriers(op, gang, outcome)
    return outcome


# --- tagging -------------------------------------------------------------


def _tag_legacy_grants(gang, outcome):
    """Match untagged grants by carrier and content, claiming copies set by set.

    Claim selected options newest selection first, then built-ins, matching their
    reverse materialisation order. Within each set use newest copies first so
    later option removal finds the copies that option originally supplied.
    """
    legacy = (
        Assignment.objects.filter(
            gang_root=gang, caused_by__isnull=False, **LEGACY_SHAPE
        )
        .filter(_of_kinds(TAGGABLE_KINDS))
        .select_related("caused_by")
        .order_by("-pk")
    )
    groups = {}
    for copy in legacy:
        kind = _kind_of(copy)
        groups.setdefault(
            (copy.caused_by_id, kind, getattr(copy, f"{kind}_id")), []
        ).append(copy)

    sets_by_carrier = {}
    for (carrier_id, kind, assignable_id), copies in groups.items():
        carrier = copies[0].caused_by
        if carrier_id not in sets_by_carrier:
            sets_by_carrier[carrier_id] = _sets_in_claiming_order(carrier)
        remaining = list(copies)
        named = False
        accounted = 0
        for default_set in sets_by_carrier[carrier_id]:
            # Match live members first so archived twins do not consume the copies
            # needed to prevent duplicate catch-up grants.
            members = list(
                default_set.members.filter(**{f"{kind}_id": assignable_id}).order_by(
                    "archived", "pk"
                )
            )
            if not members:
                continue
            named = True
            # A member already accounted for by a tagged copy — live or
            # archived — is settled; only the rest may claim a legacy copy.
            settled = set(
                Assignment.objects.filter(
                    materialised_from__in=members, materialised_for=carrier
                ).values_list("materialised_from_id", flat=True)
            )
            accounted += len(settled)
            open_members = [member for member in members if member.pk not in settled]
            for copy, member in zip(remaining, open_members, strict=False):
                copy.materialised_from = member
                copy.materialised_for = carrier
                copy.save(
                    update_fields=["materialised_from", "materialised_for", "modified"]
                )
                outcome.tagged += 1
            remaining = remaining[len(open_members) :]
        if not named:
            outcome.unmatched += len(copies)
            continue
        already = min(len(remaining), accounted)
        outcome.already += already
        outcome.ambiguous += len(remaining) - already


def _sets_in_claiming_order(carrier):
    """Return options in reverse recorded order, then built-ins, for newest-first pairing."""
    chosen = carrier.chosen_options.select_related("default_set").order_by("-pk")
    ordered = [taken.default_set for taken in chosen]
    built = getattr(carrier.assignable, "built_ins", None)
    if built is not None and built.pk not in {s.pk for s in ordered}:
        ordered.append(built)
    return ordered


def _of_kinds(kinds):
    holds = Q()
    for kind in kinds:
        holds |= Q(**{f"{kind}__isnull": False})
    return holds


def _kind_of(assignment):
    for kind in TAGGABLE_KINDS:
        if getattr(assignment, f"{kind}_id") is not None:
            return kind
    raise ValueError(f"{assignment} names nothing a set can grant.")


# --- catching up ---------------------------------------------------------


def _catch_up_carriers(op, gang, outcome):
    for carrier in _carriers_in(gang):
        # The founding is gang-hosted and about no model, so its grants
        # land on the gang — the same split hire makes.
        hosted_on_gang = (
            carrier.miniature_root_id is None and carrier.gang_id is not None
        )
        host_gang = carrier.gang if hosted_on_gang else None
        omit = []
        for member in plan_defaults(carrier).missing:
            held = _held_another_way(member, carrier, host_gang)
            if held:
                omit.append(member.pk)
                outcome.held_another_way.append(held)
        result = op.reconcile_defaults(
            carrier,
            gang=host_gang,
            strict=False,
            event_kind=LedgerEvent.Kind.CAUGHT_UP,
            omit=omit,
        )
        outcome.granted += len(result.created)
        outcome.skipped += len(result.skipped) - len(omit)


def _carriers_in(gang):
    """Find live, non-removal assignments with built-ins or recorded selected sets."""
    holds = Q(chosen_options__isnull=False)
    for kind in Assignment.ASSIGNABLE_FIELDS:
        holds |= Q(**{f"{kind}__built_ins__isnull": False})
    return (
        Assignment.objects.filter(gang_root=gang, archived=False, removes=False)
        .filter(holds)
        .distinct()
        .order_by("pk")
    )


def _held_another_way(member, carrier, host_gang):
    """Describe existing content that should suppress a backfill grant, or return None.

    For ordinary kinds, accept untagged non-DEFAULT assignments and computed grants.
    For ammunition, any untagged matching profile counts because included profiles
    and untagged set grants share a representation. Match the intended weapon:
    its named member copy, or a matching live host weapon when unanchored.
    """
    from n26.core.builtins import copies_of
    from n26.library.models import WeaponProfile

    assignable = member.assignable
    if host_gang is not None:
        host = {"gang": host_gang}
    elif carrier.miniature_root_id is not None:
        host = {"miniature_root_id": carrier.miniature_root_id}
    else:
        return None
    who = _name_of(carrier, host_gang)

    if isinstance(assignable, WeaponProfile):
        if member.gun_member_id is not None:
            guns = copies_of(member.gun_member, carrier, include_archived=False)
        else:
            guns = Assignment.objects.filter(
                weapon=assignable.weapon, archived=False, **host
            )
        line = Assignment.objects.filter(
            weapon_profile=assignable,
            parent__in=guns,
            archived=False,
            removes=False,
            materialised_from__isnull=True,
        ).first()
        if line is None:
            return None
        return f"{who} already carries {assignable} under its {assignable.weapon}"

    held = (
        Assignment.objects.filter(
            archived=False,
            removes=False,
            materialised_from__isnull=True,
            **{Assignment.field_for(assignable): assignable},
            **host,
        )
        .exclude(ledger_entry__reason=Reason.DEFAULT)
        .exists()
    )
    return f"{who} already holds {assignable} another way" if held else None


def _name_of(carrier, host_gang):
    if host_gang is not None:
        return f"the gang ({carrier.assignable})"
    model = carrier.miniature_root
    return f"{model.name} ({carrier.assignable})" if model else str(carrier)


# --- preview -------------------------------------------------------------


def legacy_grants_by_kind():
    """Count untagged grants by assignable kind in one query, including archived gangs."""
    counted = Assignment.objects.filter(**LEGACY_SHAPE).aggregate(
        **{
            kind: Count("pk", filter=Q(**{f"{kind}__isnull": False}))
            for kind in DEFAULT_ASSIGNABLE_FIELDS
        }
    )
    return {kind: counted[kind] for kind in DEFAULT_ASSIGNABLE_FIELDS}
