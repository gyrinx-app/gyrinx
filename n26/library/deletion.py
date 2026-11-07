"""Plan content deletion, including eligible staff test gangs and free copies.

The shared reference reader classifies dependencies as cascading parts, eligible
test data or blocking references. Test gangs must be staff-owned and share no
campaign or battle with player gangs. A campaign is eligible only when every gang
is eligible. Preserve reusable carried modifiers; delete unshared modifiers that
reference removed content.

``remove_free_lines`` permits removal of unpaid weapon profiles without dependent
content. ``remove_built_in_copies`` permits equivalent free default copies after
authors remove every live membership granting them. Paid copies and copies with
dependants block deletion.

The preview enumerates the complete plan. ``apply`` locks and replans before
deleting eligible test gangs, campaigns and library content in one transaction. It
rejects changed plans and performs no ledger reconciliation.

Free-copy removal uses ``remove_free_lines_from`` gang by gang with reconciliation
checks. The final gang deletes unused library content once its remaining
references are gone.
"""

from collections import Counter
from dataclasses import dataclass, replace
from functools import wraps

from django.db import transaction

from n26.library.references import named, references_to


class Refused(Exception):
    """Deletion was refused with a message suitable for the task record."""


@dataclass(frozen=True)
class Holder:
    """A gang or campaign holding content affected by the deletion."""

    kind: str
    pk: str
    name: str
    owner: str
    #: Whether the gang is staff-owned; eligibility also depends on shared play.
    staff: bool
    archived: bool
    #: What it holds, in words, so a page can say why it is named.
    holds: tuple = ()
    #: Why it is not a test gang, or empty where it is.
    why_not: str = ""

    @property
    def is_test(self):
        return not self.why_not

    def as_dict(self):
        return {
            "kind": self.kind,
            "pk": str(self.pk),
            "name": self.name,
            "owner": self.owner,
            "staff": self.staff,
            "archived": self.archived,
            "holds": list(self.holds),
            "why_not": self.why_not,
        }

    @classmethod
    def from_dict(cls, held):
        return cls(
            kind=held["kind"],
            pk=held["pk"],
            name=held["name"],
            owner=held["owner"],
            staff=bool(held.get("staff")),
            archived=bool(held.get("archived")),
            holds=tuple(held.get("holds", ())),
            why_not=held.get("why_not", ""),
        )


@dataclass(frozen=True)
class Line:
    """Free profile or built-in assignments to remove from one gang's models."""

    pk: str
    name: str
    owner: str
    archived: bool
    #: The fighters' names, one per line held.
    fighters: tuple = ()
    #: The assignments that are the lines, one per fighter.
    assignment_ids: tuple = ()

    def as_dict(self):
        return {
            "pk": str(self.pk),
            "name": self.name,
            "owner": self.owner,
            "archived": self.archived,
            "fighters": list(self.fighters),
            "assignment_ids": [str(pk) for pk in self.assignment_ids],
        }

    @classmethod
    def from_dict(cls, held):
        return cls(
            pk=held["pk"],
            name=held["name"],
            owner=held["owner"],
            archived=bool(held.get("archived")),
            fighters=tuple(held.get("fighters", ())),
            assignment_ids=tuple(held.get("assignment_ids", ())),
        )


@dataclass(frozen=True)
class DeletionPlan:
    """Deletion targets, dependent records, affected holders and blocking references."""

    #: ``(model label, pk)`` of what was asked for.
    targets: tuple = ()
    #: ``(model label, pk, said)`` of every library row that goes: the
    #: targets, their parts, the modifiers nothing else carries, and
    #: what a deleted campaign owned. Parts go by cascade; everything is
    #: named so the page can promise the whole of it.
    rows: tuple = ()
    #: Records explicitly deleted, in order; their parts cascade.
    roots: tuple = ()
    #: Modifiers that go, parts first.
    modifier_ids: tuple = ()
    gangs: tuple = ()
    campaigns: tuple = ()
    #: Gangs whose fighters have a free firing line that is going, and
    #: from which it is removed first.
    lines: tuple = ()
    refusals: tuple = ()
    nothing_here: bool = False
    #: Whether built-in copies were read as removable, so a second
    #: reading asks the same question.
    removes_built_in_copies: bool = False

    @property
    def ok(self):
        return not self.refusals

    @property
    def touches_players(self):
        """Whether the plan affects gangs and must run through the recorded task runner."""
        return bool(self.gangs or self.campaigns or self.lines)

    @property
    def fighters_with_lines(self):
        return sum(len(line.fighters) for line in self.lines)

    @property
    def lines_are_built_ins(self):
        """Whether removable copies are built-ins rather than weapon profiles."""
        return self.removes_built_in_copies

    @property
    def test_gangs(self):
        return tuple(gang for gang in self.gangs if gang.is_test)

    @property
    def test_campaigns(self):
        return tuple(campaign for campaign in self.campaigns if campaign.is_test)

    def counts(self):
        """Count deleted records by each model's plural display name."""
        from django.apps import apps

        found = Counter()
        for label, _, _ in self.rows:
            found[str(apps.get_model(label)._meta.verbose_name_plural)] += 1
        return dict(found)

    def _counted(self):
        """Format each deleted kind with its count."""
        from django.apps import apps

        found = Counter()
        names = {}
        for label, _, _ in self.rows:
            meta = apps.get_model(label)._meta
            found[label] += 1
            names[label] = (str(meta.verbose_name), str(meta.verbose_name_plural))
        return sorted(
            f"{count} {names[label][0] if count == 1 else names[label][1]}"
            for label, count in found.items()
        )

    def preview(self):
        """Describe planned deletion in sentences for confirmation and the task record."""
        if self.nothing_here:
            return ["nothing to delete"]
        lines = [f"delete {said}" for said in self._counted()]
        for gang in self.test_gangs:
            state = "archived" if gang.archived else "live"
            lines.append(
                f"delete the {state} test gang “{gang.name}” ({gang.owner}), "
                f"which holds {_and(gang.holds)}"
            )
        for campaign in self.test_campaigns:
            lines.append(
                f"delete the test campaign “{campaign.name}” ({campaign.owner}), "
                f"which holds {_and(campaign.holds)}, with its own campaign "
                "type and pack"
            )
        if self.lines and self.lines_are_built_ins:
            models = self.fighters_with_lines
            gangs = len(self.lines)
            lines.append(
                f"remove it from {models} model{'' if models == 1 else 's'} on "
                f"{gangs} gang{'' if gangs == 1 else 's'} first: it came built "
                "in, so nobody paid for it"
            )
        elif self.lines:
            fighters = self.fighters_with_lines
            gangs = len(self.lines)
            lines.append(
                f"remove the firing line from {fighters} "
                f"fighter{'' if fighters == 1 else 's'} on {gangs} "
                f"gang{'' if gangs == 1 else 's'} first: nobody paid for it, "
                "the weapon brought it"
            )
        for refusal in self.refusals:
            lines.append(f"refused: {refusal}")
        return lines

    def as_record(self):
        """Serialise the confirmed plan for comparison when the task runs."""
        return {
            "targets": [[label, str(pk)] for label, pk in self.targets],
            "rows": [[label, str(pk), said] for label, pk, said in self.rows],
            "gangs": [gang.as_dict() for gang in self.gangs],
            "campaigns": [campaign.as_dict() for campaign in self.campaigns],
            "lines": [line.as_dict() for line in self.lines],
            "refusals": list(self.refusals),
            "preview": list(self.preview()),
            "removes_built_in_copies": self.removes_built_in_copies,
        }

    @classmethod
    def from_record(cls, summary):
        """Restore the confirmed plan; execution reloads additional library dependencies."""
        return cls(
            targets=tuple((label, pk) for label, pk in summary.get("targets", [])),
            rows=tuple(
                (label, pk, said) for label, pk, said in summary.get("rows", [])
            ),
            gangs=tuple(Holder.from_dict(h) for h in summary.get("gangs", [])),
            campaigns=tuple(Holder.from_dict(h) for h in summary.get("campaigns", [])),
            lines=tuple(Line.from_dict(line) for line in summary.get("lines", [])),
            refusals=tuple(summary.get("refusals", [])),
            nothing_here=not summary.get("targets"),
            removes_built_in_copies=bool(summary.get("removes_built_in_copies")),
        )

    def same_as(self, other):
        """Compare the complete affected sets from two plan readings."""
        return (
            set(self.targets) == set(other.targets)
            and {(label, str(pk)) for label, pk, _ in self.rows}
            == {(label, str(pk)) for label, pk, _ in other.rows}
            and {str(gang.pk) for gang in self.test_gangs}
            == {str(gang.pk) for gang in other.test_gangs}
            and {str(campaign.pk) for campaign in self.test_campaigns}
            == {str(campaign.pk) for campaign in other.test_campaigns}
            and {str(pk) for line in self.lines for pk in line.assignment_ids}
            == {str(pk) for line in other.lines for pk in line.assignment_ids}
            and self.refusals == other.refusals
        )


def _and(words):
    words = list(words)
    if not words:
        return "nothing"
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def _key(row):
    return (type(row)._meta.label_lower, str(row.pk))


def _said(row):
    """Use a record's authoring label when available, otherwise its reference label."""
    return getattr(row, "authoring_label", None) or named(row)


def _kind(row):
    return str(type(row)._meta.verbose_name)


def _modifier_of(part):
    """Find the modifier owning a scope, effect or condition, or return ``None``."""
    if hasattr(part, "scope_id"):
        scope = getattr(part, "scope", None)
        return _modifier_of(scope) if scope is not None else None
    try:
        return getattr(part, "modifier", None)
    except Exception:  # noqa: BLE001 — a reverse one-to-one with no row
        return None


def _carriers_of(modifier):
    from n26.library.conversion.base import carriers_of

    return [row for _, row in carriers_of(modifier)]


def _parts_of(modifier):
    """A modifier's scope and effect rows, and the scope's conditions."""
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    parts = []
    for name in (*SCOPE_FIELDS, *EFFECT_FIELDS):
        held = getattr(modifier, name, None)
        if held is not None:
            parts.append(held)
    return parts


class _Planner:
    """Traverse queued deletion candidates and classify their references recursively."""

    def __init__(self, things, remove_free_lines=False, remove_built_in_copies=False):
        self.targets = [thing for thing in things]
        self.remove_free_lines = remove_free_lines
        self.remove_built_in_copies = remove_built_in_copies
        self.doomed = {}
        self.roots = []
        self.modifiers = {}
        self.holders = {}
        self.lines = {}
        self.refusals = []
        self.queue = []
        self._gangs = {}

    # -- what goes -------------------------------------------------------

    def doom(self, row, *, root=False):
        key = _key(row)
        if key in self.doomed:
            return False
        self.doomed[key] = row
        if root:
            self.roots.append(key)
        self.queue.append(row)
        return True

    def doom_modifier(self, modifier):
        key = _key(modifier)
        if key in self.modifiers:
            return
        self.modifiers[key] = modifier
        self.doomed[key] = modifier
        # The parts are the rows that hold the references, so they are
        # what is read; the modifier rides down with them.
        for part in _parts_of(modifier):
            self.doom(part)

    # -- who holds it ----------------------------------------------------

    def hold(self, kind, row, holds):
        key = (kind, str(row.pk))
        holder = self.holders.get(key)
        if holder is None:
            holder = Holder(
                kind=kind,
                pk=str(row.pk),
                name=row.name,
                owner=row.owner.username if row.owner_id else "",
                staff=bool(row.owner_id and row.owner.is_staff),
                archived=row.archived,
            )
        if holds not in holder.holds:
            holder = replace(holder, holds=(*holder.holds, holds))
        self.holders[key] = holder

    def line(self, gang, assignment):
        """Register a model's free assignment for removal before deleting its content."""
        key = str(gang.pk)
        held = self.lines.get(key)
        if held is None:
            held = Line(
                pk=key,
                name=gang.name,
                owner=gang.owner.username if gang.owner_id else "",
                archived=gang.archived,
            )
        if str(assignment.pk) in held.assignment_ids:
            return
        fighter = assignment.miniature_root.name if assignment.miniature_root_id else ""
        self.lines[key] = replace(
            held,
            fighters=(*held.fighters, fighter),
            assignment_ids=(*held.assignment_ids, str(assignment.pk)),
        )

    def refuse(self, words):
        if words not in self.refusals:
            self.refusals.append(words)

    # -- the reading -----------------------------------------------------

    def read(self):
        from n26.library.models import ScenarioEntry, ScenarioTable

        for thing in self.targets:
            if isinstance(thing, (ScenarioTable, ScenarioEntry)):
                self.refuse(
                    "Scenario content may be referenced by saved results. Retire its table instead."
                )
            self.doom(thing, root=True)
        while self.queue:
            batch, self.queue = self.queue, []
            by_model = {}
            for row in batch:
                by_model.setdefault(type(row), []).append(row)
            for model, rows in by_model.items():
                for reference in references_to(*rows):
                    self.sort(reference, model)
        self.judge_holders()

    def sort(self, reference, thing_model):
        row = reference.row
        if _key(row) in self.doomed:
            return
        label = reference.label
        if reference.cascades and label.startswith("library."):
            # A part of the thing: it goes, and what it holds is read.
            self.doom(row)
            return
        if not reference.protects:
            # A list membership — a trait on a firing line, a modifier
            # on a carrier — is forgotten, not deleted. A column that is
            # emptied — a purchase's list line, a pick's offer — was
            # declared that way because the row it names may go while
            # the row naming it stays true. A player-side row that
            # cascades goes with the thing.
            return
        if label.startswith("n26."):
            self.sort_player_row(reference)
            return
        self.sort_library_row(reference, thing_model)

    def sort_library_row(self, reference, thing_model):
        from n26.library.models import (
            CollectionEntry,
            ContentPack,
            DefaultAssignment,
            DefaultAssignmentSet,
            InterstitialSlot,
            Option,
            PicklistMember,
        )

        row = reference.row
        what = _said(self.thing_named_by(reference, thing_model))
        modifier = _modifier_of(row) if not isinstance(row, ContentPack) else None
        if modifier is not None or _is_modifier_part(row):
            if modifier is None:
                # A part nothing holds: leftover, and it goes.
                self.doom(row)
                return
            carriers = _carriers_of(modifier)
            standing = [c for c in carriers if _key(c) not in self.doomed]
            if not standing:
                self.doom_modifier(modifier)
                return
            self.refuse(
                f"the modifier “{modifier}” names {what} and is carried by "
                f"{_and(_said(c) for c in standing[:3])}"
                + (f" and {len(standing) - 3} more" if len(standing) > 3 else "")
            )
            return
        if isinstance(row, DefaultAssignment):
            from n26.library.models import Asset, AssetTable

            if isinstance(
                self.thing_named_by(reference, thing_model), (Asset, AssetTable)
            ):
                # A possession is built in by being created, so nobody
                # authored the membership: it goes with the asset, the
                # way the delete verb takes it out.
                self.doom(row)
                return
            if self.remove_built_in_copies and row.archived:
                # Already out of its set and invisible to every surface:
                # only its copies hold it, and those are read next.
                self.doom(row, root=True)
                return
            default_set = row.default_set
            if self.set_goes(default_set):
                return
            self.refuse(
                f"the built-in set “{default_set}” brings {what}; take it "
                "out of the set first"
            )
            return
        if isinstance(row, (CollectionEntry, PicklistMember)):
            listing = getattr(row, "collection", None) or row.picklist
            self.refuse(
                f"“{listing}” lists {what}; remove that line first"
                if _key(listing) not in self.doomed
                else f"{what} is still listed on “{listing}”"
            )
            return
        if isinstance(row, InterstitialSlot):
            interstitial = row.interstitial
            if _key(interstitial) in self.doomed:
                # The screen goes too, and its attachment with it —
                # whichever of the two was read first.
                self.doom(row)
                return
            # An attachment has no page of its own: it is removed on the
            # interstitial's page, which is where an author is sent.
            self.refuse(
                f"“{interstitial}” is shown when {what} arrives; stop showing "
                "it there first"
            )
            return
        if isinstance(row, (Option, DefaultAssignmentSet)):
            self.refuse(f"the {_kind(row)} “{_said(row)}” still names {what}")
            return
        self.refuse(
            f"the {_kind(row)} “{_said(row)}” still names {what}; delete it "
            "first, or delete everything staged together"
        )

    def set_goes(self, default_set):
        """Delete a default set only when all carriers and offering options are also deleted.

        Its member records cascade with the set.
        """
        from django.apps import apps

        from n26.library.models import Option

        if _key(default_set) in self.doomed:
            return True
        for model in apps.get_app_config("library").get_models():
            if not any(f.name == "built_ins" for f in model._meta.fields):
                continue
            for carrier in model.objects.filter(built_ins=default_set):
                if _key(carrier) not in self.doomed:
                    return False
        for option in Option.objects.filter(default_set=default_set):
            if _key(option) not in self.doomed:
                return False
        self.doom(default_set)
        return True

    def thing_named_by(self, reference, thing_model):
        """Find the deletion candidate targeted by a reference."""
        target_id = getattr(reference.row, f"{reference.field}_id", None)
        key = (thing_model._meta.label_lower, str(target_id))
        return self.doomed.get(key) or reference.row

    def sort_player_row(self, reference):
        from n26.core.models.assignment import ASSIGNABLE_FIELDS

        row = reference.row
        label = reference.label
        what = _said(self.thing_named_by(reference, self.model_of(reference)))
        gang = campaign = None
        if label == "n26.assignment":
            gang = self.gang_of_assignment(row)
            if (
                self.remove_built_in_copies
                and gang is not None
                and (
                    reference.field in ASSIGNABLE_FIELDS
                    or reference.field == "materialised_from"
                )
                and not _why_not_a_built_in_copy(row)
            ):
                # A copy that is not free falls through and holds, as
                # any gang's assignment does.
                self.line(gang, row)
                return
            if (
                self.remove_free_lines
                and reference.field == "weapon_profile"
                and gang is not None
            ):
                why_not = _why_not_a_free_line(row)
                if not why_not:
                    self.line(gang, row)
                    return
                fighter = (
                    row.miniature_root.name if row.miniature_root_id else "a fighter"
                )
                self.refuse(
                    f"“{gang.name}” ({gang.owner.username if gang.owner_id else ''}) "
                    f"has {what} on {fighter} and {why_not}; refund or remove "
                    "it first"
                )
                return
        elif label == "n26.gang":
            gang = row
        elif label == "n26.campaign":
            campaign = row
        elif label == "n26.campaignasset":
            campaign = row.campaign
        elif label == "n26.chosenprofileoption":
            gang = self.gang_of_assignment(row.assignment)
        elif label == "n26.statoverride":
            gang = row.miniature.gang
        if gang is not None:
            self.hold("gang", gang, f"{what} ({_kind(self.doomed_row(reference))})")
            return
        if campaign is not None:
            self.hold(
                "campaign", campaign, f"{what} ({_kind(self.doomed_row(reference))})"
            )
            self.campaign_goes(campaign)
            return
        self.refuse(f"{_kind(row)} on no gang names {what}")

    def doomed_row(self, reference):
        return self.thing_named_by(reference, self.model_of(reference))

    def model_of(self, reference):
        return reference.row._meta.get_field(reference.field).related_model

    def gang_of_assignment(self, assignment):
        """Cache the root gang for assignment references, once per gang."""
        from n26.core.models import Gang

        gang_id = assignment.gang_root_id
        if not gang_id:
            return None
        if gang_id not in self._gangs:
            self._gangs[gang_id] = Gang.objects.select_related("owner").get(pk=gang_id)
        return self._gangs[gang_id]

    def campaign_goes(self, campaign):
        """Include a deleted campaign's additions type, pack, content and member gangs."""
        from n26.core.models import CampaignMembership
        from n26.library.models import Modifier
        from n26.library.staged import content_kinds

        if not self.doom(campaign.additions, root=True):
            return
        for model in content_kinds():
            for row in model.objects.filter(pack=campaign.pack):
                if isinstance(row, Modifier):
                    self.doom_modifier(row)
                else:
                    self.doom(row, root=True)
        self.doom(campaign.pack, root=True)
        for membership in CampaignMembership.objects.filter(
            campaign=campaign
        ).select_related("gang__owner"):
            self.hold("gang", membership.gang, f"a place in “{campaign.name}”")

    # -- who may go ------------------------------------------------------

    def judge_holders(self):
        from n26.core.models import Gang

        judged = {}
        for key, holder in self.holders.items():
            why_not = ""
            if holder.kind == "gang":
                why_not = _why_not_a_test_gang(Gang.objects.get(pk=holder.pk))
            else:
                why_not = self.why_not_a_test_campaign(holder)
            judged[key] = replace(holder, why_not=why_not)
        self.holders = judged
        for holder in self.holders.values():
            if holder.is_test:
                continue
            noun = "gang" if holder.kind == "gang" else "campaign"
            self.refuse(
                f"the {noun} “{holder.name}” ({holder.owner}) holds "
                f"{_and(holder.holds)} and is not a test {noun}: {holder.why_not}"
            )

    def why_not_a_test_campaign(self, holder):
        from n26.core.models import Campaign, CampaignMembership

        campaign = Campaign.objects.select_related("owner").get(pk=holder.pk)
        if not (campaign.owner_id and campaign.owner.is_staff):
            return "its owner is not staff"
        for membership in CampaignMembership.objects.filter(
            campaign=campaign
        ).select_related("gang__owner"):
            why_not = _why_not_a_test_gang(membership.gang)
            if why_not:
                return f"“{membership.gang.name}” is in it and {why_not}"
        return ""

    # -- the plan --------------------------------------------------------

    def plan(self):
        rows = tuple(
            (label, pk, _said(row)) for (label, pk), row in self.doomed.items()
        )
        gangs = tuple(h for h in self.holders.values() if h.kind == "gang")
        campaigns = tuple(h for h in self.holders.values() if h.kind == "campaign")
        return DeletionPlan(
            targets=tuple(_key(thing) for thing in self.targets),
            rows=rows,
            roots=tuple(self.roots),
            modifier_ids=tuple(pk for _, pk in self.modifiers),
            gangs=tuple(sorted(gangs, key=lambda h: (h.owner, h.name))),
            campaigns=tuple(sorted(campaigns, key=lambda h: (h.owner, h.name))),
            lines=tuple(
                sorted(self.lines.values(), key=lambda line: (line.owner, line.name))
            ),
            refusals=tuple(self.refusals),
            nothing_here=not self.targets,
            removes_built_in_copies=self.remove_built_in_copies,
        )


def _is_modifier_part(row):
    """Whether a row is a modifier's scope, effect or condition."""
    from n26.library.models import Modifier
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    parts = {
        Modifier._meta.get_field(name).related_model
        for name in (*SCOPE_FIELDS, *EFFECT_FIELDS)
    }
    return type(row) in parts or hasattr(row, "scope_id")


def _why_not_a_test_gang(gang):
    """Explain why a gang is ineligible for test-data deletion, or return no message.

    Eligible gangs are staff-owned and share no campaign or battle with a
    non-test gang.
    """
    from n26.core.models import Campaign, Gang

    if not (gang.owner_id and gang.owner.is_staff):
        return "its owner is not staff"
    campaigns = Campaign.objects.filter(memberships__gang=gang)
    stranger = (
        Gang.objects.filter(campaign_memberships__campaign__in=campaigns)
        .exclude(owner__is_staff=True)
        .order_by("name")
        .first()
    )
    if stranger is not None:
        return f"it is in a campaign with “{stranger.name}”, a player's gang"
    arbitrator = campaigns.exclude(owner__is_staff=True).order_by("name").first()
    if arbitrator is not None:
        return f"it is in “{arbitrator.name}”, a campaign a player runs"
    opponent = (
        Gang.objects.filter(battles__in=gang.battles.all())
        .exclude(owner__is_staff=True)
        .order_by("name")
        .first()
    )
    if opponent is not None:
        return f"it fought “{opponent.name}”, a player's gang"
    return ""


def _why_not_a_free_line(assignment):
    """Explain why an assignment is not a removable free profile or built-in copy.

    Require the original weapon or default provenance, zero recorded payments
    and rating, and no dependent content.
    """
    from n26.core.models import Assignment

    if assignment.parent_id is None and assignment.materialised_from_id is None:
        return "is not under a weapon and did not come built in"
    try:
        entry = assignment.ledger_entry
    except Assignment.ledger_entry.RelatedObjectDoesNotExist:
        return "has no ledger entry"
    if (
        entry.list_price,
        entry.discount,
        entry.paid,
        entry.trade_points,
        entry.rating_contribution,
    ) != (0, 0, 0, 0, 0):
        return "was paid for"
    if any(
        (event.credits_delta, event.trade_points_delta, event.rating_delta) != (0, 0, 0)
        for event in assignment.ledger_events.all()
    ):
        return "has moved money"
    if (
        assignment.children.exists()
        or assignment.caused.exists()
        or assignment.picks.exists()
        or assignment.chosen_options.exists()
        or Assignment.objects.filter(materialised_for=assignment).exists()
    ):
        return "has something under it"
    return ""


def _why_not_a_built_in_copy(assignment):
    """Explain why an assignment is not a removable carrier-default copy.

    Exclude optional sets chosen by the player and copies hosted on a gang or stash.
    """
    from n26.library.models import Option

    if assignment.materialised_from_id is None:
        return "did not come built in"
    if assignment.miniature_root_id is None:
        return "is not on a model"
    member = assignment.materialised_from
    if Option.objects.filter(default_set_id=member.default_set_id).exists():
        return "came with an option somebody chose"
    return _why_not_a_free_line(assignment)


def plan_deletion(things, *, remove_free_lines=False, remove_built_in_copies=False):
    """Read deletion targets and dependencies without writing.

    ``remove_free_lines`` permits eligible weapon-profile removals.
    ``remove_built_in_copies`` permits eligible default copies once every live
    membership granting them has been removed.
    """
    planner = _Planner(
        list(things),
        remove_free_lines=remove_free_lines,
        remove_built_in_copies=remove_built_in_copies,
    )
    planner.read()
    return planner.plan()


def plan_again(plan):
    """Reload the plan's targets and rebuild the current deletion plan."""
    from django.apps import apps

    things = []
    for label, pk in plan.targets:
        row = apps.get_model(label).objects.filter(pk=pk).first()
        if row is None:
            raise Refused(f"nothing was deleted: {label} {pk} is already gone")
        things.append(row)
    return plan_deletion(
        things,
        remove_free_lines=bool(plan.lines) and not plan.removes_built_in_copies,
        remove_built_in_copies=plan.removes_built_in_copies,
    )


class FreeLineRemoval:
    """The gang-by-gang runner's affected gangs, blocking problems and preview."""

    def __init__(self, plan):
        self.plan = plan

    @property
    def gangs(self):
        return [(line.pk,) for line in self.plan.lines]

    @property
    def problems(self):
        return list(self.plan.refusals)

    @property
    def nothing_here(self):
        return not self.plan.lines

    def preview(self):
        return list(self.plan.preview())


def free_line_removal(plan):
    """Rebuild the removal plan under the runner lock.

    Reject newly paid or acquired copies so execution stays within the confirmed plan.
    """
    now = plan_again(plan)
    if not now.same_as(plan):
        return FreeLineRemoval(
            replace(
                now,
                refusals=(
                    *now.refusals,
                    "what holds this line has changed since the page was "
                    "read — read it again",
                ),
            )
        )
    return FreeLineRemoval(now)


def remove_free_lines_from(gang_id, plan):
    """Remove eligible copies from one locked gang, then delete unused library content.

    Revalidate this gang's copies because deliveries may be separated in time.
    Paid copies or new dependants fail the gang. Remove zero-value events and
    entries with their assignments, reconciling before and after. The last
    processed gang deletes the library record when no references remain.
    An already deleted record makes replay a no-op.
    """
    from django.apps import apps

    from n26.core.models import Assignment, Gang
    from n26.core.reconcile import check_gang

    targets = [
        apps.get_model(label).objects.filter(pk=pk).first()
        for label, pk in plan.targets
    ]
    if all(row is None for row in targets):
        return "nothing left to remove: the line is already gone"
    with transaction.atomic():
        gang = Gang.objects.select_for_update().get(pk=gang_id)
        mine = [line for line in plan.lines if str(line.pk) == str(gang.pk)]
        if not mine:
            return f"gang {gang.name}: nothing left to remove"
        held = list(
            Assignment.objects.select_for_update()
            .filter(pk__in=list(mine[0].assignment_ids))
            .order_by("pk")
        )
        for line in held:
            why_not = (
                _why_not_a_built_in_copy(line)
                if plan.removes_built_in_copies
                else _why_not_a_free_line(line)
            )
            if why_not:
                fighter = (
                    line.miniature_root.name if line.miniature_root_id else "a fighter"
                )
                # Raise on an unremovable copy so the runner records a failed gang instead
                # of reporting success with the content still referenced.
                raise Refused(
                    f"gang {gang.name}: the line on {fighter} {why_not}; refund "
                    "or remove it first"
                )
        if not held:
            return f"gang {gang.name}: nothing left to remove"
        problems = check_gang(gang)
        if problems:
            raise Refused(
                f"gang {gang.name} did not reconcile before the removal: "
                + "; ".join(problems)
            )
        Assignment.objects.filter(pk__in=[line.pk for line in held]).delete()
        problems = check_gang(gang)
        if problems:
            raise Refused(
                f"gang {gang.name} did not reconcile after removing the line: "
                + "; ".join(problems)
            )
        n = len(held)
        if plan.removes_built_in_copies:
            said = f"gang {gang.name}: removed it from {n} model{'' if n == 1 else 's'}"
        else:
            said = f"gang {gang.name}: removed the line from {n} fighter{'' if n == 1 else 's'}"
        # The row goes with the last fighter: after this gang, nothing
        # may name it any more. Asked cheaply first; the full reading
        # only once the last copy is gone. That reading takes the
        # archived memberships the copies came from along with the row.
        unheld = [
            row
            for row in targets
            if row is not None
            and not Assignment.objects.filter(**{_column(row): row}).exists()
        ]
        if unheld:
            last = plan_deletion(
                unheld, remove_built_in_copies=plan.removes_built_in_copies
            )
            if last.ok and not last.lines and not last.touches_players:
                apply(last)
                said += f"; deleted {_and(_said(row) for row in unheld)}"
        return said


def _column(row):
    """The assignment column that names a row of this kind."""
    from django.apps import apps

    from n26.core.models.assignment import ASSIGNABLE_FIELDS

    for column, label in ASSIGNABLE_FIELDS.items():
        if isinstance(row, apps.get_model(label)):
            return column
    raise ValueError(f"a {row._meta.verbose_name} is never assigned")


def _refuse_data_errors(function):
    """Convert model refusals after the deletion transaction has rolled back."""

    @wraps(function)
    def refusing(*args, **kwargs):
        from django.core.exceptions import ValidationError
        from django.db.models import ProtectedError

        try:
            return function(*args, **kwargs)
        except ValidationError as refused:
            raise Refused(
                "nothing was deleted: " + "; ".join(refused.messages)
            ) from refused
        except ProtectedError as refused:
            raise Refused(
                "nothing was deleted: the content is still in use"
            ) from refused

    return refusing


@_refuse_data_errors
def apply(plan, actor=None):
    """Lock, replan and delete exactly the confirmed content.

    Gang assignments cascade, so lock both gangs and content before rebuilding
    the plan to exclude unconfirmed concurrent acquisitions. Reject any changed
    plan, then perform the fresh locked plan.
    """
    from django.apps import apps
    from django.db.models import ProtectedError

    from n26.core.deletion import destroy_campaign, destroy_gang
    from n26.core.models import Campaign, Gang
    from n26.library import authoring

    if plan.refusals:
        raise Refused("nothing was deleted: " + "; ".join(plan.refusals))
    if plan.lines:
        raise Refused(
            "nothing was deleted: fighters have this line, and it is removed "
            "from them gang by gang, not here"
        )
    if plan.nothing_here:
        return list(plan.preview())

    report = list(plan.preview())
    with transaction.atomic():
        list(
            Gang.objects.select_for_update()
            .filter(pk__in=[gang.pk for gang in plan.test_gangs])
            .order_by("pk")
        )
        # The campaigns as well: joining one takes a key-share lock on
        # its row, which this conflicts with, so no player can join
        # between the second reading and the delete.
        list(
            Campaign.objects.select_for_update()
            .filter(pk__in=[campaign.pk for campaign in plan.test_campaigns])
            .order_by("pk")
        )
        for label, pk in plan.targets:
            list(apps.get_model(label).objects.select_for_update().filter(pk=pk))
        now = plan_again(plan)
        if not now.same_as(plan):
            raise Refused(
                "nothing was deleted: what holds this content has changed "
                "since the page was read — read it again"
            )
        plan = now

        # Holders first: they protect everything else.
        for holder in plan.test_gangs:
            destroy_gang(Gang.objects.get(pk=holder.pk))
        for holder in plan.test_campaigns:
            campaign = Campaign.objects.get(pk=holder.pk)
            destroy_campaign(campaign)
        # Then the modifiers, parts first: the parts hold the references,
        # and the modifier cascades away with them.
        from n26.library.models import Modifier

        for modifier in Modifier.objects.filter(pk__in=plan.modifier_ids):
            for part in _parts_of(modifier):
                part.delete()
        # Then every root, in passes: a row another root protects goes
        # once that root has gone, and a pass that frees nothing is a
        # reading this plan got wrong.
        waiting = [(label, pk) for label, pk in plan.roots]
        while waiting:
            still = []
            for label, pk in waiting:
                row = apps.get_model(label).objects.filter(pk=pk).first()
                if row is None:
                    continue
                try:
                    authoring.delete_content(row)
                except ProtectedError:
                    still.append((label, pk))
            if len(still) == len(waiting):
                names = ", ".join(
                    _said(apps.get_model(label).objects.get(pk=pk))
                    for label, pk in still[:3]
                )
                raise Refused(
                    f"nothing was deleted: {names} could not be deleted — "
                    "something still names it that the plan did not see"
                )
            waiting = still
    return report
