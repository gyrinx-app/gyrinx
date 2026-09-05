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
    add_built_in,
    add_entry,
    add_picklist_member,
    add_stat_to_statline_type,
    attach_modifiers_to,
    counter_at_least,
    create_affiliation,
    create_category,
    create_collection,
    create_counter,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_option_group,
    create_pack,
    create_pickable,
    create_picklist,
    create_power,
    create_profile,
    create_profile_type,
    create_rule,
    create_skill,
    create_slot,
    create_slot_type,
    create_stat,
    create_statline_type,
    create_subtype,
    create_trading_post,
    create_trait,
    create_wargear,
    create_weapon,
    create_weapon_accessory,
    ef_adds,
    ef_allows_at_most,
    ef_changes_category,
    ef_changes_stat,
    ef_contributes_to_counter,
    ef_offers_choice,
    ef_places,
    ef_places_choice,
    ef_removes,
    ef_requires_companions,
    has_pickable,
    has_subtypes,
    has_traits,
    is_profile,
    is_profile_type,
    offer_option,
    op_adds_model,
    op_changes_counter,
    remove_default_member,
    restrict_use,
    section_of,
    set_statline,
    targets_attached_weapon,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
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


def targets_model(with_subtypes=(), when_counter=None, at_least=0):
    """The model carrying it, optionally narrowed by subtype and by a
    counter threshold — ``targets_model(when_counter=xp, at_least=5)``.

    Old-grammar alias: keyword filters become nested condition verbs
    (``n26.library.authoring.targets_model(has_subtypes(…), …)``). For
    everyone in the gang, use ``targets_every_model``.
    """
    conditions = []
    if with_subtypes:
        conditions.append(has_subtypes(*with_subtypes))
    if when_counter is not None:
        conditions.append(counter_at_least(when_counter, at_least))
    return _targets_model(*conditions)


def targets_weapons(with_trait=None):
    conditions = (has_traits(with_trait),) if with_trait is not None else ()
    return _targets_weapons(*conditions)


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


def offers_choice(model, from_section=None, label="", will_be_assigned_to="bearer"):
    """An OffersChoice effect — ``offers_choice(Skill, from_section=primary)``
    for "a skill from a set that is Primary for this fighter".
    ``will_be_assigned_to="gang"`` is the Leader-picks-for-the-gang arrow."""
    return ef_offers_choice(
        model,
        from_section=from_section,
        label=label,
        will_be_assigned_to=will_be_assigned_to,
    )


def places(category, section):
    """A PlacesCategory effect: for the bearer, that set sits under this
    tier of the section's collection — ``places(powers, skills_primary)``."""
    return ef_places(category, section)


def places_the_chosen(section):
    """The carrier-relative placement: whatever set the carrier's chosen
    choice is homed in sits under this tier — a Venator rank slot."""
    return ef_places_choice(section)


def requires_companions(for_each, at_least, of):
    """A composition ask — ``requires_companions(champion, 3, hive_scum)``."""
    return ef_requires_companions(for_each, at_least, of)


def allows_at_most(at_most, thing):
    """A composition ceiling — ``allows_at_most(2, aberrant)``, and
    ``allows_at_most(0, brute)`` for a ban."""
    return ef_allows_at_most(at_most, thing)


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


def found_campaign(name, campaign_type, owner=None, actor=None, **kwargs):
    """Found a campaign on a type: the row, its own pack and additions,
    and the first line of its log — what the set-up screen does."""
    from n26.core.campaigns import campaign_operation
    from n26.core.models import Campaign

    campaign = Campaign(name=name, owner=owner, **kwargs)
    with campaign_operation(campaign, actor=actor or owner) as act:
        act.found(campaign_type)
    return campaign


def join_campaign(gang, campaign, actor=None):
    """Put a gang into a campaign, as the campaign's add-a-gang screen does:
    both of the campaign's types land on the gang with their built-ins."""
    from n26.core.operations import operation

    with operation(gang, actor=actor or campaign.owner) as op:
        return op.join_campaign(campaign)


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


def attach(weapon_assignment, accessory, paid=None, actor=None, **kwargs):
    """Bolt an accessory onto a weapon — a sight, suspensors.

    A purchase hosted on the weapon's own row, which is what the
    equipment screen's dialog writes. Left unpriced it charges the
    library's figure; naming ``paid`` is the owner's own price.
    """
    from n26.core.operations import operation

    gang = weapon_assignment.gang_root
    if paid is not None:
        kwargs["paid"] = paid
    with operation(gang, actor=actor or gang.owner) as op:
        return op.buy(weapon_assignment, thing=accessory, **kwargs)


def buy_weapon_profile(weapon_assignment, weapon_profile, actor=None, **kwargs):
    from n26.core.operations import operation

    gang = weapon_assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.buy_weapon_profile(weapon_assignment, weapon_profile, **kwargs)


def assign(assignable, *, actor=None, gang=None, miniature=None, **kwargs):
    from n26.core.operations import operation

    stash = kwargs.get("stash")
    host_gang = (
        gang
        or (miniature.gang if miniature else None)
        or (stash.gang if stash is not None else None)
    )
    actor = actor or (host_gang.owner if host_gang else None)
    with operation(host_gang, actor=actor) as op:
        return op.assign(assignable, gang=gang, miniature=miniature, **kwargs)


def remove(assignment, actor=None, note=""):
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.remove(assignment, note=note)


def choose(anchor, chosen, actor=None, **kwargs):
    """Make an offered choice — pick a specialisation."""
    from n26.core.operations import operation

    gang = anchor.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.choose(anchor, chosen, **kwargs)


def buy(miniature, line=None, *, thing=None, entry=None, actor=None, **kwargs):
    """Buy for a model — a browsed line, or freely (the get-out).

    ``option=`` names what was chosen where the thing offers a choice.

    A line that counts Trade Points counts against the gang's open
    visit, which is the decision the equip screen makes: what an action
    has spent is what points back at it, so a test buying through this
    wrapper has to record the same thing a click would.
    """
    from n26.core.operations import operation

    gang = miniature.gang
    with operation(gang, actor=actor or gang.owner) as op:
        # Under the gang's own line, as the equip screen reads it: which
        # visit is open can have changed since the page decided what to ask.
        if line is not None and kwargs.get("action") is None:
            if getattr(line, "charges_trade_points", False):
                kwargs["action"] = gang.open_visit
        return op.buy(miniature, line, thing=thing, entry=entry, **kwargs)


def visit_trading_post(gang, visitors=(), brought=None, actor=None):
    """Perform the Visit Trading Post action.

    ``brought`` states what the visit is worth outright, for a test that
    wants a figure rather than a cast; otherwise it is what the visitors
    bring between them.
    """
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.visit_trading_post(visitors, brought=brought)


def start_action(gang, kind, trade_points=None, actor=None):
    """Start one of the gang's actions — founding it, a trip to the post."""
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.open_action(kind, trade_points=trade_points)


def complete_action(gang, kind, actor=None):
    """Finish whichever action of this kind the gang has open."""
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.close_action(gang.open_action(kind))


def leave_trading_post(gang, actor=None):
    """Finish the action. Whatever it had left is lost."""
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.leave_trading_post()


def select(miniature, thing, actor=None, note=""):
    """Take on a skill or a power — free, and nothing causes it."""
    from n26.core.operations import operation

    gang = miniature.gang
    with operation(gang, actor=actor or gang.owner) as op:
        return op.select(miniature, thing, note=note)


def tally(assignment, change, actor=None, note=""):
    """Change a counter's value — earn XP, mark a kill."""
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.tally(assignment, change, note=note)


def move(assignment, to, actor=None, note=""):
    """Re-home between a model, the stash, and a weapon to bolt it onto."""
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


def add_asset(campaign, asset, name="", actor=None):
    """Add one copy of a pooled asset to a campaign, held by nobody."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.add_asset(asset, name=name)


def grant_asset(token, gang, actor=None):
    """Grant a copy to a gang playing the campaign, as the campaign
    page's Grant does: campaign line first, then the gang's."""
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignMembership

    campaign = token.campaign
    membership = CampaignMembership.objects.get(
        campaign=campaign, gang=gang, left__isnull=True
    )
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.grant(token, membership)


def take_away_asset(token, actor=None):
    """Take a copy back from the gang holding it."""
    from n26.core.campaigns import campaign_operation

    campaign = token.campaign
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.take_away(token)


def drop_asset(token, actor=None):
    """Drop a copy nobody holds."""
    from n26.core.campaigns import campaign_operation

    campaign = token.campaign
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.drop_asset(token)


def transfer_asset(token, gang, actor=None):
    """Hand a held copy to another gang playing the campaign."""
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignMembership

    campaign = token.campaign
    membership = CampaignMembership.objects.get(
        campaign=campaign, gang=gang, left__isnull=True
    )
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.transfer(token, membership)


def add_kind(campaign, label, mode="pooled", plural="", actor=None):
    """Declare a kind of asset on the campaign's additions."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.add_kind(label, mode, label_plural=plural)


def create_campaign_asset(campaign, kind, name, annotation="", income=0, actor=None):
    """Write an asset into the campaign's pack under one of its kinds."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.create_asset(kind, name, annotation=annotation, income=income)


def add_campaign_counter(campaign, name, opening=0, actor=None):
    """Give every gang in the campaign a counter opening at a value."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.add_counter(name, opening=opening)


def add_campaign_label(campaign, name, options, actor=None):
    """Ask every gang in the campaign one question with fixed options."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.add_label(name, options)
