"""The admin is the main content-ingestion surface, so it gets its own tests."""

import pytest

from n26.library.models import ContentPack, Profile

pytestmark = pytest.mark.django_db


def test_changelist_renders(admin_client, make_profile):
    make_profile("Alpha")
    assert admin_client.get("/admin/library/profile/").status_code == 200


def test_change_page_resolves_a_ulid_url(admin_client, make_profile):
    profile = make_profile("Alpha")
    response = admin_client.get(f"/admin/library/profile/{profile.pk}/change/")
    assert response.status_code == 200


def test_add_page_renders(admin_client):
    assert admin_client.get("/admin/library/profile/add/").status_code == 200


def test_add_form_preselects_the_n26_pack(admin_client, default_pack):
    """Ingestion through the admin should land in N26 without anyone choosing it."""
    response = admin_client.get("/admin/library/profile/add/")
    form = response.context["adminform"].form
    assert form.get_initial_for_field(form.fields["pack"], "pack") == default_pack.pk


def test_saving_the_add_form_lands_content_in_n26(
    admin_client, default_pack, person_type, gang_type
):
    response = admin_client.post(
        "/admin/library/profile/add/",
        {
            "name": "Ingested",
            "pack": str(default_pack.pk),
            "profile_type": str(person_type.pk),
            "gang_type": str(gang_type.pk),
            "price": "10",
            # The reference price fields — profiles compose their credit
            # price, so they carry no stored cost.
            "trade_point_price": "0",
            "position": "0",
            "statline-TOTAL_FORMS": "0",
            "statline-INITIAL_FORMS": "0",
            "statline-MIN_NUM_FORMS": "0",
            "statline-MAX_NUM_FORMS": "1",
            "_save": "Save",
        },
    )
    assert response.status_code == 302, response.context["errors"]
    profile = Profile.objects.get(name="Ingested")
    assert profile.pack.slug == "n26"
    assert profile.price == 10


def test_pack_changelist_renders(admin_client):
    ContentPack.objects.create(name="Homebrew", slug="homebrew")
    assert admin_client.get("/admin/library/contentpack/").status_code == 200


def test_admin_links_use_the_base32_form(admin_client, make_profile):
    """Nicer than the UUID-hex rendering, and what people will paste around."""
    import re

    profile = make_profile("Alpha")
    html = admin_client.get("/admin/library/profile/").content.decode()
    links = re.findall(r'href="(/admin/library/profile/[^"]+/change/)"', html)
    assert f"/admin/library/profile/{profile.pk}/change/" in links
    assert str(profile.pk) in links[0]


def test_admin_also_accepts_the_uuid_form_in_a_url(admin_client, make_profile):
    profile = make_profile("Alpha")
    url = f"/admin/library/profile/{profile.pk.to_uuid()}/change/"
    assert admin_client.get(url).status_code == 200


@pytest.mark.parametrize(
    "model",
    [
        "contentpack",
        "gangtype",
        "stat",
        "statlinetype",
        "profiletype",
        "profile",
        "statline",
        "slottype",
        "pickable",
        "picklist",
        "picklistmember",
        "slot",
        "interstitial",
        "interstitialslot",
    ],
)
@pytest.mark.parametrize("page", ["", "add/"])
def test_every_registered_admin_page_renders(admin_client, model, page):
    response = admin_client.get(f"/admin/library/{model}/{page}")
    assert response.status_code == 200


def test_statline_type_admin_inlines_its_stats(admin_client, person_statline_type):
    response = admin_client.get(
        f"/admin/library/statlinetype/{person_statline_type.pk}/change/"
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "Movement" in html and "Weapon Skill" in html


def test_statline_admin_inlines_its_values(admin_client, make_profile, make_statline):
    profile = make_profile("Juve")
    statline = make_statline(profile, movement=4, weapon_skill=3, toughness=5)
    response = admin_client.get(f"/admin/library/statline/{statline.pk}/change/")
    assert response.status_code == 200


def test_an_attachment_added_with_its_interstitial_joins_its_pack(
    admin_client, default_pack, homebrew
):
    """On the add page nothing can know the parent's pack before it is
    saved, so the inline's save is what puts a new attachment there."""
    from n26.library.authoring import (
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
    )
    from n26.library.models import Interstitial, InterstitialSlot

    legacy = create_slot_type("Gang Legacy")
    houses = create_picklist(
        "Houses", legacy, members=[create_pickable("Cawdor", legacy)]
    )
    slot = create_slot("House legacy", legacy, houses)

    response = admin_client.post(
        "/admin/library/interstitial/add/",
        {
            "name": "Outcast archetype",
            "title": "",
            "description": "",
            "position": "0",
            "pack": str(homebrew.pk),
            "attachments-TOTAL_FORMS": "1",
            "attachments-INITIAL_FORMS": "0",
            "attachments-MIN_NUM_FORMS": "0",
            "attachments-MAX_NUM_FORMS": "1000",
            "attachments-0-slot": str(slot.pk),
            "attachments-0-position": "0",
            "attachments-0-pack": "",
        },
    )

    assert response.status_code == 302, response.content.decode()[:2000]
    made = Interstitial.objects.get(name="Outcast archetype")
    assert made.pack == homebrew
    attachment = InterstitialSlot.objects.get(interstitial=made)
    assert attachment.pack == homebrew
    assert attachment.staged is False


def test_a_pack_picked_by_hand_for_an_attachment_is_honoured(
    admin_client, default_pack, homebrew
):
    """Blank means the interstitial's pack; a pack chosen on the row is
    the author's choice, the default pack included, and stands."""
    from n26.library.authoring import (
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
    )
    from n26.library.models import Interstitial, InterstitialSlot

    legacy = create_slot_type("Gang Legacy")
    houses = create_picklist(
        "Houses", legacy, members=[create_pickable("Cawdor", legacy)]
    )
    slot = create_slot("House legacy", legacy, houses)

    response = admin_client.post(
        "/admin/library/interstitial/add/",
        {
            "name": "Outcast archetype",
            "title": "",
            "description": "",
            "position": "0",
            "pack": str(homebrew.pk),
            "attachments-TOTAL_FORMS": "1",
            "attachments-INITIAL_FORMS": "0",
            "attachments-MIN_NUM_FORMS": "0",
            "attachments-MAX_NUM_FORMS": "1000",
            "attachments-0-slot": str(slot.pk),
            "attachments-0-position": "0",
            "attachments-0-pack": str(default_pack.pk),
        },
    )

    assert response.status_code == 302, response.content.decode()[:2000]
    made = Interstitial.objects.get(name="Outcast archetype")
    assert InterstitialSlot.objects.get(interstitial=made).pack == default_pack


def test_clearing_the_pack_on_an_existing_attachment_inherits_it(
    admin_client, default_pack, homebrew
):
    """An existing row cleared to blank on the change page follows the
    same rule as a new one, rather than failing on a missing pack."""
    from n26.library.authoring import (
        attach_interstitial,
        create_interstitial,
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
    )
    from n26.library.models import InterstitialSlot

    legacy = create_slot_type("Gang Legacy")
    houses = create_picklist(
        "Houses", legacy, members=[create_pickable("Cawdor", legacy)]
    )
    slot = create_slot("House legacy", legacy, houses)
    shown = create_interstitial("Outcast archetype", pack=homebrew)
    attachment = attach_interstitial(shown, slot, pack=default_pack)

    response = admin_client.post(
        f"/admin/library/interstitial/{shown.pk}/change/",
        {
            "name": "Outcast archetype",
            "title": "",
            "description": "",
            "position": "0",
            "pack": str(homebrew.pk),
            "attachments-TOTAL_FORMS": "1",
            "attachments-INITIAL_FORMS": "1",
            "attachments-MIN_NUM_FORMS": "0",
            "attachments-MAX_NUM_FORMS": "1000",
            "attachments-0-id": str(attachment.pk),
            "attachments-0-interstitial": str(shown.pk),
            "attachments-0-slot": str(slot.pk),
            "attachments-0-position": "0",
            "attachments-0-pack": "",
            # The pack has a callable default, so the change page carries
            # its initial in a hidden input the browser posts back; a
            # change is read against that, not against the row.
            "initial-attachments-0-pack": str(default_pack.pk),
        },
    )

    assert response.status_code == 302, response.content.decode()[:2000]
    assert InterstitialSlot.objects.get(pk=attachment.pk).pack == homebrew


def test_the_standalone_attachment_page_inherits_the_pack_too(
    admin_client, default_pack, homebrew
):
    from n26.library.authoring import (
        create_interstitial,
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
    )
    from n26.library.models import InterstitialSlot

    legacy = create_slot_type("Gang Legacy")
    houses = create_picklist(
        "Houses", legacy, members=[create_pickable("Cawdor", legacy)]
    )
    slot = create_slot("House legacy", legacy, houses)
    shown = create_interstitial("Outcast archetype", pack=homebrew)

    response = admin_client.post(
        "/admin/library/interstitialslot/add/",
        {
            "interstitial": str(shown.pk),
            "slot": str(slot.pk),
            "position": "0",
            "pack": "",
        },
    )

    assert response.status_code == 302, response.content.decode()[:2000]
    assert InterstitialSlot.objects.get(interstitial=shown).pack == homebrew


def test_an_attachment_can_be_held_back_from_the_admin(
    admin_client, default_pack, homebrew
):
    """The admin is where an attachment is staged, so the inline offers
    the switch, and a row ticked there lands staged — in the parent's
    pack still."""
    from n26.library.authoring import (
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
    )
    from n26.library.models import Interstitial, InterstitialSlot

    legacy = create_slot_type("Gang Legacy")
    houses = create_picklist(
        "Houses", legacy, members=[create_pickable("Cawdor", legacy)]
    )
    slot = create_slot("House legacy", legacy, houses)

    response = admin_client.post(
        "/admin/library/interstitial/add/",
        {
            "name": "Outcast archetype",
            "title": "",
            "description": "",
            "position": "0",
            "pack": str(homebrew.pk),
            "attachments-TOTAL_FORMS": "1",
            "attachments-INITIAL_FORMS": "0",
            "attachments-MIN_NUM_FORMS": "0",
            "attachments-MAX_NUM_FORMS": "1000",
            "attachments-0-slot": str(slot.pk),
            "attachments-0-position": "0",
            "attachments-0-pack": "",
            "attachments-0-staged": "on",
        },
    )

    assert response.status_code == 302, response.content.decode()[:2000]
    attachment = InterstitialSlot.objects.get(
        interstitial=Interstitial.objects.get(name="Outcast archetype")
    )
    assert attachment.staged is True
    assert attachment.pack == homebrew
    assert list(slot.interstitials(include_staged=False)) == []


def test_a_slot_type_of_choice_is_inspectable_by_its_own_name(
    admin_client, default_pack
):
    """The whole graph filters by the slot type it belongs to, so "what is
    in Gang Legacy" is one question of any of the four tables."""
    from n26.library.authoring import (
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
    )

    legacy = create_slot_type("Gang Legacy", plural_name="Gang Legacies")
    houses = create_picklist(
        "House Legacies", legacy, members=[create_pickable("Cawdor", legacy)]
    )
    create_slot("House legacy", legacy, houses)

    for model in ("pickable", "picklist", "slot"):
        response = admin_client.get(
            f"/admin/library/{model}/?slot_type__id__exact={legacy.pk}"
        )
        assert response.status_code == 200, model
        assert "Gang Legacy" in response.content.decode(), model


def test_a_lists_pickables_are_edited_on_the_list(admin_client, default_pack):
    from n26.library.authoring import (
        create_pickable,
        create_picklist,
        create_slot_type,
    )

    legacy = create_slot_type("Gang Legacy")
    houses = create_picklist(
        "House Legacies", legacy, members=[create_pickable("Cawdor", legacy)]
    )

    html = admin_client.get(
        f"/admin/library/picklist/{houses.pk}/change/"
    ).content.decode()

    assert "Cawdor" in html


def test_campaign_type_admin_pages_render(admin_client, default_pack):
    from n26.library.authoring import add_asset_type, create_campaign_type

    campaign_type = create_campaign_type("Dominion")
    add_asset_type(campaign_type, "Territory", "pooled")
    assert admin_client.get("/admin/library/campaigntype/").status_code == 200
    assert admin_client.get("/admin/library/campaigntype/add/").status_code == 200
    assert (
        admin_client.get(
            f"/admin/library/campaigntype/{campaign_type.pk}/change/"
        ).status_code
        == 200
    )


def test_asset_admin_pages_render(admin_client, default_pack):
    from n26.library.authoring import add_asset_type, create_asset, create_campaign_type

    kind = add_asset_type(create_campaign_type("Dominion"), "Territory", "pooled")
    asset = create_asset("Old Ruins", kind, income=10)
    assert admin_client.get("/admin/library/asset/").status_code == 200
    assert admin_client.get("/admin/library/asset/add/").status_code == 200
    assert (
        admin_client.get(f"/admin/library/asset/{asset.pk}/change/").status_code == 200
    )
