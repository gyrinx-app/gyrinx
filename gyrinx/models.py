import uuid

from django.db import models
from django.utils import timezone


class Archived(models.Model):
    """An Archived object is no longer in use."""

    archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=False)

    def archive(self):
        self.archived = True
        self.archived_at = timezone.now()
        # TODO: Iterate through specific, related objects and archive them
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
    CHEMS = "CHEMS", "Chems"
    CLOSE_COMBAT = "CLOSE_COMBAT", "Close Combat"
    DRIVE_UPGRADES = "DRIVE_UPGRADES", "Drive Upgrades"
    ENGINE_UPGRADES = "ENGINE_UPGRADES", "Engine Upgrades"
    EQUIPMENT = "EQUIPMENT", "Equipment"
    GRENADES = "GRENADES", "Grenades"
    HARDPOINT_UPGRADES = "HARDPOINT_UPGRADES", "Hardpoint Upgrades"
    HEAVY_WEAPONS = "HEAVY_WEAPONS", "Heavy Weapons"
    MOUNTS = "MOUNTS", "Mounts"
    PISTOLS = "PISTOLS", "Pistols"
    SPECIAL_WEAPONS = "SPECIAL_WEAPONS", "Special Weapons"
    STATUS_ITEMS = "STATUS_ITEMS", "Status Items"
    VEHICLE_EQUIPMENT = "VEHICLE_EQUIPMENT", "Vehicle Equipment"
