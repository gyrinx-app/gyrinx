"""Handler for copying campaign assets and resources between campaigns."""

from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count

from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAsset,
    CampaignAssetType,
    CampaignAttributeType,
    CampaignAttributeValue,
    CampaignContentPack,
    CampaignResourceType,
    CampaignSubAsset,
)


@dataclass
class CopyConflicts:
    """Represents name conflicts between source and target campaigns."""

    asset_type_conflicts: list[str] = field(default_factory=list)
    resource_type_conflicts: list[str] = field(default_factory=list)
    attribute_type_conflicts: list[str] = field(default_factory=list)

    @property
    def has_conflicts(self):
        return bool(
            self.asset_type_conflicts
            or self.resource_type_conflicts
            or self.attribute_type_conflicts
        )


@dataclass
class CopyResult:
    """Result of copying campaign content."""

    asset_types_copied: int = 0
    assets_copied: int = 0
    sub_assets_copied: int = 0
    resource_types_copied: int = 0
    attribute_types_copied: int = 0
    attribute_values_copied: int = 0
    packs_copied: int = 0

    @property
    def total_copied(self):
        return (
            self.asset_types_copied
            + self.assets_copied
            + self.sub_assets_copied
            + self.resource_types_copied
            + self.attribute_types_copied
            + self.attribute_values_copied
            + self.packs_copied
        )


def check_copy_conflicts(
    source_campaign: Campaign,
    target_campaign: Campaign,
    asset_type_ids: list[str] | None = None,
    resource_type_ids: list[str] | None = None,
    attribute_type_ids: list[str] | None = None,
    pack_ids: list[str] | None = None,
) -> CopyConflicts:
    """Check for name conflicts between source and target campaigns.

    Args:
        source_campaign: The campaign to copy from
        target_campaign: The campaign to copy to
        asset_type_ids: List of asset type IDs to check (None/empty = none)
        resource_type_ids: List of resource type IDs to check (None/empty = none)
        attribute_type_ids: List of attribute type IDs to check (None/empty = none)
        pack_ids: List of pack IDs to copy (None/empty = none). Packs are
            existing entities added by reference, so no conflict check is needed.

    Returns:
        CopyConflicts with lists of conflicting names
    """
    conflicts = CopyConflicts()

    # Get source asset type names (only if IDs provided)
    if asset_type_ids:
        source_asset_types = source_campaign.asset_types.filter(id__in=asset_type_ids)
        source_asset_type_names = set(
            source_asset_types.values_list("name_singular", flat=True)
        )

        # Check for conflicts with target asset types
        target_asset_type_names = set(
            target_campaign.asset_types.values_list("name_singular", flat=True)
        )
        conflicts.asset_type_conflicts = sorted(
            source_asset_type_names & target_asset_type_names
        )

    # Get source resource type names (only if IDs provided)
    if resource_type_ids:
        source_resource_types = source_campaign.resource_types.filter(
            id__in=resource_type_ids
        )
        source_resource_type_names = set(
            source_resource_types.values_list("name", flat=True)
        )

        # Check for conflicts with target resource types
        target_resource_type_names = set(
            target_campaign.resource_types.values_list("name", flat=True)
        )
        conflicts.resource_type_conflicts = sorted(
            source_resource_type_names & target_resource_type_names
        )

    # Get source attribute type names (only if IDs provided)
    if attribute_type_ids:
        source_attribute_types = source_campaign.attribute_types.filter(
            id__in=attribute_type_ids
        )
        source_attribute_type_names = set(
            source_attribute_types.values_list("name", flat=True)
        )

        # Check for conflicts with target attribute types
        target_attribute_type_names = set(
            target_campaign.attribute_types.values_list("name", flat=True)
        )
        conflicts.attribute_type_conflicts = sorted(
            source_attribute_type_names & target_attribute_type_names
        )

    return conflicts


@transaction.atomic
def copy_campaign_content(
    source_campaign: Campaign,
    target_campaign: Campaign,
    user,
    asset_type_ids: list[str] | None = None,
    resource_type_ids: list[str] | None = None,
    attribute_type_ids: list[str] | None = None,
    pack_ids: list[str] | None = None,
) -> CopyResult:
    """Copy selected content from source campaign to target campaign.

    This copies:
    - Asset types with their property and sub-asset schemas
    - Assets with their properties (but NOT holder assignments)
    - Sub-assets with their properties
    - Resource types (but NOT per-list allocations)
    - Attribute types with their values (but NOT per-list assignments)
    - Content packs (added by reference to the target campaign)

    Conflicts (same name exists in target) are skipped.

    Args:
        source_campaign: The campaign to copy from
        target_campaign: The campaign to copy to
        user: The user performing the copy (for ownership)
        asset_type_ids: List of asset type IDs to copy (None = none)
        resource_type_ids: List of resource type IDs to copy (None = none)
        attribute_type_ids: List of attribute type IDs to copy (None = none)
        pack_ids: List of pack IDs to copy (None = none)

    Returns:
        CopyResult with counts of what was copied
    """
    result = CopyResult()

    # Get existing names in target to skip conflicts
    existing_asset_type_names = set(
        target_campaign.asset_types.values_list("name_singular", flat=True)
    )
    existing_resource_type_names = set(
        target_campaign.resource_types.values_list("name", flat=True)
    )
    existing_attribute_type_names = set(
        target_campaign.attribute_types.values_list("name", flat=True)
    )

    # Copy asset types and their assets
    if asset_type_ids:
        source_asset_types = source_campaign.asset_types.filter(
            id__in=asset_type_ids
        ).prefetch_related("assets__sub_assets")

        for source_type in source_asset_types:
            # Skip if name already exists in target
            if source_type.name_singular in existing_asset_type_names:
                continue

            # Create the asset type copy
            new_type = CampaignAssetType.objects.create(
                campaign=target_campaign,
                owner=user,
                name_singular=source_type.name_singular,
                name_plural=source_type.name_plural,
                description=source_type.description,
                property_schema=source_type.property_schema,
                sub_asset_schema=source_type.sub_asset_schema,
            )
            result.asset_types_copied += 1

            # Copy assets for this type
            for source_asset in source_type.assets.all():
                new_asset = CampaignAsset.objects.create(
                    asset_type=new_type,
                    owner=user,
                    name=source_asset.name,
                    description=source_asset.description,
                    holder=None,  # Don't copy holder assignment
                    properties=source_asset.properties,
                )
                result.assets_copied += 1

                # Copy sub-assets
                for source_sub_asset in source_asset.sub_assets.all():
                    CampaignSubAsset.objects.create(
                        parent_asset=new_asset,
                        owner=user,
                        sub_asset_type=source_sub_asset.sub_asset_type,
                        name=source_sub_asset.name,
                        properties=source_sub_asset.properties,
                    )
                    result.sub_assets_copied += 1

    # Copy resource types
    if resource_type_ids:
        source_resource_types = source_campaign.resource_types.filter(
            id__in=resource_type_ids
        )

        for source_type in source_resource_types:
            # Skip if name already exists in target
            if source_type.name in existing_resource_type_names:
                continue

            CampaignResourceType.objects.create(
                campaign=target_campaign,
                owner=user,
                name=source_type.name,
                description=source_type.description,
                default_amount=source_type.default_amount,
            )
            result.resource_types_copied += 1

    # Copy attribute types and their values
    if attribute_type_ids:
        source_attribute_types = source_campaign.attribute_types.filter(
            id__in=attribute_type_ids
        ).prefetch_related("values")

        for source_type in source_attribute_types:
            # Skip if name already exists in target
            if source_type.name in existing_attribute_type_names:
                continue

            new_type = CampaignAttributeType.objects.create(
                campaign=target_campaign,
                owner=user,
                name=source_type.name,
                description=source_type.description,
                is_single_select=source_type.is_single_select,
            )
            result.attribute_types_copied += 1

            # Copy values for this attribute type
            for source_value in source_type.values.all():
                CampaignAttributeValue.objects.create(
                    attribute_type=new_type,
                    owner=user,
                    name=source_value.name,
                    description=source_value.description,
                    colour=source_value.colour,
                )
                result.attribute_values_copied += 1

    # Copy packs (add by reference — packs are shared entities, not cloned).
    # Carry the `required` flag from the source link onto the target link.
    if pack_ids:
        existing_pack_ids = set(target_campaign.packs.values_list("id", flat=True))
        source_links = source_campaign.pack_links.filter(
            pack_id__in=pack_ids
        ).select_related("pack")
        for link in source_links:
            if link.pack_id not in existing_pack_ids:
                CampaignContentPack.objects.create(
                    campaign=target_campaign,
                    pack=link.pack,
                    required=link.required,
                )
                result.packs_copied += 1

    return result


DEFAULT_RESOURCE_TYPE_NAME = "Reputation"
DEFAULT_RESOURCE_TYPE_DESCRIPTION = "Gang reputation gained during the campaign"


@dataclass
class TemplateApplication:
    """Result of seeding a new campaign from a template campaign."""

    copied: CopyResult
    settings_copied: list[str] = field(default_factory=list)


def ensure_default_resource_type(
    *, campaign: Campaign, user
) -> CampaignResourceType | None:
    """Give a campaign the default Reputation resource type unless it already has one.

    Every campaign gets Reputation on creation. A campaign seeded from a template
    may already have its own — with the template author's description and default
    amount — in which case we leave that alone rather than adding a near-duplicate.

    Returns the created resource type, or None if one already existed.
    """
    if campaign.resource_types.filter(name__iexact=DEFAULT_RESOURCE_TYPE_NAME).exists():
        return None

    return CampaignResourceType.objects.create(
        campaign=campaign,
        name=DEFAULT_RESOURCE_TYPE_NAME,
        description=DEFAULT_RESOURCE_TYPE_DESCRIPTION,
        default_amount=1,
        owner=user,
    )


@transaction.atomic
def apply_campaign_template(
    *,
    template_campaign: Campaign,
    campaign: Campaign,
    user,
) -> TemplateApplication:
    """Seed a freshly created campaign from a template campaign.

    Copies everything the template has — asset types (with their assets and
    sub-assets), resource types, attribute types and values, and content packs —
    with no per-type selection: a brand-new campaign has nothing to conflict with.

    Also carries over `default_included_crew_categories`, which shapes how crews
    are picked and has no equivalent on the new-campaign form. `budget` is NOT
    copied here — it is a visible field on that form, prefilled from the template,
    so whatever the user submitted wins.

    Two fields are deliberately left alone: `group_attribute_type` and
    `default_gang_sort` both hold IDs pointing at the template's own rows, and
    copying them verbatim would aim the new campaign at the template's data.
    """
    copied = copy_campaign_content(
        source_campaign=template_campaign,
        target_campaign=campaign,
        user=user,
        asset_type_ids=list(template_campaign.asset_types.values_list("id", flat=True)),
        resource_type_ids=list(
            template_campaign.resource_types.values_list("id", flat=True)
        ),
        attribute_type_ids=list(
            template_campaign.attribute_types.values_list("id", flat=True)
        ),
        pack_ids=list(template_campaign.packs.values_list("id", flat=True)),
    )

    settings_copied = []
    if template_campaign.default_included_crew_categories:
        campaign.default_included_crew_categories = list(
            template_campaign.default_included_crew_categories
        )
        campaign.save(update_fields=["default_included_crew_categories"])
        settings_copied.append("default_included_crew_categories")

    return TemplateApplication(copied=copied, settings_copied=settings_copied)


def describe_campaign_contents(campaign: Campaign) -> list[dict]:
    """Summarise what `apply_campaign_template` would copy out of a campaign.

    Returns groups of ``{"label": str, "names": list[str]}`` for display before
    the user commits — so "start from this template" is not a leap of faith.
    """
    groups = []

    asset_types = campaign.asset_types.annotate(asset_count=Count("assets"))
    asset_names = [
        f"{t.name_plural} ({t.asset_count})" if t.asset_count else t.name_plural
        for t in asset_types
    ]
    if asset_names:
        groups.append({"label": "Assets", "names": asset_names})

    resource_names = list(campaign.resource_types.values_list("name", flat=True))
    if resource_names:
        groups.append({"label": "Resources", "names": resource_names})

    attribute_names = list(campaign.attribute_types.values_list("name", flat=True))
    if attribute_names:
        groups.append({"label": "Attributes", "names": attribute_names})

    pack_names = list(campaign.packs.values_list("name", flat=True))
    if pack_names:
        groups.append({"label": "Content Packs", "names": pack_names})

    return groups
