"""
The abstract ``Content`` base class.

Default-open pack scoping
-------------------------

The manager here does **no** implicit filtering. ``Profile.objects.all()``
returns every profile in every pack, archived or not, and following a FK from
user data always resolves. Narrowing is opt-in, and belongs only at the
handful of *discovery and authoring* surfaces that ask "what may this user
pick from?" — search, pickers, pack galleries, admin.

This is deliberately the inverse of the earlier gyrinx design, where the
default manager excluded pack content and every read path had to opt back in.
That cost 260+ ``with_packs()`` / ``all_content()`` call sites, a bespoke
prefetch-marker system layered on the ORM, through-table workarounds to dodge
the excluding manager, a standing domain rule in CLAUDE.md, and a recurring
bug class where a forgotten call site silently dropped a subscriber's content
(gyrinx#1742). An anti-join rode along on 50 of 82 queries in the performance
snapshot.

Inverting it means:

- The "forgot pack context" bug class cannot occur — the failure mode of
  forgetting to filter is *showing too much on a discovery page*, which is
  visible and cheap, rather than *silently dropping content a user owns*.
- Eligibility ("may this user add that pack's content?") is enforced once, at
  assignment time in forms and handlers, not re-derived on every read.
- Pack scoping is an ordinary indexed ``WHERE pack_id IN (...)`` on the content
  table, not an ``EXISTS`` anti-join against a generic-FK side table.

Archived content behaves the same way, for the same reason: archiving a pack
or an item is a soft delete by its owner and must not retract content from
lists that already reference it.
"""

from django.conf import settings
from django.db import models

from n26.library.models.pack import ContentPack, default_pack_id
from n26.core.models import Archived, Base


class ContentQuerySet(models.QuerySet):
    """Explicit, opt-in narrowing helpers.

    None of these are applied by default. Reach for them at discovery and
    authoring surfaces only.
    """

    def in_packs(self, packs):
        """Narrow to content whose primary pack is one of ``packs``.

        ``packs`` may be pack instances, pks, or a queryset.
        """
        return self.filter(pack__in=packs)

    def in_default_pack(self):
        """Narrow to the N26 pack."""
        return self.filter(pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG)

    def unarchived(self):
        """Drop archived content, and content in archived packs."""
        return self.filter(archived=False, pack__archived=False)

    def selectable(self, packs=()):
        """Content a user may choose from: the default pack, plus ``packs``.

        This is the discovery-surface query — a picker, a search, a gallery.
        Archived content is excluded here because you should not be able to
        *newly* select it, which is a separate question from whether existing
        references to it still resolve (they do).
        """
        return self.filter(
            models.Q(pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG)
            | models.Q(pack__in=packs)
        ).unarchived()

    def with_pack(self):
        """``select_related`` the pack. Cheap, and avoids N+1 on ``__str__``."""
        return self.select_related("pack")


#: Plain manager — no implicit filtering, by design. See the module docstring.
ContentManager = models.Manager.from_queryset(ContentQuerySet)


class Content(Base, Archived):
    """Abstract base for every content model.

    Gives you a ULID pk, created/modified timestamps, archive flags, and a
    required primary pack defaulting to N26.
    """

    pack = models.ForeignKey(
        ContentPack,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
        default=default_pack_id,
        db_index=True,
        help_text="The pack this content belongs to. Defaults to N26.",
    )

    objects = ContentManager()

    class Meta:
        abstract = True
