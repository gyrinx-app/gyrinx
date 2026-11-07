"""Control discovery of staged library content.

Staff and users allowed by the ``staged-content`` flag can discover staged
content through the ordinary founding, hiring and equipment surfaces.
Existing assignments render for every viewer, including staged content;
shared rosters must not change with the viewer's permissions.

Staging applies to newly discoverable content. Editing live content changes
it immediately. Uploaded CSV files in ``models/staging.py`` are separate
from staged content. See design/collections.md.
"""

from functools import cache

from n26 import flags

#: Where the flag's reading is kept on the user for the rest of the request.
_KEPT_ON_USER = "_sees_staged"


def sees_staged(user) -> bool:
    """Check staged-content access and cache the result on the user for this request.

    Anonymous users have no discovery access. Existing roster content remains
    visible independently of this check.
    """
    if user is None or not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    kept = getattr(user, _KEPT_ON_USER, None)
    if kept is None:
        kept = flags.enabled(flags.STAGED_CONTENT, user)
        setattr(user, _KEPT_ON_USER, kept)
    return kept


@cache
def content_kinds():
    """Cache concrete Content subclasses carrying the staged field, in authoring order."""
    from django.apps import apps

    from n26.library.models import Content

    found = [
        model
        for model in apps.get_app_config("library").get_models()
        if issubclass(model, Content)
    ]
    return tuple(sorted(found, key=lambda model: str(model._meta.verbose_name_plural)))


def stageable_kinds():
    """Discover kinds exposed by player selection surfaces.

    Include collection entries and picklist members because a new membership
    can expose existing content. Include interstitials and their attachments
    because they introduce new screens. Supporting categories, modifiers and
    statlines are reached through discoverable content and need no separate gate.
    """
    from django.apps import apps

    from n26.core.models import Assignment
    from n26.core.views.edit import EDITABLE_KINDS
    from n26.library.models import (
        Asset,
        CampaignType,
        CollectionEntry,
        GangType,
        Interstitial,
        InterstitialSlot,
        PicklistMember,
        ScenarioTable,
    )
    from n26.library.models.collection import entryable_kinds
    from n26.library.models.modifier import OFFERABLE_KINDS

    kinds = {
        GangType,
        CampaignType,
        Asset,
        CollectionEntry,
        PicklistMember,
        ScenarioTable,
        PicklistMember._meta.get_field("pickable").related_model,
        Interstitial,
        InterstitialSlot,
        *entryable_kinds().values(),
        *(apps.get_model("library", name) for name in OFFERABLE_KINDS),
        *(
            Assignment._meta.get_field(field).related_model
            for field in EDITABLE_KINDS.values()
        ),
    }
    return frozenset(kinds)


def stageable(model) -> bool:
    """Whether rows of this kind can be staged from the authoring pages."""
    return model in stageable_kinds()


def staged_counts():
    """How many rows are staged, kind by kind. One count per kind, and only
    the kinds with something staged."""
    found = []
    for model in content_kinds():
        count = model.objects.outside_campaign_packs().filter(staged=True).count()
        if count:
            found.append((model, count))
    return found


def staged_count():
    """How many rows are staged across the library — the figure the index
    shows beside its link."""
    return sum(count for _model, count in staged_counts())


def staged_rows():
    """List staged authoring content by kind, excluding campaign packs.

    Include all Content kinds so records staged outside normal workflows remain
    reachable. Omit empty kinds; issue one query per kind.
    """
    from n26.library.references import forward_relations

    found = []
    for model in content_kinds():
        # Load relations used by staged entry labels together to avoid per-entry queries.
        rows = list(
            model.objects.outside_campaign_packs()
            .filter(staged=True)
            .select_related(*forward_relations(model))
        )
        if rows:
            found.append((model, rows))
    return found
