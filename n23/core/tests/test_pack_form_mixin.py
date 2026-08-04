"""PackItemFormMixin: the shared pack-item form behaviour (#1863).

The `Content*PackForm` family shares its name-uniqueness checks and its
Default/Custom choice grouping through `PackItemFormMixin`. Centralising that
logic means one place now decides how archived pack items are treated across
all thirteen forms — so the archive-semantics rule is pinned here rather than
resting on thirteen separate implementations.
"""

import pytest
from django import forms
from django.contrib.contenttypes.models import ContentType

from n23.content.models import ContentWeaponTrait
from n23.core.forms.pack import ContentWeaponTraitPackForm, PackItemFormMixin
from n23.core.models.pack import CustomContentPackItem


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

    Archiving is the pack owner's soft-delete, so an archived item has to stop
    reserving its name against its own owner — otherwise they can never reuse
    a name they archived. See CLAUDE.md, "Content packs: archive semantics".
    """
    _trait, item = trait_in_pack
    # The trait is pack-registered, so the default manager (which excludes
    # pack content) cannot see it. Asserted so that if that ever changes this
    # test fails here, rather than silently passing the base-library half.
    assert not ContentWeaponTrait.objects.filter(name__iexact="Blaze").exists()
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
def test_pack_item_object_ids_excludes_archived(pack, trait_in_pack):
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


def test_forms_that_are_never_pack_scoped_still_have_a_pack_default():
    """Six `Content*Form`s inherit the mixin without ever assigning `_pack`.
    The class default is what keeps their "no pack" branches from raising."""
    assert PackItemFormMixin._pack is None


@pytest.mark.django_db
def test_editing_an_object_does_not_collide_with_itself(pack, trait_in_pack):
    """`_raise_if_name_taken` excludes the instance being edited — otherwise
    every edit form would reject its own current name. This is now the single
    self-exclusion for all thirteen forms."""
    trait, _item = trait_in_pack
    form = ContentWeaponTraitPackForm(
        data={"name": "Blaze", "description": "Edited"},
        instance=trait,
        pack=pack,
    )
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_grouped_choices_put_custom_before_default(pack, trait_in_pack):
    """The shared grouping helper: a blank sentinel, then this pack's items
    under "Custom", then base-library items under "Default". Pinned because
    three call sites collapsed into this one implementation."""
    in_pack, _item = trait_in_pack
    base = ContentWeaponTrait.objects.create(name="Ancient")

    class _GroupingForm(PackItemFormMixin, forms.Form):
        trait = forms.ModelChoiceField(queryset=ContentWeaponTrait.objects.none())

    form = _GroupingForm()
    form._pack = pack
    form._apply_grouped_pack_choices(
        "trait", ContentWeaponTrait.objects.all_content(), ContentWeaponTrait
    )

    choices = form.fields["trait"].choices
    assert choices[0] == ("", "---------")
    assert choices[1][0] == "Custom"
    assert [label for _pk, label in choices[1][1]] == [str(in_pack)]
    assert choices[2][0] == "Default"
    assert [label for _pk, label in choices[2][1]] == [str(base)]


@pytest.mark.django_db
def test_grouping_omits_empty_groups_and_no_ops_without_a_pack(pack):
    """Empty groups are dropped, and a form with no pack keeps plain choices."""
    base = ContentWeaponTrait.objects.create(name="Ancient")

    class _GroupingForm(PackItemFormMixin, forms.Form):
        trait = forms.ModelChoiceField(queryset=ContentWeaponTrait.objects.none())

    # Pack with no items of this type -> sentinel + Default only.
    form = _GroupingForm()
    form._pack = pack
    form._apply_grouped_pack_choices(
        "trait", ContentWeaponTrait.objects.all_content(), ContentWeaponTrait
    )
    groups = [g[0] for g in form.fields["trait"].choices]
    assert groups == ["", "Default"]
    assert [label for _pk, label in form.fields["trait"].choices[1][1]] == [str(base)]

    # No pack at all -> helper leaves the field's own choices alone.
    plain = _GroupingForm()
    before = list(plain.fields["trait"].choices)
    plain._apply_grouped_pack_choices(
        "trait", ContentWeaponTrait.objects.all_content(), ContentWeaponTrait
    )
    assert list(plain.fields["trait"].choices) == before
