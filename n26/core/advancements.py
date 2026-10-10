"""Persist and resolve fighter advancement rolls and skill or power choices."""

from dataclasses import dataclass
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Prefetch

from n26.core.card import Node, build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import (
    ActionRecord,
    AdvancementSelection,
    Assignment,
    LedgerEvent,
    SkillSelection,
)
from n26.core.models.action_record import RESERVING_STATES
from n26.core.operations import Refusal, subtree
from n26.core.promotions import (
    apply_bonus_promotion,
    may_decline,
    promotion_for,
    promotion_state,
    replaces_roll,
    result_slot,
)


@dataclass(frozen=True)
class AdvancementOption:
    id: str
    name: str
    rating: int
    gainable: bool
    needs_skill: bool
    skill_mode: str
    effect: str = ""
    roll_minimum: int | None = None
    landed: bool = True
    choice_noun: str = "skill"

    @property
    def choice_set_noun(self):
        return {
            "skill": "skill set",
            "power": "power family",
            "skill or power": "skill set or power family",
        }[self.choice_noun]


def _validate_draft(op, record, configured):
    from n26.core.models import ActionRecord

    record = (
        ActionRecord.objects.select_for_update(of=("self",))
        .select_related("fighter__membership", "action", "allowance")
        .filter(pk=record.pk, gang=op.gang, state=ActionRecord.State.STARTED)
        .first()
    )
    if record is None:
        raise Refusal("That advancement is no longer awaiting a roll.")
    from n26.core.action_records import (
        _refuse_unless_owned,
        _validate_draft_definition,
    )

    _refuse_unless_owned(op, record.fighter)
    _validate_draft_definition(record)
    if not record.action.outcomes.filter(
        outcome__resolve_advancement=configured
    ).exists():
        raise Refusal("That advancement does not belong to this action.")
    if (
        record.outcome_id is not None
        and not record.action.outcomes.filter(
            outcome_id=record.outcome_id,
            outcome__resolve_advancement=configured,
        ).exists()
    ):
        raise Refusal("That advancement does not match the selected outcome.")
    return record


def _correction_result(record, *, lock=False):
    """Return and validate the completed result being counterfactually removed."""
    if record.state != ActionRecord.State.COMPLETED:
        return None, None
    query = AdvancementSelection.objects
    if lock:
        query = query.select_for_update(of=("self",))
    try:
        selection = query.select_related("pick_assignment").get(action_record=record)
    except AdvancementSelection.DoesNotExist as error:
        raise Refusal("This action has no advancement result to correct.") from error
    skill_selection = (
        SkillSelection.objects.select_related("skill_assignment")
        .filter(action_record=record)
        .first()
    )
    old_pick = selection.pick_assignment
    old_skill = skill_selection.skill_assignment if skill_selection else None
    if (
        old_pick is None
        or old_pick.archived
        or old_pick.miniature_root_id != record.fighter_id
        or old_pick.chosen_for_id != selection.slot_assignment_id
        or (
            old_skill is not None
            and (
                old_skill.archived
                or old_skill.miniature_root_id != record.fighter_id
                or old_skill.caused_by_id != old_pick.pk
            )
        )
    ):
        raise Refusal("Later changes depend on this advancement.")
    permitted = {old_skill.pk} if old_skill is not None else set()
    if selection.promotion_assignment_id:
        permitted.add(selection.promotion_assignment_id)
        permitted.add(selection.promotion_assignment.caused_by_id)
    if (
        selection.promotion_id
        and record.fighter.action_records.filter(
            action=record.action,
            created__gt=record.created,
            state__in=RESERVING_STATES,
        ).exists()
    ):
        raise Refusal("A later advancement depends on this promotion.")
    if any(
        not descendant.archived and descendant.pk not in permitted
        for descendant in subtree(old_pick)
    ):
        raise Refusal("Later changes depend on this advancement.")
    return selection, skill_selection


def _counterfactual_card(record):
    card = build_card(record.fighter, with_statlines=True)
    selection, skill_selection = _correction_result(record)
    if selection is None:
        return card, None, None
    hidden = {selection.pick_assignment_id}
    if skill_selection and skill_selection.skill_assignment_id:
        hidden.add(skill_selection.skill_assignment_id)
    if selection.promotion_assignment_id:
        hidden.add(selection.promotion_assignment_id)
        hidden.add(selection.promotion_assignment.caused_by_id)

    def without_hidden(nodes):
        kept = []
        for node in nodes:
            if node.assignment is not None and node.assignment.pk in hidden:
                continue
            node.children = without_hidden(node.children)
            kept.append(node)
        return kept

    card.roots = without_hidden(card.roots)
    card.granted = without_hidden(card.granted)
    return card, selection, skill_selection


def _fighter_state(record, additions=()):
    """JSON target facts that can change advancement availability or effects."""
    from n26.core.render import build_model_card

    card, _selection, _skill_selection = _counterfactual_card(record)
    profile = next(node for node in card.all_nodes() if node.is_primary_profile)
    nodes = [
        Node(
            assignable=thing,
            key=("advancement-target", position, thing.pk),
            rating=getattr(thing, "rating_contribution", 0),
            caused_by_key=profile.key,
            chosen_for_key=profile.key,
        )
        for position, thing in enumerate(additions)
    ]
    profile.children.extend(nodes)
    computed = compute(card, build_modifier_index([*carriers(card), *additions]))
    rendered = build_model_card(
        record.fighter, card=card, computed=computed, rank_summaries=()
    )
    stored_skills = {
        str(node.assignable.pk)
        for node in card.all_nodes()
        if not node.suppressed
        and node.assignment is not None
        and getattr(node.assignable._meta, "label_lower", "") == "library.skill"
    }
    return {
        "stats": [cell.value for cell in rendered.statline.cells],
        "skills": sorted(
            stored_skills
            | {
                str(contribution.thing.pk)
                for contribution in computed.skills
                if getattr(contribution.thing, "pk", None) is not None
            }
        ),
        "powers": sorted(
            {
                str(node.assignable.pk)
                for node in card.all_nodes()
                if not node.suppressed
                and node.assignment is not None
                and node.assignable._meta.label_lower == "library.power"
            }
            | {str(contribution.thing.pk) for contribution in computed.powers}
        ),
        "placements": sorted(
            [str(row.category.pk), str(row.section.pk)] for row in computed.placements
        ),
    }


def _skill_offer(pickable):
    from n26.library.models import OffersChoice, Power, Skill

    found = [
        modifier.effect
        for modifier in pickable.modifiers.all()
        if isinstance(modifier.effect, OffersChoice)
        and modifier.effect.of_kind.model_class() in (Skill, Power)
    ]
    if len(found) > 1:
        raise ValueError(f"{pickable} offers more than one skill choice.")
    return found[0] if found else None


def _choice_noun(offer):
    kinds = {kind._meta.model_name for kind in offer.offered_kinds}
    return "skill or power" if len(kinds) == 2 else next(iter(kinds))


def _stat_gainable(fighter, pickable, *, evaluation=None):
    from n26.core.render import build_model_card
    from n26.library.models import ChangesStat

    changes = [
        modifier.effect
        for modifier in pickable.modifiers.all()
        if isinstance(modifier.effect, ChangesStat)
    ]
    if not changes:
        return None
    if evaluation is None:
        card = build_card(fighter, with_statlines=True)
        index = build_modifier_index([*carriers(card), pickable])
        before = build_model_card(
            fighter, card=card, computed=compute(card, index), rank_summaries=()
        )
    else:
        card, index, before = evaluation
    node = Node(
        assignable=pickable,
        key=("advancement-preview", pickable.pk),
        rating=pickable.rating_contribution,
    )
    profile = next(line for line in card.all_nodes() if line.is_primary_profile)
    node.caused_by_key = profile.key
    node.chosen_for_key = profile.key
    profile.children.append(node)
    try:
        after = build_model_card(
            fighter,
            card=card,
            computed=compute(card, index),
            rank_summaries=(),
        )
    finally:
        profile.children.remove(node)
    return [cell.value for cell in before.statline.cells] != [
        cell.value for cell in after.statline.cells
    ]


def _listed_skills(
    record, offer, *, computed=None, owned=None, fighter=None, _catalogues=None
):
    from n26.core.browse import offered_by, usability_for
    from n26.library.models.assignable import USABLE_BY_LISTS

    card = None
    if computed is None or owned is None:
        card, _selection, _skill_selection = _counterfactual_card(record)
    if computed is None:
        computed = compute(card, build_modifier_index(carriers(card)))
    question = SimpleNamespace(slot=None, offer=offer, kind_label=offer.kind_label)
    listed = offered_by(question, computed, _catalogues=_catalogues)
    rows = listed.all_lines() if hasattr(listed, "all_lines") else listed
    if fighter is None:
        fighter = usability_for(computed)
    if owned is None:
        owned = {
            node.assignable.pk
            for node in card.all_nodes()
            if node.assignment is not None
            and getattr(node.assignable._meta, "label_lower", "")
            in ("library.skill", "library.power")
        }
        owned.update(
            contribution.thing.pk
            for contribution in [*computed.skills, *computed.powers]
            if getattr(contribution.thing, "pk", None) is not None
        )
    things = [
        getattr(row, "thing", row)
        for row in rows
        if isinstance(getattr(row, "thing", row), offer.offered_kinds)
        and getattr(row, "thing", row).pk not in owned
    ]
    hydrated = {}
    for kind in offer.offered_kinds:
        ids = [thing.pk for thing in things if isinstance(thing, kind)]
        if ids:
            hydrated.update(
                {
                    thing.pk: thing
                    for thing in kind.objects.filter(pk__in=ids)
                    .select_related("category")
                    .prefetch_related(*USABLE_BY_LISTS)
                }
            )
    # A random roll is a D6 within one set, so a skill with no set cannot be
    # rolled for.
    random = offer.mode == offer.Mode.RANDOM
    return [
        hydrated[thing.pk]
        for thing in things
        if thing.pk in hydrated
        and hydrated[thing.pk].is_usable_by(fighter)
        and not (random and hydrated[thing.pk].category_id is None)
    ]


def _gainable(record, pickable, *, evaluation=None, skills_for=None):
    stat = _stat_gainable(record.fighter, pickable, evaluation=evaluation)
    if stat is not None:
        return stat
    offer = _skill_offer(pickable)
    return (
        bool(skills_for(offer) if skills_for else _listed_skills(record, offer))
        if offer
        else True
    )


def _configuration(row):
    """Return stable semantic fields for a modifier scope or effect."""
    fields = []
    for field in row._meta.concrete_fields:
        if field.primary_key:
            continue
        value = getattr(row, field.attname)
        fields.append([field.attname, None if value is None else str(value)])
    many = [
        [
            field.name,
            sorted(
                str(pk) for pk in getattr(row, field.name).values_list("pk", flat=True)
            ),
        ]
        for field in row._meta.local_many_to_many
    ]
    conditions = sorted(
        (
            _configuration(condition)
            for related in getattr(row, "CONDITIONS", ())
            for condition in getattr(row, related).all()
        ),
        key=repr,
    )
    return [row._meta.label_lower, fields, many, conditions]


def _roll_table(configured):
    """Return active members and the semantic table state bound to a roll."""
    from n26.core.browse import picklist_lines
    from n26.library.models import Modifier
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    condition_paths = []
    for scope_field in SCOPE_FIELDS:
        scope_model = Modifier._meta.get_field(scope_field).related_model
        for related in getattr(scope_model, "CONDITIONS", ()):
            path = f"{scope_field}__{related}"
            condition_paths.append(path)
            condition_model = scope_model._meta.get_field(related).related_model
            condition_paths.extend(
                f"{path}__{field.name}"
                for field in condition_model._meta.local_many_to_many
            )

    members = list(
        picklist_lines(configured.slot.picklist)
        .select_related("pickable")
        .prefetch_related(
            Prefetch(
                "pickable__modifiers",
                queryset=Modifier.objects.select_related(
                    *SCOPE_FIELDS, *EFFECT_FIELDS, "offers_choice__of_kind"
                ).prefetch_related(*condition_paths),
            )
        )
    )
    state = {
        "slot_id": str(configured.slot_id),
        "slot_modified": configured.slot.modified.isoformat(),
        "picklist_id": str(configured.slot.picklist_id),
        "picklist_modified": configured.slot.picklist.modified.isoformat(),
        "members": [
            {
                "id": str(member.pk),
                "modified": member.modified.isoformat(),
                "pickable_id": str(member.pickable_id),
                "pickable_modified": member.pickable.modified.isoformat(),
                "roll_low": member.roll_low,
                "roll_high": member.roll_high,
                "modifiers": sorted(
                    [
                        str(modifier.pk),
                        modifier.modified.isoformat(),
                        _configuration(modifier.scope),
                        _configuration(modifier.effect),
                    ]
                    for modifier in member.pickable.modifiers.all()
                ),
            }
            for member in members
        ],
    }
    return members, state


def _same_roll_table(stored, current):
    """Keep a saved roll valid when its offer gains the power substitution field."""
    if stored == current:
        return True
    if not isinstance(stored, dict):
        return False

    def offers(state):
        return [
            modifier[3]
            for member in state.get("members", [])
            for modifier in member.get("modifiers", [])
            if len(modifier) == 4 and modifier[3][0] == "library.offerschoice"
        ]

    previous = offers(stored)
    if not previous or any(
        name == "power_access_collection_id"
        for configuration in previous
        for name, _value in configuration[1]
    ):
        return False
    from copy import deepcopy

    legacy = deepcopy(current)
    for configuration in offers(legacy):
        configuration[1] = [
            field
            for field in configuration[1]
            if field[0] != "power_access_collection_id"
        ]
    return stored == legacy


def record_action_roll(
    op,
    record,
    configured,
    request_key,
    *,
    rolled=None,
    rng=None,
    decline_promotion=False,
    previous_roll=None,
):
    """Record a 2D6 roll, retaining earlier events when a draft roll is changed."""
    requested_record = record
    record = _validate_draft(op, record, configured)
    promotion = promotion_for(record, configured)
    if replaces_roll(record, configured) and not (
        decline_promotion and may_decline(record, promotion)
    ):
        raise Refusal("Choose a promotion instead of rolling this advancement.")
    selection, _ = AdvancementSelection.objects.select_for_update().get_or_create(
        action_record=record
    )
    if selection.roll_event_id:
        if (
            selection.slot_assignment_id is None
            or selection.slot_assignment.slot_id != configured.slot_id
        ):
            raise Refusal("This action already has a roll for another advancement.")
        if previous_roll is None or record.terms.get("action_roll_request") == str(
            request_key
        ):
            return selection
        if str(selection.roll_event_id) != str(previous_roll):
            raise Refusal("This roll has changed. Reload this page before changing it.")
        if rolled == selection.roll_event.roll:
            return selection
    elif previous_roll is not None:
        raise Refusal("This roll has changed. Reload this page before changing it.")
    from n26.core.promotions import remove_unfinished_promotion

    remove_unfinished_promotion(op, record, selection)
    _members, table_state = _roll_table(configured)
    slots_owned_by_other_drafts = (
        AdvancementSelection.objects.filter(
            action_record__state=ActionRecord.State.STARTED,
            slot_assignment__isnull=False,
        )
        .exclude(action_record=record)
        .values("slot_assignment_id")
    )
    bound = list(
        Assignment.objects.select_for_update()
        .filter(
            miniature_root=record.fighter,
            slot=configured.slot,
            caused_by=record.fighter.membership,
            archived=False,
        )
        .exclude(pk__in=slots_owned_by_other_drafts)
        .exclude(caused__pickable__isnull=False, caused__archived=False)[:2]
    )
    if len(bound) > 1:
        raise Refusal("This advancement has more than one available result slot.")
    anchor = (
        bound[0]
        if bound
        else op.assign(
            configured.slot,
            miniature=record.fighter,
            caused_by=record.fighter.membership,
            action_record=record,
        )
    )
    event = op.roll(
        configured.slot,
        miniature=record.fighter,
        rolled=rolled,
        rng=rng,
        action_record=record,
    )
    selection.slot_assignment, selection.roll_event = anchor, event
    selection.promotion = promotion
    selection.intended_pick = None
    selection.save(
        update_fields=[
            "slot_assignment",
            "roll_event",
            "promotion",
            "intended_pick",
            "modified",
        ]
    )
    if previous_roll is not None:
        record.terms = {
            key: value
            for key, value in record.terms.items()
            if key not in {"pickable_id", "skill_id", "skill_kind", "skill_set_id"}
        }
        record.review = {}
        record.revision += 1
    record.terms = {
        **record.terms,
        "action_roll_request": str(request_key),
        "advancement_table": table_state,
        "promotion_rule": str(promotion.pk) if promotion else None,
        "decline_promotion": bool(promotion and promotion.replaces_advancement),
    }
    record.save(update_fields=["terms", "review", "revision", "modified"])
    requested_record.terms = record.terms
    return selection


def _effect_text(pickable, index=None, seen=None):
    """Describe fixed hidden choices by their effects, not their container slot."""
    from n26.library.prose import CARD, sentence_for

    seen = set() if seen is None else seen
    if pickable.pk in seen:
        return ""
    seen.add(pickable.pk)
    if index is None:
        index = build_modifier_index([pickable])
    sentences = []
    for modifier, _ in index.for_thing(pickable):
        grant = modifier.adds_assignable
        if grant and grant.slot_id and grant.slot.hidden and grant.with_pick_id:
            sentences.append(_effect_text(grant.with_pick, index, seen))
        else:
            sentences.append(sentence_for(modifier, carriage=CARD, thing=pickable).text)
    return " ".join(dict.fromkeys(filter(None, sentences)))


def advancement_options(record, configured):
    options, _skills_for = _advancement_read(record, configured)
    return options


def _advancement_read(record, configured):
    """Options and their skill listings from one read of the current fighter."""
    if replaces_roll(record, configured):
        slot = result_slot(record, configured)
        members, _ = _roll_table(SimpleNamespace(slot=slot, slot_id=slot.pk))
        if not members and (
            record.state == ActionRecord.State.COMPLETED
            or not may_decline(record, promotion_for(record, configured))
        ):
            raise Refusal(
                "You cannot complete this promotion. A content author must make a result available."
            )
        landed = members
    else:
        try:
            selection = record.advancement_selection
        except AdvancementSelection.DoesNotExist as error:
            raise Refusal("Roll 2D6 for this advancement first.") from error
        if not selection.roll_event_id:
            raise Refusal("Roll 2D6 for this advancement first.")
        members, table_state = _roll_table(configured)
        if not _same_roll_table(record.terms.get("advancement_table"), table_state):
            raise Refusal("This advancement table changed after the roll was recorded.")
        landed = configured.slot.picklist.landing(selection.roll_event.roll, members)
    card, _selection, _skill_selection = _counterfactual_card(record)
    index = build_modifier_index(
        [*carriers(card), *(member.pickable for member in members)]
    )
    computed = compute(card, index)
    from n26.core.browse import usability_for
    from n26.core.render import build_model_card

    # Stat previews mutate card nodes; choice eligibility stays on the
    # fighter as they are before any proposed result.
    fighter = usability_for(computed)

    evaluation = (
        card,
        index,
        build_model_card(
            record.fighter, card=card, computed=computed, rank_summaries=()
        ),
    )
    owned = {
        node.assignable.pk
        for node in card.all_nodes()
        if node.assignment is not None
        and getattr(node.assignable._meta, "label_lower", "")
        in ("library.skill", "library.power")
    }
    owned.update(
        contribution.thing.pk
        for contribution in [*computed.skills, *computed.powers]
        if getattr(contribution.thing, "pk", None) is not None
    )
    skill_cache = {}
    catalogues = {}

    def skills_for(offer):
        if offer.pk not in skill_cache:
            skill_cache[offer.pk] = _listed_skills(
                record,
                offer,
                computed=computed,
                owned=owned,
                fighter=fighter,
                _catalogues=catalogues,
            )
        return skill_cache[offer.pk]

    offers = {member.pk: _skill_offer(member.pickable) for member in members}

    gainable = {}
    for member in members:
        offer = offers[member.pk]
        can_gain = _gainable(
            record,
            member.pickable,
            evaluation=evaluation,
            skills_for=skills_for,
        )
        if (
            can_gain
            and record.state == ActionRecord.State.COMPLETED
            and offer is not None
            and offer.mode == offer.Mode.RANDOM
        ):
            recorded = recorded_skill(record, configured, member.pickable_id)
            can_gain = recorded is not None and any(
                skill.pk == recorded.pk for skill in skills_for(offer)
            )
        gainable[member.pk] = can_gain

    gainable_members = [member for member in landed if gainable[member.pk]]
    offered = gainable_members or members
    options = tuple(
        AdvancementOption(
            str(member.pickable_id),
            str(member.pickable),
            member.pickable.rating_contribution,
            gainable[member.pk],
            offers[member.pk] is not None,
            offers[member.pk].mode if offers[member.pk] else "",
            _effect_text(member.pickable, index),
            member.roll_low,
            member in landed,
            _choice_noun(offers[member.pk]) if offers[member.pk] else "skill",
        )
        for member in offered
    )

    return options, skills_for


def skill_options(record, configured, pickable_id):
    read = _advancement_read(record, configured)
    return _skill_options(record, configured, pickable_id, read=read)


def _skill_options(record, configured, pickable_id, *, read):
    options, skills_for = read
    option = next(
        (option for option in options if option.id == str(pickable_id)),
        None,
    )
    if option is None or not option.gainable:
        raise Refusal("That result is not available for this advancement.")
    pickable = (
        result_slot(record, configured)
        .picklist.members.get(pickable_id=pickable_id)
        .pickable
    )
    offer = _skill_offer(pickable)
    if offer is None:
        return {}
    grouped = {}
    for skill in skills_for(offer):
        grouped.setdefault(skill.category, []).append(skill)
    return grouped


def _skill_access(record, configured, pickable_id):
    pickable = (
        result_slot(record, configured)
        .picklist.members.get(pickable_id=pickable_id)
        .pickable
    )
    offer = _skill_offer(pickable)
    return "any" if offer.from_section_id is None else offer.from_section.name.lower()


def recorded_skill(record, configured, pickable_id):
    """Return the immutable random result only when it belongs to this choice."""
    pickable = (
        result_slot(record, configured)
        .picklist.members.get(pickable_id=pickable_id)
        .pickable
    )
    offer = _skill_offer(pickable)
    if offer is None or offer.mode != offer.Mode.RANDOM:
        return None
    selection = getattr(record, "skill_selection", None)
    if selection is None:
        return None
    access = _skill_access(record, configured, pickable_id)
    if record.state != ActionRecord.State.COMPLETED:
        if selection.mode != offer.Mode.RANDOM:
            return None
        skill = selection.selected
        if (
            skill is None
            or selection.access != access
            or selection.skill_set_id != skill.category_id
        ):
            return None
        accepted = any(
            attempt.get("is_available")
            and attempt.get("pickable_id") == str(pickable.pk)
            and attempt.get("skill_id") == str(skill.pk)
            and attempt.get("skill_kind", "skill") == skill._meta.model_name
            and attempt.get("skill_set_id") == str(skill.category_id)
            for attempt in selection.random_attempts
        )
        return skill if accepted else None
    accepted = next(
        (
            attempt
            for attempt in reversed(selection.random_attempts)
            if attempt.get("is_available")
            and attempt.get("pickable_id") == str(pickable.pk)
            and attempt.get("skill_id")
            and attempt.get("skill_set_id")
            and attempt.get("access", selection.access) == access
        ),
        None,
    )
    if accepted is None:
        return None
    return (
        _attempt_kind(accepted)
        .objects.filter(pk=accepted["skill_id"], category_id=accepted["skill_set_id"])
        .first()
    )


def _attempt_kind(attempt):
    from n26.library.models import Power, Skill

    return Power if attempt.get("skill_kind") == "power" else Skill


def _matching_attempts(selection, pickable_id, category, access):
    return [
        attempt
        for attempt in selection.random_attempts
        if attempt.get("pickable_id") == str(pickable_id)
        and attempt.get("skill_set_id") == str(category.pk)
        and (
            attempt.get("access") == access
            or (
                "access" not in attempt
                and selection.access == access
                and selection.skill_set_id == category.pk
            )
        )
    ]


def _carried_attempt(selection, pickable_id, category, access):
    """The earlier attempt whose die the next roll for this set reuses.

    Switching to another random result or skill set after a roll keeps that
    die. A fresh D6 is rolled only for the set and result rolled last, or for
    one that already has its own attempts.
    """
    if not selection.random_attempts:
        return None
    if _matching_attempts(selection, pickable_id, category, access):
        return None
    if selection.access == access and selection.skill_set_id == category.pk:
        return None
    return selection.random_attempts[-1]


def carried_skill_rolls(record, configured, pickable_id, groups):
    """Map each skill set's key to the D6 its next roll reuses, if any."""
    selection = getattr(record, "skill_selection", None)
    if selection is None or not selection.random_attempts:
        return {}
    access = _skill_access(record, configured, pickable_id)
    carried = {}
    for category in groups:
        if category is None:
            continue
        attempt = _carried_attempt(selection, pickable_id, category, access)
        if attempt is not None:
            carried[str(category.pk)] = attempt["roll"]
    return carried


def record_skill_roll(
    op,
    record,
    configured,
    request_key,
    *,
    pickable_id,
    skill_set_id,
    rolled=None,
    rng=None,
):
    record = _validate_draft(op, record, configured)
    from n26.core.browse import picklist_lines

    member = (
        picklist_lines(result_slot(record, configured).picklist)
        .filter(pickable_id=pickable_id)
        .first()
    )
    if member is None:
        raise Refusal("That result is not available for this advancement.")
    offer = _skill_offer(member.pickable)
    if offer is None or offer.mode != offer.Mode.RANDOM:
        raise Refusal("That advancement result does not use a random skill roll.")
    selection, _ = SkillSelection.objects.select_for_update().get_or_create(
        action_record=record,
        defaults={
            "mode": "random",
            "access": _skill_access(record, configured, pickable_id),
        },
    )
    for attempt in selection.random_attempts:
        if attempt["request_key"] == str(request_key):
            if attempt.get("pickable_id") != str(pickable_id) or attempt.get(
                "skill_set_id"
            ) != str(skill_set_id):
                raise Refusal(
                    "That request was already used for a different skill roll."
                )
            return attempt
    options = skill_options(record, configured, pickable_id)
    category = next((row for row in options if str(row.pk) == str(skill_set_id)), None)
    if category is None:
        raise Refusal("That skill set is not available for this advancement.")
    access = _skill_access(record, configured, pickable_id)
    matching = _matching_attempts(selection, pickable_id, category, access)
    available_skill_ids = {str(skill.pk) for skill in options[category]}
    accepted = next(
        (
            attempt
            for attempt in reversed(matching)
            if attempt.get("is_available")
            and attempt.get("skill_id") in available_skill_ids
        ),
        None,
    )
    if accepted is not None:
        selection.access = access
        selection.skill_set = category
        selection.selected = _attempt_kind(accepted).objects.get(
            pk=accepted["skill_id"]
        )
        selection.save()
        return accepted
    from n26.library.models import Dice

    carried = _carried_attempt(selection, pickable_id, category, access)
    if carried is not None:
        if rolled is not None and rolled != carried["roll"]:
            raise Refusal(
                f"You cannot record a different roll for {category.name}. "
                f"Your D6 roll of {carried['roll']} carries over to it."
            )
        event_id, result = carried["event_id"], carried["roll"]
    else:
        if rolled is None:
            rolled = Dice.roll(Dice.D6, rng)
        elif rolled not in Dice.rolls(Dice.D6):
            raise Refusal(f"You cannot roll {rolled} on a {Dice.D6.label}.")
        event = op.event(
            record.fighter,
            LedgerEvent.Kind.ROLLED,
            roll=rolled,
            dice=Dice.D6.value,
            note=str(category),
            action_record=record,
        )
        event_id, result = str(event.pk), event.roll
    rolled = [
        thing
        for kind in offer.offered_kinds
        for thing in kind.objects.unarchived()
        .live()
        .filter(category=category, position=result)
    ]
    if len(rolled) > 1:
        raise ValueError(
            f"{category} has more than one result at D6 position {result}."
        )
    rolled_skill = rolled[0] if rolled else None
    available = next(
        (
            row
            for row in options[category]
            if row.pk == getattr(rolled_skill, "pk", None)
        ),
        None,
    )
    attempt = {
        "request_key": str(request_key),
        "pickable_id": str(pickable_id),
        "event_id": event_id,
        "access": access,
        "skill_set_id": str(category.pk),
        "roll": result,
        "skill_id": str(rolled_skill.pk) if rolled_skill else None,
        "skill_kind": rolled_skill._meta.model_name if rolled_skill else None,
        "result_name": str(rolled_skill) if rolled_skill else None,
        "is_available": available is not None,
        "unavailable_reason": (
            None
            if available is not None
            else f"No {_choice_noun(offer)} has D6 result {result} in {category.name}."
            if rolled_skill is None
            else f"No available {_choice_noun(offer)} was rolled."
        ),
    }
    selection.random_attempts = [*selection.random_attempts, attempt]
    selection.access = access
    selection.skill_set, selection.selected = category, available
    selection.save()
    return attempt


def _resolved(record, configured, terms):
    pickable_id = str(terms.get("pickable_id", ""))
    read = _advancement_read(record, configured)
    options_by_id = {option.id: option for option in read[0]}
    if pickable_id not in options_by_id or not options_by_id[pickable_id].gainable:
        raise Refusal("Choose an available advancement result.")
    pickable = (
        result_slot(record, configured)
        .picklist.members.get(pickable_id=pickable_id)
        .pickable
    )
    offer, skill = _skill_offer(pickable), None
    if offer is not None:
        kind_name = _choice_noun(offer)
        options = _skill_options(record, configured, pickable_id, read=read)
        if offer.mode == offer.Mode.RANDOM:
            skill = recorded_skill(record, configured, pickable_id)
            available = {row.pk for rows in options.values() for row in rows}
            if skill is None or skill.pk not in available:
                raise Refusal(f"Roll D6 again for an available {kind_name}.")
        else:
            skill_id = str(terms.get("skill_id", ""))
            skill = next(
                (
                    row
                    for rows in options.values()
                    for row in rows
                    if str(row.pk) == skill_id
                    and (
                        terms.get("skill_kind") is None
                        or terms["skill_kind"] == row._meta.model_name
                    )
                ),
                None,
            )
            if skill is None:
                raise Refusal(f"Choose an available {kind_name}.")
    return pickable, offer, skill


def preview_advancement(record, configured, terms):
    pickable, offer, skill = _resolved(record, configured, terms)
    selection = record.advancement_selection
    promotion = promotion_for(record, configured)
    bonus = (
        list(promotion.slot.picklist.available_members())
        if promotion and not promotion.replaces_advancement
        else []
    )
    if promotion and not promotion.replaces_advancement and len(bonus) != 1:
        raise Refusal("This promotion needs one configured result.")
    snapshot = {
        "roll": selection.roll_event.roll if selection.roll_event_id else None,
        "roll_event_id": str(selection.roll_event_id)
        if selection.roll_event_id
        else None,
        "slot_assignment_id": str(selection.slot_assignment_id),
        "pickable_id": str(pickable.pk),
        "result": str(pickable),
        "effect": _effect_text(pickable),
        "rating": pickable.rating_contribution,
        "skill_id": str(skill.pk) if skill else None,
        "skill_kind": skill._meta.model_name if skill else None,
        "skill": str(skill) if skill else None,
        "skill_mode": offer.mode if offer else None,
        "skill_from_section_id": str(offer.from_section_id) if offer else None,
        "skill_will_be_assigned_to": offer.will_be_assigned_to if offer else None,
        "fighter_state": _fighter_state(record),
        "result_state": _fighter_state(
            record,
            [
                pickable,
                *([skill] if skill is not None else []),
                *(member.pickable for member in bonus),
            ],
        ),
        "promotion": promotion_state(record, configured),
        "promotion_result": str(bonus[0].pickable) if bonus else "",
    }
    original, original_skill = _correction_result(record)
    if original is not None:
        snapshot["original_result"] = {
            "pick_assignment_id": str(original.pick_assignment_id),
            "pick_modified": original.pick_assignment.modified.isoformat(),
            "pickable_id": str(original.intended_pick_id),
            "skill_assignment_id": (
                str(original_skill.skill_assignment_id)
                if original_skill and original_skill.skill_assignment_id
                else None
            ),
            "skill_modified": (
                original_skill.skill_assignment.modified.isoformat()
                if original_skill and original_skill.skill_assignment_id
                else None
            ),
        }
    return snapshot


@transaction.atomic
def apply_advancement(op, record, configured, terms):
    snapshot = preview_advancement(record, configured, terms)
    selection = record.advancement_selection
    if selection.pick_assignment_id:
        return snapshot
    from n26.core.promotions import stash_promotion_weapons

    stash_promotion_weapons(op, record, configured)
    pickable, offer, skill = _resolved(record, configured, terms)
    pick = op.choose(
        selection.slot_assignment,
        pickable,
        slot=result_slot(record, configured),
        roll=selection.roll_event,
        action_record=record,
    )
    selection.intended_pick, selection.pick_assignment = pickable, pick
    selection.save(update_fields=["intended_pick", "pick_assignment", "modified"])
    apply_bonus_promotion(op, record, selection, pick)
    if skill is not None:
        skill_pick = op.choose(
            pick, skill, offer=offer, miniature=record.fighter, action_record=record
        )
        skill_selection, _ = SkillSelection.objects.get_or_create(
            action_record=record,
            defaults={
                "mode": offer.mode,
                "access": _skill_access(record, configured, pickable.pk),
            },
        )
        skill_selection.mode, skill_selection.access = (
            offer.mode,
            _skill_access(record, configured, pickable.pk),
        )
        skill_selection.skill_set, skill_selection.selected = (
            skill.category,
            skill,
        )
        skill_selection.skill_assignment = skill_pick
        skill_selection.save()
    return snapshot


def correct_advancement(op, record, configured, terms):
    selection, skill_selection = _correction_result(record, lock=True)
    old_pick = selection.pick_assignment
    old_skill = skill_selection.skill_assignment if skill_selection else None
    snapshot = preview_advancement(record, configured, terms)
    pickable, offer, skill = _resolved(record, configured, terms)
    if old_skill is not None:
        op.remove(old_skill, action_record=record, before_pick=old_skill)
    replacement = op.replace_slot_pick(
        selection.slot_assignment,
        result_slot(record, configured),
        pickable,
        previous_pick=old_pick,
        miniature=record.fighter,
        action_record=record,
        roll=selection.roll_event,
    )
    selection.intended_pick, selection.pick_assignment = pickable, replacement
    selection.save(update_fields=["intended_pick", "pick_assignment", "modified"])
    apply_bonus_promotion(op, record, selection, replacement)
    if skill_selection is not None:
        skill_selection.skill_set = None
        skill_selection.selected_skill = None
        skill_selection.selected_power = None
        skill_selection.skill_assignment = None
        skill_selection.save(
            update_fields=[
                "skill_set",
                "selected_skill",
                "selected_power",
                "skill_assignment",
                "modified",
            ]
        )
    if skill is not None:
        skill_pick = op.choose(
            replacement,
            skill,
            offer=offer,
            miniature=record.fighter,
            action_record=record,
        )
        skill_selection, _ = SkillSelection.objects.get_or_create(
            action_record=record,
            defaults={
                "mode": offer.mode,
                "access": _skill_access(record, configured, pickable.pk),
            },
        )
        skill_selection.mode, skill_selection.access = (
            offer.mode,
            _skill_access(record, configured, pickable.pk),
        )
        skill_selection.skill_set, skill_selection.selected = (
            skill.category,
            skill,
        )
        skill_selection.skill_assignment = skill_pick
        skill_selection.save()
    return snapshot
