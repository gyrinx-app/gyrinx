"""What the authoring pages offer as a way out of themselves.

Three switchers, all built here rather than added to nine view contexts:
every authoring page draws the same bar and none of them differ in what it
should hold. Tags rather than a context processor for the reason the
drawer's gang list is one — the query, where there is one, runs only on the
pages that draw the control.
"""

from django import template

register = template.Library()


@register.simple_tag
def kinds_switcher(here="", menu_label="Switch kind", named=False):
    """Every kind of content, as somewhere to go.

    Costs no query: the kinds are a dict and their names come off the
    model classes, so there is nothing to save by leaving this off the
    pages that are not one kind.

    ``here`` is the kind slug the page is showing. A page showing none
    passes nothing and the list opens with no row marked.

    ``named`` draws the leading link: the kind's own listing when the
    page is showing one, the library index when it is not — so from a
    row's page the name is the way up to its listing, and the chevron
    the way across to another kind. The bar wants that; beside a heading
    that already names the kind, the default chevron alone is right.

    ``menu_label`` is the chevron's accessible name. A page drawing this
    twice — once in the bar, once beside its heading — must name the
    second one itself: two controls announced identically tell a reader
    who cannot see where they sit nothing about either.

    Sorted by name rather than left in ``LEAF_KINDS`` order, which is
    menu order within a family and reads as no order at all once the
    families are flattened into one list.
    """
    from django.urls import reverse

    from n26.core.navigation import Switcher, SwitcherItem
    from n26.library.specs import specs
    from n26.library.views import (
        LEAF_KINDS,
        NESTED_KINDS,
        RETIRED_KINDS,
        _model_for,
    )

    # A kind listed only on its parent's page has no listing to go to,
    # so the switcher never offers it — from one of its rows the leading
    # link is the library index, and the breadcrumb is the way up.
    items = sorted(
        (
            SwitcherItem(
                label=str(
                    _model_for(specs()[verb])._meta.verbose_name_plural
                ).capitalize(),
                href=reverse("authoring-leaf", args=[kind]),
                current=kind == here,
            )
            for kind, verb in LEAF_KINDS.items()
            if kind not in NESTED_KINDS and (kind not in RETIRED_KINDS or kind == here)
        ),
        key=lambda item: item.label,
    )
    label = ""
    href = ""
    if named:
        marked = next((item for item in items if item.current), None)
        if marked is not None:
            label, href = marked.label, marked.href
        else:
            label, href = "Content library", reverse("authoring-index")
    return Switcher(
        label=label,
        href=href,
        heading="Kinds of content",
        menu_label=menu_label,
        placeholder="Search kinds",
        empty="No kinds match",
        items=items,
    )


def _in_stable_order(rows):
    """``rows`` with the primary key as the last tie-breaker.

    A switcher reads its list a page at a time by offset, so two rows the
    listing order cannot tell apart must still come back in one order.
    """
    order = list(rows.query.order_by) or list(rows.model._meta.ordering)
    return rows.order_by(*order, "pk")


def _sibling_rows(kind):
    from n26.library.views import _model_for, _rows, _spec_for

    model = _model_for(_spec_for(kind))
    return model, _in_stable_order(_rows(model, kind))


def _sibling_item(kind, current=None):
    from django.urls import reverse

    from n26.core.navigation import SwitcherItem
    from n26.library.views import _label_for

    def item(row):
        return SwitcherItem(
            label=_label_for(row),
            href=reverse("authoring-detail", args=[kind, row.pk]),
            current=current is not None and row.pk == current.pk,
        )

    return item


def _staff_or_404(request):
    from django.http import Http404

    if not request.user.is_staff:
        raise Http404("No such list")


def _label_search(model):
    """How a kind's rows are searched on the server: the stored words its
    label is made of, where it has them.

    None for a kind with no name, whose label is matched row by row.
    """
    from django.db.models import Q

    fields = {field.name for field in model._meta.get_fields()}
    words = [name for name in ("name", "qualifier", "annotation") if name in fields]
    if "name" not in words:
        return None

    def search(rows, query):
        match = Q()
        for name in words:
            match |= Q((f"{name}__icontains", query))
        return rows.filter(match)

    return search


def sibling_source(request, params):
    """The rows of one kind, for the siblings switcher's further pages."""
    _staff_or_404(request)
    kind = params.get("kind", "")
    model, rows = _sibling_rows(kind)
    return rows, _sibling_item(kind), _label_search(model)


@register.simple_tag
def siblings_switcher(kind, thing):
    """The other rows of one kind, from the page of one of them.

    The first page arrives with the page and the rest as the list
    scrolls, so a kind with three hundred rows costs this page what a
    kind with thirty does. The row being looked at is always in the
    first page — a switcher that does not list the page it is sitting on
    says the reader is nowhere.
    """
    from n26.core.navigation import Switcher, first_page, source_url, with_current

    model, rows = _sibling_rows(kind)
    plural = str(model._meta.verbose_name_plural)
    item = _sibling_item(kind, thing)
    found, more = first_page(rows)
    return Switcher(
        heading=plural.capitalize(),
        menu_label=f"Switch to another {model._meta.verbose_name}",
        placeholder=f"Search {plural}",
        empty=f"No {plural} match",
        items=with_current([item(row) for row in found], item(thing)),
        source=source_url("siblings", kind=kind),
        more=more,
    )


def _weapon_profile_item(current=None):
    from django.urls import reverse

    from n26.core.navigation import SwitcherItem
    from n26.library.views import _label_for

    def item(line):
        return SwitcherItem(
            label=_label_for(line),
            href=reverse("authoring-weapon-profile", args=[line.pk]),
            current=current is not None and line.pk == current.pk,
        )

    return item


def _weapon_profile_rows(weapon_pk):
    from n26.library.models import WeaponProfile

    return WeaponProfile.objects.filter(weapon_id=weapon_pk).order_by("position", "pk")


def weapon_profile_source(request, params):
    """One weapon's profiles, for the profile switcher's further pages."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.library.models import Weapon, WeaponProfile

    _staff_or_404(request)
    try:
        weapon = Weapon.objects.filter(pk=params.get("weapon", "")).first()
    except ValidationError:
        weapon = None
    if weapon is None:
        raise Http404("No such weapon")
    return (
        _weapon_profile_rows(weapon.pk),
        _weapon_profile_item(),
        _label_search(WeaponProfile),
    )


@register.simple_tag
def weapon_profiles_switcher(profile):
    """The other profiles of one weapon, from the page of one of them.

    The set that means something here: a gun's lines are read against
    each other — the standard shot, then what each ammo type changes.
    Ordered by position, which is the order the book's table prints.
    """
    from n26.core.navigation import Switcher, first_page, source_url, with_current
    from n26.library.models import WeaponProfile

    plural = str(WeaponProfile._meta.verbose_name_plural)
    item = _weapon_profile_item(profile)
    found, more = first_page(_weapon_profile_rows(profile.weapon_id))
    return Switcher(
        heading=plural.capitalize(),
        menu_label=f"Switch to another {WeaponProfile._meta.verbose_name}",
        placeholder=f"Search {plural}",
        empty=f"No {plural} match",
        items=with_current([item(line) for line in found], item(profile)),
        source=source_url("weapon-profiles", weapon=profile.weapon_id),
        more=more,
    )
