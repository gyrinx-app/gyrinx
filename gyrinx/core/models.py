from django.core.exceptions import ValidationError
from django.db import models


class Base(models.Model):
    id = models.AutoField(primary_key=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


##
## Content Models
##


class ContentImportVersion(Base):
    """Represents a version of the content import."""

    uuid = models.UUIDField(editable=False, db_index=True)
    ruleset = models.CharField(max_length=255, default="necromunda-2018")
    directory = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.ruleset} {self.uuid}"

    class Meta:
        verbose_name = "Content Import Version"
        verbose_name_plural = "Content Import Versions"


class Content(Base):
    # The uuid and version must be supplied when creating a new instance
    uuid = models.UUIDField(editable=False, db_index=True)
    version = models.ForeignKey(
        ContentImportVersion, on_delete=models.CASCADE, null=True, blank=True
    )

    class Meta:
        abstract = True


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
        return ContentHouse.Choices(self.name).label

    class Meta:
        verbose_name = "Content House"
        verbose_name_plural = "Content Houses"


class ContentCategory(Content):
    class Choices(models.TextChoices):
        # TODO: The None value is a placeholder for now. It should be removed
        NONE = "NONE", "None"
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
        return ContentCategory.Choices(self.name).label

    class Meta:
        verbose_name = "Content Category"
        verbose_name_plural = "Content Categories"


class ContentSkill(Content):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, default="None")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Content Skill"
        verbose_name_plural = "Content Skills"


class ContentEquipmentCategory(Content):
    class Choices(models.TextChoices):
        # TODO: The None value is a placeholder for now. It should be removed
        NONE = "NONE", "None"
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
        return ContentEquipmentCategory.Choices(self.name).label

    class Meta:
        verbose_name = "Content Equipment Category"
        verbose_name_plural = "Content Equipment Categories"


class ContentEquipment(Content):
    name = models.CharField(max_length=255)
    category = models.ForeignKey(ContentEquipmentCategory, on_delete=models.CASCADE)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Content Equipment"
        verbose_name_plural = "Content Equipment"


class ContentFighter(Content):
    type = models.CharField(max_length=255)
    category = models.ForeignKey(ContentCategory, on_delete=models.CASCADE)
    house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=True, blank=True
    )
    equipment = models.ManyToManyField(
        ContentEquipment, through="ContentFighterEquipmentAssignment"
    )
    skills = models.ManyToManyField(ContentSkill)

    def __str__(self):
        house = f"{self.house}" if self.house else ""
        return f"{house} {self.type} ({self.category})".strip()

    class Meta:
        verbose_name = "Content Fighter"
        verbose_name_plural = "Content Fighters"


class ContentFighterEquipmentAssignment(Content):
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, db_index=True
    )
    qty = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.fighter} {self.equipment} Equipment Assignment ({self.qty})"

    class Meta:
        verbose_name = "Content Fighter Equipment Assignment"
        verbose_name_plural = "Content Fighter Equipment Assignments"
        unique_together = ["fighter", "equipment"]


class ContentFighterEquipment(Content):
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    equipment = models.ForeignKey(
        ContentEquipment, on_delete=models.CASCADE, db_index=True
    )
    cost = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.fighter} Equipment"

    class Meta:
        verbose_name = "Content Fighter Equipment Join"
        verbose_name_plural = "Content Fighter Equipment Joins"
        unique_together = ["fighter", "equipment"]


def check(rule, category, name):
    """Check if the rule applies to the category and name."""
    dc = rule.get("category") in [None, category]
    dn = rule.get("name") in [None, name]
    return dc and dn


class ContentPolicy(Content):
    fighter = models.ForeignKey(ContentFighter, on_delete=models.CASCADE, db_index=True)
    rules = models.JSONField()

    def allows(self, equipment: ContentEquipment) -> bool:
        """Check if the policy allows the equipment."""
        name = equipment.name
        category = equipment.category.name.label
        # Work through the rules in reverse order. If any of them
        # allow, then the equipment is allowed.
        # If we get to an explicit deny, then the equipment is denied.
        # If we get to the end, then the equipment is allowed.
        for rule in reversed(self.rules):
            deny = rule.get("deny", [])
            if deny == "all":
                return False
            # The deny rule is an AND rule. The category and name must
            # both match, or be missing, for the rule to apply.
            deny_fail = any([check(d, category, name) for d in deny])
            if deny_fail:
                return False

            allow = rule.get("allow", [])
            if allow == "all":
                return True
            # The allow rule is an AND rule. The category and name must
            # both match, or be missing, for the allow to apply.
            allow_pass = any([check(a, category, name) for a in allow])
            if allow_pass:
                return True

        return True

    class Meta:
        verbose_name = "Content Policy"
        verbose_name_plural = "Content Policies"
        verbose_name_plural = "Content Policies"


##
## Application Models
##


class Build(Base):
    """A Build is a reusable collection of fighters."""

    name = models.CharField(max_length=255)
    content_house_uuid = models.UUIDField(null=False, blank=False)

    class Meta:
        verbose_name = "Build"
        verbose_name_plural = "Builds"

    def __str__(self):
        return self.name

    def get_content_house(self):
        return ContentHouse.objects.get(uuid=self.content_house_uuid)


class BuildFighter(Base):
    """A Fighter is a member of a build."""

    name = models.CharField(max_length=255)
    content_fighter_uuid = models.UUIDField(null=False, blank=False)
    build = models.ForeignKey(Build, on_delete=models.CASCADE, null=False, blank=False)

    class Meta:
        verbose_name = "Build Fighter"
        verbose_name_plural = "Build Fighters"

    def __str__(self):
        cf = self.get_content_fighter()
        return f"{self.name} – {cf.type} ({cf.category})"

    def get_content_fighter(self):
        return ContentFighter.objects.get(uuid=self.content_fighter_uuid)

    def clean(self):
        cf = self.get_content_fighter()
        cf_house = cf.house
        build_house = self.build.get_content_house()
        if cf_house != build_house:
            raise ValidationError(
                f"{cf.type} cannot be a member of {build_house} build"
            )
