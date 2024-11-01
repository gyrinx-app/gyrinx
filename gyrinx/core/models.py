from django.core.exceptions import ValidationError
from django.db import models

from gyrinx.content.models import Base, ContentFighter, ContentHouse

##
## Application Models
##


class Build(Base):
    """A Build is a reusable collection of fighters."""

    help_text = (
        "A Build is a reusable collection of fighters, linked to a Content House."
    )
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

    help_text = "A Build Fighter is a member of a Build, linked to a Content Fighter archetype to give base stats and equipment."
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
