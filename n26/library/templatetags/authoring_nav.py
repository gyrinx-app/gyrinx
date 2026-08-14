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
    from n26.library.views import LEAF_KINDS, _model_for

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


@register.simple_tag
def siblings_switcher(kind, thing):
    """The other rows of one kind, from the page of one of them.

    Capped, and the cap is on the query: a kind with three hundred rows
    costs this page what a kind with three does. The row being looked at
    is put back if the cap dropped it — a switcher that does not list the
    page it is sitting on says the reader is nowhere.

    The listing is the whole set and is a press away, which is what makes
    a cap honest here rather than a hidden limit.
    """
    from django.urls import reverse

    from n26.core.navigation import (
        NAV_SIBLINGS,
        Switcher,
        SwitcherItem,
        with_current,
    )
    from n26.library.views import _label_for, _model_for, _rows, _spec_for

    model = _model_for(_spec_for(kind))
    plural = str(model._meta.verbose_name_plural)

    def item(row):
        return SwitcherItem(
            label=_label_for(row),
            href=reverse("authoring-detail", args=[kind, row.pk]),
            current=row.pk == thing.pk,
        )

    return Switcher(
        heading=plural.capitalize(),
        menu_label=f"Switch to another {model._meta.verbose_name}",
        placeholder=f"Search {plural}",
        empty=f"No {plural} match",
        items=with_current(
            [item(row) for row in _rows(model, kind)[:NAV_SIBLINGS]], item(thing)
        ),
    )


@register.simple_tag
def weapon_profiles_switcher(profile):
    """The other firing lines of one weapon, from the page of one of them.

    The same shortcut the kind pages offer over their rows, over the set
    that means something here: a gun's lines are read against each other
    — the standard shot, then what each ammo type changes — and the
    weapon's own page is the way back to all of them.

    Ordered by position, which is the order the book's table prints, and
    capped like every other switcher; the weapon's page lists them all.
    """
    from django.urls import reverse

    from n26.core.navigation import (
        NAV_SIBLINGS,
        Switcher,
        SwitcherItem,
        with_current,
    )
    from n26.library.models import WeaponProfile
    from n26.library.views import _label_for

    plural = str(WeaponProfile._meta.verbose_name_plural)

    def item(line):
        return SwitcherItem(
            label=_label_for(line),
            href=reverse("authoring-weapon-profile", args=[line.pk]),
            current=line.pk == profile.pk,
        )

    lines = profile.weapon.profiles.order_by("position")[:NAV_SIBLINGS]
    return Switcher(
        heading=plural.capitalize(),
        menu_label=f"Switch to another {WeaponProfile._meta.verbose_name}",
        placeholder=f"Search {plural}",
        empty=f"No {plural} match",
        items=with_current([item(line) for line in lines], item(profile)),
    )
