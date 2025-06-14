import random
import uuid
from typing import Literal, Optional
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import generic
from pydantic import BaseModel, field_validator

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentHouse,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentSkill,
    ContentSkillCategory,
    ContentWeaponAccessory,
)
from gyrinx.core.forms.advancement import (
    AdvancementDiceChoiceForm,
    AdvancementTypeForm,
    SkillCategorySelectionForm,
    SkillSelectionForm,
)
from gyrinx.core.forms.list import (
    AddInjuryForm,
    CloneListFighterForm,
    CloneListForm,
    EditFighterStateForm,
    EditListFighterNarrativeForm,
    EditListForm,
    ListFighterEquipmentAssignmentAccessoriesForm,
    ListFighterEquipmentAssignmentCostForm,
    ListFighterEquipmentAssignmentForm,
    ListFighterEquipmentAssignmentUpgradeForm,
    ListFighterForm,
    ListFighterSkillsForm,
    NewListForm,
)
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterAdvancement,
    ListFighterEquipmentAssignment,
    ListFighterInjury,
    ListFighterPsykerPowerAssignment,
    VirtualListFighterEquipmentAssignment,
    VirtualListFighterPsykerPowerAssignment,
)
from gyrinx.core.views import make_query_params_str
from gyrinx.models import QuerySetOf, is_int, is_valid_uuid


class ListsListView(generic.ListView):
    """
    Display a list of public :model:`core.List` objects.

    **Context**

    ``lists``
        A list of :model:`core.List` objects where `public=True`.

    **Template**

    :template:`core/lists.html`
    """

    template_name = "core/lists.html"
    context_object_name = "lists"

    def get_queryset(self):
        """
        Return :model:`core.List` objects that are public and in list building mode.
        Campaign mode lists are only visible within their campaigns.
        Archived lists are excluded from this view.
        """
        return List.objects.filter(
            public=True, status=List.LIST_BUILDING, archived=False
        )


class ListDetailView(generic.DetailView):
    """
    Display a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.
    ``recent_actions``
        Recent campaign actions related to this list (if in campaign mode).
    ``campaign_resources``
        Resources held by this list in the campaign (if in campaign mode).
    ``held_assets``
        Assets held by this list in the campaign (if in campaign mode).

    **Template**

    :template:`core/list.html`
    """

    template_name = "core/list.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.
        """
        return get_object_or_404(List, id=self.kwargs["id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        list_obj = context["list"]

        # If list is in campaign mode and has a campaign, fetch recent actions
        if list_obj.is_campaign_mode and list_obj.campaign:
            from gyrinx.core.models.campaign import CampaignAction

            # Get recent actions for this specific list only
            recent_actions = (
                CampaignAction.objects.filter(campaign=list_obj.campaign)
                .filter(list=list_obj)
                .select_related("user", "list")
                .order_by("-created")[:5]
            )

            context["recent_actions"] = recent_actions

            # Get campaign resources held by this list
            campaign_resources = list_obj.campaign_resources.filter(
                amount__gt=0
            ).select_related("resource_type")
            context["campaign_resources"] = campaign_resources

            # Get assets held by this list
            held_assets = list_obj.held_assets.select_related("asset_type")
            context["held_assets"] = held_assets

        return context


class ListAboutDetailView(generic.DetailView):
    """
    Display a narrative view of a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.

    **Template**

    :template:`core/list_about.html`
    """

    template_name = "core/list_about.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.
        """
        return get_object_or_404(List, id=self.kwargs["id"])


class ListPrintView(generic.DetailView):
    """
    Display a printable view of a single :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.

    **Template**

    :template:`core/list_print.html`
    """

    template_name = "core/list_print.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.
        """
        return get_object_or_404(List, id=self.kwargs["id"])


@login_required
def new_list(request):
    """
    Create a new :model:`core.List` owned by the current user.

    **Context**

    ``form``
        A NewListForm for entering the name and details of the new list.
    ``houses``
        A queryset of :model:`content.ContentHouse` objects, possibly used in the form display.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_new.html`
    """
    houses = ContentHouse.objects.all()

    error_message = None
    if request.method == "POST":
        form = NewListForm(request.POST)
        if form.is_valid():
            list_ = form.save(commit=False)
            list_.owner = request.user
            list_.save()
            return HttpResponseRedirect(reverse("core:list", args=(list_.id,)))
    else:
        form = NewListForm(
            initial={
                "name": request.GET.get("name", ""),
            }
        )

    return render(
        request,
        "core/list_new.html",
        {"form": form, "houses": houses, "error_message": error_message},
    )


@login_required
def edit_list(request, id):
    """
    Edit an existing :model:`core.List` owned by the current user.

    **Context**

    ``form``
        A EditListForm for editing the list's details.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_edit.html`
    """
    list_ = get_object_or_404(List, id=id, owner=request.user)

    error_message = None
    if request.method == "POST":
        form = EditListForm(request.POST, instance=list_)
        if form.is_valid():
            updated_list = form.save(commit=False)
            updated_list.save()
            return HttpResponseRedirect(reverse("core:list", args=(list_.id,)))
    else:
        form = EditListForm(instance=list_)

    return render(
        request,
        "core/list_edit.html",
        {"form": form, "error_message": error_message},
    )


@login_required
def edit_list_credits(request, id):
    """
    Modify credits for a :model:`core.List` in campaign mode.

    **Context**

    ``form``
        An EditListCreditsForm for modifying list credits.
    ``list``
        The :model:`core.List` whose credits are being modified.

    **Template**

    :template:`core/list_credits_edit.html`
    """
    from django.contrib import messages

    from gyrinx.core.forms.list import EditListCreditsForm
    from gyrinx.core.models.campaign import CampaignAction

    # Allow both list owner and campaign owner to modify credits
    lst = get_object_or_404(List, id=id)

    # Check permissions - must be list owner or campaign owner
    if lst.owner != request.user:
        if not (lst.campaign and lst.campaign.owner == request.user):
            messages.error(
                request, "You don't have permission to modify credits for this list."
            )
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(
            request, "Credits can only be tracked for lists in campaign mode."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = EditListCreditsForm(request.POST, lst=lst)
        if form.is_valid():
            operation = form.cleaned_data["operation"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data.get("description", "")

            # Validate the operation
            if operation == "spend" and amount > lst.credits_current:
                form.add_error(
                    "amount",
                    f"Cannot spend more credits than available ({lst.credits_current}¢)",
                )
            elif operation == "reduce" and amount > lst.credits_current:
                form.add_error(
                    "amount",
                    f"Cannot reduce credits below zero (current: {lst.credits_current}¢)",
                )
            elif operation == "reduce" and amount > lst.credits_earned:
                form.add_error(
                    "amount",
                    f"Cannot reduce all time credits below zero (all time: {lst.credits_earned}¢)",
                )
            else:
                # Apply the credit change
                if operation == "add":
                    lst.credits_current += amount
                    lst.credits_earned += amount
                    action_desc = f"Added {amount}¢"
                    outcome = f"+{amount}¢ (to {lst.credits_current}¢)"
                elif operation == "spend":
                    lst.credits_current -= amount
                    action_desc = f"Spent {amount}¢"
                    outcome = f"-{amount}¢ (to {lst.credits_current}¢)"
                else:  # reduce
                    lst.credits_current -= amount
                    lst.credits_earned -= amount
                    action_desc = f"Reduced {amount}¢"
                    outcome = f"-{amount}¢ (to {lst.credits_current}¢, all time: {lst.credits_earned}¢)"

                if description:
                    action_desc += f": {description}"

                lst.save()

                # Log to campaign action
                if lst.campaign:
                    CampaignAction.objects.create(
                        user=request.user,
                        owner=request.user,
                        campaign=lst.campaign,
                        list=lst,
                        description=action_desc,
                        outcome=outcome,
                    )

                messages.success(request, f"Credits updated for {lst.name}")
                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = EditListCreditsForm(lst=lst)

    return render(
        request,
        "core/list_credits_edit.html",
        {
            "form": form,
            "list": lst,
        },
    )


@login_required
def archive_list(request, id):
    """
    Archive or unarchive a :model:`core.List`.

    **Context**

    ``list``
        The :model:`core.List` to be archived or unarchived.
    ``is_in_active_campaign``
        Boolean indicating if the list is in an active campaign.
    ``active_campaigns``
        List of active campaigns this list is participating in.

    **Template**

    :template:`core/list_archive.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)

    # Check if the list is in any active campaigns
    active_campaigns = lst.campaigns.filter(status="in_progress")
    is_in_active_campaign = active_campaigns.exists()

    if request.method == "POST":
        from gyrinx.core.models.campaign import CampaignAction

        if request.POST.get("archive") == "1":
            lst.archive()

            # Add campaign action log entries for active campaigns
            for campaign in active_campaigns:
                CampaignAction.objects.create(
                    campaign=campaign,
                    user=request.user,
                    list=lst,
                    description=f"Gang '{lst.name}' has been archived by its owner",
                    owner=request.user,
                )
        elif lst.archived:
            lst.unarchive()

            # Add campaign action log entries for active campaigns when unarchiving
            for campaign in active_campaigns:
                CampaignAction.objects.create(
                    campaign=campaign,
                    user=request.user,
                    list=lst,
                    description=f"Gang '{lst.name}' has been unarchived by its owner",
                    owner=request.user,
                )

        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_archive.html",
        {
            "list": lst,
            "is_in_active_campaign": is_in_active_campaign,
            "active_campaigns": active_campaigns,
        },
    )


@login_required
def clone_list(request, id):
    """
    Clone an existing :model:`core.List` owned by any user.

    **Context**

    ``form``
        A CloneListForm for entering the name and details of the new list.
    ``list``
        The :model:`core.List` to be cloned.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_clone.html`
    """
    # You can clone a list owned by another user
    list_ = get_object_or_404(List, id=id)

    error_message = None
    if request.method == "POST":
        form = CloneListForm(request.POST, instance=list_)
        if form.is_valid():
            new_list = list_.clone(
                name=form.cleaned_data["name"],
                owner=request.user,
                public=form.cleaned_data["public"],
            )
            new_list.save()
            return HttpResponseRedirect(reverse("core:list", args=(new_list.id,)))
    else:
        form = CloneListForm(
            instance=list_,
            initial={
                "name": f"{list_.name} (Clone)",
            },
        )

    return render(
        request,
        "core/list_clone.html",
        {"form": form, "list": list_, "error_message": error_message},
    )


@login_required
def new_list_fighter(request, id):
    """
    Add a new :model:`core.ListFighter` to an existing :model:`core.List`.

    **Context**

    ``form``
        A ListFighterForm for adding a new fighter.
    ``list``
        The :model:`core.List` to which this fighter will be added.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_new.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = ListFighter(list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = ListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            fighter = form.save(commit=False)
            fighter.list = lst
            fighter.owner = lst.owner
            fighter.save()
            query_params = urlencode(dict(flash=fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )
    else:
        form = ListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_new.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def edit_list_fighter(request, id, fighter_id):
    """
    Edit an existing :model:`core.ListFighter` within a :model:`core.List`.

    **Context**

    ``form``
        A ListFighterForm for editing fighter details.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_edit.html`
    """
    print(f"Editing fighter {fighter_id} in list {id}")
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = ListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            fighter = form.save(commit=False)
            fighter.list = lst
            fighter.owner = lst.owner
            fighter.save()
            query_params = urlencode(dict(flash=fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,))
                + f"?{query_params}"
                + f"#{str(fighter.id)}"
            )
    else:
        form = ListFighterForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_edit.html",
        {"form": form, "list": lst, "error_message": error_message},
    )


@login_required
def clone_list_fighter(request: HttpRequest, id, fighter_id):
    """
    Clone an existing :model:`core.ListFighter` to the same or another :model:`core.List`.

    **Context**

    ``form``
        A CloneListFighterForm for entering the name and details of the new fighter.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``fighter``
        The :model:`core.ListFighter` to be cloned.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_clone.html`
    """
    lst = get_object_or_404(List, id=id)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst)

    error_message = None
    if request.method == "POST":
        form = CloneListFighterForm(request.POST, instance=fighter)
        if form.is_valid():
            new_fighter = fighter.clone(
                name=form.cleaned_data["name"],
                content_fighter=form.cleaned_data["content_fighter"],
                list=form.cleaned_data["list"],
            )
            new_fighter.save()
            query_params = urlencode(dict(flash=new_fighter.id))
            return HttpResponseRedirect(
                reverse("core:list", args=(new_fighter.list.id,))
                + f"?{query_params}"
                + f"#{str(new_fighter.id)}"
            )
    else:
        form = CloneListFighterForm(
            instance=fighter,
            initial={"name": f"{fighter.name} (Clone)"},
            user=request.user,
        )

    return render(
        request,
        "core/list_fighter_clone.html",
        {"form": form, "list": lst, "fighter": fighter, "error_message": error_message},
    )


@login_required
def edit_list_fighter_skills(request, id, fighter_id):
    """
    Edit the skills of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A ListFighterSkillsForm for selecting fighter skills.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_skills_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = ListFighterSkillsForm(request.POST, instance=fighter)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
            )
    else:
        form = ListFighterSkillsForm(instance=fighter)

    skill_cats = ContentSkillCategory.objects.filter(restricted=False).annotate(
        primary=Exists(
            ContentSkillCategory.primary_fighters.through.objects.filter(
                contentskillcategory_id=OuterRef("pk"),
                contentfighter_id=fighter.content_fighter.id,
            )
        ),
        secondary=Exists(
            ContentSkillCategory.secondary_fighters.through.objects.filter(
                contentskillcategory_id=OuterRef("pk"),
                contentfighter_id=fighter.content_fighter.id,
            )
        ),
    )
    special_cats = fighter.content_fighter.house.skill_categories.all().annotate(
        primary=Exists(
            ContentSkillCategory.primary_fighters.through.objects.filter(
                contentskillcategory_id=OuterRef("pk"),
                contentfighter_id=fighter.content_fighter.id,
            )
        ),
        secondary=Exists(
            ContentSkillCategory.secondary_fighters.through.objects.filter(
                contentskillcategory_id=OuterRef("pk"),
                contentfighter_id=fighter.content_fighter.id,
            )
        ),
    )
    n_cats = skill_cats.count() + special_cats.count()

    return render(
        request,
        "core/list_fighter_skills_edit.html",
        {
            "form": form,
            "list": lst,
            "error_message": error_message,
            "n_cats": n_cats,
            "skill_cats": list(skill_cats),
            "special_cats": list(special_cats),
        },
    )


@login_required
def edit_list_fighter_powers(request, id, fighter_id):
    """
    Edit the psyker powers of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A ListFighterPowersForm for selecting fighter powers.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_psyker_powers_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        power_id = request.POST.get("psyker_power_id", None)
        if not power_id:
            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )

        if request.POST.get("action") == "remove":
            kind = request.POST.get("assign_kind")
            if kind == "default":
                default_assign = get_object_or_404(
                    ContentFighterPsykerPowerDefaultAssignment,
                    psyker_power=power_id,
                    fighter=fighter.content_fighter_cached,
                )
                fighter.disabled_pskyer_default_powers.add(default_assign)
                fighter.save()
                return HttpResponseRedirect(
                    reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
                )
            elif kind == "assigned":
                assign = get_object_or_404(
                    ListFighterPsykerPowerAssignment,
                    psyker_power=power_id,
                    list_fighter=fighter,
                )
                assign.delete()
                return HttpResponseRedirect(
                    reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
                )
            else:
                error_message = "Invalid action."
        elif request.POST.get("action") == "add":
            power = get_object_or_404(
                ContentPsykerPower,
                id=power_id,
            )
            assign = ListFighterPsykerPowerAssignment(
                list_fighter=fighter,
                psyker_power=power,
            )
            assign.save()
            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )

    # TODO: A fair bit of this logic should live in the model, or a manager method of some kind
    disabled_defaults = fighter.disabled_pskyer_default_powers.values("id")
    powers: QuerySetOf[ContentPsykerPower] = (
        ContentPsykerPower.objects.filter(
            # Get powers via disciplines that are are assigned, or are generic...
            Q(
                discipline__in=ContentPsykerDiscipline.objects.filter(
                    Q(fighter_assignments__fighter=fighter.content_fighter_cached)
                    | Q(generic=True)
                ).distinct()
            )
            # ...and get powers that are assigned to this fighter by default
            | Q(
                fighter_assignments__fighter=fighter.content_fighter_cached,
            )
        )
        .distinct()
        .prefetch_related("discipline")
        .annotate(
            assigned_direct=Exists(
                ListFighterPsykerPowerAssignment.objects.filter(
                    list_fighter=fighter,
                    psyker_power=OuterRef("pk"),
                ).values("psyker_power_id")
            ),
            assigned_default=Exists(
                ContentFighterPsykerPowerDefaultAssignment.objects.filter(
                    fighter=fighter.content_fighter_cached,
                    psyker_power=OuterRef("pk"),
                )
                .exclude(id__in=disabled_defaults)
                .values("psyker_power_id")
            ),
        )
    )

    # TODO: Re-querying this is inefficient, but it's ok for now.
    assigns = []
    for power in powers:
        if power.assigned_direct:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment.from_assignment(
                    ListFighterPsykerPowerAssignment(
                        list_fighter=fighter,
                        psyker_power=power,
                    ),
                )
            )
        elif power.assigned_default:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment.from_default_assignment(
                    ContentFighterPsykerPowerDefaultAssignment(
                        fighter=fighter.content_fighter_cached,
                        psyker_power=power,
                    ),
                    fighter=fighter,
                )
            )
        else:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment(
                    fighter=fighter, psyker_power=power
                )
            )

    return render(
        request,
        "core/list_fighter_psyker_powers_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "powers": powers,
            "assigns": assigns,
            "error_message": error_message,
        },
    )


@login_required
def edit_list_fighter_narrative(request, id, fighter_id):
    """
    Edit the narrative of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A EditListFighterNarrativeForm for editing fighter narrative.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_narrative_edit.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    error_message = None
    if request.method == "POST":
        form = EditListFighterNarrativeForm(request.POST, instance=fighter)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list-about", args=(lst.id,)) + f"#about-{str(fighter.id)}"
            )
    else:
        form = EditListFighterNarrativeForm(instance=fighter)

    return render(
        request,
        "core/list_fighter_narrative_edit.html",
        {
            "form": form,
            "list": lst,
            "error_message": error_message,
        },
    )


@login_required
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
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    view_name = (
        "core:list-fighter-weapons-edit" if is_weapon else "core:list-fighter-gear-edit"
    )
    template_name = (
        "core/list_fighter_weapons_edit.html"
        if is_weapon
        else "core/list_fighter_gear_edit.html"
    )

    error_message = None
    if request.method == "POST":
        instance = ListFighterEquipmentAssignment(list_fighter=fighter)
        form = ListFighterEquipmentAssignmentForm(request.POST, instance=instance)
        if form.is_valid():
            assign: ListFighterEquipmentAssignment = form.save(commit=False)

            # If this is in campaign, we need to take credits from the list
            if lst.campaign and assign.cost_int() > lst.credits_current:
                error_message = "Insufficient funds."
            else:
                assign.save()
                form.save_m2m()

                if lst.campaign:
                    # If this is a stash, we need to take credits from the list
                    lst.credits_current -= assign.cost_int()
                    lst.save()

                    description = f"Bought {assign.content_equipment.name} for {fighter.name} ({assign.cost_int()}¢)"

                    # Spend credits and create campaign action
                    CampaignAction.objects.create(
                        user=request.user,
                        owner=request.user,
                        campaign=lst.campaign,
                        list=lst,
                        description=description,
                        outcome=f"Credits remaining: {lst.credits_current}¢",
                    )

                messages.success(request, description)

                query_params = make_query_params_str(
                    flash=instance.id,
                    filter=request.POST.get("filter"),
                    q=request.POST.get("q"),
                )
                return HttpResponseRedirect(
                    reverse(view_name, args=(lst.id, fighter.id))
                    + f"?{query_params}"
                    + f"#{str(fighter.id)}"
                )

    # Get the appropriate equipment
    if is_weapon:
        equipment = (
            ContentEquipment.objects.weapons()
            .with_cost_for_fighter(fighter.equipment_list_fighter)
            .with_profiles_for_fighter(fighter.equipment_list_fighter)
        )
        search_vector = SearchVector(
            "name", "category__name", "contentweaponprofile__name"
        )
    else:
        equipment = ContentEquipment.objects.non_weapons().with_cost_for_fighter(
            fighter.equipment_list_fighter
        )
        search_vector = SearchVector("name", "category__name")

    # Get categories for this equipment type
    categories = (
        ContentEquipmentCategory.objects.filter(id__in=equipment.values("category_id"))
        .distinct()
        .order_by("name")
    )

    # Filter by category if specified
    cats = (
        [
            cat
            for cat in request.GET.getlist("cat", list())
            if cat and is_valid_uuid(cat)
        ]
        if not is_weapon
        else request.GET.getlist("cat", list())
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

    # Filter by availability level
    als = request.GET.getlist("al", ["C", "R"])
    if request.GET.get("filter", None) in [None, "", "equipment-list"]:
        # Always show Exclusive in equipment lists
        als += ["E"]
        equipment = equipment.exclude(
            ~Q(
                id__in=ContentFighterEquipmentListItem.objects.filter(
                    fighter=fighter.equipment_list_fighter
                ).values("equipment_id")
            )
        )

    equipment = equipment.filter(rarity__in=set(als))

    # Apply maximum availability level filter if provided
    mal = (
        int(request.GET.get("mal"))
        if request.GET.get("mal") and is_int(request.GET.get("mal"))
        else None
    )
    if mal:
        # Only filter by rarity_roll for items that aren't Common
        # Common items should always be visible
        equipment = equipment.filter(Q(rarity="C") | Q(rarity_roll__lte=mal))

    # Create assignment objects
    assigns = []
    for item in equipment:
        if is_weapon:
            profiles = item.profiles_for_fighter(fighter.equipment_list_fighter)

            # If equipment list filter is active, only show profiles that are on the equipment list
            if request.GET.get("filter", None) in [None, "", "equipment-list"]:
                # Get weapon profiles that are specifically on the equipment list
                equipment_list_profiles = (
                    ContentFighterEquipmentListItem.objects.filter(
                        fighter=fighter.equipment_list_fighter,
                        equipment=item,
                        weapon_profile__isnull=False,
                    ).values_list("weapon_profile_id", flat=True)
                )

                profiles = [
                    profile
                    for profile in profiles
                    # Keep standard profiles (cost = 0)
                    if profile.cost == 0
                    # Or keep profiles that are specifically on the equipment list
                    or profile.id in equipment_list_profiles
                ]
            else:
                # Standard filtering when equipment list filter is not active
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
    }

    # Add weapons-specific context if needed
    if is_weapon:
        context["weapons"] = equipment

    return render(request, template_name, context)


@login_required
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
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        form = ListFighterEquipmentAssignmentCostForm(request.POST, instance=assignment)
        if form.is_valid():
            form.save()
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
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )

    if request.method == "POST":
        assignment.delete()
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_delete_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
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
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )
    upgrade = get_object_or_404(
        ContentEquipmentUpgrade,
        pk=upgrade_id,
    )

    if request.method == "POST":
        assignment.upgrade = None
        assignment.upgrades_field.remove(upgrade)
        assignment.save()
        return HttpResponseRedirect(reverse(back_name, args=(lst.id, fighter.id)))

    return render(
        request,
        "core/list_fighter_assign_upgrade_delete_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "assign": assignment,
            "upgrade": upgrade,
            "action_url": action_name,
            "back_url": back_name,
        },
    )


@login_required
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

    **Template**

    :template:`core/list_fighter_weapons_accessories_edit.html`

    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )

    error_message = None
    if request.method == "POST":
        form = ListFighterEquipmentAssignmentAccessoriesForm(
            request.POST, instance=assignment
        )
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    # TODO: Exclude accessories that cannot be added to this weapon
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
        },
    )


@login_required
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
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )
    accessory = get_object_or_404(
        ContentWeaponAccessory,
        pk=accessory_id,
    )

    if request.method == "POST":
        assignment.weapon_accessories_field.remove(accessory)
        return HttpResponseRedirect(
            reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_weapons_accessory_delete.html",
        {"list": lst, "fighter": fighter, "assign": assignment, "accessory": accessory},
    )


@login_required
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
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        pk=assign_id,
        list_fighter=fighter,
    )

    if request.method == "POST":
        form = ListFighterEquipmentAssignmentUpgradeForm(
            request.POST, instance=assignment
        )
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
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
        },
    )


@login_required
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
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
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
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
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
def archive_list_fighter(request, id, fighter_id):
    """
    Archive or unarchive a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be archived or unarchived.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_archive.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    if request.method == "POST":
        if request.POST.get("archive") == "1":
            fighter.archive()
        elif fighter.archived:
            fighter.unarchive()
        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{str(fighter.id)}"
        )

    return render(
        request,
        "core/list_fighter_archive.html",
        {"fighter": fighter, "list": lst},
    )


@login_required
def delete_list_fighter(request, id, fighter_id):
    """
    Delete a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` to be deleted.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_delete.html`
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    if request.method == "POST":
        fighter.delete()
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_delete.html",
        {"fighter": fighter, "list": lst},
    )


def embed_list_fighter(request, id, fighter_id):
    """
    Display a single :model:`core.ListFighter` object in an embedded view.

    **Context**

    ``fighter``
        The requested :model:`core.ListFighter` object.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_embed.html`
    """
    lst = get_object_or_404(List, id=id)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    return render(
        request,
        "core/list_fighter_embed.html",
        {"fighter": fighter, "list": lst},
    )


class ListArchivedFightersView(generic.ListView):
    """
    Display a page with archived :model:`core.ListFighter` objects within a given :model:`core.List`.

    **Context**

    ``list``
        The requested :model:`core.List` object (retrieved by ID).

    **Template**

    :template:`core/list_archived_fighters.html`
    """

    template_name = "core/list_archived_fighters.html"
    context_object_name = "list"

    def get_queryset(self):
        """
        Retrieve the :model:`core.List` by its `id`, ensuring it's owned by the current user.
        """
        return get_object_or_404(List, id=self.kwargs["id"], owner=self.request.user)


@login_required
def list_fighter_injuries_edit(request, id, fighter_id):
    """
    Edit injuries for a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` whose injuries are being managed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_injuries_edit.html`
    """
    from django.contrib import messages

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(
            request, "Injuries can only be managed for fighters in campaign mode."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_injuries_edit.html",
        {
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def list_fighter_state_edit(request, id, fighter_id):
    """
    Edit the injury state of a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An EditFighterStateForm for changing the fighter's state.
    ``fighter``
        The :model:`core.ListFighter` whose state is being changed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_state_edit.html`
    """
    from django.contrib import messages

    from gyrinx.core.models.campaign import CampaignAction

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(request, "Fighter state can only be managed in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = EditFighterStateForm(request.POST, current_state=fighter.injury_state)
        if form.is_valid():
            old_state = fighter.get_injury_state_display()
            new_state = form.cleaned_data["fighter_state"]

            # Only update if state actually changed
            if fighter.injury_state != new_state:
                fighter.injury_state = new_state
                fighter.save()

                new_state_display = dict(ListFighter.INJURY_STATE_CHOICES)[new_state]

                # Log to campaign action
                if lst.campaign:
                    description = f"State Change: {fighter.name} changed from {old_state} to {new_state_display}"
                    if form.cleaned_data.get("reason"):
                        description += f" - {form.cleaned_data['reason']}"

                    CampaignAction.objects.create(
                        user=request.user,
                        owner=request.user,
                        campaign=lst.campaign,
                        list=lst,
                        description=description,
                        outcome=f"{fighter.name} is now {new_state_display}",
                    )

                messages.success(
                    request, f"Updated {fighter.name}'s state to {new_state_display}"
                )
            else:
                messages.info(request, "Fighter state was not changed.")

            return HttpResponseRedirect(
                reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
            )
    else:
        form = EditFighterStateForm(current_state=fighter.injury_state)

    return render(
        request,
        "core/list_fighter_state_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def list_fighter_add_injury(request, id, fighter_id):
    """
    Add an injury to a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An AddInjuryForm for selecting the injury to add.
    ``fighter``
        The :model:`core.ListFighter` being injured.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_add_injury.html`
    """
    from django.contrib import messages

    from gyrinx.core.models.campaign import CampaignAction

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(
            request, "Injuries can only be added to fighters in campaign mode."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = AddInjuryForm(request.POST, fighter=fighter)
        if form.is_valid():
            injury = ListFighterInjury.objects.create_with_user(
                user=request.user,
                fighter=fighter,
                injury=form.cleaned_data["injury"],
                notes=form.cleaned_data.get("notes", ""),
                owner=request.user,
            )

            # Update fighter state
            fighter.injury_state = form.cleaned_data["fighter_state"]
            fighter.save()

            # Log to campaign action
            if lst.campaign:
                description = f"Injury: {fighter.name} suffered {injury.injury.name}"
                if form.cleaned_data.get("notes"):
                    description += f" - {form.cleaned_data['notes']}"

                # Update outcome to show fighter state
                fighter_state_display = dict(ListFighter.INJURY_STATE_CHOICES)[
                    fighter.injury_state
                ]
                outcome = f"{fighter.name} was put into {fighter_state_display}"

                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=lst.campaign,
                    list=lst,
                    description=description,
                    outcome=outcome,
                )

            messages.success(
                request, f"Added injury '{injury.injury.name}' to {fighter.name}"
            )
            return HttpResponseRedirect(
                reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
            )
    else:
        form = AddInjuryForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_add_injury.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def list_fighter_remove_injury(request, id, fighter_id, injury_id):
    """
    Remove an injury from a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``injury``
        The :model:`core.ListFighterInjury` to be removed.
    ``fighter``
        The :model:`core.ListFighter` being healed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_remove_injury.html`
    """
    from django.contrib import messages

    from gyrinx.core.models.campaign import CampaignAction

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(ListFighter, id=fighter_id, list=lst, owner=lst.owner)
    injury = get_object_or_404(ListFighterInjury, id=injury_id, fighter=fighter)

    if request.method == "POST":
        injury_name = injury.injury.name
        injury.delete()

        # If fighter has no more injuries, reset state to active
        if fighter.injuries.count() == 0:
            fighter.injury_state = ListFighter.ACTIVE
            fighter.save()
            outcome = "Fighter became available"
        else:
            outcome = "Injury removed"

        # Log to campaign action
        if lst.campaign:
            CampaignAction.objects.create(
                user=request.user,
                owner=request.user,
                campaign=lst.campaign,
                list=lst,
                description=f"Recovery: {fighter.name} recovered from {injury_name}",
                outcome=outcome,
            )

        messages.success(request, f"Removed injury '{injury_name}' from {fighter.name}")
        return HttpResponseRedirect(
            reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_remove_injury.html",
        {
            "injury": injury,
            "fighter": fighter,
            "list": lst,
        },
    )


@login_required
def edit_list_fighter_xp(request, id, fighter_id):
    """
    Modify XP for a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An EditFighterXPForm for modifying fighter XP.
    ``fighter``
        The :model:`core.ListFighter` whose XP is being modified.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_xp_edit.html`
    """
    from django.contrib import messages

    from gyrinx.core.forms.list import EditFighterXPForm
    from gyrinx.core.models.campaign import CampaignAction

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(request, "XP can only be tracked for fighters in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = EditFighterXPForm(request.POST, fighter=fighter)
        if form.is_valid():
            operation = form.cleaned_data["operation"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data.get("description", "")

            # Validate the operation
            if operation == "spend" and amount > fighter.xp_current:
                form.add_error(
                    "amount",
                    f"Cannot spend more XP than available ({fighter.xp_current})",
                )
            elif operation == "reduce" and amount > fighter.xp_current:
                form.add_error(
                    "amount",
                    f"Cannot reduce XP below zero (current: {fighter.xp_current})",
                )
            elif operation == "reduce" and amount > fighter.xp_total:
                form.add_error(
                    "amount",
                    f"Cannot reduce total XP below zero (total: {fighter.xp_total})",
                )
            else:
                # Apply the XP change
                if operation == "add":
                    fighter.xp_current += amount
                    fighter.xp_total += amount
                    action_desc = f"Added {amount} XP for {fighter.name}"
                elif operation == "spend":
                    fighter.xp_current -= amount
                    action_desc = f"Spent {amount} XP for {fighter.name}"
                elif operation == "reduce":
                    fighter.xp_current -= amount
                    fighter.xp_total -= amount
                    action_desc = f"Reduced {amount} XP for {fighter.name}"

                fighter.save_with_user(user=request.user)

                # Add description if provided
                if description:
                    action_desc += f" - {description}"

                # Log to campaign action
                if lst.campaign:
                    outcome = f"Current: {fighter.xp_current} XP, Total: {fighter.xp_total} XP"
                    CampaignAction.objects.create(
                        user=request.user,
                        owner=request.user,
                        campaign=lst.campaign,
                        list=lst,
                        description=action_desc,
                        outcome=outcome,
                    )

                messages.success(request, f"XP updated for {fighter.name}")
                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = EditFighterXPForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_xp_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


class ListCampaignClonesView(generic.DetailView):
    """
    Display the campaign clones of a :model:`core.List` object.

    **Context**

    ``list``
        The requested :model:`core.List` object.
    ``campaign_clones``
        QuerySet of campaign mode clones of this list.

    **Template**

    :template:`core/list_campaign_clones.html`
    """

    template_name = "core/list_campaign_clones.html"
    context_object_name = "list"

    def get_object(self):
        """
        Retrieve the :model:`core.List` by its `id`.
        """
        return get_object_or_404(List, id=self.kwargs["id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get all campaign clones, not just active ones
        context["campaign_clones"] = self.object.campaign_clones.all().select_related(
            "campaign", "campaign__owner"
        )
        return context


# Fighter Advancement Views
@login_required
def list_fighter_advancements(request, id, fighter_id):
    """
    Display all advancements for a :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` whose advancements are displayed.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``advancements``
        QuerySet of :model:`core.ListFighterAdvancement` for this fighter.

    **Template**

    :template:`core/list_fighter_advancements.html`
    """
    from gyrinx.core.models import ListFighterAdvancement

    lst = get_object_or_404(List, id=id)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    advancements = ListFighterAdvancement.objects.filter(
        fighter=fighter
    ).select_related("skill", "campaign_action")

    return render(
        request,
        "core/list_fighter_advancements.html",
        {
            "list": lst,
            "fighter": fighter,
            "advancements": advancements,
        },
    )


@login_required
def list_fighter_advancement_start(request, id, fighter_id):
    """
    Redirect to the appropriate advancement flow entry point.
    """
    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        from django.contrib import messages

        messages.error(request, "Advancements can only be purchased in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Redirect to dice choice
    return HttpResponseRedirect(
        reverse("core:list-fighter-advancement-dice-choice", args=(lst.id, fighter.id))
    )


@login_required
def list_fighter_advancement_dice_choice(request, id, fighter_id):
    """
    Choose whether to roll 2d6 for advancement.

    **Context**

    ``form``
        An AdvancementDiceChoiceForm.
    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_advancement_dice_choice.html`
    """

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    if request.method == "POST":
        form = AdvancementDiceChoiceForm(request.POST)
        if form.is_valid():
            roll_dice = form.cleaned_data["roll_dice"]

            if roll_dice:
                # Roll 2d6 and create campaign action
                dice1 = random.randint(1, 6)
                dice2 = random.randint(1, 6)
                total = dice1 + dice2

                # Create campaign action for the roll
                campaign_action = CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=lst.campaign,
                    list=lst,
                    description=f"Rolling for advancement to {fighter.name}",
                    dice_count=2,
                    dice_results=[dice1, dice2],
                    dice_total=total,
                )

                # Redirect to type selection with campaign action
                url = reverse(
                    "core:list-fighter-advancement-type", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?campaign_action_id={campaign_action.id}"
                )
            else:
                # Redirect to type selection without campaign action
                return HttpResponseRedirect(
                    reverse(
                        "core:list-fighter-advancement-type", args=(lst.id, fighter.id)
                    )
                )
    else:
        form = AdvancementDiceChoiceForm()

    return render(
        request,
        "core/list_fighter_advancement_dice_choice.html",
        {
            "form": form,
            "fighter": fighter,
            "list": lst,
        },
    )


class AdvancementBaseParams(BaseModel):
    # UUID of the campaign action if dice were rolled
    campaign_action_id: Optional[uuid.UUID] = None


class AdvancementFlowParams(AdvancementBaseParams):
    # Type of advancement being selected (e.g., "stat_strength", "skill_primary_random")
    advancement_choice: str
    # Spend XP cost for this advancement
    xp_cost: int = 0
    # Fighter cost increase from this advancement
    cost_increase: int = 0
    # Free text description for "other" advancement types
    description: Optional[str] = None

    @field_validator("advancement_choice")
    @classmethod
    def validate_advancement_choice(cls, value: str) -> str:
        if value not in dict(AdvancementTypeForm.ADVANCEMENT_CHOICES).keys():
            raise ValueError("Invalid advancement type choice.")
        return value

    def is_stat_advancement(self) -> bool:
        """
        Check if this is a stat advancement.
        """
        return self.advancement_choice.startswith("stat_")

    def is_skill_advancement(self) -> bool:
        """
        Check if this is a skill advancement.
        """
        return self.advancement_choice in [
            "skill_primary_chosen",
            "skill_secondary_chosen",
            "skill_primary_random",
            "skill_secondary_random",
            "skill_promote_specialist",
            "skill_any_random",
        ]

    def is_other_advancement(self) -> bool:
        """
        Check if this is an 'other' free text advancement.
        """
        return self.advancement_choice == "other"

    def is_chosen_skill_advancement(self) -> bool:
        """
        Check if this is a chosen skill advancement.
        """
        return self.advancement_choice in [
            "skill_primary_chosen",
            "skill_secondary_chosen",
        ]

    def is_random_skill_advancement(self) -> bool:
        """
        Check if this is a random skill advancement.
        """
        return self.advancement_choice in [
            "skill_primary_random",
            "skill_secondary_random",
            "skill_promote_specialist",
            "skill_any_random",
        ]

    def skill_category_from_choice(self) -> Literal["primary", "secondary", "any"]:
        """
        Extract the skill category from the advancement choice.
        """
        if self.is_skill_advancement():
            if self.advancement_choice in [
                "skill_primary_chosen",
                "skill_primary_random",
                "skill_promote_specialist",
            ]:
                return "primary"
            elif self.advancement_choice in [
                "skill_secondary_chosen",
                "skill_secondary_random",
            ]:
                return "secondary"
            elif self.advancement_choice == "skill_any_random":
                return "any"

        raise ValueError("Not a skill advancement choice.")

    def stat_from_choice(self) -> str:
        """
        Extract the stat from the advancement choice.
        """
        if self.is_stat_advancement():
            return self.advancement_choice.split("_", 1)[1]

        raise ValueError("Not a stat advancement choice.")

    def description_from_choice(self) -> str:
        """
        Get the description for the advancement based on the choice.
        """
        if self.is_stat_advancement():
            return dict(AdvancementTypeForm.ADVANCEMENT_CHOICES).get(
                self.advancement_choice, ""
            )

        raise ValueError("Invalid advancement type for description.")


@login_required
def list_fighter_advancement_type(request, id, fighter_id):
    """
    Select the type of advancement and costs.

    **Context**

    ``form``
        An AdvancementTypeForm.
    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``campaign_action``
        Optional CampaignAction if dice were rolled.

    **Template**

    :template:`core/list_fighter_advancement_type.html`
    """

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    params = AdvancementBaseParams.model_validate(request.GET.dict())
    # Get campaign action if provided
    campaign_action = None
    if params.campaign_action_id:
        campaign_action = get_object_or_404(
            CampaignAction, id=params.campaign_action_id
        )

    if request.method == "POST":
        form = AdvancementTypeForm(request.POST, fighter=fighter)
        if form.is_valid():
            next_params = AdvancementFlowParams.model_validate(form.cleaned_data)

            # Check if this is a stat advancement - go directly to confirm
            if next_params.is_stat_advancement():
                url = reverse(
                    "core:list-fighter-advancement-confirm", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?{urlencode(next_params.model_dump(mode='json', exclude_none=True))}"
                )
            elif next_params.is_other_advancement():
                # For "other" advancements, go to the other view
                url = reverse(
                    "core:list-fighter-advancement-other", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?{urlencode(next_params.model_dump(mode='json', exclude_none=True))}"
                )
            else:
                # For skills, still need selection step
                url = reverse(
                    "core:list-fighter-advancement-select", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?{urlencode(next_params.model_dump(mode='json', exclude_none=True))}"
                )
    else:
        initial = {
            **params.model_dump(mode="json", exclude_none=True),
            **AdvancementTypeForm.get_initial_for_action(campaign_action),
        }
        form = AdvancementTypeForm(initial=initial, fighter=fighter)

    return render(
        request,
        "core/list_fighter_advancement_type.html",
        {
            "form": form,
            "fighter": fighter,
            "list": lst,
            "campaign_action": campaign_action,
        },
    )


@login_required
def list_fighter_advancement_confirm(request, id, fighter_id):
    """
    Confirm and create the advancement.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``advancement_details``
        Dictionary containing details about the advancement to be created.

    **Template**

    :template:`core/list_fighter_advancement_confirm.html`
    """

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # Get and sanitize parameters from query string, and make sure only stat or other advancements
    # reach this stage. Then build the details object.
    try:
        params = AdvancementFlowParams.model_validate(request.GET.dict())
        if not (params.is_stat_advancement() or params.is_other_advancement()):
            raise ValueError(
                "Only stat or other advancements allowed at the confirm stage"
            )

        if params.is_stat_advancement():
            stat = params.stat_from_choice()
            stat_desc = params.description_from_choice()
        elif params.is_other_advancement():
            stat = None
            stat_desc = params.description
    except ValueError as e:
        messages.error(request, f"Invalid advancement: {e}.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    if request.method == "POST":
        # Create the advancement
        if params.is_stat_advancement():
            advancement = ListFighterAdvancement(
                fighter=fighter,
                advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
                xp_cost=params.xp_cost,
                cost_increase=params.cost_increase,
                stat_increased=stat,
            )
            outcome = f"Improved {stat_desc}"
        elif params.is_other_advancement():
            advancement = ListFighterAdvancement(
                fighter=fighter,
                advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
                xp_cost=params.xp_cost,
                cost_increase=params.cost_increase,
                description=stat_desc,
            )
            outcome = f"Gained {stat_desc}"

        if params.campaign_action_id:
            # Add outcome to campaign action if exists
            campaign_action = get_object_or_404(
                CampaignAction, id=params.campaign_action_id
            )
            advancement.campaign_action = campaign_action
            campaign_action.outcome = outcome
            campaign_action.save()
        else:
            # Create new campaign action if not exists
            if lst.campaign:
                description = f"{fighter.name} spent {params.xp_cost} XP to advance"

                campaign_action = CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=lst.campaign,
                    list=lst,
                    description=description,
                    outcome=outcome,
                )
                advancement.campaign_action = campaign_action

        advancement.save()

        # Apply the advancement (this deducts XP)
        # Don't update cost_override - the cost will be computed from advancements
        advancement.apply_advancement()

        messages.success(
            request,
            f"Advanced: {fighter.name} has improved {stat_desc}",
        )

        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_advancement_confirm.html",  # TODO: Check and update this template
        {
            "fighter": fighter,
            "list": lst,
            "details": {
                **params.model_dump(),
                "stat": stat,
                "description": stat_desc,
            },
        },
    )


def apply_skill_advancement(
    request: HttpRequest,
    lst: List,
    fighter: ListFighter,
    skill: ContentSkill,
    params: AdvancementFlowParams,
) -> ListFighterAdvancement:
    # Create the advancement
    advancement = ListFighterAdvancement(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=params.xp_cost,
        cost_increase=params.cost_increase,
        skill=skill,
    )

    outcome = f"Gained {skill.name} skill"

    if params.campaign_action_id:
        # Add outcome to campaign action if exists
        campaign_action = get_object_or_404(
            CampaignAction, id=params.campaign_action_id
        )
        advancement.campaign_action = campaign_action
        campaign_action.outcome = outcome
        campaign_action.save()
    else:
        # Create new campaign action if not exists
        if lst.campaign:
            description = f"{fighter.name} spent {params.xp_cost} XP to advance"

            campaign_action = CampaignAction.objects.create(
                user=request.user,
                owner=request.user,
                campaign=lst.campaign,
                list=lst,
                description=description,
                outcome=outcome,
            )
            advancement.campaign_action = campaign_action

    advancement.save()

    # Apply the advancement (this deducts XP)
    # Don't update cost_override - the cost will be computed from advancements
    advancement.apply_advancement()

    return advancement


@login_required
def list_fighter_advancement_select(request, id, fighter_id):
    """
    Select specific stat or skill based on advancement type.

    **Context**

    ``form``
        StatSelectionForm, SkillSelectionForm, or RandomSkillForm based on type.
    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``advancement_type``
        The type of advancement being selected.

    **Template**

    :template:`core/list_fighter_advancement_select.html`
    """

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # Get and sanitize parameters from query string, and make sure only stat advancements
    # reach this stage. Then build the details object.
    try:
        params = AdvancementFlowParams.model_validate(request.GET.dict())
        if not params.is_skill_advancement():
            raise ValueError("Only skill advancements allowed at the target stage")

        skill_type = params.skill_category_from_choice()
    except ValueError as e:
        messages.error(request, f"Invalid advancement: {e}.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    if params.is_chosen_skill_advancement():
        # Chosen skill
        if request.method == "POST":
            form = SkillSelectionForm(
                request.POST, fighter=fighter, skill_type=skill_type
            )
            if form.is_valid():
                skill = form.cleaned_data["skill"]

                apply_skill_advancement(
                    request,
                    lst,
                    fighter,
                    skill,
                    params,
                )

                messages.success(
                    request,
                    f"Advanced: {fighter.name} has gained {skill.name} skill",
                )

                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
        else:
            form = SkillSelectionForm(fighter=fighter, skill_type=skill_type)

    elif params.is_random_skill_advancement():
        if request.method == "POST":
            form = SkillCategorySelectionForm(
                request.POST, fighter=fighter, skill_type=skill_type
            )
            if form.is_valid():
                category = form.cleaned_data["category"]

                # Auto-select a random skill from the category
                existing_skills = fighter.skills.all()
                available_skills = ContentSkill.objects.filter(
                    category=category
                ).exclude(id__in=existing_skills.values_list("id", flat=True))

                if available_skills.exists():
                    # Pick a random skill from the available ones
                    random_skill = random.choice(available_skills)

                    apply_skill_advancement(
                        request,
                        lst,
                        fighter,
                        random_skill,
                        params,
                    )

                    messages.success(
                        request,
                        f"Advanced: {fighter.name} has gained {random_skill.name} skill",
                    )

                    return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
                else:
                    # No available skills - show error
                    form.add_error(None, "No available skills in this category.")
        else:
            form = SkillCategorySelectionForm(fighter=fighter, skill_type=skill_type)

    else:
        messages.error(
            request,
            "Sorry, something went really wrong with the advancement. Try again.",
        )
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_advancement_select.html",
        {
            "form": form,
            "fighter": fighter,
            "list": lst,
            "skill_type": skill_type,
            "is_random": params.is_random_skill_advancement(),
        },
    )


@login_required
def list_fighter_advancement_other(request, id, fighter_id):
    """
    Enter a free text description for an 'other' advancement.

    **Context**

    ``form``
        An OtherAdvancementForm.
    ``fighter``
        The :model:`core.ListFighter` purchasing the advancement.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``params``
        The AdvancementFlowParams from previous steps.

    **Template**

    :template:`core/list_fighter_advancement_other.html`
    """

    from gyrinx.core.forms.advancement import OtherAdvancementForm

    lst = get_object_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # Get parameters from query string
    try:
        params = AdvancementFlowParams.model_validate(request.GET.dict())
        if not params.is_other_advancement():
            raise ValueError("Only 'other' advancements allowed at this stage")
    except ValueError as e:
        messages.error(request, f"Invalid advancement: {e}.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    if request.method == "POST":
        form = OtherAdvancementForm(request.POST)
        if form.is_valid():
            # Add the description to params and proceed to confirmation
            params.description = form.cleaned_data["description"]
            url = reverse(
                "core:list-fighter-advancement-confirm", args=(lst.id, fighter.id)
            )
            return HttpResponseRedirect(
                f"{url}?{urlencode(params.model_dump(mode='json', exclude_none=True))}"
            )
    else:
        form = OtherAdvancementForm()

    return render(
        request,
        "core/list_fighter_advancement_other.html",
        {
            "form": form,
            "fighter": fighter,
            "list": lst,
            "params": params,
        },
    )
