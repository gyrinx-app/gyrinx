"""Saved crew selections and equipment snapshots, without changing the gang.

A draw is a write. It chooses a card for each eligible model before drawing
models, and saves the result under the same revision as the manual choices.
Reading or resubmitting that revision cannot roll the draw again.
"""

import random
from dataclasses import dataclass, field

from django.db.models import Q

from n26.core.battle_permissions import may_record_gang
from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.effects import compute, compute_gang
from n26.core.fields import to_ulid
from n26.core.models import Assignment, AssignmentSet, Battle, Campaign, Gang, Miniature
from n26.core.models.crew import BattleCrew, CrewMember
from n26.core.operations import Refusal
from n26.core.render import ModelCard, brought_in_by, build_model_card
from n26.core.status import Status
from n26.write_pause import guarded_write


@dataclass(frozen=True)
class CrewSelection:
    miniature_id: str
    role: str
    card_key: str = "full"
    eligibility_override: bool = False


@dataclass(frozen=True)
class CardOption:
    key: str
    name: str
    equipment_ids: tuple[str, ...]
    assignment_set_id: object = None


@dataclass
class CrewRosterModel:
    miniature: Miniature
    cards: list[CardOption]
    saved: CrewMember | None = None
    available: bool = True


@dataclass(frozen=True)
class CrewSaveResult:
    crew: BattleCrew
    drawn: tuple[str, ...] = ()


def may_edit_crew(*, campaign, gang, actor):
    return may_record_gang(campaign=campaign, gang=gang, actor=actor)


def crew_roster(gang, crew=None):
    """One fetch family for the roster, its named cards and their equipment."""
    saved = list(crew.members.all()) if crew else []
    saved_by_model = {m.miniature_id: m for m in saved if m.miniature_id}
    models = list(
        Miniature.objects.filter(
            (
                Q(membership__gang=gang, membership__archived=False)
                & ~Q(status=Status.DEAD)
            )
            | Q(pk__in=saved_by_model)
        )
        .select_related("membership__profile", "membership__caused_by__miniature_root")
        .order_by("name", "pk")
    )
    equipment = list(
        Assignment.objects.filter(
            miniature__in=models, archived=False, removes=False
        ).filter(Q(weapon__isnull=False) | Q(wargear__isnull=False))
    )
    equipment_by_model = {}
    for assignment in equipment:
        equipment_by_model.setdefault(assignment.miniature_id, set()).add(
            str(assignment.pk)
        )
    sets = AssignmentSet.objects.filter(miniature__in=models).prefetch_related(
        "assignments"
    )
    cards_by_model = {}
    for named in sets:
        allowed = equipment_by_model.get(named.miniature_id, set())
        ids = tuple(
            sorted(str(a.pk) for a in named.assignments.all() if str(a.pk) in allowed)
        )
        cards_by_model.setdefault(named.miniature_id, []).append(
            CardOption(str(named.pk), named.name, ids, named.pk)
        )
    return [
        CrewRosterModel(
            miniature=m,
            cards=cards_by_model.get(m.pk)
            or [
                CardOption(
                    "full",
                    "Full equipment",
                    tuple(sorted(equipment_by_model.get(m.pk, set()))),
                )
            ],
            saved=saved_by_model.get(m.pk),
            available=bool(
                m.membership
                and m.membership.gang_id == gang.pk
                and not m.membership.archived
                and m.status != Status.DEAD
            ),
        )
        for m in models
    ]


def saved_card_key(member):
    return f"saved:{member.pk}"


@guarded_write
def save_crew(
    *,
    battle,
    gang,
    actor,
    revision,
    selections,
    confirm=False,
    random_count=0,
    random_role=CrewMember.Role.STARTING,
):
    campaign = Campaign.objects.select_for_update(no_key=True).get(
        pk=battle.campaign_id
    )
    gang = Gang.objects.select_for_update().get(pk=gang.pk)
    battle = Battle.objects.select_for_update().filter(pk=battle.pk).first()
    if battle is None:
        raise Refusal("This battle has been removed. Return to the campaign.")
    if not may_edit_crew(campaign=campaign, gang=gang, actor=actor):
        raise Refusal(
            "You cannot edit this crew. Only its owner or the gang’s current campaign arbitrator can."
        )
    if not battle.gangs.filter(pk=gang.pk).exists():
        raise Refusal("This gang is not a participant in this battle.")
    crew = (
        BattleCrew.objects.select_for_update().filter(battle=battle, gang=gang).first()
    )
    if revision != (crew.revision if crew else 0):
        raise Refusal(
            "This crew changed while you were editing it. Reload the saved crew before saving again."
        )
    roster = crew_roster(gang, crew)
    by_id = {str(item.miniature.pk): item for item in roster}
    selected = {}
    for selection in selections:
        key = str(selection.miniature_id)
        item = by_id.get(key)
        if item is None or not item.available:
            raise Refusal(
                "A selected model is no longer available. Remove it from the crew before saving."
            )
        if key in selected:
            raise Refusal("A model can only be selected once for this battle.")
        if selection.role not in CrewMember.Role.values:
            raise Refusal("Select starting crew or reinforcements for each model.")
        model = item.miniature
        if model.status != Status.ACTIVE and not selection.eligibility_override:
            raise Refusal(
                f"{model.name} is unavailable. Allow this model for this battle or remove it from the crew."
            )
        saved = item.saved
        if saved is not None and selection.card_key == saved_card_key(saved):
            card = CardOption(
                selection.card_key,
                saved.card_name,
                tuple(saved.equipment_ids),
                saved.assignment_set_id,
            )
            card_source = saved.card_source
            rating = saved.rating
        else:
            card = next((c for c in item.cards if c.key == selection.card_key), None)
            if card is None:
                raise Refusal(
                    f"The selected model card for {model.name} is no longer available. Select another card."
                )
            card_source = (
                CrewMember.Source.OVERRIDE
                if saved
                and saved.card_source
                in {CrewMember.Source.RANDOM, CrewMember.Source.OVERRIDE}
                else CrewMember.Source.MANUAL
            )
            rating = model.rating
        selected[key] = dict(
            miniature=model,
            miniature_name=model.name,
            role=selection.role,
            source=saved.source
            if saved and saved.role == selection.role
            else CrewMember.Source.MANUAL,
            card_source=card_source,
            eligibility_override=selection.eligibility_override,
            assignment_set_id=card.assignment_set_id,
            card_name=card.name,
            equipment_ids=list(card.equipment_ids),
            rating=rating,
        )
    if not isinstance(random_count, int) or random_count < 0:
        raise Refusal("Enter a whole number of models to draw, 0 or more.")
    if random_role not in CrewMember.Role.values:
        raise Refusal("Select starting crew or reinforcements for the draw.")
    drawn = ()
    draw_record = None
    if random_count:
        pool = [
            item
            for item in roster
            if item.available
            and item.miniature.status == Status.ACTIVE
            and str(item.miniature.pk) not in selected
        ]
        if random_count > len(pool):
            raise Refusal(
                f"Only {len(pool)} eligible models remain. Enter a smaller draw."
            )
        rng = random.SystemRandom()
        cards = {str(item.miniature.pk): rng.choice(item.cards) for item in pool}
        chosen = rng.sample(pool, random_count)
        drawn = tuple(item.miniature.name for item in chosen)
        draw_record = {
            "role": random_role,
            "cards": {
                key: {
                    "name": card.name,
                    "equipment_ids": list(card.equipment_ids),
                    "key": card.key,
                }
                for key, card in cards.items()
            },
            "models": [str(item.miniature.pk) for item in chosen],
        }
        for item in chosen:
            model = item.miniature
            card = cards[str(model.pk)]
            selected[str(model.pk)] = dict(
                miniature=model,
                miniature_name=model.name,
                role=random_role,
                source=CrewMember.Source.RANDOM,
                card_source=CrewMember.Source.RANDOM,
                eligibility_override=False,
                assignment_set_id=card.assignment_set_id,
                card_name=card.name,
                equipment_ids=list(card.equipment_ids),
                rating=model.rating,
            )
    if confirm and not selected:
        raise Refusal("Select at least one model before saving the crew.")
    if crew is None:
        crew = BattleCrew.objects.create(battle=battle, gang=gang)
    kept = []
    for values in selected.values():
        member, _ = CrewMember.objects.update_or_create(
            crew=crew, miniature=values["miniature"], defaults=values
        )
        kept.append(member.pk)
    crew.members.exclude(pk__in=kept).exclude(miniature__isnull=True).delete()
    crew.revision += 1
    crew.confirmed = confirm
    crew.updated_by = actor
    if draw_record is not None:
        crew.draw_number += 1
        crew.last_draw = draw_record | {"number": crew.draw_number}
    crew.save()
    crew.gang = gang
    return CrewSaveResult(crew=crew, drawn=drawn)


@dataclass(frozen=True)
class EquipmentSnapshot:
    ids: tuple[str, ...]

    def selected_ids(self):
        return {to_ulid(value) for value in self.ids}


@dataclass(frozen=True)
class CrewCard:
    member: CrewMember
    card: ModelCard | None
    missing_equipment: bool = False


@dataclass
class CrewSheet:
    crew: BattleCrew
    starting: list[CrewCard] = field(default_factory=list)
    reserves: list[CrewCard] = field(default_factory=list)
    rating: int = 0


def build_crew_sheet(crew):
    members = list(
        crew.members.select_related(
            "miniature__membership__profile",
            "miniature__membership__caused_by__miniature_root",
        )
    )
    gang_card = build_gang_card(crew.gang)
    available_by_model = {
        miniature_id: {str(a.pk) for a in assignments if a.miniature_id == miniature_id}
        for miniature_id, assignments in gang_card.member_rows.items()
    }
    # A saved weapon moved to another crew member must not follow it there.
    selected = EquipmentSnapshot(
        tuple(
            value
            for member in members
            for value in member.equipment_ids
            if value in available_by_model.get(member.miniature_id, set())
        )
    )
    gang_card.members = gang_card.members_under(selected)
    index = build_modifier_index(carriers(gang_card, *gang_card.members.values()))
    compute_gang(gang_card, index)
    minis = [member.miniature for member in members if member.miniature]
    brought = brought_in_by(minis)
    sheet = CrewSheet(crew=crew, rating=sum(m.rating for m in members))
    for member in members:
        miniature = member.miniature
        raw = gang_card.members.get(member.miniature_id)
        card = (
            build_model_card(
                miniature, card=raw, computed=compute(raw, index), brought_in=brought
            )
            if miniature and raw
            else None
        )
        line = CrewCard(
            member,
            card,
            bool(
                set(member.equipment_ids)
                - available_by_model.get(member.miniature_id, set())
            ),
        )
        (
            sheet.starting
            if member.role == CrewMember.Role.STARTING
            else sheet.reserves
        ).append(line)
    return sheet
