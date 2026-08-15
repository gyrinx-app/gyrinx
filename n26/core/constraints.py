"""Naming exactly one of several kinds of thing.

Several models point at "an assignable" — a player's ``Assignment``, a
profile's ``DefaultAssignment``, a modifier's add/remove effect. Since
assignables are a mixin rather than a table, each holds one nullable
foreign key per kind with a check constraint that exactly one is set.

This module holds the shape they share: the constraint builder, and a
mixin giving them all the same small API.
"""

from django.core.exceptions import ValidationError
from django.db import models


def exactly_one_of(fields):
    """A Q matching rows where exactly one of ``fields`` is set."""
    condition = models.Q()
    for field in fields:
        term = models.Q(**{f"{field}__isnull": False})
        for other in fields:
            if other != field:
                term &= models.Q(**{f"{other}__isnull": True})
        condition |= term
    return condition


class NamesAnAssignable(models.Model):
    """Mixin for a model that names exactly one assignable.

    Subclasses declare their own foreign keys — the permitted kinds differ,
    since a player can be assigned a fighter profile but a profile cannot
    *come with* one — and list them in ``ASSIGNABLE_FIELDS``. Everything
    else is shared: constructing with ``assignable=``, reading it back, and
    validating that exactly one is named.
    """

    #: Field names holding an assignable. A dict (name -> label) is fine;
    #: only the keys are read.
    ASSIGNABLE_FIELDS = ()

    class Meta:
        abstract = True

    def __init__(self, *args, assignable=None, **kwargs):
        if assignable is not None:
            kwargs[self.field_for(assignable)] = assignable
        super().__init__(*args, **kwargs)

    @classmethod
    def field_for(cls, assignable):
        """Which column holds this kind of assignable."""
        for name in cls.ASSIGNABLE_FIELDS:
            related = cls._meta.get_field(name).related_model
            if isinstance(assignable, related):
                return name
        allowed = ", ".join(cls.ASSIGNABLE_FIELDS)
        raise ValueError(
            f"{type(assignable).__name__} is not something a "
            f"{cls._meta.verbose_name} can name. Allowed: {allowed}."
        )

    @property
    def assignable(self):
        """Whichever assignable this names. No queries for the empty columns."""
        for name in self.ASSIGNABLE_FIELDS:
            if getattr(self, f"{name}_id") is not None:
                return getattr(self, name)
        return None

    def names_exactly_one(self):
        return (
            sum(
                getattr(self, f"{name}_id") is not None
                for name in self.ASSIGNABLE_FIELDS
            )
            == 1
        )

    def clean(self):
        super().clean()
        if not self.names_exactly_one():
            raise ValidationError(
                f"A {self._meta.verbose_name} must name exactly one assignable."
            )
