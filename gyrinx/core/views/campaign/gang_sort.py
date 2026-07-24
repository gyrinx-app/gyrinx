"""Sorting for the Gangs table on the campaign page (#1459).

Gangs can be ordered by name, by one of the cached cost figures (rating, stash,
credits, wealth), or by any of the campaign's resource types — Reputation is a
resource type, created automatically with every campaign.

A sort is a token: the metric name, optionally prefixed with ``-`` for
descending. Resource metrics carry the resource type's id, e.g.
``-resource:3f2b…``. The same vocabulary is used for the ``?sort=`` query
parameter and for the campaign's stored default (``Campaign.default_gang_sort``),
so a default can be set from whatever the viewer is currently looking at.

Sorting happens in Python over the already-prefetched lists: campaigns hold tens
of gangs, the cost figures are cached columns, and the resource amounts are
already in the view's ``resource_lookup``. No extra queries.
"""

from dataclasses import dataclass
from typing import Callable, Optional

#: Used when neither the request nor the campaign specifies a valid sort.
DEFAULT_GANG_SORT = "-wealth"

RESOURCE_PREFIX = "resource:"

#: metric token -> (label, key function over a List)
METRIC_SORTS: dict[str, tuple[str, Callable]] = {
    "name": ("Gang name", lambda lst: lst.name.lower()),
    "wealth": ("Wealth", lambda lst: lst.wealth_current),
    "rating": ("Rating", lambda lst: lst.rating_current),
    "stash": ("Stash", lambda lst: lst.stash_current),
    "credits": ("Credits", lambda lst: lst.credits_current),
}


@dataclass(frozen=True)
class GangSort:
    """A resolved sort: which metric, which direction, and how to read it."""

    metric: str
    descending: bool
    label: str
    key: Callable

    @property
    def token(self) -> str:
        return f"-{self.metric}" if self.descending else self.metric

    @property
    def direction_label(self) -> str:
        if self.metric == "name":
            return "Z–A" if self.descending else "A–Z"
        return "high to low" if self.descending else "low to high"

    @property
    def icon(self) -> str:
        return "bi-sort-down" if self.descending else "bi-sort-up"


def _split(token: str) -> tuple[str, bool]:
    """Split a sort token into (metric, descending)."""
    token = (token or "").strip()
    if token.startswith("-"):
        return token[1:], True
    return token, False


def _resource_key(resource_type_id, resource_lookup) -> Callable:
    def key(lst):
        resource = resource_lookup.get(lst.id, {}).get(resource_type_id)
        return resource.amount if resource else 0

    return key


def parse_gang_sort(token, resource_types, resource_lookup=None) -> Optional[GangSort]:
    """Build a :class:`GangSort` from a token, or None if it isn't valid here.

    Resource metrics are validated against this campaign's resource types, so a
    stored default that points at a since-deleted resource simply falls back
    rather than breaking the page. ``resource_lookup`` is only needed to sort
    gangs; callers that just want to validate a token can omit it.
    """
    resource_lookup = resource_lookup or {}
    metric, descending = _split(token)
    if not metric:
        return None

    if metric in METRIC_SORTS:
        label, key = METRIC_SORTS[metric]
        return GangSort(metric=metric, descending=descending, label=label, key=key)

    if metric.startswith(RESOURCE_PREFIX):
        wanted = metric[len(RESOURCE_PREFIX) :]
        for resource_type in resource_types:
            if str(resource_type.id) == wanted:
                return GangSort(
                    metric=metric,
                    descending=descending,
                    label=resource_type.name,
                    key=_resource_key(resource_type.id, resource_lookup),
                )

    return None


def resolve_gang_sort(requested, campaign_default, resource_types, resource_lookup):
    """Pick the sort to use: the request's, else the campaign's, else wealth."""
    for token in (requested, campaign_default, DEFAULT_GANG_SORT):
        sort = parse_gang_sort(token, resource_types, resource_lookup)
        if sort:
            return sort
    # DEFAULT_GANG_SORT is always parseable, so this is unreachable in practice.
    raise ValueError(f"Invalid default gang sort: {DEFAULT_GANG_SORT}")


def sort_lists(lists, gang_sort):
    """Order lists by the given sort, keeping gangs still joining at the end.

    A gang that is still being cloned into the campaign (#1222) has no fighters
    or cost yet, so its figures are all zero — sorting it in among real values
    would be misleading. It goes last, alphabetically.
    """
    joined = [lst for lst in lists if not lst.is_cloning]
    cloning = sorted(
        (lst for lst in lists if lst.is_cloning), key=lambda lst: lst.name.lower()
    )

    # Pre-sort by name so gangs with equal values stay alphabetical (sort is stable).
    joined.sort(key=lambda lst: lst.name.lower())
    if gang_sort.metric == "name":
        if gang_sort.descending:
            joined.reverse()
    else:
        joined.sort(key=gang_sort.key, reverse=gang_sort.descending)

    return joined + cloning


def build_sort_options(current, resource_types):
    """Dropdown options for the sort control.

    Selecting the metric already in use flips its direction; selecting any other
    metric uses its natural direction — highest first for numbers, A–Z for names.
    """
    options = [
        _option(metric, label, current) for metric, (label, _) in METRIC_SORTS.items()
    ]
    options += [
        _option(f"{RESOURCE_PREFIX}{resource_type.id}", resource_type.name, current)
        for resource_type in resource_types
    ]
    return options


def _option(metric, label, current):
    active = current.metric == metric
    descending = not current.descending if active else metric != "name"
    return {
        "value": f"-{metric}" if descending else metric,
        "label": label,
        "active": active,
        # Shown on the active option: which way it is currently sorted.
        "icon": current.icon if active else "",
    }
