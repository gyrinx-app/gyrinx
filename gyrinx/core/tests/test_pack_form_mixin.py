"""PackItemFormMixin: the shared pack-item form behaviour (#1863).

The `Content*PackForm` family shares its name-uniqueness checks and its
Default/Custom choice grouping through `PackItemFormMixin`. Centralising that
logic means one place now decides how archived pack items are treated across
all thirteen forms — so the archive-semantics rule is pinned here rather than
resting on thirteen separate implementations.
"""

import pytest
from django.contrib.contenttypes.models import ContentType

from gyrinx.content.models import ContentWeaponTrait
from gyrinx.core.forms.pack import ContentWeaponTraitPackForm
from gyrinx.core.models.pack import CustomContentPackItem


@pytest.fixture
def trait_in_pack(pack, user):
    """A weapon trait registered to `pack` — returns (trait, pack item)."""
    trait = ContentWeaponTrait.objects.create(name="Blaze")
    item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentWeaponTrait),
        object_id=trait.pk,
        owner=user,
    )
    return trait, item


@pytest.mark.django_db
def test_duplicate_name_within_the_pack_is_rejected(pack, trait_in_pack):
    """The in-pack uniqueness half of the shared check."""
    form = ContentWeaponTraitPackForm(
        data={"name": "Blaze", "description": ""}, pack=pack
    )
    assert not form.is_valid()
    assert "already exists in this Content Pack" in str(form.errors["name"])


@pytest.mark.django_db
def test_archived_pack_item_does_not_block_the_name(pack, trait_in_pack):
    """An archived pack item must not reserve its name.

    `CustomContentPackItem`'s unique constraint is conditional on
    `archived=False`, so the form's "is this name taken?" lookup has to match
    it — otherwise the form rejects a name the database would happily accept,
    and the pack owner can never reuse a name they archived. See CLAUDE.md,
    "Content packs: archive semantics".
    """
    _trait, item = trait_in_pack
    # Same name is rejected while the item is live...
    assert not ContentWeaponTraitPackForm(
        data={"name": "Blaze", "description": ""}, pack=pack
    ).is_valid()

    # ...and accepted once it is archived. (The trait row stays: registering it
    # to a pack takes it out of the default manager, so the base-library half
    # of the check does not see it and only the archive rule is under test.)
    item.archived = True
    item.save()

    form = ContentWeaponTraitPackForm(
        data={"name": "Blaze", "description": ""}, pack=pack
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_pack_item_object_ids_excludes_archived(pack, trait_in_pack, user):
    """The shared primitive both the uniqueness check and the choice grouping
    build on — archived items are out of scope for both."""
    trait, item = trait_in_pack
    form = ContentWeaponTraitPackForm(pack=pack)

    assert list(form._pack_item_object_ids(ContentWeaponTrait)) == [trait.pk]

    item.archived = True
    item.save()
    assert list(form._pack_item_object_ids(ContentWeaponTrait)) == []


@pytest.mark.django_db
def test_no_pack_means_no_in_pack_checks():
    """Forms used outside a pack context skip the pack lookups entirely."""
    form = ContentWeaponTraitPackForm(pack=None)
    assert list(form._pack_item_object_ids(ContentWeaponTrait)) == []
    # A name that exists in no library at all validates fine.
    form = ContentWeaponTraitPackForm(data={"name": "Novel Trait", "description": ""})
    assert form.is_valid(), form.errors
