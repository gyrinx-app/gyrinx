"""Fighter advancement views."""

import json
import random
import uuid
from typing import Literal, Optional
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from pydantic import BaseModel, ValidationError, field_validator

from gyrinx import messages
from gyrinx.content.models import ContentAdvancementEquipment, ContentSkill
from gyrinx.core.forms.advancement import (
    AdvancementDiceChoiceForm,
    AdvancementTypeForm,
    EquipmentAssignmentSelectionForm,
    OtherAdvancementForm,
    SkillCategorySelectionForm,
    SkillSelectionForm,
)
from gyrinx.core.handlers.fighter import (
    handle_fighter_advancement,
    handle_fighter_advancement_deletion,
)
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterAdvancement,
    ListFighterEquipmentAssignment,
)
from gyrinx.core.views.list.common import get_clean_list_or_404
from gyrinx.models import FighterCategoryChoices


def can_fighter_roll_dice_for_advancement(fighter):
    """Check if a fighter can roll dice for advancement (GANGERs and EXOTIC_BEASTs can)."""
    category = fighter.get_category()
    return category in [
        FighterCategoryChoices.GANGER.value,
        FighterCategoryChoices.EXOTIC_BEAST.value,
    ]


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

    lst = get_clean_list_or_404(List, id=id)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    advancements = ListFighterAdvancement.objects.filter(
        fighter=fighter,
        archived=False,
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
def delete_list_fighter_advancement(request, id, fighter_id, advancement_id):
    """
    Delete (archive) a :model:`core.ListFighterAdvancement`.

    This reverses the effects of the advancement:
    - Restores XP to the fighter
    - Reduces rating/stash by cost_increase
    - For stat advancements: stat change disappears (mod system) or recalculates override
    - For skill advancements: removes skill and recalculates category_override
    - For equipment advancements: warns user to remove equipment manually
    - For other advancements: just archives (no side effects)

    **Context**

    ``fighter``
        The :model:`core.ListFighter` whose advancement is being deleted.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``advancement``
        The :model:`core.ListFighterAdvancement` to be deleted.

    **Template**

    :template:`core/list_fighter_advancement_delete.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )
    advancement = get_object_or_404(
        ListFighterAdvancement, id=advancement_id, fighter=fighter, archived=False
    )

    if request.method == "POST":
        try:
            result = handle_fighter_advancement_deletion(
                user=request.user,
                fighter=fighter,
                advancement=advancement,
            )

            # Show warnings if any
            for warning in result.warnings:
                messages.warning(request, warning)

            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                advancement_type=advancement.advancement_type,
            )

            messages.success(
                request,
                f"Advancement removed: {result.advancement_description}. "
                f"XP restored: {result.xp_restored}.",
            )
        except DjangoValidationError as e:
            messages.error(request, str(e))

        return HttpResponseRedirect(
            reverse("core:list-fighter-advancements", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_advancement_delete.html",
        {
            "list": lst,
            "fighter": fighter,
            "advancement": advancement,
        },
    )


@login_required
def list_fighter_advancement_start(request, id, fighter_id):
    """
    Redirect to the appropriate advancement flow entry point.
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

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

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    # TODO: This should be removed once ListActions are implemented, so that dice-rolls for advancements
    # are possible even outside of campaign mode.
    if lst.status != List.CAMPAIGN_MODE:
        url = reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        return HttpResponseRedirect(url)

    # Check if fighter can roll dice for advancement
    if not can_fighter_roll_dice_for_advancement(fighter):
        url = reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        return HttpResponseRedirect(url)

    if request.method == "POST":
        form = AdvancementDiceChoiceForm(request.POST)
        if form.is_valid():
            roll_dice = form.cleaned_data["roll_dice"]

            if roll_dice:
                with transaction.atomic():
                    # Roll 2d6 and create campaign action
                    dice1 = random.randint(1, 6)  # nosec B311 - game dice, not crypto
                    dice2 = random.randint(1, 6)  # nosec B311 - game dice, not crypto
                    total = dice1 + dice2

                    # Create campaign action for the roll if in campaign mode
                    campaign_action = None
                    if lst.status == List.CAMPAIGN_MODE and lst.campaign:
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
                if campaign_action:
                    return HttpResponseRedirect(
                        f"{url}?campaign_action_id={campaign_action.id}"
                    )
                else:
                    return HttpResponseRedirect(url)
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
            "can_roll_dice": can_fighter_roll_dice_for_advancement(fighter),
            "fighter_category": fighter.get_category_label(),
        },
    )


def filter_equipment_assignments_for_duplicates(equipment_advancement, fighter):
    """
    Filter equipment advancement assignments to exclude those with upgrades
    that the fighter already has on their equipment.

    Args:
        equipment_advancement: ContentAdvancementEquipment instance
        fighter: ListFighter instance

    Returns:
        QuerySet of ContentAdvancementAssignment objects that don't have duplicate upgrades
    """
    # Get all assignments from the advancement
    available_assignments = equipment_advancement.assignments.all()

    # Get all upgrade IDs from the fighter's existing equipment assignments
    existing_upgrade_ids = set(
        ListFighterEquipmentAssignment.objects.filter(
            list_fighter=fighter, archived=False
        ).values_list("upgrades_field", flat=True)
    )
    # Remove None values if any
    existing_upgrade_ids.discard(None)

    # Filter out assignments that have any upgrade matching existing upgrades
    if existing_upgrade_ids:
        # Exclude assignments that have any of the existing upgrades
        available_assignments = available_assignments.exclude(
            upgrades_field__in=existing_upgrade_ids
        ).distinct()

    return available_assignments


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
        if value not in AdvancementTypeForm.all_advancement_choices().keys():
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
            "skill_promote_champion",
            "skill_any_random",
        ]

    def is_equipment_advancement(self) -> bool:
        """
        Check if this is an equipment advancement.
        """
        return self.advancement_choice.startswith("equipment_")

    def is_equipment_random_advancement(self) -> bool:
        """
        Check if this is a random equipment advancement.
        """
        return self.advancement_choice.startswith("equipment_random_")

    def is_equipment_chosen_advancement(self) -> bool:
        """
        Check if this is a chosen equipment advancement.
        """
        return self.advancement_choice.startswith("equipment_chosen_")

    def get_equipment_advancement_id(self) -> str:
        """
        Extract the equipment advancement ID from the choice.
        """
        if self.is_equipment_advancement():
            # Format is "equipment_[random|chosen]_<uuid>"
            parts = self.advancement_choice.split("_", 2)
            if len(parts) >= 3:
                return parts[2]
        raise ValueError("Not an equipment advancement choice.")

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
            "skill_promote_champion",
            "skill_any_random",
        ]

    def is_promote_advancement(self) -> bool:
        """
        Check if this is a specialist or champion promotion advancement.
        """
        return self.advancement_choice in [
            "skill_promote_specialist",
            "skill_promote_champion",
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
                "skill_promote_champion",
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
            return AdvancementTypeForm.all_stat_choices().get(
                self.advancement_choice, "Unknown"
            )

        if self.is_equipment_advancement():
            return AdvancementTypeForm.all_equipment_choices().get(
                self.advancement_choice, "Unknown"
            )

        # For other advancement types, use the full list
        return AdvancementTypeForm.all_advancement_choices().get(
            self.advancement_choice, "Unknown"
        )


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

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    is_campaign_mode = lst.status == List.CAMPAIGN_MODE

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
            elif (
                next_params.is_equipment_advancement()
                and "_random_" in next_params.advancement_choice
            ):
                # For random equipment advancements, go straight to confirm
                url = reverse(
                    "core:list-fighter-advancement-confirm", args=(lst.id, fighter.id)
                )
                return HttpResponseRedirect(
                    f"{url}?{urlencode(next_params.model_dump(mode='json', exclude_none=True))}"
                )
            else:
                # For skills and chosen equipment, still need selection step
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
            "is_campaign_mode": is_campaign_mode,
            "steps": 3 if is_campaign_mode else 2,
            "current_step": 2 if is_campaign_mode else 1,
            "progress": 66 if is_campaign_mode else 50,
            "advancement_configs_json": json.dumps(form.get_all_configs_json()),
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
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    is_campaign_mode = lst.status == List.CAMPAIGN_MODE

    # Get and sanitize parameters from query string
    try:
        params = AdvancementFlowParams.model_validate(request.GET.dict())
        # Allow stat, other, and random equipment advancements at confirm stage
        is_random_equipment = (
            params.is_equipment_advancement()
            and "_random_" in params.advancement_choice
        )
        if not (
            params.is_stat_advancement()
            or params.is_other_advancement()
            or is_random_equipment
        ):
            raise ValueError(
                "Only stat, other, or random equipment advancements allowed at the confirm stage"
            )

        if params.is_stat_advancement():
            stat = params.stat_from_choice()
            stat_desc = params.description_from_choice()
        elif params.is_other_advancement():
            stat = None
            stat_desc = params.description
        elif is_random_equipment:
            # For random equipment, prepare the details
            stat = None
            stat_desc = params.description_from_choice()
    except ValueError as e:
        messages.error(request, f"Invalid advancement: {e}.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    if request.method == "POST":
        # Prepare type-specific parameters for the handler
        selected_assignment = None
        equipment_description = None

        if is_random_equipment:
            # For random equipment, select the assignment before calling handler
            try:
                advancement_id = params.get_equipment_advancement_id()
                equipment_advancement = ContentAdvancementEquipment.objects.get(
                    id=advancement_id
                )

                # Randomly select assignment, filtering out duplicates
                available_assignments = filter_equipment_assignments_for_duplicates(
                    equipment_advancement, fighter
                )
                if not available_assignments.exists():
                    error_msg = (
                        f"No available options from {equipment_advancement.name}. "
                    )
                    raise ValueError(error_msg)

                selected_assignment = available_assignments.order_by("?").first()
                equipment_description = (
                    f"Random {equipment_advancement.name}: {selected_assignment}"
                )
            except (ValueError, ContentAdvancementEquipment.DoesNotExist) as e:
                messages.error(request, f"Invalid equipment advancement: {e}")
                return HttpResponseRedirect(
                    reverse(
                        "core:list-fighter-advancement-type",
                        args=(lst.id, fighter.id),
                    )
                )

        # Call the handler
        try:
            if params.is_stat_advancement():
                result = handle_fighter_advancement(
                    user=request.user,
                    fighter=fighter,
                    advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
                    xp_cost=params.xp_cost,
                    cost_increase=params.cost_increase,
                    advancement_choice=params.advancement_choice,
                    stat_increased=stat,
                    campaign_action_id=params.campaign_action_id,
                )
            elif params.is_other_advancement():
                result = handle_fighter_advancement(
                    user=request.user,
                    fighter=fighter,
                    advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
                    xp_cost=params.xp_cost,
                    cost_increase=params.cost_increase,
                    advancement_choice=params.advancement_choice,
                    description=stat_desc,
                    campaign_action_id=params.campaign_action_id,
                )
            elif is_random_equipment:
                result = handle_fighter_advancement(
                    user=request.user,
                    fighter=fighter,
                    advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
                    xp_cost=params.xp_cost,
                    cost_increase=params.cost_increase,
                    advancement_choice=params.advancement_choice,
                    equipment_assignment=selected_assignment,
                    description=equipment_description,
                    campaign_action_id=params.campaign_action_id,
                )
        except DjangoValidationError as e:
            messages.validation(request, e)
            return HttpResponseRedirect(
                reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
            )

        # Handle idempotent case (already applied)
        if result is None:
            messages.info(request, "Advancement already applied.")
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

        # Log the advancement event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="advancement_applied",
            advancement_type=result.advancement.advancement_type,
            advancement_detail=stat_desc,
            xp_cost=params.xp_cost,
            cost_increase=params.cost_increase,
        )

        messages.success(
            request,
            f"Advanced: {fighter.name} - {result.outcome}",
        )

        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    steps = 3
    if not is_campaign_mode and not params.is_other_advancement():
        steps = 2

    # Prepare context based on advancement type
    context = {
        "fighter": fighter,
        "list": lst,
        "details": {
            **params.model_dump(),
            "stat": stat,
            "description": stat_desc,
        },
        "is_campaign_mode": is_campaign_mode,
        "steps": steps,
        "current_step": steps,
    }

    # Add equipment-specific context for random equipment
    if is_random_equipment:
        context["advancement_type"] = "equipment"
        context["is_random"] = True
        # Get the equipment advancement name for display
        try:
            advancement_id = params.get_equipment_advancement_id()
            equipment_advancement = ContentAdvancementEquipment.objects.get(
                id=advancement_id
            )
            context["advancement_name"] = equipment_advancement.name
        except (ValueError, ContentAdvancementEquipment.DoesNotExist):
            context["advancement_name"] = "Equipment"

    return render(
        request,
        "core/list_fighter_advancement_confirm.html",
        context,
    )


def apply_skill_advancement(
    request: HttpRequest,
    lst: List,
    fighter: ListFighter,
    skill: ContentSkill,
    params: AdvancementFlowParams,
) -> ListFighterAdvancement | None:
    """
    Apply a skill advancement to a fighter using the handler.

    Returns the advancement if created, or None if already applied (idempotent)
    or if a validation error occurred.
    """
    try:
        result = handle_fighter_advancement(
            user=request.user,
            fighter=fighter,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
            xp_cost=params.xp_cost,
            cost_increase=params.cost_increase,
            advancement_choice=params.advancement_choice,
            skill=skill,
            campaign_action_id=params.campaign_action_id,
        )
    except DjangoValidationError as e:
        messages.validation(request, e)
        return None

    if result is None:
        # Idempotent case - already applied
        messages.info(request, "Advancement already applied.")
        return None

    # Log the skill advancement event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        action="skill_advancement_applied",
        skill_name=skill.name,
        xp_cost=params.xp_cost,
        cost_increase=params.cost_increase,
    )

    return result.advancement


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

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    is_campaign_mode = lst.status == List.CAMPAIGN_MODE

    # Get and sanitize parameters from query string, and make sure only skill or equipment advancements
    # reach this stage. Then build the details object.
    try:
        params = AdvancementFlowParams.model_validate(request.GET.dict())
        if not (params.is_skill_advancement() or params.is_equipment_advancement()):
            raise ValueError(
                "Only skill or equipment advancements allowed at the target stage"
            )

        skill_type = (
            params.skill_category_from_choice()
            if params.is_skill_advancement()
            else None
        )
    except ValidationError as e:
        messages.error(request, f"Invalid advancement: {e}.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
        )

    if params.is_equipment_advancement():
        # Handle chosen equipment advancement
        # Note: Random equipment advancements are redirected to confirm view from type view

        # Get the equipment advancement
        try:
            advancement_id = params.get_equipment_advancement_id()
            advancement = ContentAdvancementEquipment.objects.get(id=advancement_id)
        except (ValueError, ContentAdvancementEquipment.DoesNotExist):
            messages.error(request, "Invalid equipment advancement.")
            return HttpResponseRedirect(
                reverse("core:list-fighter-advancement-type", args=(lst.id, fighter.id))
            )

        # Chosen equipment selection
        if request.method == "POST":
            form = EquipmentAssignmentSelectionForm(
                request.POST, advancement=advancement, fighter=fighter
            )
            if form.is_valid():
                assignment = form.cleaned_data["assignment"]

                # Use the handler to create the advancement
                try:
                    result = handle_fighter_advancement(
                        user=request.user,
                        fighter=fighter,
                        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
                        xp_cost=params.xp_cost,
                        cost_increase=params.cost_increase,
                        advancement_choice=params.advancement_choice,
                        equipment_assignment=assignment,
                        description=f"Chosen {advancement.name}: {assignment}",
                        campaign_action_id=params.campaign_action_id,
                    )
                except DjangoValidationError as e:
                    messages.validation(request, e)
                    return HttpResponseRedirect(
                        reverse(
                            "core:list-fighter-advancement-type",
                            args=(lst.id, fighter.id),
                        )
                    )

                if result is None:
                    # Idempotent case - already applied
                    messages.info(request, "Advancement already applied.")
                    return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

                # Log the equipment advancement event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.UPDATE,
                    object=fighter,
                    request=request,
                    fighter_name=fighter.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    action="equipment_advancement_applied",
                    equipment_name=str(assignment),
                    xp_cost=params.xp_cost,
                    cost_increase=params.cost_increase,
                )

                messages.success(
                    request,
                    f"Advanced: {fighter.name} has gained {assignment}",
                )

                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
        else:
            form = EquipmentAssignmentSelectionForm(
                advancement=advancement, fighter=fighter
            )

    elif params.is_chosen_skill_advancement():
        # Chosen skill
        if request.method == "POST":
            form = SkillSelectionForm(
                request.POST, fighter=fighter, skill_type=skill_type
            )
            if form.is_valid():
                skill = form.cleaned_data["skill"]

                advancement = apply_skill_advancement(
                    request,
                    lst,
                    fighter,
                    skill,
                    params,
                )

                if advancement:
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
                    random_skill = available_skills.order_by("?").first()

                    advancement = apply_skill_advancement(
                        request,
                        lst,
                        fighter,
                        random_skill,
                        params,
                    )

                    if advancement:
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

    # Prepare context based on advancement type
    context = {
        "form": form,
        "fighter": fighter,
        "list": lst,
        "is_campaign_mode": is_campaign_mode,
        "steps": 3 if is_campaign_mode else 2,
        "current_step": 3 if is_campaign_mode else 2,
    }

    if params.is_equipment_advancement():
        context.update(
            {
                "advancement_type": "equipment",
                "is_random": False,  # Random equipment goes to confirm, not here
                "advancement_name": advancement.name
                if "advancement" in locals()
                else None,
            }
        )
    else:
        context.update(
            {
                "advancement_type": "skill",
                "skill_type": skill_type,
                "is_random": params.is_random_skill_advancement(),
            }
        )

    return render(
        request,
        "core/list_fighter_advancement_select.html",
        context,
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

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
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
            "is_campaign_mode": lst.status == List.CAMPAIGN_MODE,
        },
    )
