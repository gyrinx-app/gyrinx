"""
Content packs.

A pack is a named body of content. Every content object belongs to exactly
one pack — its *primary* pack — via a required FK on the content row itself.

The N26 pack is the default: content created without an explicit pack (most
notably anything ingested through the Django admin) lands there. It is
identified by slug, configured as ``settings.DEFAULT_CONTENT_PACK_SLUG``, so
that a different pack can be made the default per-environment without a
schema change.

Later we expect content to gain *secondary* pack memberships through a
join model. That is purely additive: the primary pack FK stays where it is,
and pack scoping stays an ordinary indexed filter on the content table.
"""

from django.conf import settings
from django.db import models

from n26.core.models import Archived, Base, Owned


class ContentPack(Base, Owned, Archived):
    """A named body of content.

    A pack with no ``owner`` is a system pack — N26 itself is one. Archiving a
    pack is a soft delete by its owner and deliberately does *not* retract its
    content from anything already referencing it.
    """

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "content pack"
        verbose_name_plural = "content packs"

    def __str__(self):
        return self.name

    @property
    def is_default(self):
        return self.slug == settings.DEFAULT_CONTENT_PACK_SLUG


def get_default_pack():
    """Return the default (N26) pack, creating it if it doesn't exist yet.

    Creating on demand keeps fresh databases and test databases working
    without a data migration or fixture. There is one query per call; if that
    ever shows up in a profile, cache it per-request rather than making the
    field nullable.
    """
    pack, _ = ContentPack.objects.get_or_create(
        slug=settings.DEFAULT_CONTENT_PACK_SLUG,
        defaults={"name": settings.DEFAULT_CONTENT_PACK_NAME},
    )
    return pack


def default_pack_id():
    """``default=`` callable for :attr:`Content.pack`.

    Referenced by name in migrations, so it must stay importable from here.
    """
    return get_default_pack().pk
