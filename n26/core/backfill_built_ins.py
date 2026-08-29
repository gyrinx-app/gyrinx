"""Fighters catch up with the built-ins they were hired without.

Two things went unrecorded before provenance existed. A grant a set
materialised carried no note of which member it came from or which
carrier it came for — only the shape it was written in: reason
``DEFAULT``, caused by the carrier. And a member added to a set after
a hire never reached the models already hired from it. This module
settles both, one gang at a time, inside one ``operation(gang)``:

1. **Tag.** Every grant in the gang written in the legacy shape is
   matched to the member it must have come from — a member of one of
   its carrier's sets (``sets_for``: the carrier's built-ins and the
   option sets it took) naming the same assignable — and the pair is
   written onto it. A weapon's own free firing lines are not set
   members and are left alone. Where a set names the same assignable
   more than once (twin guns), the carrier's untagged copies are paired
   to the members newest copy first, one per member, as many as the
   set has members and provenance does not already account for; a copy
   left over stays untagged and is counted as ambiguous. A copy whose
   member is gone stays untagged and is counted.

   Tagging writes provenance and nothing else — no ledger entry, no
   event, no repin. It changes how a grant is recorded, not what the
   owner has, which is the one exception ``n26/core/CLAUDE.md`` allows
   to the rule that player data is written only by an operation's
   verbs: it moves no money, and the gang is proved to reconcile after.

2. **Catch up.** Every live carrier in the gang is reconciled against
   its sets, so a member added after the hire arrives now, recorded as
   caught up. Where the carrier's model — or the gang, for a
   gang-hosted carrier — already holds a live copy of the member's
   thing that arrived some other way (bought, rewarded, edited in,
   granted by a modifier), the member is skipped and the carrier named
   in the outcome: the backfill never creates a duplicate. That is a
   backfill-only reading; live propagation judges by provenance alone
   (``n26.core.builtins``).

Both steps are idempotent, so a gang may be walked again: a second
pass tags nothing and grants nothing. Archived grants are tagged like
live ones, because a grant the owner sold or removed is settled and
must never be granted again — the tag is what says so.
"""

from dataclasses import dataclass, field

from django.db.models import Count, Q

from n26.core.builtins import plan_defaults, sets_for
from n26.core.models import Assignment, Gang, LedgerEvent, Reason
from n26.core.operations import operation
from n26.library.models.defaults import DEFAULT_ASSIGNABLE_FIELDS

#: The kinds a legacy grant may be: what a set can name, less a
#: weapon's firing lines, which are its own free profiles rather than
#: members of any set.
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
        _catch_up_carriers(op, gang, outcome)
    return outcome


# --- tagging -------------------------------------------------------------


def _tag_legacy_grants(gang, outcome):
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
            sets_by_carrier[carrier_id] = sets_for(carrier)
        candidates = [
            member
            for default_set in sets_by_carrier[carrier_id]
            for member in default_set.members.filter(**{f"{kind}_id": assignable_id})
        ]
        if not candidates:
            outcome.unmatched += len(copies)
            continue
        # A member already accounted for by a tagged copy — live or
        # archived — is settled; only the rest may claim a legacy copy.
        accounted = set(
            Assignment.objects.filter(
                materialised_from__in=candidates, materialised_for=carrier
            ).values_list("materialised_from_id", flat=True)
        )
        open_members = [member for member in candidates if member.pk not in accounted]
        for copy, member in zip(copies, open_members, strict=False):
            copy.materialised_from = member
            copy.materialised_for = carrier
            copy.save(
                update_fields=["materialised_from", "materialised_for", "modified"]
            )
            outcome.tagged += 1
        left_over = max(len(copies) - len(open_members), 0)
        already = min(left_over, len(accounted))
        outcome.already += already
        outcome.ambiguous += left_over - already


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
    """The gang's live carriers: every assignment whose thing has
    built-ins, and every one that took an option set. A removal is
    machinery, not a use; an archived carrier is settled history."""
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
    """A sentence saying how the carrier's model — or the gang, for a
    gang-hosted carrier — already holds the member's thing without a
    set having materialised it, or None where it does not.

    For most kinds that is a live copy with no provenance and a reason
    other than ``DEFAULT``: bought, rewarded, edited in, or granted by
    a modifier. Ammo is read differently: a firing line stacked on a
    gun with no provenance is held whatever its reason, because a
    weapon's own free lines and a legacy ammo grant are written in the
    same shape, and a second line under the same gun is the duplicate
    this check exists to prevent. The gun is the one the member would
    land under — its named gun member's live copy for this carrier, or
    any live gun of that weapon on the host where it names none.
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
    """How many grants in unarchived gangs still carry no provenance,
    by what they name. One query."""
    counted = Assignment.objects.filter(
        gang_root__archived=False, **LEGACY_SHAPE
    ).aggregate(
        **{
            kind: Count("pk", filter=Q(**{f"{kind}__isnull": False}))
            for kind in DEFAULT_ASSIGNABLE_FIELDS
        }
    )
    return {kind: counted[kind] for kind in DEFAULT_ASSIGNABLE_FIELDS}
