"""Test verbs for authored content and player operations. Re-export the shipped
n26.library.authoring API and retain compatibility aliases used by existing suites;
prefer authoring names in new tests. Content defaults to the N26 pack when no pack is
supplied.

Player wrappers open n26.core.operations or campaign_operation and default the actor to
the gang or campaign owner. Production operations require callers to choose their actor
explicitly.
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
    has_gang_pickable,
    has_pickable,
    has_status,
    has_subtypes,
    has_traits,
    is_profile,
    is_profile_type,
    offer_option,
    op_adds_model,
    op_changes_counter,
    op_sets_status,
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


def targets_model(with_subtypes=(), when_counter=None, at_least=0):
    """Target the bearer with optional subtype and counter-threshold conditions. This
    compatibility wrapper converts keyword filters into authoring condition verbs; use
    targets_every_model to reach the whole gang.
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
    """Create a modifier, optionally attaching it to carried_by."""
    return _modifier(name, scope, effect, attach_to=carried_by, **kwargs)


def adds(thing):

    return ef_adds(thing)


def removes(thing):
    return ef_removes(thing)


def changes_stat(stat, mode="worsen", amount=1):
    return ef_changes_stat(stat, mode=mode, amount=amount)


def offers_choice(model, from_section=None, label="", will_be_assigned_to="bearer"):
    """Offer a choice from a model or section. will_be_assigned_to="gang" hosts the result
    on the gang instead of the bearer.
    """
    return ef_offers_choice(
        model,
        from_section=from_section,
        label=label,
        will_be_assigned_to=will_be_assigned_to,
    )


def places(category, section):
    """Place the category within a section for the bearer, such as powers in a Primary
    skill section.
    """
    return ef_places(category, section)


def places_the_chosen(section):
    """Place the category containing the carrier's chosen item within the supplied section."""
    return ef_places_choice(section)


def requires_companions(for_each, at_least, of):

    return ef_requires_companions(for_each, at_least, of)


def allows_at_most(at_most, thing):
    """Limit how many of the specified content a gang may hold; zero represents a ban."""
    return ef_allows_at_most(at_most, thing)


def found_gang(name, gang_type, owner=None, budget=None, actor=None, **kwargs):
    """Create a gang and found it through the domain operation. None uses the gang type's
    starting_credits; when both are None, credits are unlimited.
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
    """Create the campaign through campaign_operation, including its pack, additions type
    and founding event.
    """
    from n26.core.campaigns import campaign_operation
    from n26.core.models import Campaign

    campaign = Campaign(name=name, owner=owner, **kwargs)
    with campaign_operation(campaign, actor=actor or owner) as act:
        act.found(campaign_type)
    return campaign


def join_campaign(gang, campaign, actor=None):
    """Join a campaign and grant its campaign-type and additions carriers to the gang."""
    from n26.core.operations import operation

    with operation(gang, actor=actor or campaign.owner) as op:
        return op.join_campaign(campaign)


def join_campaign_after_deletion(gang, campaign, actor=None):
    """Build an archived gang with active campaign membership for malformed-state tests.
    Temporarily unarchive it to join, then archive it again.
    """
    from n26.core.models import Gang

    Gang.objects.filter(pk=gang.pk).update(archived=False)
    gang.refresh_from_db()
    membership = join_campaign(gang, campaign, actor=actor)
    gang.archive()
    return membership


def open_founding(gang, actor=None):
    """Open the gang's Spend founding TP activity."""
    from n26.core.models import Activity
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        op.open_activity(Activity.Kind.FOUNDING)
    return gang


def hire(gang, profile, model_name, paid=0, actor=None, **kwargs):
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.hire(profile, model_name, paid=paid, **kwargs)


def hire_with_option(gang, profile, model_name, option=None, actor=None, **kwargs):
    """Hire using the profile's pricing and selected option."""
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
    """Buy an accessory hosted on the weapon assignment. Use the library price unless paid
    is explicitly supplied.
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

    from n26.core.operations import operation

    gang = anchor.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.choose(anchor, chosen, **kwargs)


def buy(miniature, line=None, *, thing=None, entry=None, actor=None, **kwargs):
    """Buy a browsed line or directly named content for a model. option selects among the
    item's offered alternatives. For a Trade Point line, record the gang's open visit
    under its operation lock, matching the equip flow.
    """
    from n26.core.operations import operation

    gang = miniature.gang
    with operation(gang, actor=actor or gang.owner) as op:
        # Read the open visit under the operation lock because it can change after the
        # page was rendered.
        if line is not None and kwargs.get("activity") is None:
            if getattr(line, "charges_trade_points", False):
                kwargs["activity"] = gang.open_visit
        return op.buy(miniature, line, thing=thing, entry=entry, **kwargs)


def visit_trading_post(gang, visitors=(), brought=None, actor=None):
    """Open a trading-post visit with the supplied contributors. brought overrides their
    calculated allowance when a test needs a fixed figure.
    """
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.visit_trading_post(visitors, brought=brought)


def start_action(gang, kind, trade_points=None, actor=None):

    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.open_activity(kind, trade_points=trade_points)


def complete_action(gang, kind, actor=None):
    """Finish whichever action of this kind the gang has open."""
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.close_activity(gang.open_activity(kind))


def leave_trading_post(gang, actor=None):
    """Close the visit and discard its unspent Trade Points."""
    from n26.core.operations import operation

    with operation(gang, actor=actor or gang.owner) as op:
        return op.leave_trading_post()


def select(miniature, thing, actor=None, note=""):
    """Select a skill or power for free without a causing assignment."""
    from n26.core.operations import operation

    gang = miniature.gang
    with operation(gang, actor=actor or gang.owner) as op:
        return op.select(miniature, thing, note=note)


def tally(assignment, change, actor=None, note=""):

    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.tally(assignment, change, note=note)


def move(assignment, to, actor=None, note=""):
    """Move an assignment between a model, stash or compatible weapon host."""
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.move(assignment, to, note=note)


def refund(assignment, actor=None, note=""):
    """Return the recorded purchase payment and remove the assignment."""
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.refund(assignment, note=note)


def sell(assignment, actor=None, note=""):
    """Sell the assignment and return the proceeds."""
    from n26.core.operations import operation

    gang = assignment.gang_root
    with operation(gang, actor=actor or gang.owner) as op:
        return op.sell(assignment, note=note)


def create_assignment_set(miniature, name, assignments):
    """Create and validate a named equipment selection for one model card."""
    from n26.core.models import AssignmentSet

    selection = AssignmentSet.objects.create(miniature=miniature, name=name)
    selection.assignments.set(assignments)
    selection.validate_assignments()
    return selection


def add_asset(campaign, asset, name="", actor=None):
    """Add an asset to a campaign, held by nobody."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.add_asset(asset, name=name)


def assign_asset(campaign_asset, gang, actor=None):
    """Assign an asset to an active gang membership through campaign_operation, locking the
    campaign before the gang.
    """
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignMembership

    campaign = campaign_asset.campaign
    membership = CampaignMembership.objects.get(
        campaign=campaign, gang=gang, left__isnull=True
    )
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.assign(campaign_asset, membership)


def unassign_asset(campaign_asset, actor=None):
    """Take an asset back from the gang holding it."""
    from n26.core.campaigns import campaign_operation

    campaign = campaign_asset.campaign
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.unassign(campaign_asset)


def remove_from_campaign(gang, campaign, actor=None):
    """Remove an active gang membership through campaign_operation, locking the campaign
    before the gang.
    """
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignMembership

    membership = CampaignMembership.objects.get(
        campaign=campaign, gang=gang, left__isnull=True
    )
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.remove_gang(membership)


def archive_campaign(campaign, actor=None):
    """Archive a campaign, taking every gang out first."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.archive()


def remove_asset(campaign_asset, actor=None):
    """Remove an asset nobody holds from its campaign."""
    from n26.core.campaigns import campaign_operation

    campaign = campaign_asset.campaign
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.remove_asset(campaign_asset)


def transfer_asset(campaign_asset, gang, actor=None):
    """Hand a held asset to another gang playing the campaign."""
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignMembership

    campaign = campaign_asset.campaign
    membership = CampaignMembership.objects.get(
        campaign=campaign, gang=gang, left__isnull=True
    )
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.transfer(campaign_asset, membership)


def add_campaign_asset_type(campaign, label, ownership="pooled", plural="", actor=None):
    """Add an asset type through the campaign operation."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.add_asset_type(label, ownership, label_plural=plural)


def create_campaign_asset(
    campaign, asset_type, name, annotation="", income=0, actor=None
):
    """Write an asset into the campaign's pack under one of its asset types."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.create_asset(asset_type, name, annotation=annotation, income=income)


def add_campaign_counter(campaign, name, opening=0, actor=None):
    """Grant each campaign gang a counter with the specified starting value."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.add_counter(name, opening=opening)


def add_campaign_label(campaign, name, options, actor=None):
    """Give campaign gangs a label with fixed options."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.add_label(name, options)


def roll_asset(campaign, table, gang=None, rolled=None, rng=None, actor=None):
    """Roll on an asset table for the campaign pool or the specified gang's starting asset."""
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignMembership

    membership = (
        CampaignMembership.objects.get(campaign=campaign, gang=gang, left__isnull=True)
        if gang is not None
        else None
    )
    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.roll_asset(table, membership=membership, rolled=rolled, rng=rng)


def open_table(campaign, table, actor=None):
    """Allow campaign gangs to roll on this table."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.open_table(table)


def close_table(campaign, table, actor=None):
    """Withdraw campaign access to a previously opened table."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.close_table(table)


def create_campaign_table(campaign, asset_type, name, dice="", actor=None):
    """Write a table into the campaign's pack, built into its additions."""
    from n26.core.campaigns import campaign_operation

    with campaign_operation(campaign, actor=actor or campaign.owner) as act:
        return act.create_table(asset_type, name, dice=dice)
