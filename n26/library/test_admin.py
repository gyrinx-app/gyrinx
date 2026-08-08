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
