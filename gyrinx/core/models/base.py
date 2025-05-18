from gyrinx.models import Archived, Base, Owned


class AppBase(Base, Owned, Archived):
    """An AppBase object is a base class for all application models."""

    class Meta:
        abstract = True
        abstract = True
