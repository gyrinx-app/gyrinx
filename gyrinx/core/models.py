from django.core.exceptions import ValidationError
from django.db import models

from gyrinx.content.models import Base, ContentFighter, ContentHouse


class Archived(models.Model):
    """An Archived object is no longer in use."""

    archived = models.BooleanField(default=False)

    class Meta:
        abstract = True


class Owned(models.Model):
    """An Owned object is owned by a User."""

    owner = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=False
    )

    class Meta:
        abstract = True


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
