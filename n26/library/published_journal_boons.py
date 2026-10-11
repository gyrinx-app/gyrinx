"""Remove the published, empty House Controlled journal placeholders.

This repair targets eleven named rules and their exact journal grants.
Publishing changes discovery availability without adding rule behaviour.
Authored payloads, shared modifiers and rules referenced by content or player
history are retained. Territories, baseline Income and House tables stay as
they are; this operation seeds nothing.
"""

from django.conf import settings
from django.db import transaction
from django.db.models import ProtectedError

from n26.library.core_campaign import CAMPAIGN_TYPE
from n26.library.gang_supertypes import supertype_pick
from n26.library.journal_content import JOURNALS, _is_seeded_boon
from n26.library.territory_table import TERRITORY
from n26.write_pause import SCOPE, exclusive_write_scope, write_guard

NOTHING_TO_DO = "Nothing to do: no published journal boon placeholders can be removed."


def _is_published_placeholder(rule):
    """A published name-only placeholder, with no authored behaviour."""
    return not (
        rule.staged
        or rule.archived
        or rule.archived_at is not None
        or rule.modifiers.exists()
        or rule.built_ins_id is not None
        or rule.library_author_help
        or rule.price != 0
        or rule.trade_point_price is not None
        or rule.is_exclusive
        or rule.category_id is not None
        or rule.position != 0
    )


def remove_published_journal_boons():
    """Report each removal and retained candidate in one exclusive transaction."""
    from n26.library.authoring import delete_content, delete_modifier
    from n26.library.models import Asset, AssetType, ContentPack, Modifier, Rule

    removed = []
    skipped = []
    # Drain authoring before reading references, so a new carrier cannot
    # appear between the exact-shape check and deletion.
    with exclusive_write_scope(SCOPE), write_guard():
        pack = ContentPack.objects.filter(
            slug=settings.DEFAULT_CONTENT_PACK_SLUG
        ).first()
        if pack is None:
            return [NOTHING_TO_DO]
        territory = AssetType.objects.filter(
            campaign_type__pack=pack,
            campaign_type__name=CAMPAIGN_TYPE,
            campaign_type__qualifier="",
            label_singular=TERRITORY,
        ).first()
        for house, _table, territories in JOURNALS:
            pick = supertype_pick(house)
            for entry in territories:
                if entry.name == "Amneo-vats":
                    continue
                rule = Rule.objects.filter(
                    pack=pack,
                    name=f"{house} Controlled",
                    annotation=entry.name,
                    qualifier="",
                ).first()
                boon_name = f"{entry.name}: {house} Controlled"
                boon = Modifier.objects.filter(pack=pack, name=boon_name).first()
                if rule is None and boon is None:
                    continue
                if rule is not None and not _is_published_placeholder(rule):
                    reason = (
                        "it is staged"
                        if rule.staged
                        else "its content or archive state differs from the published placeholder"
                    )
                    skipped.append(f"skipped rule {rule} and its modifier: {reason}")
                    continue
                if boon is not None:
                    asset = (
                        Asset.objects.filter(
                            pack=pack,
                            name=entry.name,
                            qualifier="",
                            asset_type=territory,
                        ).first()
                        if territory is not None
                        else None
                    )
                    if asset is None or not _is_seeded_boon(
                        boon, asset, pick, rule, income=None
                    ):
                        skipped.append(
                            f"skipped modifier {boon_name}: its content or carriers differ from the journal seed"
                        )
                        continue
                    delete_modifier(boon)
                    removed.append(f"removed modifier {boon_name}")
                if rule is None:
                    continue
                label = str(rule)
                try:
                    delete_content(rule)
                except ProtectedError:
                    skipped.append(
                        f"skipped rule {label}: it is still referenced by content or player history"
                    )
                else:
                    removed.append(f"removed rule {label}")
    return [*removed, *skipped] if removed else [NOTHING_TO_DO, *skipped]


class _RolledBack(Exception):
    """Carry the repair's report out of a transaction that is rolled back."""


def preview():
    """Return the repair's exact report without retaining any changes."""
    try:
        with transaction.atomic():
            raise _RolledBack(remove_published_journal_boons())
    except _RolledBack as rolled_back:
        return rolled_back.args[0]
