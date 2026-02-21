"""Fighter equipment views."""

import random
from collections import defaultdict
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect, QueryDict
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.content.models import (
    ContentAvailabilityPreset,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentUpgrade,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentWeaponAccessory,
    ContentWeaponProfile,
    ExpansionRuleInputs,
    VirtualWeaponProfile,
)
from gyrinx.core.forms.list import (
    EquipmentReassignForm,
    EquipmentSellSelectionForm,
    ListFighterEquipmentAssignmentAccessoriesForm,
    ListFighterEquipmentAssignmentCostForm,
    ListFighterEquipmentAssignmentForm,
    ListFighterEquipmentAssignmentUpgradeForm,
)
from gyrinx.core.handlers.equipment import (
    SaleItemDetail,
    handle_accessory_purchase,
    handle_equipment_component_removal,
    handle_equipment_cost_override,
    handle_equipment_purchase,
    handle_equipment_reassignment,
    handle_equipment_removal,
    handle_equipment_sale,
    handle_equipment_upgrade,
    handle_weapon_profile_purchase,
)
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    VirtualListFighterEquipmentAssignment,
)
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.core.views import make_query_params_str
from gyrinx.core.views.list.common import get_clean_list_or_404
from gyrinx.models import is_int, is_valid_uuid


@login_required
@transaction.atomic
def edit_list_fighter_equipment(request, id, fighter_id, is_weapon=False):
    """
    Edit the equipment (weapons or gear) of an existing :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``equipment``
        A filtered list of :model:`content.ContentEquipment` items.
    ``categories``
        Available equipment categories.
    ``assigns``
        A list of :class:`.VirtualListFighterEquipmentAssignment` objects.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.
    ``is_weapon``
        Boolean indicating if we're editing weapons or gear.

    **Template**

    :template:`core/list_fighter_weapons_edit.html` or :template:`core/list_fighter_gear_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    view_name = (
        "core:list-fighter-weapons-edit" if is_weapon else "core:list-fighter-gear-edit"
    )
    template_name = (
        "core/list_fighter_weapons_edit.html"
        if is_weapon
        else "core/list_fighter_gear_edit.html"
    )

    packs = lst.packs.all()

    error_message = None
    if request.method == "POST":
        instance = ListFighterEquipmentAssignment(list_fighter=fighter)
        form = ListFighterEquipmentAssignmentForm(request.POST, instance=instance)
        form.fields["content_equipment"].queryset = ContentEquipment.objects.with_packs(
            packs
        )
        if form.is_valid():
            assign: ListFighterEquipmentAssignment = form.save(commit=False)

            try:
                # Save the assignment and m2m relationships
                assign.save()
                form.save_m2m()

                # Call handler to handle business logic (credit spending, actions)
                result = handle_equipment_purchase(
                    user=request.user,
                    lst=lst,
                    fighter=fighter,
                    assignment=assign,
                )

                # Extract results for HTTP-specific operations
                assign = result.assignment
                total_cost = result.total_cost
                description = result.description

                # Log the equipment assignment event
                log_event(
                    user=request.user,
                    noun=EventNoun.EQUIPMENT_ASSIGNMENT,
                    verb=EventVerb.CREATE,
                    object=assign,
                    request=request,
                    fighter_id=str(fighter.id),
                    fighter_name=fighter.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    equipment_name=assign.content_equipment.name,
                    equipment_type="weapon" if is_weapon else "gear",
                    cost=total_cost,
                    credits_remaining=lst.credits_current if lst.campaign else None,
                )

                messages.success(request, description)

                # Build query parameters, preserving filters from both POST and GET
                query_dict = {}
                query_dict["flash"] = assign.id

                # From POST
                if request.POST.get("filter"):
                    query_dict["filter"] = request.POST.get("filter")
                if request.POST.get("q"):
                    query_dict["q"] = request.POST.get("q")

                # From POST - category and availability filters (forms submit via POST)
                cat_list = request.POST.getlist("cat")
                if cat_list:
                    # For lists, we need to use QueryDict to properly encode them
                    qd = QueryDict(mutable=True)
                    for k, v in query_dict.items():
                        qd[k] = v
                    qd.setlist("cat", cat_list)

                    al_list = request.POST.getlist("al")
                    if al_list:
                        qd.setlist("al", al_list)

                    mal = request.POST.get("mal")
                    if mal:
                        qd["mal"] = mal

                    mc = request.POST.get("mc")
                    if mc:
                        qd["mc"] = mc

                    query_params = qd.urlencode()
                else:
                    # No lists, use simple approach - also check for al list
                    al_list = request.POST.getlist("al")
                    if al_list:
                        qd = QueryDict(mutable=True)
                        for k, v in query_dict.items():
                            qd[k] = v
                        qd.setlist("al", al_list)

                        mal = request.POST.get("mal")
                        if mal:
                            qd["mal"] = mal

                        mc = request.POST.get("mc")
                        if mc:
                            qd["mc"] = mc

                        query_params = qd.urlencode()
                    else:
                        if request.POST.get("mal"):
                            query_dict["mal"] = request.POST.get("mal")
                        if request.POST.get("mc"):
                            query_dict["mc"] = request.POST.get("mc")
                        query_params = make_query_params_str(**query_dict)
                return HttpResponseRedirect(
                    reverse(view_name, args=(lst.id, fighter.id))
                    + f"?{query_params}"
                    + f"#{str(fighter.id)}"
                )
            except DjangoValidationError as e:
                # Handler failed (e.g., insufficient credits) - clean up the assignment
                assign.delete()

                # Not enough credits or other validation error
                error_message = messages.validation(request, e)

    # Get the appropriate equipment
    # Create expansion rule inputs for cost calculations
    expansion_inputs = ExpansionRuleInputs(list=lst, fighter=fighter)

    if is_weapon:
        equipment = (
            ContentEquipment.objects.with_packs(packs)
            .weapons()
            .with_expansion_cost_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )
        )
        search_vector = SearchVector(
            "name",
            "category__name",
            "contentweaponprofile__name",
            "contentweaponprofile__traits__name",
        )
    else:
        equipment = (
            ContentEquipment.objects.with_packs(packs)
            .non_weapons()
            .with_expansion_cost_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )
        )
        search_vector = SearchVector("name", "category__name")

    # Get categories for this equipment type
    categories = (
        ContentEquipmentCategory.objects.filter(id__in=equipment.values("category_id"))
        .distinct()
        .order_by("name")
    )

    # Filter categories based on fighter category restrictions
    # Batch-fetch all restrictions to avoid N+1 queries
    fighter_category = fighter.get_category()

    all_restrictions = ContentEquipmentCategoryFighterRestriction.objects.filter(
        equipment_category__in=categories
    ).values("equipment_category_id", "fighter_category")
    restrictions_by_category = defaultdict(list)
    for r in all_restrictions:
        restrictions_by_category[r["equipment_category_id"]].append(
            r["fighter_category"]
        )

    restricted_category_ids = []
    for category in categories:
        restrictions = restrictions_by_category.get(category.id, [])
        # If restrictions exist and fighter category is not in them, it's restricted
        if restrictions and fighter_category not in restrictions:
            restricted_category_ids.append(category.id)

    # Remove restricted categories
    if restricted_category_ids:
        categories = categories.exclude(id__in=restricted_category_ids)
        equipment = equipment.exclude(category_id__in=restricted_category_ids)

    # Compute house-restricted category IDs.
    # Categories with restricted_to set should be excluded from the default selection
    # when the list's house is not in the restriction set. Unlike fighter category
    # restrictions (which are hard-excluded above), house-restricted categories remain
    # in the dropdown so users can opt-in by checking the checkbox.
    house_restrictions_qs = (
        ContentEquipmentCategory.restricted_to.through.objects.filter(
            contentequipmentcategory_id__in=categories.values("id")
        ).values("contentequipmentcategory_id", "contenthouse_id")
    )
    house_restrictions_by_category = defaultdict(set)
    for r in house_restrictions_qs:
        house_restrictions_by_category[r["contentequipmentcategory_id"]].add(
            r["contenthouse_id"]
        )

    house_restricted_category_ids = set()
    for category in categories:
        restricted_house_ids = house_restrictions_by_category.get(category.id, set())
        if restricted_house_ids and lst.content_house_id not in restricted_house_ids:
            house_restricted_category_ids.add(category.id)

    # Filter by category if specified
    cats = [
        cat for cat in request.GET.getlist("cat", list()) if cat and is_valid_uuid(cat)
    ]

    # Strip cat IDs that don't match any available category for this page.
    # This handles cross-page navigation (e.g. gear cat IDs carried to the
    # weapons page via {% querystring %} in template links).
    if cats and "all" not in cats:
        valid_cat_ids = {str(c.id) for c in categories}
        valid_cats = [c for c in cats if c in valid_cat_ids]
        if cats != valid_cats:
            query_dict = request.GET.copy()
            if valid_cats:
                query_dict.setlist("cat", valid_cats)
            else:
                # No valid cats remain - remove cat key to trigger default logic
                del query_dict["cat"]
            return HttpResponseRedirect(
                reverse(view_name, args=(lst.id, fighter.id))
                + f"?{query_dict.urlencode()}"
            )
        cats = valid_cats

    # When house-restricted categories exist and no cat filter is provided,
    # redirect with default cat values that exclude those categories. This
    # fires regardless of other params (filter, al, etc.) so that arriving
    # via {% querystring cat=None %} or any other catless URL still gets
    # the correct defaults.
    if house_restricted_category_ids and "cat" not in request.GET:
        default_cats = [
            str(cat.id)
            for cat in categories
            if cat.id not in house_restricted_category_ids
        ]
        if default_cats:
            query_dict = request.GET.copy()
            for cat_id in default_cats:
                query_dict.appendlist("cat", cat_id)
            return HttpResponseRedirect(
                reverse(view_name, args=(lst.id, fighter.id))
                + f"?{query_dict.urlencode()}"
            )

    if cats and "all" not in cats:
        equipment = equipment.filter(category_id__in=cats)

    # Apply search filter if provided
    if request.GET.get("q"):
        search_query = SearchQuery(request.GET.get("q", ""))
        equipment = (
            equipment.annotate(search=search_vector)
            .filter(search=search_query)
            .distinct("category__name", "name", "id")
        )

    # Check if the house has can_buy_any flag
    house_can_buy_any = lst.content_house.can_buy_any

    # Look up availability preset for this fighter/category/house
    preset = ContentAvailabilityPreset.get_preset_for(
        fighter=fighter.content_fighter,
        category=fighter.get_category(),
        house=lst.content_house,
    )

    # Get preset values (or defaults if no preset)
    preset_al = preset.availability_types_list if preset else ["C", "R", "I"]
    preset_mal = preset.max_availability_level if preset else None

    # Figure out default view - show all if house OR preset allows it
    default_to_all = house_can_buy_any or (preset and preset.fighter_can_buy_any)

    # If defaulting to all and no filter is provided, redirect to filter=all
    # with preset values applied, unless user has provided explicit values.
    if default_to_all and "filter" not in request.GET:
        query_dict = request.GET.copy()
        query_dict["filter"] = "all"

        # Apply preset values only if preset exists and user hasn't provided explicit filters
        if preset and "al" not in request.GET and "mal" not in request.GET:
            for al in preset_al:
                query_dict.appendlist("al", al)
            if preset_mal is not None:
                query_dict["mal"] = str(preset_mal)

        return HttpResponseRedirect(
            reverse(view_name, args=(lst.id, fighter.id)) + f"?{query_dict.urlencode()}"
        )

    filter_value = request.GET.get("filter", "equipment-list")
    is_equipment_list = filter_value == "equipment-list"

    # Determine whether to render preset values in the form (for next submission)
    # Render preset when: equipment-list mode, OR filter=all with no explicit al/mal in URL
    render_preset_al = is_equipment_list or "al" not in request.GET
    render_preset_mal = is_equipment_list or "mal" not in request.GET

    # Apply maximum availability level filter if provided
    mal = (
        int(request.GET.get("mal"))
        if request.GET.get("mal") and is_int(request.GET.get("mal"))
        else None
    )

    # Get equipment list IDs once - used in multiple places
    equipment_list_ids = ContentFighterEquipmentListItem.objects.filter(
        fighter__in=fighter.equipment_list_fighters
    ).values_list("equipment_id", flat=True)

    # Also include equipment from applicable expansions
    expansion_equipment = ContentEquipmentListExpansion.get_expansion_equipment(
        expansion_inputs
    )
    expansion_equipment_ids = list(expansion_equipment.values_list("id", flat=True))

    # Combine regular equipment list IDs with expansion equipment IDs
    equipment_list_ids = list(equipment_list_ids) + expansion_equipment_ids

    if is_equipment_list:
        # When equipment list is toggled and no explicit availability filter is provided,
        # show all equipment from the fighter's equipment list regardless of availability
        equipment = equipment.filter(id__in=equipment_list_ids)
        # For profile filtering later, we need to know all rarities are allowed
        als = ["C", "R", "I", "L", "E"]  # All possible rarities

        # Use expansion profiles when equipment list filter is active
        if is_weapon:
            equipment = equipment.with_expansion_profiles_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )
    else:
        # Apply availability filters (either explicit or default)
        # Note: `als` is also used later for profile filtering, so we must always set it
        als_raw = request.GET.getlist("al")
        als = [a for a in als_raw if a]
        if als:
            equipment = equipment.filter(rarity__in=set(als))
        elif als_raw:
            # Had values but all filtered out (e.g. empty string for "None") - show nothing
            equipment = equipment.none()
            als = []  # No profiles should match either
        else:
            # No parameter at all - use defaults
            als = preset_al
            equipment = equipment.filter(rarity__in=set(als))

        # Still need profiles for weapons when not in equipment list mode
        if is_weapon:
            equipment = equipment.with_profiles_for_fighter(
                fighter.equipment_list_fighter
            )

        if mal:
            # Only filter by rarity_roll for items that aren't Common
            # Common items should always be visible
            equipment = equipment.filter(Q(rarity="C") | Q(rarity_roll__lte=mal))

    # Apply maximum cost filter if provided (works in both filter modes)
    mc = (
        int(request.GET.get("mc"))
        if request.GET.get("mc") and is_int(request.GET.get("mc"))
        else None
    )
    if mc is not None:
        equipment = equipment.filter(cost_for_fighter__lte=mc)

    # If defaulting to all (house or preset), also include equipment from equipment list
    if default_to_all:
        # Filter equipment list items to match the current equipment type
        # (weapons or non-weapons) to prevent cross-type items from leaking
        # into the combine (e.g. Armour appearing on the weapons page).
        equipment_type_qs = (
            ContentEquipment.objects.with_packs(packs).weapons()
            if is_weapon
            else ContentEquipment.objects.with_packs(packs).non_weapons()
        )
        filtered_list_ids = list(
            equipment_type_qs.filter(id__in=equipment_list_ids).values_list(
                "id", flat=True
            )
        )

        # When category filter is active, also filter equipment list items by
        # the selected categories to prevent house-restricted items from being
        # re-added via the combine (e.g. Ancestry items via squat legacy).
        if cats and "all" not in cats:
            filtered_list_ids = list(
                ContentEquipment.objects.with_packs(packs)
                .filter(id__in=filtered_list_ids, category_id__in=cats)
                .values_list("id", flat=True)
            )

        # Combine equipment and equipment_list_items using a single filter with Q
        combined_equipment_qs = ContentEquipment.objects.with_packs(packs).filter(
            Q(id__in=equipment.values("id")) | Q(id__in=filtered_list_ids)
        )

        if is_weapon:
            equipment = combined_equipment_qs.with_expansion_cost_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            ).with_expansion_profiles_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )
        else:
            equipment = combined_equipment_qs.with_expansion_cost_for_fighter(
                fighter.equipment_list_fighter, expansion_inputs
            )

        # Re-apply cost filter after re-annotation
        if mc is not None:
            equipment = equipment.filter(cost_for_fighter__lte=mc)

    # Create assignment objects
    assigns = []
    for item in equipment:
        if is_weapon:
            # Get profiles from all equipment list fighters (legacy and base)
            profiles = []
            for ef in fighter.equipment_list_fighters:
                profiles.extend(item.profiles_for_fighter(ef))

            # Apply profile filtering based on availability
            profiles = [
                profile
                for profile in profiles
                # Keep standard profiles
                if profile.cost == 0
                # They have an Al that matches the filter, and no roll value
                or (not profile.rarity_roll and profile.rarity in als)
                # They have an Al that matches the filter, and a roll
                or (
                    profile.rarity_roll
                    and profile.rarity in als
                    and (
                        # If mal is set, check if profile passes the threshold
                        (mal and profile.rarity_roll <= mal)
                        # If mal is not set, show all profiles with matching rarity
                        or not mal
                    )
                )
            ]

            # If equipment list filter is active, further filter to only profiles on the equipment list
            if is_equipment_list:
                # Get weapon profiles that are specifically on the equipment list
                equipment_list_profiles = (
                    ContentFighterEquipmentListItem.objects.filter(
                        fighter__in=fighter.equipment_list_fighters,
                        equipment=item,
                        weapon_profile__isnull=False,
                    ).values_list("weapon_profile_id", flat=True)
                )

                # Also get weapon profiles from expansions
                # Get applicable expansions using existing expansion_inputs
                applicable_expansions = (
                    ContentEquipmentListExpansion.get_applicable_expansions(
                        expansion_inputs
                    )
                )

                # Get weapon profiles from expansion items
                expansion_profiles = ContentEquipmentListExpansionItem.objects.filter(
                    expansion__in=applicable_expansions,
                    equipment=item,
                    weapon_profile__isnull=False,
                ).values_list("weapon_profile_id", flat=True)

                # Combine both sets of profiles
                all_equipment_list_profiles = set(equipment_list_profiles) | set(
                    expansion_profiles
                )

                profiles = [
                    profile
                    for profile in profiles
                    # Keep standard profiles (cost = 0)
                    if profile.cost == 0
                    # Or keep profiles that are specifically on the equipment list
                    or profile.id in all_equipment_list_profiles
                ]

            assigns.append(
                VirtualListFighterEquipmentAssignment(
                    fighter=fighter,
                    equipment=item,
                    profiles=profiles,
                )
            )
        else:
            assigns.append(
                VirtualListFighterEquipmentAssignment(
                    fighter=fighter,
                    equipment=item,
                )
            )

    context = {
        "fighter": fighter,
        "equipment": equipment,
        "categories": categories,
        "assigns": assigns,
        "list": lst,
        "error_message": error_message,
        "is_weapon": is_weapon,
        "is_equipment_list": is_equipment_list,
        "render_preset_al": render_preset_al,
        "render_preset_mal": render_preset_mal,
        "preset_al": preset_al,
        "preset_mal": preset_mal,
    }

    # Add weapons-specific context if needed
    if is_weapon:
        context["weapons"] = equipment

    return render(request, template_name, context)


@login_required
@transaction.atomic
def edit_list_fighter_assign_cost(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Edit the cost of an existing :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_assign_cost_edit.html`
    """
    lst = get_clean_list_or_404(
        List.objects.with_related_data(), id=id, owner=request.user
    )
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        # Capture old value before form.is_valid() modifies the instance
        old_total_cost_override = assignment.total_cost_override

        form = ListFighterEquipmentAssignmentCostForm(request.POST, instance=assignment)
        if form.is_valid():
            # Form's is_valid() already applied new value to assignment
            # Call handler to save and track changes via ListAction
            handle_equipment_cost_override(
                user=request.user,
                lst=lst,
                fighter=fighter,
                assignment=assignment,
                old_total_cost_override=old_total_cost_override,
                new_total_cost_override=assignment.total_cost_override,
            )

            # Log the cost update event
            log_event(
                user=request.user,
                noun=EventNoun.EQUIPMENT_ASSIGNMENT,
                verb=EventVerb.UPDATE,
                object=assignment,
                request=request,
                fighter_id=str(fighter.id),
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                equipment_name=assignment.content_equipment.name,
                field="total_cost_override",
                new_cost=assignment.total_cost_override,
            )

            return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    form = ListFighterEquipmentAssignmentCostForm(
        instance=assignment,
    )

    return render(
        request,
        "core/list_fighter_assign_cost_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "form": form,
            "error_message": error_message,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
@transaction.atomic
def delete_list_fighter_assign(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Remove a :model:`core.ListFighterEquipmentAssignment` from a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.

    **Template**

    :template:`core/list_fighter_assign_delete_confirm.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        # Store equipment name for logging before handler deletes it
        equipment_name = assignment.content_equipment.name

        try:
            # Call handler to perform business logic
            handle_equipment_removal(
                user=request.user,
                lst=lst,
                fighter=fighter,
                assignment=assignment,
                request_refund=request.POST.get("refund") == "on",
            )

            # Log the equipment deletion
            log_event(
                user=request.user,
                noun=EventNoun.EQUIPMENT_ASSIGNMENT,
                verb=EventVerb.DELETE,
                object=fighter,  # Log against the fighter since assignment is deleted
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                equipment_name=equipment_name,
            )

            return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))
        except DjangoValidationError as e:
            error_message = e.message if hasattr(e, "message") else str(e.messages[0])

    return render(
        request,
        "core/list_fighter_assign_delete_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
            "error_message": error_message,
        },
    )


@login_required
@transaction.atomic
def delete_list_fighter_gear_upgrade(
    request, id, fighter_id, assign_id, upgrade_id, back_name, action_name
):
    """
    Remove am upgrade from a :model:`core.ListFighterEquipmentAssignment` for a fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.
    ``upgrade``
        The :model:`content.ContentEquipmentUpgrade` upgrade to be removed.

    **Template**

    :template:`core/list_fighter_assign_upgrade_delete_confirm.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )
    upgrade = get_object_or_404(
        ContentEquipmentUpgrade,
        pk=upgrade_id,
    )

    default_url = reverse(back_name, args=(lst.id, fighter.id))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        # Call handler to perform business logic
        handle_equipment_component_removal(
            user=request.user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            component_type="upgrade",
            component=upgrade,
            request_refund=request.POST.get("refund") == "on",
        )

        # Log the upgrade removal
        log_event(
            user=request.user,
            noun=EventNoun.EQUIPMENT_ASSIGNMENT,
            verb=EventVerb.UPDATE,
            object=assignment,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            equipment_name=assignment.content_equipment.name,
            upgrade_removed=upgrade.name,
        )

        return safe_redirect(request, return_url, default_url)

    # Calculate upgrade cost for display
    upgrade_cost = assignment._upgrade_cost_with_override(upgrade)

    return render(
        request,
        "core/list_fighter_assign_upgrade_delete_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "upgrade": upgrade,
            "upgrade_cost": upgrade_cost,
            "action_url": action_name,
            "return_url": return_url,
        },
    )


@login_required
@transaction.atomic
def edit_list_fighter_weapon_accessories(request, id, fighter_id, assign_id):
    """
    Managed weapon accessories for a :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``accessories``
        A list of :model:`content.ContentWeaponAccessory` objects.
    ``error_message``
        None or a string describing a form error.
    ``filter``
        Filter mode - "equipment-list" or "all".
    ``search_query``
        Search query for filtering accessories.

    **Template**

    :template:`core/list_fighter_weapons_accessories_edit.html`

    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None

    # Handle adding a new accessory
    if request.method == "POST" and "accessory_id" in request.POST:
        accessory_id = request.POST.get("accessory_id")
        accessory = get_object_or_404(ContentWeaponAccessory, pk=accessory_id)

        try:
            # Call handler to handle business logic (credit spending, actions)
            result = handle_accessory_purchase(
                user=request.user,
                lst=lst,
                fighter=fighter,
                assignment=assignment,
                accessory=accessory,
            )

            messages.success(request, result.description)
        except DjangoValidationError as e:
            # Handler failed (e.g., insufficient credits)
            error_message = messages.validation(request, e)

        # Only redirect if there's no error
        if not error_message:
            # Build query parameters to preserve filters
            query_params = {}
            if request.POST.get("filter"):
                query_params["filter"] = request.POST.get("filter")
            if request.POST.get("q"):
                query_params["q"] = request.POST.get("q")
            query_string = f"?{urlencode(query_params)}" if query_params else ""

            # Redirect back to the same page with filters preserved
            return HttpResponseRedirect(
                reverse(
                    "core:list-fighter-weapon-accessories-edit",
                    args=(lst.id, fighter.id, assignment.id),
                )
                + query_string
            )

    # Handle removing accessories via form
    elif request.method == "POST":
        form = ListFighterEquipmentAssignmentAccessoriesForm(
            request.POST, instance=assignment
        )
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    # Get filter parameters
    filter_mode = request.GET.get("filter", "equipment-list")
    search_query = request.GET.get("q", "")

    # Build the accessories queryset
    if filter_mode == "equipment-list":
        # Get accessories from equipment list
        equipment_list_accessories = (
            ContentFighterEquipmentListWeaponAccessory.objects.filter(
                fighter=fighter.content_fighter
            ).values_list("weapon_accessory_id", flat=True)
        )

        accessories_qs = ContentWeaponAccessory.objects.filter(
            id__in=equipment_list_accessories
        ).with_cost_for_fighter(fighter.content_fighter)
    else:
        # Get all accessories
        accessories_qs = ContentWeaponAccessory.objects.all().with_cost_for_fighter(
            fighter.content_fighter
        )

    # Apply search filter
    if search_query:
        accessories_qs = accessories_qs.filter(name__icontains=search_query)

    # Order by name
    accessories_qs = accessories_qs.order_by("name")

    # Get accessories already on the weapon
    existing_accessory_ids = assignment.weapon_accessories_field.values_list(
        "id", flat=True
    )

    # Prepare accessories for display
    accessories = []
    for accessory in accessories_qs:
        # Calculate the actual cost for this accessory on this weapon assignment
        # TODO: this should probably be refactored to use a method on the assignment named
        #       something finishing `..._display`
        cost_int = assignment.accessory_cost_int(accessory)
        cost_display = f"{cost_int}¢" if cost_int != 0 else ""

        if accessory.id not in existing_accessory_ids:
            accessories.append(
                {
                    "id": accessory.id,
                    "name": accessory.name,
                    "cost_int": cost_int,
                    "cost_display": cost_display,
                }
            )

    form = ListFighterEquipmentAssignmentAccessoriesForm(
        instance=assignment,
    )

    return render(
        request,
        "core/list_fighter_weapons_accessories_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "form": form,
            "error_message": error_message,
            "assign": VirtualListFighterEquipmentAssignment.from_assignment(assignment),
            "accessories": accessories,
            "filter": filter_mode,
            "search_query": search_query,
            "mode": "edit",
        },
    )


@login_required
@transaction.atomic
def edit_single_weapon(request, id, fighter_id, assign_id):
    """
    Edit weapon profiles for a single :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``profiles``
        A list of available :model:`content.ContentWeaponProfile` objects.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_weapon_edit.html`

    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None

    # Handle adding a new profile
    if request.method == "POST" and "profile_id" in request.POST:
        profile_id = request.POST.get("profile_id")
        profile = get_object_or_404(
            ContentWeaponProfile, pk=profile_id, equipment=assignment.content_equipment
        )

        try:
            # Call handler to handle business logic (credit spending, actions)
            result = handle_weapon_profile_purchase(
                user=request.user,
                lst=lst,
                fighter=fighter,
                assignment=assignment,
                profile=profile,
            )

            messages.success(request, result.description)
        except DjangoValidationError as e:
            # Handler failed (e.g., insufficient credits)
            error_message = messages.validation(request, e)

        # Only redirect if there's no error
        if not error_message:
            # Redirect back to the same page
            return HttpResponseRedirect(
                reverse(
                    "core:list-fighter-weapon-edit",
                    args=(lst.id, fighter.id, assignment.id),
                )
            )

    # Get all available profiles for this weapon
    # Exclude standard (free) profiles as they're automatically included
    profiles_qs = (
        ContentWeaponProfile.objects.filter(equipment=assignment.content_equipment)
        .exclude(cost=0)
        .prefetch_related("traits")
        .order_by("cost", "name")
    )

    # Get already assigned profile IDs to filter them out from available profiles
    existing_profile_ids = set(
        assignment.weapon_profiles_field.values_list("id", flat=True)
    )

    # Build list of available profiles
    profiles = []
    for profile in profiles_qs:
        if profile.id not in existing_profile_ids:
            # Calculate the actual cost for this profile on this weapon assignment
            # Wrap the profile in VirtualWeaponProfile as expected by profile_cost_int
            virtual_profile = VirtualWeaponProfile(profile=profile)
            cost_int = assignment.profile_cost_int(virtual_profile)
            cost_display = f"{cost_int}¢" if cost_int != 0 else ""

            # Format traits as a comma-separated string
            traits_list = list(profile.traits.all())
            traits_str = (
                ", ".join([trait.name for trait in traits_list]) if traits_list else ""
            )

            profiles.append(
                {
                    "id": profile.id,
                    "name": profile.name,
                    "cost_int": cost_int,
                    "cost_display": cost_display,
                    # Use correct field names that VirtualWeaponProfile provides
                    "range_short": profile.range_short,
                    "range_long": profile.range_long,
                    "accuracy_short": profile.accuracy_short,
                    "accuracy_long": profile.accuracy_long,
                    "strength": profile.strength,
                    "armour_piercing": profile.armour_piercing,
                    "damage": profile.damage,
                    "ammo": profile.ammo,
                    "traits": traits_str,
                }
            )

    return render(
        request,
        "core/list_fighter_weapon_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": VirtualListFighterEquipmentAssignment.from_assignment(assignment),
            "profiles": profiles,
            "error_message": error_message,
        },
    )


@login_required
@transaction.atomic
def delete_list_fighter_weapon_profile(request, id, fighter_id, assign_id, profile_id):
    """
    Remove a :model:`content.ContentWeaponProfile` from a fighter :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``profile``
        The :model:`content.ContentWeaponProfile` to be removed.

    **Template**

    :template:`core/list_fighter_weapon_profile_delete.html`

    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )
    profile = get_object_or_404(
        ContentWeaponProfile,
        pk=profile_id,
    )

    if request.method == "POST":
        # Call handler to perform business logic
        handle_equipment_component_removal(
            user=request.user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            component_type="profile",
            component=profile,
            request_refund=request.POST.get("refund") == "on",
        )

        # Redirect back to the weapon edit page
        return HttpResponseRedirect(
            reverse(
                "core:list-fighter-weapon-edit",
                args=(lst.id, fighter.id, assignment.id),
            )
        )

    # Calculate profile cost for template
    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    return render(
        request,
        "core/list_fighter_weapon_profile_delete.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": VirtualListFighterEquipmentAssignment.from_assignment(assignment),
            "profile": profile,
            "profile_cost": profile_cost,
        },
    )


@login_required
@transaction.atomic
def delete_list_fighter_weapon_accessory(
    request, id, fighter_id, assign_id, accessory_id
):
    """
    Remove a :model:`content.ContentWeaponAccessory` from a fighter :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be deleted.
    ``accessory``
        The :model:`content.ContentWeaponAccessory` to be removed.

    **Template**

    :template:`core/list_fighter_weapons_accessory_delete.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )
    accessory = get_object_or_404(
        ContentWeaponAccessory,
        pk=accessory_id,
    )

    default_url = (
        reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        + f"?flash={assignment.id}#{str(fighter.id)}"
    )
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        # Call handler to perform business logic
        handle_equipment_component_removal(
            user=request.user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            component_type="accessory",
            component=accessory,
            request_refund=request.POST.get("refund") == "on",
        )

        # Log the weapon accessory removal
        log_event(
            user=request.user,
            noun=EventNoun.EQUIPMENT_ASSIGNMENT,
            verb=EventVerb.UPDATE,
            object=assignment,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            equipment_name=assignment.content_equipment.name,
            accessory_removed=accessory.name,
        )

        return safe_redirect(request, return_url, default_url)

    # Calculate accessory cost for template
    accessory_cost = assignment.accessory_cost_int(accessory)

    return render(
        request,
        "core/list_fighter_weapons_accessory_delete.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "accessory": accessory,
            "accessory_cost": accessory_cost,
            "return_url": return_url,
        },
    )


@login_required
@transaction.atomic
def edit_list_fighter_weapon_upgrade(
    request, id, fighter_id, assign_id, back_name, action_name
):
    """
    Edit the weapon upgrade of an existing :model:`core.ListFighterEquipmentAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be edited.
    ``upgrade``
        The :model:`content.ContentEquipmentUpgrade` upgrade to be added.

    **Template**

    :template:`core/list_fighter_assign_upgrade_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        form = ListFighterEquipmentAssignmentUpgradeForm(
            request.POST, instance=assignment
        )
        if form.is_valid():
            # Extract new upgrades from form
            new_upgrades = form.cleaned_data["upgrades_field"]

            try:
                # Call handler to handle business logic (credit spending, actions, upgrade update)
                result = handle_equipment_upgrade(
                    user=request.user,
                    lst=lst,
                    fighter=fighter,
                    assignment=assignment,
                    new_upgrades=list(new_upgrades),
                )
                messages.success(request, result.description)
            except DjangoValidationError as e:
                # Handler failed (e.g., insufficient credits)
                error_message = messages.validation(request, e)

            # Only redirect if there's no error
            if not error_message:
                return HttpResponseRedirect(
                    reverse(back_name, args=(lst.id, fighter.id))
                )
    else:
        form = ListFighterEquipmentAssignmentUpgradeForm(instance=assignment)

    return render(
        request,
        "core/list_fighter_assign_upgrade_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
            "form": form,
            "error_message": error_message,
        },
    )


@login_required
@transaction.atomic
def disable_list_fighter_default_assign(
    request, id, fighter_id, assign_id, action_name, back_name
):
    """
    Disable a default assignment from :model:`content.ContentFighterDefaultAssignment`.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`content.ContentFighterDefaultAssignment` to be disabled.

    **Template**

    :template:`core/list_fighter_assign_disable.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ContentFighterDefaultAssignment,
        pk=assign_id,
    )

    if request.method == "POST":
        fighter.disabled_default_assignments.add(assignment)
        fighter.save()
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_disable.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
@transaction.atomic
def convert_list_fighter_default_assign(
    request, id, fighter_id, assign_id, action_name, back_name
):
    """
    Convert a default assignment from :model:`content.ContentFighterDefaultAssignment` to a
    :model:`core.ListFighterEquipmentAssignment`.
    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` owning this equipment assignment.
    ``assign``
        The :model:`content.ContentFighterDefaultAssignment` to be converted.
    ``action_url``
        The URL to redirect to after the conversion.
    ``back_url``
        The URL to redirect back to the list fighter.

    **Template**
    :template:`core/list_fighter_assign_convert.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ContentFighterDefaultAssignment,
        pk=assign_id,
    )

    if request.method == "POST":
        fighter.convert_default_assignment(assignment)
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_convert.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
@transaction.atomic
def reassign_list_fighter_equipment(
    request, id, fighter_id, assign_id, is_weapon, back_name
):
    """
    Reassign a :model:`core.ListFighterEquipmentAssignment` to another fighter.

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` currently owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be reassigned.
    ``target_fighters``
        Available fighters to reassign to, including stash fighter.
    ``is_weapon``
        Whether this is a weapon assignment.

    **Template**

    :template:`core/list_fighter_assign_reassign.html`
    """
    lst = get_clean_list_or_404(
        List.objects.with_related_data(), id=id, owner=request.user
    )
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment.objects.with_related_data(),
        pk=assign_id,
        list_fighter=fighter,
    )

    # Prevent reassigning default assignments
    if assignment.from_default_assignment:
        messages.error(request, "Default equipment cannot be reassigned.")
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    # Get available fighters (exclude current fighter, include stash)
    target_fighters = lst.listfighter_set.filter(archived=False).exclude(id=fighter.id)

    if request.method == "POST":
        form = EquipmentReassignForm(request.POST, fighters=target_fighters)
        if form.is_valid():
            target_fighter = form.cleaned_data["target_fighter"]

            with transaction.atomic():
                # Handle the reassignment (performs update and creates ListAction/CampaignAction)
                result = handle_equipment_reassignment(
                    user=request.user,
                    lst=lst,
                    from_fighter=fighter,
                    to_fighter=target_fighter,
                    assignment=assignment,
                )

                # Log the equipment reassignment
                log_event(
                    user=request.user,
                    noun=EventNoun.EQUIPMENT_ASSIGNMENT,
                    verb=EventVerb.UPDATE,
                    object=result.assignment,
                    request=request,
                    from_fighter_name=result.from_fighter.name,
                    to_fighter_name=result.to_fighter.name,
                    equipment_name=result.assignment.content_equipment.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    action="reassigned",
                )

            messages.success(
                request,
                f"{result.assignment.content_equipment.name} reassigned to {result.to_fighter.name}.",
            )
            return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))
    else:
        form = EquipmentReassignForm(fighters=target_fighters)

    return render(
        request,
        "core/list_fighter_assign_reassign.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "form": form,
            "is_weapon": is_weapon,
            "back_url": back_name,
        },
    )


@login_required
@transaction.atomic
def sell_list_fighter_equipment(request, id, fighter_id, assign_id):
    """
    Sell equipment from a stash fighter with dice roll mechanics.

    This is a three-step flow:
    1. Selection table - choose what to sell and pricing method
    2. Dice roll & campaign action - calculate prices and create action
    3. Summary - show results

    **Context**

    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` (must be stash) owning this equipment assignment.
    ``assign``
        The :model:`core.ListFighterEquipmentAssignment` to be sold.

    **Template**

    :template:`core/list_fighter_equipment_sell.html`
    """
    lst = get_clean_list_or_404(
        List.objects.with_related_data(), id=id, owner=request.user
    )
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
    )

    # For summary step, assignment might not exist (already deleted)
    step = request.GET.get("step", "selection")
    if step == "summary":
        assignment = None
    else:
        assignment = get_object_or_404(
            ListFighterEquipmentAssignment.objects.select_related(
                "content_equipment", "list_fighter"
            ).prefetch_related(
                "weapon_profiles_field", "weapon_accessories_field", "upgrades_field"
            ),
            pk=assign_id,
            list_fighter=fighter,
        )

    # Only allow selling from stash fighters in campaign mode
    if not fighter.content_fighter.is_stash:
        messages.error(request, "Equipment can only be sold from the stash.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-gear-edit", args=(lst.id, fighter.id))
        )

    if lst.status != List.CAMPAIGN_MODE:
        messages.error(request, "Equipment can only be sold in campaign mode.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-gear-edit", args=(lst.id, fighter.id))
        )

    # Parse URL parameters to determine what's being sold (skip for summary)
    if step != "summary":
        sell_assign = request.GET.get("sell_assign") == str(assignment.id)
        sell_profiles = request.GET.getlist("sell_profile", [])
        sell_accessories = request.GET.getlist("sell_accessory", [])

    # Calculate what's being sold (skip for summary)
    items_to_sell = []

    if step != "summary" and sell_assign:
        # Selling entire assignment (equipment + upgrades)
        base_cost = assignment.content_equipment.cost_int()
        print(f"Base cost for {assignment.content_equipment.name}: {base_cost}")
        for upgrade in assignment.upgrades_field.all():
            print(f"Adding upgrade cost: {upgrade.cost_int_cached} for {upgrade.name}")
            base_cost += upgrade.cost_int_cached

        items_to_sell.append(
            {
                "type": "equipment",
                "name": assignment.content_equipment.name,
                "upgrades": list(assignment.upgrades_field.all()),
                "base_cost": base_cost,
                "total_cost": base_cost,  # Total cost including upgrades
                "assignment": assignment,
            }
        )

        # Add all profiles
        for profile in assignment.weapon_profiles_field.all():
            items_to_sell.append(
                {
                    "type": "profile",
                    "name": f"- {profile.name}",
                    "base_cost": profile.cost,
                    "total_cost": profile.cost,  # No upgrades for profiles
                    "profile": profile,
                }
            )

        # Add all accessories
        for accessory in assignment.weapon_accessories_field.all():
            items_to_sell.append(
                {
                    "type": "accessory",
                    "name": accessory.name,
                    "base_cost": accessory.cost,
                    "total_cost": accessory.cost,  # No upgrades for accessories
                    "accessory": accessory,
                }
            )
    elif step != "summary":
        # Selling individual components
        for profile_id in sell_profiles:
            profile = assignment.weapon_profiles_field.filter(id=profile_id).first()
            if profile:
                items_to_sell.append(
                    {
                        "type": "profile",
                        "name": profile.name,
                        "base_cost": profile.cost,
                        "total_cost": profile.cost,  # No upgrades for profiles
                        "profile": profile,
                    }
                )

        for accessory_id in sell_accessories:
            accessory = assignment.weapon_accessories_field.filter(
                id=accessory_id
            ).first()
            if accessory:
                items_to_sell.append(
                    {
                        "type": "accessory",
                        "name": accessory.name,
                        "base_cost": accessory.cost,
                        "total_cost": accessory.cost,  # No upgrades for accessories
                        "accessory": accessory,
                    }
                )

    # Handle the form submission
    if request.method == "POST":
        step = request.POST.get("step", "selection")

        if step == "selection":
            # Step 1: Process selection form
            forms = []
            for i, item in enumerate(items_to_sell):
                form = EquipmentSellSelectionForm(request.POST, prefix=str(i))
                forms.append((item, form))

            if all(form.is_valid() for _, form in forms):
                # Store form data in session for next step
                sell_data = []
                for item, form in forms:
                    price_method = form.cleaned_data["price_method"]
                    price_manual_value = form.cleaned_data.get("price_manual_value")
                    roll_manual_d6 = form.cleaned_data.get("roll_manual_d6")

                    sell_data.append(
                        {
                            "name": item["name"],
                            "type": item["type"],
                            "base_cost": item["base_cost"],
                            "total_cost": item.get("total_cost", item["base_cost"]),
                            "price_method": price_method,
                            "roll_manual_d6": roll_manual_d6,
                            "price_manual_value": price_manual_value,
                        }
                    )

                request.session["sell_data"] = sell_data
                request.session["sell_assign_id"] = str(assignment.id)
                request.session["sell_assign"] = sell_assign
                request.session["sell_profiles"] = sell_profiles
                request.session["sell_accessories"] = sell_accessories

                # Redirect to confirmation step
                return HttpResponseRedirect(
                    reverse(
                        "core:list-fighter-equipment-sell",
                        args=(lst.id, fighter.id, assignment.id),
                    )
                    + "?step=confirm"
                )

        elif step == "confirm":
            # Step 2: Process confirmation and create campaign action
            sell_data = request.session.get("sell_data", [])

            if sell_data:
                # Calculate prices and roll dice
                total_dice = 0
                dice_rolls = []
                total_credits = 0
                sale_items = []

                for item_data in sell_data:
                    if item_data["price_method"] == "roll_auto":
                        # Roll D6 for this item
                        roll = random.randint(1, 6)  # nosec B311 - game dice, not crypto
                        dice_rolls.append(roll)
                        total_dice += 1

                        # Calculate sale price: total cost - (roll × 10), minimum 5¢
                        sale_price = max(
                            5,
                            item_data.get("total_cost", item_data["base_cost"])
                            - (roll * 10),
                        )
                    elif item_data["price_method"] == "roll_manual":
                        roll = item_data.get("roll_manual_d6")
                        dice_rolls.append(roll)
                        total_dice += 1

                        # Calculate sale price: total cost - (roll × 10), minimum 5¢
                        sale_price = max(
                            5,
                            item_data.get("total_cost", item_data["base_cost"])
                            - (roll * 10),
                        )
                    else:
                        # Use manual (price_manual) price
                        sale_price = item_data["price_manual_value"]
                        roll = None

                    total_credits += sale_price
                    sale_items.append(
                        SaleItemDetail(
                            name=item_data["name"],
                            cost=item_data.get("total_cost", item_data["base_cost"]),
                            sale_price=sale_price,
                            dice_roll=roll,
                        )
                    )

                # Gather profiles and accessories to remove
                sell_assign = request.session.get("sell_assign")
                profiles_to_remove = []
                accessories_to_remove = []

                if not sell_assign:
                    for profile_id in request.session.get("sell_profiles", []):
                        profile = assignment.weapon_profiles_field.filter(
                            id=profile_id
                        ).first()
                        if profile:
                            profiles_to_remove.append(profile)

                    for accessory_id in request.session.get("sell_accessories", []):
                        accessory = assignment.weapon_accessories_field.filter(
                            id=accessory_id
                        ).first()
                        if accessory:
                            accessories_to_remove.append(accessory)

                # Call the handler
                try:
                    result = handle_equipment_sale(
                        user=request.user,
                        lst=lst,
                        fighter=fighter,
                        assignment=assignment,
                        sell_assignment=sell_assign,
                        profiles_to_remove=profiles_to_remove,
                        accessories_to_remove=accessories_to_remove,
                        sale_items=sale_items,
                        dice_count=total_dice,
                        dice_rolls=dice_rolls,
                    )
                except DjangoValidationError as e:
                    messages.validation(request, e)
                    return HttpResponseRedirect(
                        reverse(
                            "core:list-fighter-equipment-sell",
                            args=(lst.id, fighter.id, assignment.id),
                        )
                        + "?step=selection"
                    )

                # Log the equipment sale event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST,
                    verb=EventVerb.UPDATE,
                    object=lst,
                    request=request,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    action="equipment_sold",
                    credits_gained=result.total_sale_credits,
                    items_sold=len(sale_items),
                    sale_summary=result.description,
                )

                # Store results in session for summary (convert to dicts for JSON serialization)
                request.session["sale_results"] = {
                    "total_credits": result.total_sale_credits,
                    "sale_details": [
                        {
                            "name": item.name,
                            "total_cost": item.cost,  # Template expects total_cost
                            "sale_price": item.sale_price,
                            "dice_roll": item.dice_roll,
                        }
                        for item in sale_items
                    ],
                    "dice_rolls": dice_rolls,
                }

                # Clear sell data
                request.session.pop("sell_data", None)
                request.session.pop("sell_assign_id", None)
                request.session.pop("sell_assign", None)
                request.session.pop("sell_profiles", None)
                request.session.pop("sell_accessories", None)

                # Redirect to summary
                return HttpResponseRedirect(
                    reverse(
                        "core:list-fighter-equipment-sell",
                        args=(lst.id, fighter.id, assign_id),
                    )
                    + "?step=summary"
                )

    # Determine which step we're on
    step = request.GET.get("step", "selection")

    if step == "selection":
        # Step 1: Show selection form
        forms = []
        for i, item in enumerate(items_to_sell):
            form = EquipmentSellSelectionForm(prefix=str(i))
            forms.append((item, form))

        context = {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "forms": forms,
            "step": "selection",
        }

    elif step == "confirm":
        # Step 2: Show confirmation
        sell_data = request.session.get("sell_data", [])

        context = {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "sell_data": sell_data,
            "step": "confirm",
        }

    elif step == "summary":
        # Step 3: Show summary
        sale_results = request.session.get("sale_results", {})

        # Clear results from session
        if "sale_results" in request.session:
            del request.session["sale_results"]

        context = {
            "list": lst,
            "fighter": fighter,
            "sale_results": sale_results,
            "step": "summary",
        }

    else:
        # Invalid step, redirect to selection
        return HttpResponseRedirect(
            reverse(
                "core:list-fighter-equipment-sell",
                args=(lst.id, fighter.id, assignment.id),
            )
        )

    return render(request, "core/list_fighter_equipment_sell.html", context)
