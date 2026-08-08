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
from collections import Counter

from django import forms
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


def _carries_modifiers(kind):
    """Whether this kind's rows can carry modifiers — true for every
    assignable (the mixin's M2M is the tell), never for the foundation
    shapes. Derived, not enumerated: a new assignable kind gets its
    modifier section without anyone remembering to say so."""
    return hasattr(_model_for(_spec_for(kind)), "modifiers")


def _has_detail(kind):
    """Whether this kind's rows have a page of their own.

    Every authored kind does: a row's page is where it is edited, and
    the parts (DETAIL_KINDS), a kind's own view (DETAIL_VIEWS, defined
    below the views themselves) and an assignable's modifier section
    are what some of them add on top of that.
    """
    return (
        kind in LEAF_KINDS
        or kind in DETAIL_KINDS
        or kind in DETAIL_VIEWS
        or _carries_modifiers(kind)
    )


#: The most empty condition rows a composer will offer at once. The
#: count rides in the URL, where any number can be typed, and each row
#: is a whole rendered form — a scope narrowed twenty ways is already
#: past what an author can read.
MAX_CHIPS = 20


def _assignable_models():
    """Every concrete kind that can carry modifiers."""
    from django.apps import apps

    return [
        model
        for model in apps.get_app_config("library").get_models()
        if hasattr(model, "modifiers")
    ]


def _carrier_counts(modifiers):
    """How many things carry each of these modifiers, keyed by pk.

    The number is what stops an author editing a shared modifier
    thinking it is theirs alone. The kinds share no table, so the tally
    costs one query per kind — per *page*, though, not per kind per
    modifier: a page listing every modifier would otherwise spend
    hundreds of queries counting.
    """
    counts = Counter()
    pks = [modifier.pk for modifier in modifiers]
    if not pks:
        return counts
    for model in _assignable_models():
        counts.update(
            model.objects.filter(modifiers__in=pks).values_list("modifiers", flat=True)
        )
    return counts


def _carrier_count(modifier):
    """How many things carry this one modifier."""
    return _carrier_counts([modifier])[modifier.pk]


def _reading_sentences(modifiers):
    """A modifier queryset with everything its sentences read loaded.

    A modifier says itself by walking its scope and its effect, and
    each of those walks further — the stat a change names, the subtypes
    a condition lists. Unhinted that is several queries per row. The
    paths are derived from the fields rather than listed, so a new
    scope, effect or condition kind is covered the day it is added.
    """
    from n26.library.models import Modifier
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    def forward_relations(model):
        return [
            field.name
            for field in model._meta.get_fields()
            if field.concrete and (field.many_to_one or field.one_to_one)
        ]

    select, prefetch = [], []
    for half in (*SCOPE_FIELDS, *EFFECT_FIELDS):
        select.append(half)
        related = Modifier._meta.get_field(half).related_model
        select.extend(f"{half}__{name}" for name in forward_relations(related))
        # Conditions hang off their scope the other way round, so they
        # are fetched separately rather than joined.
        for condition in getattr(related, "CONDITIONS", ()):
            model = related._meta.get_field(condition).related_model
            prefetch.append(f"{half}__{condition}")
            prefetch.extend(
                f"{half}__{condition}__{field.name}"
                for field in model._meta.get_fields()
                if field.concrete and (field.many_to_one or field.many_to_many)
            )

    return modifiers.select_related(*select).prefetch_related(*prefetch)


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
    """One leaf kind: what it is, and every one of them.

    Reading and writing are separate pages. This one is the list an
    author checks content against, so it holds no form — making one is
    a button, and changing one is the row itself.
    """
    spec = _spec_for(kind)
    model = _model_for(spec)
    describe = LEAF_DESCRIBE.get(kind, _describe_row)

    rows = []
    for row in _rows(model):
        label, notes = _label_for(row), describe(row)
        rows.append(
            {
                "pk": row.pk,
                "label": label,
                "notes": notes,
                # What the in-page search reads. Lowercased here so the
                # comparison is a plain substring test in the browser.
                "search": " ".join([label, *notes]).lower(),
            }
        )

    return render(
        request,
        "authoring/leaf.html",
        {
            "kind": kind,
            "verbose_name": model._meta.verbose_name,
            "verbose_name_plural": model._meta.verbose_name_plural,
            "kind_help": kind_help(model),
            "rows": rows,
            "count": len(rows),
        },
    )


@staff_member_required
def create(request, kind):
    """The form that makes one more of a leaf kind, on its own page."""
    spec = _spec_for(kind)
    model = _model_for(spec)
    form_class = generate_form(spec)
    suggestion_class = suggestion_form_for(model)

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
                # Not every kind calls its name "name" — the spec says
                # which field an author reads as one, so the refusal
                # lands on a field the form actually has.
                named = spec.identity
                form.add_error(
                    named,
                    f"A {model._meta.verbose_name} named "
                    f"“{form.cleaned_data[named]}” already exists in this pack.",
                )
            else:
                messages.success(request, f"Created {created}.")
                return redirect("authoring-detail", kind=kind, pk=created.pk)
    else:
        form = form_class()
        suggestions = suggestion_class(prefix="suggested") if suggestion_class else None

    return render(
        request,
        "authoring/create.html",
        {
            "kind": kind,
            "verbose_name": model._meta.verbose_name,
            "verbose_name_plural": model._meta.verbose_name_plural,
            "kind_help": kind_help(model),
            "form": form,
            "suggestion_form": suggestions,
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
    with_modifiers = _carries_modifiers(kind)

    composer = None
    act = request.POST.get("act", "")
    if request.method == "POST" and act and with_modifiers and act != "edit":
        response, composer = _modifier_action(request, kind, thing, act)
        if response is not None:
            return response

    edit_class = generate_form(spec)
    if request.method == "POST" and act == "edit":
        edit_form = edit_class.opened_on(thing, request.POST)
        if edit_form.is_valid():
            try:
                with transaction.atomic():
                    edit_form.apply_to(thing)
            except IntegrityError:
                named = spec.identity
                edit_form.add_error(
                    named,
                    f"A {model._meta.verbose_name} named "
                    f"“{edit_form.cleaned_data[named]}” already exists in this pack.",
                )
            else:
                messages.success(request, f"Saved {thing}.")
                return redirect("authoring-detail", kind=kind, pk=pk)
    else:
        edit_form = edit_class.opened_on(thing)

    if detail_of is not None:
        part_spec = specs()[detail_of["verb"]]
        part_model = _model_for(part_spec)
        form_class = generate_form(part_spec)
        statline_class = (
            statline_form_for(thing.statline_type)
            if detail_of["statline"] and thing.statline_type
            else None
        )
        if request.method == "POST" and not act:
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
        part_context = {
            "has_parts": True,
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
        }
    else:
        part_context = {"has_parts": False}

    return render(
        request,
        "authoring/detail.html",
        {
            "kind": kind,
            "thing": thing,
            "verbose_name": model._meta.verbose_name,
            "verbose_name_plural": model._meta.verbose_name_plural,
            "edit_form": edit_form,
            **part_context,
            **(
                _modifier_section(request, thing, composer)
                if with_modifiers
                else {"with_modifiers": False}
            ),
        },
    )


def _modifier_action(request, kind, thing, act):
    """One modifier action against a carrier: compose, attach, detach.

    Returns ``(response, composer)`` — a redirect when the action
    landed, or ``(None, bound_form)`` when a compose refused and the
    page should redraw with its errors in place.
    """
    from n26.library import authoring
    from n26.library.forms import ModifierComposerForm
    from n26.library.models import Modifier

    if act == "compose":
        composer = ModifierComposerForm(request.POST, attach_to=thing)
        if composer.is_valid():
            try:
                with transaction.atomic():
                    made = composer.save()
            except IntegrityError:
                composer.add_error(
                    "name",
                    "A modifier with that name already exists in this pack — "
                    "attach the existing one instead, or pick another name.",
                )
                return None, composer
            if composer.cleaned_data.get("keep_reusable"):
                messages.success(request, f"Saved {made.name} as a reusable modifier.")
            else:
                messages.success(request, f"Attached {made.name}.")
            return redirect("authoring-detail", kind=kind, pk=thing.pk), None
        return None, composer

    modifier = get_object_or_404(Modifier, pk=request.POST.get("modifier", ""))
    if act == "attach":
        authoring.attach_modifiers_to(thing, [modifier])
        messages.success(request, f"Attached {modifier.name}.")
    elif act == "detach":
        authoring.detach_modifier(thing, modifier)
        messages.success(request, f"Detached {modifier.name} — it still exists.")
    else:
        raise Http404(f"No such action: {act}")
    return redirect("authoring-detail", kind=kind, pk=thing.pk), None


def _composer_state(request, attach_to=None, bound_composer=None):
    """The composer as the URL describes it: closed, open at the named
    kinds, or bound with errors after a refused submit. Shared by the
    carrier pages and the standalone modifiers page."""
    from n26.library.forms import ModifierComposerForm

    scope_kind = request.POST.get("scope_kind", request.GET.get("scope_kind", ""))
    effect_kind = request.POST.get("effect_kind", request.GET.get("effect_kind", ""))
    try:
        chips = max(0, int(request.GET.get("chips", 0)))
    except ValueError:
        chips = 0
    chips = min(chips, MAX_CHIPS)

    composer = bound_composer
    if composer is None and scope_kind in specs() and effect_kind in specs():
        composer = ModifierComposerForm.unbound(
            scope_kind, effect_kind, attach_to=attach_to, chips=chips
        )

    return {
        "kind_picker": ModifierComposerForm(
            initial={"scope_kind": scope_kind, "effect_kind": effect_kind}
        ),
        "composer": composer,
        "composer_scope": scope_kind,
        "composer_effect": effect_kind,
        "composer_chips": chips,
    }


def _modifier_section(request, thing, bound_composer=None):
    """Everything the modifiers section draws: what hangs here (with
    its sentences and how shared it is), what could be attached, and
    the composer."""
    from n26.library.models import Modifier

    attached = list(_reading_sentences(thing.modifiers.all()))
    counts = _carrier_counts(attached)

    rows = []
    for modifier in attached:
        others = counts[modifier.pk] - 1
        notes = [str(modifier.scope), str(modifier.effect)]
        if others:
            notes.append(f"also on {others} other carrier{'' if others == 1 else 's'}")
        rows.append({"pk": modifier.pk, "label": modifier.name, "notes": notes})

    attachable = [
        {
            "pk": modifier.pk,
            "label": f"{modifier.name} — {modifier.scope}: {modifier.effect}",
        }
        for modifier in _reading_sentences(
            Modifier.objects.exclude(pk__in=[m.pk for m in attached])
        )
    ]

    return {
        "with_modifiers": True,
        "modifier_rows": rows,
        "attachable_modifiers": attachable,
        **_composer_state(request, attach_to=thing, bound_composer=bound_composer),
    }


@staff_member_required
def modifiers(request):
    """The modifiers themselves: every one in the pack, and the
    composer with nothing to attach to — what it makes is reusable by
    construction, waiting in every carrier page's attach picker."""
    from n26.library.forms import ModifierComposerForm
    from n26.library.models import Modifier

    bound = None
    if request.method == "POST":
        bound = ModifierComposerForm(request.POST, attach_to=None)
        if bound.is_valid():
            try:
                with transaction.atomic():
                    made = bound.save()
            except IntegrityError:
                bound.add_error(
                    "name",
                    "A modifier with that name already exists in this pack.",
                )
            else:
                messages.success(
                    request,
                    f"Composed {made.name} — attach it from any carrier's page.",
                )
                return redirect("authoring-modifiers")

    every = list(_reading_sentences(Modifier.objects.all()))
    counts = _carrier_counts(every)

    rows = []
    for modifier in every:
        carriers = counts[modifier.pk]
        notes = [str(modifier.scope), str(modifier.effect)]
        notes.append(
            f"on {carriers} carrier{'' if carriers == 1 else 's'}"
            if carriers
            else "reusable — attached nowhere yet"
        )
        rows.append({"label": modifier.name, "notes": notes})

    return render(
        request,
        "authoring/modifiers.html",
        {
            "rows": rows,
            **_composer_state(request, bound_composer=bound),
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
    from n26.core.browse import browse
    from n26.library.models import Collection
    from n26.library.models.collection import ENTRY_ASSIGNABLE_FIELDS

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


#: The sheets an upload may carry, in the order they are planned:
#: ``(what the planner calls it, the sheet's own name, what it holds)``.
#: The two names differ where the spreadsheet's heading is not the
#: planner's word for the sheet — an author looks for the heading.
INGEST_SHEETS = [
    (
        "equipment",
        "Equipment",
        "The catalogue: one row per thing the game sells, with its price.",
    ),
    ("weapon_profiles", "Weapon profiles", "The statlines, and nothing else."),
    (
        "equipment_lists",
        "Equipment lists",
        "A named list per gang, one entry per line.",
    ),
    (
        "profiles",
        "All Profiles",
        "The fighters, each with the heading and category it is hired under.",
    ),
]


class IngestForm(forms.Form):
    """Four optional CSVs. Optional because a partial upload is a real
    thing to want — the statlines alone, to fix a column — and because
    what a missing sheet costs is said in the preview rather than
    refused here."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, label, help_text in INGEST_SHEETS:
            self.fields[name] = forms.FileField(
                required=False,
                label=label,
                help_text=help_text,
                widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
            )

    def sheets(self):
        """The uploaded files, read into rows the planner takes."""
        from n26.library.ingest import read_csv

        found = {}
        for name, _label, _help in INGEST_SHEETS:
            upload = self.cleaned_data.get(name)
            if upload:
                found[name] = read_csv(upload.read().decode("utf-8-sig"))
        return found


def _problems_by_shape(problems):
    """Problems grouped by what they are, not by which line hit them.

    A hundred problems are usually five kinds of problem, and a list
    that says so is a morning's work rather than a wall. The quoted
    names come out of the message to make the shape; the lines they
    happened on are kept beside it.
    """
    shapes = {}
    for problem in problems:
        shape = problem.message
        for quote in ("'", '"'):
            parts = shape.split(quote)
            if len(parts) > 2:
                shape = f"{parts[0]}{quote}…{quote}{parts[-1]}"
        key = (problem.severity, shape)
        entry = shapes.setdefault(
            key,
            {"severity": problem.severity, "shape": shape, "count": 0, "examples": []},
        )
        entry["count"] += 1
        if len(entry["examples"]) < 4:
            entry["examples"].append(
                {
                    "where": f"{problem.sheet}:{problem.line}",
                    "message": problem.message,
                }
            )
    return sorted(
        shapes.values(),
        key=lambda e: (e["severity"] != "error", -e["count"]),
    )


def _changes_by_shape(changes, examples=6):
    """Differences grouped by what changed, not by which row changed it.

    A thousand corrected prices are one fact about the upload and a
    thousand lines nobody reads. Grouping by the kind and the fields
    that moved says the fact; a few worked examples under each show
    what it looks like, and the count says how far it goes.
    """
    shapes = {}
    for change in changes:
        moved = tuple(sorted(change["changes"]))
        key = (change["kind"], moved)
        entry = shapes.setdefault(
            key,
            {
                "kind": change["kind"],
                "shape": f"{change['kind']} — {', '.join(moved)}",
                "count": 0,
                "examples": [],
            },
        )
        entry["count"] += 1
        if len(entry["examples"]) < examples:
            entry["examples"].append(
                {
                    "name": change["name"] or change["key"],
                    "said": "; ".join(
                        _difference_said(field, change["changes"][field])
                        for field in moved
                    ),
                }
            )
    return sorted(shapes.values(), key=lambda entry: -entry["count"])


def _difference_said(field, difference):
    """One field's difference, in a line — "price 20 → 25", "traits
    + Unwieldy − Rapid Fire (1)"."""
    if "to" in difference:
        return f"{field} {_value_said(difference['from'])} → {_value_said(difference['to'])}"
    parts = []
    for mark, name in (("+", "added"), ("−", "removed"), ("~", "changed")):
        for said in difference.get(name, ()):
            parts.append(f"{mark} {said}")
    return f"{field} {' '.join(parts)}"


def _value_said(value):
    return "—" if value is None or value == "" else value


@staff_member_required
def ingest(request):
    """Spreadsheets in, a preview, then the rows.

    Two buttons over one set of files, because the preview *is* the
    contract: planning the same sheets twice says the same thing, so
    what Preview showed is what Import does. Nothing is kept between
    the two — an upload that is never imported leaves nothing behind.

    Undoing an import is its own page. Counting what would go is real
    work, and a page that did it on every visit would charge everyone
    for a button almost nobody presses — but the greater part of the
    reason is that nothing irreversible should happen on one click.
    """
    from n26.library.ingest import perform, plan_ingest

    form = IngestForm()
    preview = None
    performed = None

    if request.method == "POST":
        form = IngestForm(request.POST, request.FILES)
        if form.is_valid():
            sheets = form.sheets()
            if not sheets:
                messages.error(request, "Choose at least one sheet.")
            else:
                plan = plan_ingest(**sheets)
                preview = plan.preview(examples=2)
                preview["shapes"] = _problems_by_shape(plan.problems)
                preview["errors"] = sum(
                    1 for p in plan.problems if p.severity == "error"
                )
                preview["notes"] = len(plan.problems) - preview["errors"]
                preview["diffs"] = _changes_by_shape(preview["changes"])
                # Uploading last year's export over this year's content
                # is the realistic accident, and it is invisible row by
                # row and unmistakable in the aggregate.
                held = preview["actions"].get("update", 0) + preview["actions"].get(
                    "unchanged", 0
                )
                preview["mostly_changed"] = (
                    held > 0 and preview["actions"].get("update", 0) * 2 > held
                )
                if "apply" in request.POST:
                    if not plan.ok:
                        messages.error(
                            request,
                            f"{preview['errors']} problem(s) block this upload — "
                            f"nothing was written.",
                        )
                    else:
                        with transaction.atomic():
                            performed = perform(plan).counts()
                        messages.success(
                            request,
                            f"Imported {sum(performed.values())} rows.",
                        )

    return render(
        request,
        "authoring/ingest.html",
        {"form": form, "preview": preview, "performed": performed},
    )


@staff_member_required
def ingest_clear(request):
    """Undo an import, having said first what that means.

    The count is the whole page: a confirmation that did not name what
    it was about to take would be a checkbox with extra steps. Posting
    is the act — a link can be followed by accident, and something has
    to be irreversible somewhere.
    """
    from django.db.models import ProtectedError

    from n26.library.ingest import clear_imported, count_imported

    if request.method == "POST":
        try:
            with transaction.atomic():
                gone = clear_imported()
        except ProtectedError as protected:
            # Anything may hold imported content: a gang that bought a
            # weapon, an authored modifier that names a trait. Saying
            # which is the difference between a dead end and a next
            # step, so the holders are counted by kind and named.
            holders = Counter(
                str(type(held)._meta.verbose_name)
                for held in protected.protected_objects
            )
            said = ", ".join(
                f"{count} {kind}" for kind, count in sorted(holders.items())
            )
            messages.error(
                request,
                f"Nothing was removed. Some of this content is held by "
                f"{said}, which protects it — remove those first.",
            )
            return redirect("authoring-ingest-clear")
        said = ", ".join(f"{count} {kind}" for kind, count in sorted(gone.items()))
        messages.success(request, f"Cleared {said}." if said else "Nothing to clear.")
        return redirect("authoring-ingest")

    standing = count_imported()
    return render(
        request,
        "authoring/ingest_clear.html",
        {"standing": standing, "total": sum(standing.values())},
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
