import uuid
from typing import List, TypeVar, Union

from django.db import models
from django.db.models import QuerySet
from django.utils import timezone


class Archived(models.Model):
    """An Archived object is no longer in use."""

    archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)

    def archive(self):
        self.archived = True
        self.archived_at = timezone.now()
        # TODO: Iterate through specific, related objects and archive them
        self.save()

    def unarchive(self):
        self.archived = False
        self.archived_at = None
        self.save()

    class Meta:
        abstract = True


class Owned(models.Model):
    """An Owned object is owned by a User."""

    owner = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=False
    )

    class Meta:
        abstract = True


class Base(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class FighterCategoryChoices(models.TextChoices):
    LEADER = "LEADER", "Leader"
    CHAMPION = "CHAMPION", "Champion"
    GANGER = "GANGER", "Ganger"
    JUVE = "JUVE", "Juve"
    CREW = "CREW", "Crew"
    EXOTIC_BEAST = "EXOTIC_BEAST", "Exotic Beast"
    HANGER_ON = "HANGER_ON", "Hanger-on"
    BRUTE = "BRUTE", "Brute"
    HIRED_GUN = "HIRED_GUN", "Hired Gun"
    BOUNTY_HUNTER = "BOUNTY_HUNTER", "Bounty Hunter"
    HOUSE_AGENT = "HOUSE_AGENT", "House Agent"
    HIVE_SCUM = "HIVE_SCUM", "Hive Scum"
    DRAMATIS_PERSONAE = "DRAMATIS_PERSONAE", "Dramatis Personae"
    PROSPECT = "PROSPECT", "Prospect"
    SPECIALIST = "SPECIALIST", "Specialist"


class EquipmentCategoryChoices(models.TextChoices):
    AMMO = "AMMO", "Ammo"
    ARMOR = "ARMOR", "Armor"
    BASIC_WEAPONS = "BASIC_WEAPONS", "Basic Weapons"
    BIONICS = "BIONICS", "Bionics"
    BODY_UPGRADES = "BODY_UPGRADES", "Body Upgrades"
    BOOBY_TRAPS = "BOOBY_TRAPS", "Booby Traps"
    CHEM_ALCHEMY_ELIXIRS = "CHEM_ALCHEMY_ELIXIRS", "Chem-alchemy Elixirs"
    CHEMS = "CHEMS", "Chems"
    CLOSE_COMBAT = "CLOSE_COMBAT", "Close Combat Weapons"
    CYBERTEKNIKA = "CYBERTEKNIKA", "Cyberteknika"
    DRIVE_UPGRADES = "DRIVE_UPGRADES", "Drive Upgrades"
    ENGINE_UPGRADES = "ENGINE_UPGRADES", "Engine Upgrades"
    EQUIPMENT = "EQUIPMENT", "Personal Equipment"
    FIELD_ARMOUR = "FIELD_ARMOUR", "Field Armour"
    GANG_EQUIPMENT = "GANG_EQUIPMENT", "Gang Equipment"
    GANG_TERRAIN = "GANG_TERRAIN", "Gang Terrain"
    GENE_SMITHING = "GENE_SMITHING", "Gene-smithing"
    GRENADES = "GRENADES", "Grenades"
    HARDPOINT_UPGRADES = "HARDPOINT_UPGRADES", "Hardpoint Upgrades"
    HEAVY_WEAPONS = "HEAVY_WEAPONS", "Heavy Weapons"
    MOUNTS = "MOUNTS", "Mounts"
    OPTIONS = "OPTIONS", "Options"
    PISTOLS = "PISTOLS", "Pistols"
    POWER_PACK_WEAPONS = "POWER_PACK_WEAPONS", "Power Pack Weapons"
    RELICS = "RELICS", "Relics"
    SPECIAL_WEAPONS = "SPECIAL_WEAPONS", "Special Weapons"
    STATUS_ITEMS = "STATUS_ITEMS", "Status Items"
    VEHICLE_EQUIPMENT = "VEHICLE_EQUIPMENT", "Vehicle Wargear"
    VEHICLES = "VEHICLES", "Vehicles"


equipment_category_choices = {
    "Gear": {
        "ARMOR": "Armor",
        "BIONICS": "Bionics",
        "BODY_UPGRADES": "Body Upgrades",
        "BOOBY_TRAPS": "Booby Traps",
        "CHEM_ALCHEMY_ELIXIRS": "Chem-alchemy Elixirs",
        "CHEMS": "Chems",
        "CYBERTEKNIKA": "Cyberteknika",
        "EQUIPMENT": "Personal Equipment",
        "FIELD_ARMOUR": "Field Armour",
        "GANG_EQUIPMENT": "Gang Equipment",
        "GANG_TERRAIN": "Gang Terrain",
        "GENE_SMITHING": "Gene-smithing",
        "RELICS": "Relics",
        "STATUS_ITEMS": "Status Items",
    },
    "Vehicle & Mount": {
        "DRIVE_UPGRADES": "Drive Upgrades",
        "ENGINE_UPGRADES": "Engine Upgrades",
        "HARDPOINT_UPGRADES": "Hardpoint Upgrades",
        "MOUNTS": "Mounts",
        "VEHICLE_EQUIPMENT": "Vehicle Wargear",
        "VEHICLES": "Vehicles",
    },
    "Weapons & Ammo": {
        "AMMO": "Ammo",
        "BASIC_WEAPONS": "Basic Weapons",
        "CLOSE_COMBAT": "Close Combat Weapons",
        "GRENADES": "Grenades",
        "HEAVY_WEAPONS": "Heavy Weapons",
        "PISTOLS": "Pistols",
        "POWER_PACK_WEAPONS": "Power Pack Weapons",
        "SPECIAL_WEAPONS": "Special Weapons",
    },
    "Other": {"OPTIONS": "Options"},
}
equipment_category_choices_flat = {
    key: value
    for subcategories in equipment_category_choices.values()
    for key, value in subcategories.items()
}


T = TypeVar("T")
QuerySetOf = Union[QuerySet, List[T]]
