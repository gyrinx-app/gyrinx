from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.models import Archived, Base, Owned


class AppBase(Base, Owned, Archived):
    """An AppBase object is a base class for all application models."""

    class Meta:
        abstract = True


##
## Application Models
##


class Build(AppBase):
    """A Build is a reusable collection of fighters."""

    help_text = (
        "A Build is a reusable collection of fighters, linked to a Content House."
    )
    name = models.CharField(max_length=255)
    content_house = models.ForeignKey(
        ContentHouse, on_delete=models.CASCADE, null=False, blank=False
    )

    history = HistoricalRecords()

    @admin.display(description="Cost")
    def cost(self):
        return sum([f.cost() for f in self.buildfighter_set.all()])

    class Meta:
        verbose_name = "Build"
        verbose_name_plural = "Builds"

    def __str__(self):
        return self.name


class BuildFighter(AppBase):
    """A Fighter is a member of a build."""

    help_text = "A Build Fighter is a member of a Build, linked to a Content Fighter archetype to give base stats and equipment."
    name = models.CharField(max_length=255)
    content_fighter = models.ForeignKey(
        ContentFighter, on_delete=models.CASCADE, null=False, blank=False
    )
    build = models.ForeignKey(Build, on_delete=models.CASCADE, null=False, blank=False)

    history = HistoricalRecords()

    @admin.display(description="Cost")
    def cost(self):
        return self.content_fighter.cost()

    class Meta:
        verbose_name = "Build Fighter"
        verbose_name_plural = "Build Fighters"

    def __str__(self):
        cf = self.content_fighter
        return f"{self.name} – {cf.type} ({cf.category})"

    def clean(self):
        cf = self.content_fighter
        cf_house = cf.house
        build_house = self.build.content_house
        if cf_house != build_house:
            raise ValidationError(
                f"{cf.type} cannot be a member of {build_house} build"
            )
