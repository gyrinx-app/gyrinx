import uuid

from django.db import models


class Base(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class Content(Base):
    # TODO: In future?
    # ruleset = models.CharField(max_length=255, default="necromunda-2018")
    # filepath = models.CharField(max_length=255)

    class Meta:
        abstract = True


class House(Content):
    class HouseNameChoices(models.TextChoices):
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

    name = models.CharField(max_length=255, choices=HouseNameChoices)

    def __str__(self):
        return self.name


class Category(Content):
    class CategoryNameChoices(models.TextChoices):
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

    name = models.CharField(
        max_length=255,
        choices=CategoryNameChoices,
        default=CategoryNameChoices.NONE,
    )

    def __str__(self):
        return self.name


class Fighter(Content):
    type = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    house = models.ForeignKey(House, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.type
