from django.db import models


class Base(models.Model):
    id = models.AutoField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Content(Base):
    # The uuid and version must be supplied when creating a new instance
    uuid = models.UUIDField(editable=False, db_index=True)
    version = models.CharField(max_length=255, db_index=True)

    class Meta:
        abstract = True


class ContentImportVersion(Content):
    ruleset = models.CharField(max_length=255, default="necromunda-2018")
    directory = models.CharField(max_length=255)


class ContentHouse(Content):
    class Choices(models.TextChoices):
        VENATORS = "VENATORS", "Venators"
        VAN_SAAR_HOA = "VAN_SAAR_HOA", "Van Saar (HoA)"
        VAN_SAAR_GOTU = "VAN_SAAR_GOTU", "Van Saar (GotU)"
        SQUAT_PROSPECTORS = "SQUAT_PROSPECTORS", "Squat Prospectors"
        SLAVE_OGRYN = "SLAVE_OGRYN", "Slave Ogryn"
        ORLOCK_HOI = "ORLOCK_HOI", "Orlock (HoI)"
        ORLOCK_GOTU = "ORLOCK_GOTU", "Orlock (GotU)"
        GOLIATH_HOC = "GOLIATH_HOC", "Goliath (HoC)"
        GOLIATH_GOTU = "GOLIATH_GOTU", "Goliath (GotU)"
        GENESTEALER_CULT = "GENESTEALER_CULT", "Genestealer Cult"
        ESCHER_HOB = "ESCHER_HOB", "Escher (HoB)"
        ESCHER_GOTU = "ESCHER_GOTU", "Escher (GotU)"
        ENFORCERS = "ENFORCERS", "Enforcers"
        DELAQUE_HOS = "DELAQUE_HOS", "Delaque (HoS)"
        DELAQUE_GOTU = "DELAQUE_GOTU", "Delaque (GotU)"
        CORPSE_GRINDER_CULT = "CORPSE_GRINDER_CULT", "Corpse Grinder Cult"
        CHAOS_CULT = "CHAOS_CULT", "Chaos Cult"
        CAWDOR_HOF = "CAWDOR_HOF", "Cawdor (HoF)"
        CAWDOR_GOTU = "CAWDOR_GOTU", "Cawdor (GotU)"
        ASH_WASTE_NOMADS = "ASH_WASTE_NOMADS", "Ash Waste Nomads"

    name = models.CharField(max_length=255, choices=Choices)

    def __str__(self):
        return self.name


class ContentCategory(Content):
    class Choices(models.TextChoices):
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

    name = models.CharField(max_length=255, choices=Choices)

    def __str__(self):
        return self.name


class Skill(Content):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class ContentEquipmentCategory(Content):
    class Choices(models.TextChoices):
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

    name = models.CharField(max_length=255, choices=Choices)

    def __str__(self):
        return self.name


class ContentEquipment(Content):
    name = models.CharField(max_length=255)
    category = models.ForeignKey(ContentEquipmentCategory, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class ContentFighter(Content):
    type = models.CharField(max_length=255)
    category = models.ForeignKey(ContentCategory, on_delete=models.CASCADE)
    house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=True, blank=True
    )

    def __str__(self):
        return self.type


class ContentFighterEquipment(Content):
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE)
    equipment = models.ForeignKey(ContentEquipment, on_delete=models.CASCADE)
    cost = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.fighter} Equipment List"


class ContentPolicy(Content):
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    rules = models.JSONField()
