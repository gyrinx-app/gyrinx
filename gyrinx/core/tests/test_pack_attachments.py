"""Tests for content-pack file attachments (issue #1811)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from gyrinx.core.models.pack import (
    PACK_ATTACHMENT_DAILY_QUOTA,
    PACK_ATTACHMENT_MAX_PER_PACK,
    CustomContentPack,
    CustomContentPackAttachment,
    CustomContentPackPermission,
)


@pytest.fixture
def pack(user) -> CustomContentPack:
    return CustomContentPack.objects.create(name="Scenario Pack", owner=user)


def _pdf(name="scenario.pdf", content=b"%PDF-1.4 fake"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _make_attachment(pack, owner, **kwargs):
    defaults = dict(
        file=SimpleUploadedFile("f.pdf", b"%PDF-1.4", content_type="application/pdf"),
        original_filename="f.pdf",
        file_size=10,
        content_type="application/pdf",
    )
    defaults.update(kwargs)
    return CustomContentPackAttachment.objects.create(
        pack=pack, owner=owner, **defaults
    )


# --- Model-layer validation ---------------------------------------------------


@pytest.mark.django_db
def test_clean_rejects_disallowed_content_type(pack, user):
    attachment = CustomContentPackAttachment(
        pack=pack,
        owner=user,
        file=SimpleUploadedFile("a.txt", b"hi"),
        original_filename="a.txt",
        file_size=2,
        content_type="text/plain",
    )
    with pytest.raises(ValidationError):
        attachment.full_clean()


@pytest.mark.django_db
def test_clean_rejects_oversize_file(pack, user):
    attachment = CustomContentPackAttachment(
        pack=pack,
        owner=user,
        file=_pdf(),
        original_filename="big.pdf",
        file_size=21 * 1024 * 1024,
        content_type="application/pdf",
    )
    with pytest.raises(ValidationError):
        attachment.full_clean()


@pytest.mark.django_db
def test_clean_rejects_svg_content_type(pack, user):
    attachment = CustomContentPackAttachment(
        pack=pack,
        owner=user,
        file=SimpleUploadedFile("x.svg", b"<svg></svg>"),
        original_filename="x.svg",
        file_size=11,
        content_type="image/svg+xml",
    )
    with pytest.raises(ValidationError):
        attachment.full_clean()


@pytest.mark.django_db
def test_clean_rejects_svg_extension_with_spoofed_content_type(pack, user):
    # Even with a benign-looking content type, a .svg file must be rejected
    # because the CDN serves it as image/svg+xml (stored XSS vector).
    attachment = CustomContentPackAttachment(
        pack=pack,
        owner=user,
        file=SimpleUploadedFile(
            "evil.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
            content_type="image/png",
        ),
        original_filename="evil.svg",
        file_size=70,
        content_type="image/png",
    )
    with pytest.raises(ValidationError):
        attachment.full_clean()


@pytest.mark.django_db
def test_clean_accepts_pdf_and_images(pack, user):
    cases = [
        ("doc.pdf", "application/pdf"),
        ("pic.png", "image/png"),
        ("pic.jpeg", "image/jpeg"),
        ("pic.webp", "image/webp"),
    ]
    for name, ct in cases:
        attachment = CustomContentPackAttachment(
            pack=pack,
            owner=user,
            file=SimpleUploadedFile(name, b"data", content_type=ct),
            original_filename=name,
            file_size=100,
            content_type=ct,
        )
        attachment.full_clean()  # should not raise


@pytest.mark.django_db
def test_display_name_prefers_title(pack, user):
    a = _make_attachment(pack, user, title="My Scenario", original_filename="x.pdf")
    assert a.display_name == "My Scenario"
    b = _make_attachment(pack, user, title="", original_filename="x.pdf")
    assert b.display_name == "x.pdf"


# --- Upload view --------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_upload(client, pack, user):
    client.force_login(user)
    url = reverse("core:pack-attachment-add", args=[pack.id])
    resp = client.post(
        url, {"file": _pdf(), "title": "Weekend Scenario", "description": "Zombies"}
    )
    assert resp.status_code == 302
    attachment = pack.attachments.get()
    assert attachment.title == "Weekend Scenario"
    assert attachment.original_filename == "scenario.pdf"
    assert attachment.content_type == "application/pdf"
    assert attachment.owner == user

    # It appears on the pack detail page as a download link.
    detail = client.get(reverse("core:pack", args=[pack.id]))
    assert b"Weekend Scenario" in detail.content


@pytest.mark.django_db
def test_editor_can_upload(client, pack, user, make_user):
    editor = make_user("editor", "password")
    CustomContentPackPermission.objects.create(
        pack=pack, user=editor, role="editor", owner=user
    )
    client.force_login(editor)
    url = reverse("core:pack-attachment-add", args=[pack.id])
    resp = client.post(url, {"file": _pdf(), "title": "From editor"})
    assert resp.status_code == 302
    assert pack.attachments.filter(title="From editor").exists()


@pytest.mark.django_db
def test_non_editor_cannot_upload(client, pack, user, make_user):
    other = make_user("other", "password")
    client.force_login(other)
    url = reverse("core:pack-attachment-add", args=[pack.id])
    resp = client.post(url, {"file": _pdf(), "title": "Sneaky"})
    assert resp.status_code == 404
    assert not pack.attachments.exists()


@pytest.mark.django_db
def test_upload_order_does_not_collide_after_archive(client, pack, user):
    # Upload two, archive the first, upload a third: orders must stay distinct
    # (regression for count()-based ordering colliding across gaps).
    client.force_login(user)
    url = reverse("core:pack-attachment-add", args=[pack.id])
    client.post(url, {"file": _pdf(), "title": "first"})
    client.post(url, {"file": _pdf(), "title": "second"})
    pack.attachments.get(title="first").archive()
    client.post(url, {"file": _pdf(), "title": "third"})

    active = pack.attachments.filter(archived=False)
    orders = list(active.values_list("order", flat=True))
    assert len(orders) == len(set(orders)), f"orders collided: {orders}"


@pytest.mark.django_db
def test_upload_rejects_disallowed_type(client, pack, user):
    client.force_login(user)
    url = reverse("core:pack-attachment-add", args=[pack.id])
    bad = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
    resp = client.post(url, {"file": bad, "title": "Notes"})
    assert resp.status_code == 200  # re-rendered with errors
    assert not pack.attachments.exists()


@pytest.mark.django_db
def test_upload_rejects_svg_extension_spoof(client, pack, user):
    client.force_login(user)
    url = reverse("core:pack-attachment-add", args=[pack.id])
    svg = SimpleUploadedFile(
        "evil.svg",
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        content_type="image/png",  # spoofed to look benign
    )
    resp = client.post(url, {"file": svg, "title": "Sneaky SVG"})
    assert resp.status_code == 200  # re-rendered with errors
    assert not pack.attachments.exists()


@pytest.mark.django_db
def test_upload_blocked_when_pack_full(client, pack, user):
    for i in range(PACK_ATTACHMENT_MAX_PER_PACK):
        _make_attachment(pack, user, original_filename=f"f{i}.pdf")
    client.force_login(user)
    url = reverse("core:pack-attachment-add", args=[pack.id])
    resp = client.post(url, {"file": _pdf(), "title": "One too many"})
    assert resp.status_code == 302
    assert pack.attachments.filter(archived=False).count() == (
        PACK_ATTACHMENT_MAX_PER_PACK
    )
    assert not pack.attachments.filter(title="One too many").exists()


@pytest.mark.django_db
def test_upload_blocked_over_daily_quota(client, pack, user):
    # Seed today's usage right up to the quota.
    _make_attachment(pack, user, file_size=PACK_ATTACHMENT_DAILY_QUOTA)
    client.force_login(user)
    url = reverse("core:pack-attachment-add", args=[pack.id])
    resp = client.post(url, {"file": _pdf(), "title": "Over quota"})
    assert resp.status_code == 200
    assert not pack.attachments.filter(title="Over quota").exists()


# --- Delete view --------------------------------------------------------------


@pytest.mark.django_db
def test_owner_can_remove_attachment(client, pack, user):
    attachment = _make_attachment(pack, user, title="Remove me")
    client.force_login(user)
    url = reverse("core:pack-attachment-delete", args=[pack.id, attachment.id])
    resp = client.post(url)
    assert resp.status_code == 302
    attachment.refresh_from_db()
    assert attachment.archived is True
    assert not pack.attachments.filter(archived=False).exists()


@pytest.mark.django_db
def test_non_editor_cannot_remove(client, pack, user, make_user):
    attachment = _make_attachment(pack, user)
    other = make_user("other", "password")
    client.force_login(other)
    url = reverse("core:pack-attachment-delete", args=[pack.id, attachment.id])
    resp = client.post(url)
    assert resp.status_code == 404
    attachment.refresh_from_db()
    assert attachment.archived is False


# --- Visibility ---------------------------------------------------------------


@pytest.mark.django_db
def test_viewer_of_listed_pack_sees_download(client, user, make_user):
    listed_pack = CustomContentPack.objects.create(
        name="Public Pack", owner=user, listed=True
    )
    _make_attachment(listed_pack, user, title="Public Scenario")
    viewer = make_user("viewer", "password")
    client.force_login(viewer)
    detail = client.get(reverse("core:pack", args=[listed_pack.id]))
    assert detail.status_code == 200
    assert b"Public Scenario" in detail.content
    # A non-editor viewer must not see the add/remove controls. Assert against
    # the rendered URL paths (templates emit the reversed URL, not its name).
    add_url = reverse("core:pack-attachment-add", args=[listed_pack.id])
    assert add_url.encode() not in detail.content
