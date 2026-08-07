"""The authoring views — the admin surface, starting at the leaves.

The admin forms come before the preview pane, so the things can be
created — beginning with the most fundamental assignables. Each page
here is one leaf kind: the recent
rows of that kind, and the spec-generated form that creates one more.
The form *is* the verb (``form.compile()`` performs the ``create_*``
call), so nothing an author can build here is outside the API, and the
help they read is the model's own words.

Nothing fancy on purpose: two views, one template each, staff-only.
The composer and the preview pane hang off this same skeleton later
(design/authoring.md, design/preview-contexts.md).
"""

import inspect
import re

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape
from django.utils.safestring import mark_safe

from n26.library.forms import generate_form, statline_form_for, suggestion_form_for
from n26.library.models.assignable import Family
from n26.library.specs import specs

#: The leaf kinds the authoring surface offers, in menu order:
#: url slug → (create verb, the model the page lists). The guard test
#: keeps every entry backed by a spec.
LEAF_KINDS = {
    "subtype": "create_subtype",
    "rule": "create_rule",
    "trait": "create_trait",
    "skill": "create_skill",
    "power": "create_power",
    "lasting-effect": "create_lasting_effect",
    "specialisation": "create_specialisation",
    "counter": "create_counter",
    "hidden": "create_hidden",
    "wargear": "create_wargear",
    "weapon": "create_weapon",
    "weapon-accessory": "create_weapon_accessory",
    "stat": "create_stat",
    "statline-type": "create_statline_type",
    "section": "create_section",
    "category": "create_category",
    "archetype": "create_archetype",
    "affiliation": "create_affiliation",
    "skill-tree": "create_skill_tree",
    "gang-type": "create_gang_type",
    "profile": "create_profile",
    "collection": "create_collection",
}


#: Kinds whose page is a place you come back to: the thing, and the
#: parts you add to it over time. ``kind -> the verb that adds a part``.
def _describe_weapon_profile(profile):
    """A firing line, as the author needs to check it: what it is
    called, the stats they typed, its traits, and what it costs.

    An unnamed line is the weapon's own, so it is labelled with the
    weapon and says so — a blank cell would read as a missing name
    rather than a deliberate one.
    """
    label = profile.name or profile.weapon.name
    notes = []
    if not profile.name:
        notes.append("the weapon's own line")
    notes.append(_statline_summary(profile))
    notes.append(", ".join(profile.trait_names))
    notes.append("free" if profile.is_free else f"+{profile.price}cr")
    return label, [note for note in notes if note]


def _statline_summary(owner):
    """A statline as one short string — 'SR 8"  LR 24"' — so a page can
    show what was typed without rebuilding the card machinery."""
    statline = getattr(owner, "statline", None)
    if statline is None:
        return ""
    return "  ".join(
        f"{stat.short_name} {stat.formatted_value}"
        for stat in statline.stats.select_related("statline_type_stat__stat").order_by(
            "statline_type_stat__position"
        )
    )


def _describe_statline_stat(type_stat):
    """One column of a shape. Not prefixed with the shape's name — the
    page is already that shape — and showing the two display flags,
    which are the only things about the row a reader cannot infer."""
    notes = []
    if type_stat.is_first_of_group:
        notes.append("starts a group")
    if type_stat.is_highlighted:
        notes.append("highlighted")
    return str(type_stat.stat), notes


def _describe_built_in(member):
    """One row of what a profile comes with. A collection member is
    access rather than kit — the list this entry may use — and the
    page says so; everything else reads as its kind."""
    from n26.library.models import Collection

    thing = member.assignable
    if isinstance(thing, Collection):
        notes = ["collection — a list it may use"]
    else:
        notes = [str(thing._meta.verbose_name)]
    if member.amount:
        notes.append(f"opening value {member.amount}")
    return _label_for(thing), notes


DETAIL_KINDS = {
    "weapon": {
        "verb": "add_weapon_profile",
        "parts": "profiles",
        "statline": True,
        "describe": _describe_weapon_profile,
    },
    "statline-type": {
        "verb": "add_stat_to_statline_type",
        "parts": "stats",
        "statline": False,
        "describe": _describe_statline_stat,
    },
    # The words are overridden because the part model is a
    # DefaultAssignment — accurate, and nothing an author says.
    "profile": {
        "verb": "add_built_in",
        "parts": "built_in_members",
        "statline": False,
        "describe": _describe_built_in,
        "parts_label": "comes with",
        "part_name": "built-in",
    },
}


def _has_detail(kind):
    """Whether this kind's listing rows link to a page of their own —
    a parts-and-add-form page (DETAIL_KINDS) or a kind's own view
    (DETAIL_VIEWS, defined below the views themselves)."""
    return kind in DETAIL_KINDS or kind in DETAIL_VIEWS


def _label_for(row):
    """How an author reads one row.

    Assignables carry a label that adds the qualifier telling two
    same-named things apart. The foundation kinds — a category, a stat,
    a statline shape — are not assignables and simply read as
    themselves.
    """
    return getattr(row, "authoring_label", None) or str(row)


def _describe_row(row):
    """What a listing says about one row beyond its name.

    Generic on purpose: whatever a kind actually carries — where it
    sorts, what it costs — rather than a column per kind. Kinds with
    something particular to say override below.
    """
    notes = []
    category = getattr(row, "category", None)
    if category is not None:
        notes.append(category.name)
    price = getattr(row, "price", 0)
    if price:
        notes.append(f"{price}cr")
    trade_points = getattr(row, "trade_point_price", None)
    if getattr(row, "is_exclusive", False):
        notes.append("TP E")
    elif trade_points is not None:
        notes.append(f"TP {trade_points}")
    return notes


def _describe_skill(skill):
    """A skill's set, and the number it is rolled on within it."""
    notes = _describe_row(skill)
    if skill.position:
        notes.append(f"rolled on a {skill.position}")
    return notes


def _describe_skill_tree(tree):
    """A tree is only a handle on a set, so say which."""
    if tree.category is None:
        return ["stands for nothing yet"]
    return [f"stands for {tree.category.name}"]


#: Kinds whose listing says something a generic reading would miss.
def _describe_profile(profile):
    """Whose list it hires from, its Type, and what a hire pays."""
    from n26.library.models import Collection

    notes = [profile.gang_type.name, profile.profile_type.name]
    if profile.price:
        notes.append(f"{profile.price}cr")
    accessible = [
        member.assignable.name
        for member in profile.built_in_members
        if isinstance(member.assignable, Collection)
    ]
    if accessible:
        notes.append(f"uses {', '.join(accessible)}")
    return notes


def _describe_gang_type(gang_type):
    if gang_type.starting_credits is None:
        return []
    return [f"founds with {gang_type.starting_credits}cr"]


LEAF_DESCRIBE = {
    "skill": _describe_skill,
    "skill-tree": _describe_skill_tree,
    "profile": _describe_profile,
    "gang-type": _describe_gang_type,
}


def _spec_for(kind):
    verb_name = LEAF_KINDS.get(kind)
    if verb_name is None:
        raise Http404(f"No authoring page for {kind!r}")
    return specs()[verb_name]


#: ``literal`` in a docstring, as the page should draw it.
_LITERAL = re.compile(r"``([^`]+)``")


def kind_summary(model):
    """The one-line definition — a docstring's first paragraph, which
    is where every model says plainly what it is."""
    paragraphs = kind_help(model)
    return paragraphs[0] if paragraphs else ""


def kind_help(model):
    """What this kind *is*, in the model's own words.

    Sourced, never written — the same rule the field help follows, one
    level up: a kind is explained once, in its docstring, and authors
    and developers read the same paragraphs. Returned as a list so the
    page can lead with the definition and follow with the detail.
    """
    text = inspect.getdoc(model) or ""
    return [
        # Escape first, mark up second: a docstring is ours, but the
        # page must never depend on that to stay well-formed.
        mark_safe(  # nosec B703 B308 - escape() runs first; only our ``code`` markup is added
            _LITERAL.sub(r"<code>\1</code>", escape(" ".join(paragraph.split())))
        )
        for paragraph in text.split("\n\n")
        if paragraph.strip()
    ]


def _model_for(spec):
    """The model this verb makes — the page needs its queryset."""
    return spec.creates


@staff_member_required
def index(request):
    """The menu, grouped by family — the plumbing, the model's own
    qualities, the kit, the gang-scale picks."""
    grouped = {family: [] for family in Family}
    for kind, verb_name in LEAF_KINDS.items():
        model = _model_for(specs()[verb_name])
        grouped[model.family].append(
            {
                "kind": kind,
                "verbose_name": model._meta.verbose_name,
                "summary": kind_summary(model),
                "count": model.objects.count(),
            }
        )
    families = [
        {"label": family.label, "kinds": sorted(kinds, key=lambda k: k["verbose_name"])}
        for family, kinds in grouped.items()
        if kinds
    ]
    return render(request, "authoring/index.html", {"families": families})


@staff_member_required
def leaf(request, kind):
    """One leaf kind: its recent rows, and the form that makes one more."""
    spec = _spec_for(kind)
    model = _model_for(spec)
    form_class = generate_form(spec)
    suggestion_class = suggestion_form_for(model)

    describe = LEAF_DESCRIBE.get(kind, _describe_row)

    if request.method == "POST":
        form = form_class(request.POST)
        suggestions = (
            suggestion_class(request.POST, prefix="suggested")
            if suggestion_class
            else None
        )
        if form.is_valid() and (suggestions is None or suggestions.is_valid()):
            try:
                with transaction.atomic():
                    created = form.compile()
                    if suggestions is not None:
                        suggestions.apply(created)
            except IntegrityError:
                form.add_error(
                    "name",
                    f"A {model._meta.verbose_name} named "
                    f"“{form.cleaned_data['name']}” already exists in this pack.",
                )
            else:
                messages.success(request, f"Created {created}.")
                if _has_detail(kind):
                    return redirect("authoring-detail", kind=kind, pk=created.pk)
                return redirect("authoring-leaf", kind=kind)
    else:
        form = form_class()
        suggestions = suggestion_class(prefix="suggested") if suggestion_class else None

    return render(
        request,
        "authoring/leaf.html",
        {
            "kind": kind,
            "verbose_name": model._meta.verbose_name,
            "verbose_name_plural": model._meta.verbose_name_plural,
            "kind_help": kind_help(model),
            "form": form,
            "suggestion_form": suggestions,
            "rows": [
                {
                    "pk": row.pk,
                    "label": _label_for(row),
                    "notes": describe(row),
                }
                for row in _rows(model)
            ],
            "has_detail": _has_detail(kind),
            "count": model.objects.count(),
        },
    )


@staff_member_required
def detail(request, kind, pk):
    """One thing, and the parts added to it over time.

    The shape everything above the leaves needs: a weapon and its
    profiles today; a collection and its tiers, a carrier and its
    modifiers, next. The part form is spec-generated like any other,
    and where the part carries a statline the page composes one beside
    it — that form's fields come from the owner's statline type, which
    no spec can know.

    Kinds in ``DETAIL_VIEWS`` have a page of their own shape instead —
    a collection's page previews what its definition means right now.
    """
    own_view = DETAIL_VIEWS.get(kind)
    if own_view is not None:
        return own_view(request, pk)
    spec = _spec_for(kind)
    model = _model_for(spec)
    thing = get_object_or_404(model, pk=pk)
    detail_of = DETAIL_KINDS.get(kind)
    if detail_of is None:
        raise Http404(f"{kind} has no parts to add")
    part_spec = specs()[detail_of["verb"]]
    part_model = _model_for(part_spec)
    form_class = generate_form(part_spec)
    statline_class = (
        statline_form_for(thing.statline_type)
        if detail_of["statline"] and thing.statline_type
        else None
    )

    if request.method == "POST":
        form = form_class(request.POST)
        statline_form = statline_class(request.POST) if statline_class else None
        forms_valid = form.is_valid() and (
            statline_form is None or statline_form.is_valid()
        )
        if forms_valid:
            with transaction.atomic():
                part = part_spec.verb(thing, **form.verb_data())
                if statline_form is not None:
                    statline_form.save(part)
            said, _ = detail_of["describe"](part)
            messages.success(request, f"Added {said}.")
            return redirect("authoring-detail", kind=kind, pk=pk)
    else:
        form = form_class()
        statline_form = statline_class() if statline_class else None

    return render(
        request,
        "authoring/detail.html",
        {
            "kind": kind,
            "thing": thing,
            "verbose_name": model._meta.verbose_name,
            "kind_help": kind_help(model),
            "part_verbose_name": detail_of.get(
                "part_name", part_model._meta.verbose_name
            ),
            "part_verbose_name_plural": detail_of.get(
                "parts_label", part_model._meta.verbose_name_plural
            ),
            "part_help": kind_help(part_model),
            "wants_statline": detail_of["statline"],
            "parts": [
                {"label": label, "notes": notes}
                for label, notes in (
                    detail_of["describe"](part)
                    for part in getattr(thing, detail_of["parts"]).all()
                )
            ],
            "form": form,
            "statline_form": statline_form,
        },
    )


def _tp_words(line):
    """One priced line's TP cell: a number, "E", or "—" for a thing not
    offered at the Trading Post at all."""
    if line.is_exclusive:
        return "E"
    if line.trade_points is None:
        return "—"
    return str(line.trade_points)


@staff_member_required
def collection_page(request, pk):
    """A collection, previewed: what its definition means right now.

    The definition is sweeps and entries; the preview is the same
    ``browse`` structure the player-side listing draws, so what an
    author sees here is exactly what a gang will get. Membership by
    criteria keeps itself: author a weapon with a TP price and it is
    simply here on the next load, ammo rows riding under their gun.
    """
    from n26.library.models import Collection
    from n26.library.models.collection import ENTRY_ASSIGNABLE_FIELDS
    from n26.core.browse import browse

    collection = get_object_or_404(Collection, pk=pk)
    view = browse(collection)

    sections = []
    line_count = 0
    for section in view.sections:
        categories = []
        for category in section.categories:
            rows = []
            for line in category.lines:
                notes = []
                if line.entry is not None:
                    notes.append("priced by this list")
                rows.append(
                    {
                        "name": line.name,
                        "credits": f"{line.credits}cr",
                        "tp": _tp_words(line),
                        "nested": False,
                        "notes": notes,
                    }
                )
                line_count += 1
                for part in line.parts:
                    rows.append(
                        {
                            # The bare name: the row draws under its gun,
                            # so the bracket annotation would only repeat.
                            "name": part.thing.name,
                            "credits": f"+{part.credits}cr",
                            "tp": _tp_words(part),
                            "nested": True,
                            "notes": [],
                        }
                    )
                    line_count += 1
            categories.append({"name": category.name, "rows": rows})
        sections.append({"name": section.name, "categories": categories})

    entries = []
    for entry in collection.entries.select_related(*ENTRY_ASSIGNABLE_FIELDS):
        notes = []
        if entry.price_override is not None:
            notes.append(f"{entry.price_override}cr here")
        if entry.trade_point_override is not None:
            notes.append(f"TP {entry.trade_point_override} here")
        entries.append({"label": _label_for(entry.assignable), "notes": notes})

    return render(
        request,
        "authoring/collection.html",
        {
            "thing": collection,
            "kind_help": kind_help(Collection),
            "sweeps": [str(selector) for selector in collection.selectors.all()],
            "entries": entries,
            "sections": sections,
            "line_count": line_count,
        },
    )


#: Kinds whose detail page is its own view rather than the
#: parts-and-add-form shape. Checked by ``detail`` before anything else.
DETAIL_VIEWS = {"collection": collection_page}


@staff_member_required
def foundations(request):
    """The rows the rulebook fixes, created on a button.

    Stats, statline shapes and profile types are nobody's authoring
    decision — every pack needs the same ones, and nothing else can be
    built until they exist. Each kind has its own page like anything
    else; this page is only the shortcut that fills them in.
    """
    from n26.library.standard_content import STANDARD_CONTENT

    if request.method == "POST":
        item = STANDARD_CONTENT.get(request.POST.get("create", ""))
        if item is None:
            raise Http404("No such standard content")
        with transaction.atomic():
            item.create()
        messages.success(request, f"Created {item.name}.")
        return redirect("authoring-foundations")

    entries = []
    for item in STANDARD_CONTENT.values():
        present, total = item.check()
        entries.append(
            {
                "key": item.key,
                "name": item.name,
                "help": item.help,
                "status": item.status(),
                "present": present,
                "total": total,
            }
        )
    from n26.library.models import ProfileType

    return render(
        request,
        "authoring/foundations.html",
        {
            "entries": entries,
            "profile_types": ProfileType.objects.select_related("statline_type"),
            "kinds": [
                {
                    "kind": kind,
                    "verbose_name": _model_for(specs()[verb])._meta.verbose_name,
                    "summary": kind_summary(_model_for(specs()[verb])),
                    "count": _model_for(specs()[verb]).objects.count(),
                }
                for kind, verb in LEAF_KINDS.items()
                if _model_for(specs()[verb]).family == Family.FOUNDATION
            ],
        },
    )


def _rows(model):
    """Every row of a kind, in the order an author wants to read them.

    Not by recency: a listing is for checking content, and thirty-nine
    skills entered in one go would hide all but the last few. Kinds
    that sort into the taxonomy read set by set, and within a set by
    the number they are rolled on.
    """
    rows = model.objects.all()
    if any(field.name == "category" for field in model._meta.get_fields()):
        return rows.select_related("category").order_by(
            "category__position", "category__name", "position", "name"
        )
    return rows  # the model's own ordering — a stat has no "name" at all
