import pytest
from django.test import Client
from django.urls import reverse

from gyrinx.core.models.pack import CustomContentPack


@pytest.mark.django_db
def test_homepage_shows_featured_packs_for_anonymous(make_user):
    """Featured + listed packs appear on the front page for anonymous users."""
    owner = make_user("packowner", "password")
    CustomContentPack.objects.create(
        name="Prototype Weapons",
        summary="A pack of experimental weapon traits.",
        listed=True,
        featured=True,
        owner=owner,
    )

    client = Client()
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert b"Featured Content Packs" in response.content
    assert b"Prototype Weapons" in response.content


@pytest.mark.django_db
def test_homepage_shows_featured_packs_for_authenticated(client, user, make_user):
    """Featured + listed packs appear on the front page for authenticated users."""
    owner = make_user("packowner", "password")
    CustomContentPack.objects.create(
        name="Nasherhound Rules",
        summary="Custom rules for Nasherhounds.",
        listed=True,
        featured=True,
        owner=owner,
    )

    client.force_login(user)
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert b"Featured Content Packs" in response.content
    assert b"Nasherhound Rules" in response.content


@pytest.mark.django_db
def test_homepage_hides_featured_section_when_none(client, user):
    """The featured section is not rendered when there are no featured packs."""
    client.force_login(user)
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert b"Featured Content Packs" not in response.content


@pytest.mark.django_db
def test_homepage_excludes_unlisted_packs(make_user):
    """Featured but unlisted packs are not shown on the front page."""
    owner = make_user("packowner", "password")
    CustomContentPack.objects.create(
        name="Secret Sauce",
        summary="A private pack.",
        listed=False,
        featured=True,
        owner=owner,
    )

    client = Client()
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert b"Secret Sauce" not in response.content
    assert b"Featured Content Packs" not in response.content


@pytest.mark.django_db
def test_homepage_excludes_archived_packs(make_user):
    """Archived featured packs are not shown on the front page (discovery surface)."""
    owner = make_user("packowner", "password")
    CustomContentPack.objects.create(
        name="Old Pack",
        summary="An archived pack.",
        listed=True,
        featured=True,
        archived=True,
        owner=owner,
    )

    client = Client()
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert b"Old Pack" not in response.content
    assert b"Featured Content Packs" not in response.content


@pytest.mark.django_db
def test_homepage_caps_featured_packs_at_three(make_user):
    """Only up to 3 featured packs are shown on the front page."""
    owner = make_user("packowner", "password")
    for i in range(5):
        CustomContentPack.objects.create(
            name=f"Featured Pack {i}",
            summary=f"Pack number {i}.",
            listed=True,
            featured=True,
            owner=owner,
        )

    client = Client()
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    featured_packs = response.context["featured_packs"]
    assert len(list(featured_packs)) == 3


@pytest.mark.django_db
def test_homepage_featured_description_falls_back_to_summary(make_user):
    """When featured_description is blank, the card falls back to summary text."""
    owner = make_user("packowner", "password")
    CustomContentPack.objects.create(
        name="Fallback Pack",
        summary="Summary used as fallback.",
        featured_description="",
        listed=True,
        featured=True,
        owner=owner,
    )

    client = Client()
    response = client.get(reverse("core:index"))

    assert response.status_code == 200
    assert b"Summary used as fallback." in response.content
