"""Forms for vehicle addition flow."""

from typing import Optional

from django import forms

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentFighterProfile,
    ContentFighter,
    ContentHouse,
)
from gyrinx.core.forms.list import ContentFighterChoiceField, group_select
from gyrinx.core.models.list import List
from gyrinx.forms import fighter_group_key, group_sorter
from gyrinx.models import FighterCategoryChoices


class VehicleEquipmentChoiceField(forms.ModelChoiceField):
    """Custom field that shows fighter info but submits equipment ID."""

    content_house: ContentHouse | None = None

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", forms.Select(attrs={"class": "form-select"}))
        kwargs.setdefault("label", "Select Vehicle")
        super().__init__(*args, **kwargs)
        # Store the equipment-to-fighter mapping
        self._equipment_fighter_map = {}

    def label_from_instance(self, obj: ContentEquipment):
        # Get the associated fighter profile
        profile = (
            ContentEquipmentFighterProfile.objects.filter(equipment=obj)
            .select_related("content_fighter")
            .first()
        )

        if profile and profile.content_fighter:
            fighter = profile.content_fighter
            # Store the mapping for later use in grouping
            self._equipment_fighter_map[obj.id] = fighter
            cost_for_house = (
                fighter.cost_for_house(self.content_house)
                if self.content_house
                else fighter.cost_int()
            )
            return f"{fighter.name()} ({cost_for_house}¢)"

        # Fallback to equipment name if no fighter profile
        return obj.name


class VehicleSelectionForm(forms.Form):
    """Form for selecting a vehicle (equipment with ContentEquipmentFighterProfile)."""

    def __init__(self, *args, list_instance: Optional[List] = None, **kwargs):
        super().__init__(*args, **kwargs)

        # Create the field with custom choice field
        self.fields["vehicle_equipment"] = VehicleEquipmentChoiceField(
            queryset=ContentEquipment.objects.none(),
            help_text="Choose the vehicle you want to add to your list.",
        )

        if list_instance:
            # Get equipment-fighter profiles for vehicles available to this list's house
            available_fighters = ContentFighter.objects.available_for_house(
                list_instance.content_house,
                include=[FighterCategoryChoices.VEHICLE],
            )
            vehicle_equipment_ids = ContentEquipmentFighterProfile.objects.filter(
                content_fighter__in=available_fighters,
                content_fighter__category=FighterCategoryChoices.VEHICLE,
            ).values_list("equipment_id", flat=True)

            # Get equipment with prefetched fighter profiles
            queryset = (
                ContentEquipment.objects.filter(id__in=vehicle_equipment_ids)
                .select_related("category")
                .prefetch_related(
                    "contentequipmentfighterprofile_set__content_fighter__house"
                )
            )

            self.fields["vehicle_equipment"].queryset = queryset
            self.fields["vehicle_equipment"].content_house = list_instance.content_house

            # Group by fighter house using a custom key function
            # Uses prefetched contentequipmentfighterprofile_set from queryset above
            def equipment_group_key(equipment):
                # Use prefetched profiles instead of querying
                profiles = list(equipment.contentequipmentfighterprofile_set.all())
                if (
                    profiles
                    and profiles[0].content_fighter
                    and profiles[0].content_fighter.house
                ):
                    return profiles[0].content_fighter.house.name
                return "Other"

            group_select(
                self,
                "vehicle_equipment",
                key=equipment_group_key,
                sort_groups_by=group_sorter(list_instance.content_house.name),
            )


class CrewSelectionForm(forms.Form):
    """Form for selecting a crew member for the vehicle."""

    crew_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Crew Name",
        help_text="Name for your crew member.",
    )

    crew_fighter = ContentFighterChoiceField(
        queryset=ContentFighter.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Crew Type",
        help_text="Select the type of fighter to crew the vehicle.",
    )

    action = forms.CharField(
        widget=forms.HiddenInput(),
        initial="select_crew",
        required=False,
    )

    def __init__(
        self,
        *args,
        list_instance: Optional[List] = None,
        vehicle_equipment=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if list_instance and vehicle_equipment:
            # Get valid crew members for this vehicle
            # For now, use the available_for_house method to get crew options
            # This includes fighters from the house and generic houses, excluding exotic beasts and stash
            queryset = ContentFighter.objects.available_for_house(
                list_instance.content_house
            )

            # Exclude vehicles from being crew members
            queryset = queryset.filter(category__in=[FighterCategoryChoices.CREW])

            queryset = queryset.select_related("house").order_by("house__name", "type")

            self.fields["crew_fighter"].queryset = queryset
            self.fields["crew_fighter"].content_house = list_instance.content_house

            group_select(
                self,
                "crew_fighter",
                key=fighter_group_key,
                sort_groups_by=group_sorter(list_instance.content_house.name),
            )


class VehicleConfirmationForm(forms.Form):
    """Form for confirming vehicle and crew creation."""

    confirm = forms.BooleanField(
        required=True,
        initial=True,
        widget=forms.HiddenInput(),
    )
