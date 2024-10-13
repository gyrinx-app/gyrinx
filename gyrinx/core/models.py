import uuid

from django.db import models


class Base(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class Content(Base):
    filepath = models.CharField(max_length=255)

    class Meta:
        abstract = True


class ContentArchetype(Content):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name
