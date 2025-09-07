import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple, TypeVar, Union
from uuid import UUID

from django.db import connections, models
from django.db.models import QuerySet
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

SMART_QUOTES = {
    "LEFT_DOUBLE": chr(0x201C),  # " LEFT DOUBLE QUOTATION MARK
    "RIGHT_DOUBLE": chr(0x201D),  # " RIGHT DOUBLE QUOTATION MARK
    "LEFT_SINGLE": chr(0x2018),  # ' LEFT SINGLE QUOTATION MARK
    "RIGHT_SINGLE": chr(0x2019),  # ' RIGHT SINGLE QUOTATION MARK
}


def is_int(value):
    """Check if a value is a number."""
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def format_cost_display(cost_value, show_sign=False):
    """
    Format a cost value for display with proper sign handling.

    Parameters
    ----------
    cost_value : int or str
        The cost value to format
    show_sign : bool
        Whether to show '+' for positive values (default: False)

    Returns
    -------
    str
        Formatted cost string with '¢' suffix

    Examples
    --------
    >>> format_cost_display(5)
    '5¢'
    >>> format_cost_display(5, show_sign=True)
    '+5¢'
    >>> format_cost_display(-5)
    '-5¢'
    >>> format_cost_display(-5, show_sign=True)
    '-5¢'
    >>> format_cost_display(0)
    '0¢'
    >>> format_cost_display(0, show_sign=True)
    '+0¢'
    """
    # Convert to int if it's a string
    if isinstance(cost_value, str):
        if not is_int(cost_value):
            return cost_value  # Return as-is if not a number
        cost_value = int(cost_value)

    # Format with sign if requested and positive or zero
    if show_sign and cost_value >= 0:
        return f"+{cost_value}¢"

    # Otherwise just return with currency symbol
    return f"{cost_value}¢"


def is_valid_uuid(uuid_to_test, version=4):
    """
    Check if uuid_to_test is a valid UUID.

     Parameters
    ----------
    uuid_to_test : str
    version : {1, 2, 3, 4}

     Returns
    -------
    `True` if uuid_to_test is a valid UUID, otherwise `False`.

     Examples
    --------
    >>> is_valid_uuid('c9bf9e57-1685-4c89-bafb-ff5af830be8a')
    True
    >>> is_valid_uuid('c9bf9e58')
    False
    """

    try:
        uuid_obj = UUID(uuid_to_test, version=version)
    except ValueError:
        return False
    return str(uuid_obj) == uuid_to_test


class Archived(models.Model):
    """An Archived object is no longer in use."""

    archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    def archive(self):
        self.archived = True
        self.archived_at = timezone.now()
        self.save()
        if hasattr(self, "archive_with"):
            for related in self.archive_with:
                if hasattr(related, "archive"):
                    related.archive()

    def unarchive(self):
        self.archived = False
        self.archived_at = None
        self.save()
        if hasattr(self, "archive_with"):
            for related in self.archive_with:
                if hasattr(related, "unarchive"):
                    related.unarchive()

    class Meta:
        abstract = True


class Owned(models.Model):
    """An Owned object is owned by a User."""

    owner = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, null=True, blank=False, db_index=True
    )

    class Meta:
        abstract = True


class Base(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    modified = models.DateTimeField(auto_now=True, db_index=True)

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
    STASH = "STASH", "Stash"
    VEHICLE = "VEHICLE", "Vehicle"
    ALLY = "ALLY", "Ally"
    GANG_TERRAIN = "GANG_TERRAIN", "Gang Terrain"


equipment_category_groups = [
    "Gear",
    "Vehicle & Mount",
    "Weapons & Ammo",
    "Other",
]
equipment_category_group_choices = [(x, x) for x in equipment_category_groups]


T = TypeVar("T")
QuerySetOf = Union[QuerySet, List[T]]


class CostMixin(models.Model):
    """
    Mixin for models that have cost calculation logic.

    This mixin provides common cost methods (cost_int, cost_display) that can be
    used by models with cost fields. It handles both integer and string cost fields.

    For models with special cost calculation logic, override the cost_int() method.

    Attributes
    ----------
    cost_field_name : str
        The name of the field that stores the cost. Defaults to 'cost'.
        Can be overridden in subclasses if the field has a different name.
    """

    cost_field_name = "cost"

    class Meta:
        abstract = True

    def cost_int(self):
        """
        Returns the integer cost of this item.

        This method handles both integer and string cost fields:
        - If the cost field is an integer, returns it directly
        - If the cost field is a string that can be converted to int, converts and returns it
        - If the cost field is empty or non-numeric, returns 0

        Override this method in subclasses for custom cost calculation logic.

        Returns
        -------
        int
            The cost as an integer
        """
        cost_value = getattr(self, self.cost_field_name, None)

        # Handle None or empty values
        if cost_value is None or cost_value == "":
            return 0

        # If it's already an integer, return it
        if isinstance(cost_value, int):
            return cost_value

        # If it's a string, try to convert
        if isinstance(cost_value, str):
            if is_int(cost_value):
                return int(cost_value)
            return 0

        # Default case
        return 0

    def cost_display(self, show_sign=False):
        """
        Returns a readable cost string with currency symbol.

        Parameters
        ----------
        show_sign : bool
            Whether to show '+' for positive values (default: False)

        Returns
        -------
        str
            Formatted cost string with '¢' suffix
        """
        cost_value = getattr(self, self.cost_field_name, None)

        # Special handling for string costs that aren't numeric
        if isinstance(cost_value, str) and not is_int(cost_value):
            return cost_value

        # For empty string costs, return empty
        if cost_value == "" or cost_value is None:
            return ""

        return format_cost_display(self.cost_int(), show_sign=show_sign)


class FighterCostMixin(CostMixin):
    """
    Extended cost mixin for models that have fighter-specific cost overrides.

    This mixin adds the cost_for_fighter_int() method that checks for the
    presence of an annotated 'cost_for_fighter' attribute.
    """

    class Meta:
        abstract = True

    def cost_for_fighter_int(self):
        """
        Returns the fighter-specific cost if available.

        This method expects the model to be annotated with a 'cost_for_fighter'
        attribute using the model's with_cost_for_fighter() queryset method.

        Returns
        -------
        int
            The fighter-specific cost

        Raises
        ------
        AttributeError
            If the model hasn't been annotated with cost_for_fighter
        """
        if hasattr(self, "cost_for_fighter"):
            return self.cost_for_fighter

        raise AttributeError(
            "cost_for_fighter not available. Use with_cost_for_fighter()"
        )


@dataclass
class QueryInfo:
    count: int
    total_time: float
    queries: List[Dict[str, str]]  # each has "sql" and "time" (string seconds)


def capture_queries(
    func: Callable[[], Any], *, using: str = "default"
) -> Tuple[Any, QueryInfo]:
    """
    Run `func` with query capture enabled and return (result, QueryInfo).
    Uses Django's CaptureQueriesContext under the hood.

    Works even if DEBUG=False because the context forces a debug cursor temporarily.
    """
    conn = connections[using]
    with CaptureQueriesContext(conn) as ctx:
        result = func()

    # ctx.captured_queries is a list of {"sql": "...", "time": "..."} (time as string seconds)
    total_time = sum(float(q.get("time") or 0.0) for q in ctx.captured_queries)

    info = QueryInfo(
        count=len(ctx.captured_queries),
        total_time=total_time,
        queries=ctx.captured_queries,
    )
    return result, info


def with_query_capture(using="default"):
    def deco(fn):
        def inner(*args, **kwargs):
            return capture_queries(lambda: fn(*args, **kwargs), using=using)

        return inner

    return deco
