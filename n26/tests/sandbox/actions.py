"""Building blocks for sandbox tests.

Each action does one thing and returns the object it made, so a test reads as
a sequence of steps rather than a wall of ``objects.create``. Two layers live
here:

* **Library-side verbs** graduated to :mod:`library.authoring` — the real
  authoring API, re-exported. A few keep their old sandbox names and
  kwargs as thin aliases (``adds`` for ``ef_adds``, ``targets_model``'s
  keyword filters for the condition verbs) so the example suites read as
  written; new tests should prefer the authoring names.
* **Player-side wrappers** over ``n26.operations``, still owned here.

Everything is pack-aware: omit ``pack`` and it lands in N26, exactly as
admin ingestion would.
"""

from n26.library.authoring import (  # noqa: F401 — re-exported for the suites
    attach_modifiers_to,
    counter_at_least,
    create_affiliation,
    create_archetype,
    create_category,
    create_collection,
    create_counter,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_lasting_effect,
    create_option_group,
    create_pack,
    create_power,
    create_profile,
    create_profile_type,
    create_rule,
    create_skill,
    create_skill_tree,
    create_specialisation,
    create_stat,
    create_statline_type,
    create_subtype,
    create_trading_post,
    create_trait,
    create_wargear,
    create_weapon,
    create_weapon_accessory,
    ef_adds,
    ef_changes_stat,
    ef_offers_choice,
    ef_places,
    ef_places_choice,
    ef_removes,
    ef_requires_companions,
    has_subtypes,
    has_traits,
    is_profile,
    offer_option,
    op_adds_model,
    restrict_use,
    section_of,
    set_statline,
    targets_attached_weapon,
    targets_gang,
)
from n26.library.authoring import (
    modifier as _modifier,
)
from n26.library.authoring import (
    targets_model as _targets_model,
)
from n26.library.authoring import (
    targets_weapons as _targets_weapons,
)

# --- Aliases: the sandbox names the example suites were written in --------


def targets_model(with_subtypes=(), when_counter=None, at_least=0, bearer_only=False):
    """The carrier's model, optionally narrowed by subtype and by a
    counter threshold — ``targets_model(when_counter=xp, at_least=5)``.

    Old-grammar alias: keyword filters become nested condition verbs
    (``n26.library.authoring.targets_model(has_subtypes(…), …)``), and
    ``bearer_only`` became ``when_directly_assigned``.
    """
    conditions = []
    if with_subtypes:
        conditions.append(has_subtypes(*with_subtypes))
    if when_counter is not None:
        conditions.append(counter_at_least(when_counter, at_least))
    return _targets_model(*conditions, when_directly_assigned=bearer_only)


def targets_weapons(with_trait=None):
    conditions = (has_traits(with_trait),) if with_trait is not None else ()
    return _targets_weapons(*conditions)


def create_injury(name, **kwargs):
    """Old name for a lasting effect — the kind is one, the word is
    the profile type's."""
    return create_lasting_effect(name, **kwargs)


def modifier(name, scope, effect, carried_by=None, **kwargs):
    """Create a modifier and, optionally, hang it on an assignable."""
    return _modifier(name, scope, effect, attach_to=carried_by, **kwargs)


def adds(thing):
    """An ``AddsAssignable`` naming a subtype, skill, trait or weapon."""
    return ef_adds(thing)


def removes(thing):
    return ef_removes(thing)


def changes_stat(stat, mode="worsen", amount=1):
    return ef_changes_stat(stat, mode=mode, amount=amount)


def offers_choice(model, from_section=None, label="", answer_host="bearer"):
    """An OffersChoice effect — ``offers_choice(Skill, from_section=primary)``
    for "a skill from a set that is Primary for this fighter".
    ``answer_host="gang"`` is the Leader-picks-for-the-gang arrow."""
    return ef_offers_choice(
        model, from_section=from_section, label=label, answer_host=answer_host
    )


def places(category, section):
    """A PlacesCategory effect: for the bearer, that set sits under this
    tier of the section's collection — ``places(powers, skills_primary)``."""
    return ef_places(category, section)


def places_the_chosen(section):
    """The carrier-relative placement: whatever set the carrier's answered
    choice is homed in sits under this tier — a Venator rank slot."""
    return ef_places_choice(section)


def requires_companions(for_each, at_least, of):
    """A composition ask — ``requires_companions(champion, 3, hive_scum)``."""
    return ef_requires_companions(for_each, at_least, of)


# --- Gangs and assignments ----------------------------------------------
#
# Writing player data goes through n26.operations — these are thin wrappers
# so a sandbox test reads as a flow rather than as plumbing. They default the
# actor to the gang's owner; n26.operations deliberately does not, so an
# action on someone else's gang is never mis-attributed by omission.


def found_gang(name, gang_type, owner=None, budget=None, actor=None, **kwargs):
    """Found a gang: create it, then give it its type and what that brings.

    ``budget`` overrides the gang type's ``starting_credits``. Left unset
    by both, founding is unlimited: players buy what they own, and the
    gang's number is its rating.
    """
    from n26.core.models import Gang
    from n26.core.operations import operation

    if budget is None:
        budget = gang_type.starting_credits
    gang = Gang.objects.create(
        name=name,
        gang_type=gang_type,
        owner=owner,
        starting_credits=budget,
        credits=budget or 0,
        **kwargs,
    )
    with operation(gang, actor=actor or owner) as op:
        op.found(gang_type)
    return gang


def hire(gang, profile, model_name, paid=0, actor=None, **kwargs):
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.hire(profile, model_name, paid=paid, **kwargs)


def hire_with_option(gang, profile, model_name, option=None, actor=None, **kwargs):
    """Hire, letting the profile's own pricing decide what it costs."""
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.hire(profile, model_name, option=option, **kwargs)


def add_legacy_profile(miniature, profile, actor=None, **kwargs):
    from n26.core.operations import operation

    gang = miniature.gang
    with operation(gang, actor=actor or gang.owner) as op:
        return op.add_legacy_profile(miniature, profile, **kwargs)


def give_weapon(miniature, weapon, paid=0, actor=None, **kwargs):
    from n26.core.operations import operation

    gang = miniature.gang
    with operation(gang, actor=actor or gang.owner) as op:
        return op.give_weapon(miniature, weapon, paid=paid, **kwargs)


def attach(weapon_assignment, accessory, paid=0, actor=None, **kwargs):
    """Hang an accessory off a weapon — a sight, suspensors."""
    from n26.core.operations import operation

    gang = weapon_assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.assign(accessory, parent=weapon_assignment, paid=paid, **kwargs)


def buy_weapon_profile(weapon_assignment, weapon_profile, actor=None, **kwargs):
    from n26.core.operations import operation

    gang = weapon_assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.buy_weapon_profile(weapon_assignment, weapon_profile, **kwargs)


def assign(assignable, *, actor=None, gang=None, miniature=None, **kwargs):
    from n26.core.operations import operation

    host_gang = gang or (miniature.gang if miniature else None)
    actor = actor or (host_gang.owner if host_gang else None)
    with operation(host_gang, actor=actor) as op:
        return op.assign(assignable, gang=gang, miniature=miniature, **kwargs)


def remove(assignment, actor=None, note=""):
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.remove(assignment, note=note)


def choose(anchor, chosen, actor=None, **kwargs):
    """Answer an offered choice — pick a specialisation."""
    from n26.core.operations import operation

    gang = anchor.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.choose(anchor, chosen, **kwargs)


def buy(miniature, line=None, *, thing=None, entry=None, actor=None, **kwargs):
    """Buy for a model — a browsed line, or freely (the get-out).

    ``option=`` names what was chosen where the thing offers a choice.
    """
    from n26.core.operations import operation

    gang = miniature.gang
    with operation(gang, actor=actor or gang.owner) as op:
        return op.buy(miniature, line, thing=thing, entry=entry, **kwargs)


def learn(miniature, thing, actor=None, note=""):
    """Take on a skill or a power — free, and nothing causes it."""
    from n26.core.operations import operation

    gang = miniature.gang
    with operation(gang, actor=actor or gang.owner) as op:
        return op.learn(miniature, thing, note=note)


def tally(assignment, change, actor=None, note=""):
    """Change a counter's value — earn XP, mark a kill."""
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.tally(assignment, change, note=note)


def move(assignment, to, actor=None, note=""):
    """Re-home between a model and the stash, either direction."""
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.move(assignment, to, note=note)


def refund(assignment, actor=None, note=""):
    """Take something back and return what was paid — not just remove it."""
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.refund(assignment, note=note)


def sell(assignment, actor=None, note=""):
    """Sell something on for half of what it is worth. Returns the proceeds."""
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.sell(assignment, note=note)


def create_assignment_set(miniature, name, assignments):
    """A named selection of the model's equipment — one Model Card."""
    from n26.core.models import AssignmentSet

    selection = AssignmentSet.objects.create(miniature=miniature, name=name)
    selection.assignments.set(assignments)
    selection.validate_assignments()
    return selection
