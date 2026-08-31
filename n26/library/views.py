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
from dataclasses import dataclass, replace

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from n26.library.forms import generate_form, statline_form_for, suggestion_form_for
from n26.library.models.assignable import Family
from n26.library.references import carrying_models as _assignable_models
from n26.library.references import forward_relations as _forward_relations
from n26.library.references import reading_sentences as _reading_sentences
from n26.library.references import references_to
from n26.library.sheets import INGEST_SHEETS, SHEET_LABELS, SHEET_NAMES
from n26.library.specs import specs

#: What each sheet holds, by the planner's name for it — the sentence a
#: sheet's own upload page leads with.
SHEET_HOLDS = {name: holds for name, _label, holds in INGEST_SHEETS}

#: The leaf kinds the authoring surface offers, in menu order:
#: url slug → (create verb, the model the page lists). The guard test
#: keeps every entry backed by a spec.
LEAF_KINDS = {
    "subtype": "create_subtype",
    "rule": "create_rule",
    "trait": "create_trait",
    "skill": "create_skill",
    "power": "create_power",
    "counter": "create_counter",
    "hidden": "create_hidden",
    "slot-type": "create_slot_type",
    "pickable": "create_pickable",
    "picklist": "create_picklist",
    "slot": "create_slot",
    "wargear": "create_wargear",
    "weapon": "create_weapon",
    "weapon-accessory": "create_weapon_accessory",
    "stat": "create_stat",
    "statline-type": "create_statline_type",
    "section": "create_section",
    "category": "create_category",
    "affiliation": "create_affiliation",
    "gang-type": "create_gang_type",
    "profile": "create_profile",
    "collection": "create_collection",
}


#: Kinds whose page is a place you come back to: the thing, and the
#: parts you add to it over time. ``kind -> the verb that adds a part``.
def _describe_weapon_profile(profile):
    """A firing line, as the author needs to check it: what it is
    called, the stats they typed, its traits, and its price.

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
    show what was typed without rebuilding the card machinery.

    Reads the stats with ``.all()`` and sorts in Python, so a page that
    prefetched them (the parts hints below) summarises a whole listing
    without a query per line.
    """
    statline = getattr(owner, "statline", None)
    if statline is None:
        return ""
    return "  ".join(
        f"{stat.short_name} {stat.formatted_value}"
        for stat in sorted(
            statline.stats.all(), key=lambda stat: stat.statline_type_stat.position
        )
    )


def _describe_statline_stat(type_stat):
    """One column of a shape. Not prefixed with the shape's name — the
    page is already that shape — and showing the display flags and any
    renaming, which are the only things about the row a reader cannot
    infer. The row is named for the stat, so a shape that heads the
    column differently has to say so."""
    notes = []
    if type_stat.short_name_override:
        notes.append(f"prints as {type_stat.short_name_override}")
    if type_stat.is_first_of_group:
        notes.append("starts a group")
    if type_stat.is_highlighted:
        notes.append("highlighted")
    return str(type_stat.stat), notes


def _describe_built_in(member):
    """One row of what a profile comes with. A collection member is
    access rather than kit — the list this entry may use — and the
    page says so; everything else reads as its kind. An extra weapon
    line naming no gun of its set rides whatever matching gun its
    acquirer holds, which is worth a row's words because nothing else
    on the page says where it lands."""
    from n26.library.models import Collection

    thing = member.assignable
    if isinstance(thing, Collection):
        notes = ["collection — a list it may use"]
    else:
        notes = [str(thing._meta.verbose_name)]
    if member.amount:
        notes.append(f"opening value {member.amount}")
    if member.weapon_profile_id is not None and member.gun_member_id is None:
        notes.append("rides whatever matching gun is already held")
    return _label_for(thing), notes


def _describe_picklist_member(member):
    """One pickable on one list: what this list calls it, and — where
    that is not the pickable's own name — what it is called elsewhere.

    Its place in the order is not said: the rows are printed in it.
    """
    notes = []
    if member.label_override:
        notes.append(f"the {member.pickable} pickable, under another name")
    # The band leads on a roll table, as the book prints it.
    label = f"{member.band} — {member.label}" if member.band else member.label
    return label, notes


def _roll_table_summary(picklist):
    """What the members section says under its heading, for a roll table.

    The one fact worth a glance before opening the table page: how much
    of the die the bands claim. An ordinary picklist says nothing here.
    """
    if not picklist.dice:
        return ""
    said = coverage(picklist)
    words = [
        f"Rolled on a {picklist.get_dice_display()}.",
        f"{said.covered} of {said.total} rolls covered"
        + (
            f"; {', '.join(str(roll) for roll in said.unclaimed)} unclaimed"
            if said.unclaimed
            else ""
        )
        + ".",
    ]
    if said.doubled:
        rolls = ", ".join(str(roll) for roll, _ in said.doubled)
        words.append(f"Claimed by more than one result: {rolls}.")
    if said.bandless:
        names = ", ".join(member.label for member in said.bandless)
        words.append(f"No band, so never rolled: {names}.")
    return " ".join(words)


def _weapon_parts(parts):
    """What ``_describe_weapon_profile`` reads, loaded for every line at
    once — unhinted, each profile fetches its weapon, its statline's
    stats and its traits on its own."""
    return parts.select_related("weapon", "statline").prefetch_related(
        "statline__stats__statline_type_stat__stat", "traits"
    )


def _built_in_parts(parts):
    from n26.library.models import DefaultAssignment

    return parts.prefetch_related(*DefaultAssignment.ASSIGNABLE_FIELDS)


def _arrange_built_ins(pairs):
    """The comes-with rows, with each gun's own lines under it.

    ``pairs`` is ``(member, drawn row)`` in listing order. A member
    naming its gun nests under that gun's row — the grammar a card uses
    for firing lines under weapons — and every weapon row gains the way
    to build one of its lines in beside it. A member naming no gun
    lists flat, its row saying where it lands.
    """
    drawn_by_pk = {}
    for member, drawn in pairs:
        drawn["children"] = []
        drawn_by_pk[member.pk] = drawn
    arranged = []
    for member, drawn in pairs:
        if member.weapon_id is not None:
            drawn["add_profile_url"] = reverse(
                "authoring-built-in-profiles", args=[member.pk]
            )
        parent = drawn_by_pk.get(member.gun_member_id) if member.gun_member_id else None
        if parent is not None:
            parent["children"].append(drawn)
        else:
            arranged.append(drawn)
    return arranged


def _describe_option(option):
    """One option, as the author needs to check it: what taking it
    adds to the price, and what it brings.

    Which set it belongs to is not said here — the page draws options
    under their set's own heading, so the row repeating it would be
    noise.
    """
    brings = ", ".join(_label_for(member.assignable) for member in _brought_by(option))
    price = f"+{option.default_set.price}cr"
    return option.name, [price, f"brings {brings}" if brings else "brings nothing"]


def _brought_by(option):
    """What one option's set holds, in the order it was written.
    Archived members are off the set — taking the option no longer
    brings them — and are skipped in Python so the option listing's
    prefetch of members stays warm."""
    return [
        member for member in option.default_set.members.all() if not member.archived
    ]


#: The rulebook's phrase for each way a set is picked — the words the
#: page's headings and the option form's "joins" line both use, held in
#: one place so the two cannot drift.
HOW_A_SET_IS_PICKED = {
    "one": "one of the following",
    "any": "any of the following",
    "one-or-none": "one of the following, or none",
}


def _describe_option_group(group):
    """One set of options: how it is picked, and how many it offers."""
    taken = HOW_A_SET_IS_PICKED[group.choose]
    offered = len(group.options.all())
    return group.name, [taken, f"{offered} option{'' if offered == 1 else 's'}"]


def _option_parts(parts):
    """The options of one carrier, listed set by set.

    Their own ordering is by position alone, which is what a hire needs:
    within a set, the first is the one taken unasked. On a page listing
    every set at once that interleaves them — the first option of the
    second set sits between the first and second options of the main
    one — so the set leads here. The main pick-one set is first, having
    no group row at all.
    """
    from django.db.models import F

    from n26.library.models import DefaultAssignment

    return (
        parts.select_related("group", "default_set")
        .prefetch_related(
            *(
                f"default_set__members__{name}"
                for name in DefaultAssignment.ASSIGNABLE_FIELDS
            )
        )
        .order_by(F("group__position").asc(nulls_first=True), "position")
    )


#: A kind's own parts: the things only that kind has, added to one of
#: its rows over time. At most one section per kind, and a post naming
#: no section is for this one.
DETAIL_KINDS = {
    "weapon": {
        "verb": "add_weapon_profile",
        "parts": "profiles",
        "statline": True,
        "describe": _describe_weapon_profile,
        "parts_hint": _weapon_parts,
        # Where a row's name leads. A firing line is corrected on a page
        # of its own: its stats are a form of their own and its traits a
        # set, neither of which fits in a listing row.
        "opens": "authoring-weapon-profile",
        # Where a row's Remove control leads, as the built-ins rows have
        # one: what deleting a line reaches — a gang that holds it, a
        # hire that comes with it — cannot be read off the row.
        "removes": "authoring-weapon-profile-delete",
        # Adding one happens at an address of its own rather than in a
        # form under the listing. A line is a form and a whole statline
        # both, and the page already carries the weapon's own fields
        # above them. Named by the weapon, there being no line yet.
        "adds": "authoring-weapon-profile-add",
    },
    "statline-type": {
        "verb": "add_stat_to_statline_type",
        "parts": "stats",
        "statline": False,
        "describe": _describe_statline_stat,
        "parts_hint": lambda parts: parts.select_related("stat"),
    },
    "picklist": {
        "verb": "add_picklist_member",
        "parts": "members",
        "statline": False,
        "describe": _describe_picklist_member,
        "parts_hint": lambda parts: parts.select_related("pickable"),
        # A roll table's results only mean anything with their bands and
        # the coverage check, so they are worked on the table page — this
        # section names the shape, says how covered it is, and sends an
        # author there. An ordinary picklist keeps its form here.
        "adds": lambda picklist: (
            reverse("authoring-picklist-table", args=[picklist.pk])
            if picklist.dice
            else ""
        ),
        "parts_label": lambda picklist: "roll table" if picklist.dice else "pickables",
        # The row is the listing, but the name on it is the pickable's,
        # and the pickable's page is where what it does is written.
        "opens": lambda member: reverse(
            "authoring-detail", args=["pickable", member.pickable_id]
        ),
        # The part model's own name is accurate and nothing an author
        # says; what they are adding is one more pickable to choose from —
        # or, on a roll table, one more result at its band.
        "part_name": lambda picklist: "result" if picklist.dice else "pickable",
        "parts_description": lambda picklist: (
            _roll_table_summary(picklist)
            or (
                "A list of pickables for a particular slot type, in the order "
                "a player reads them. Taking one off changes only what is "
                "offered next: the pickable itself stays in the library, and "
                "anyone who already made a pick keeps it."
            )
        ),
        "nothing_yet": (
            "No pickables yet — a choice drawing on this list has nothing to offer."
        ),
        # Taking a pickable off a list is a question asked at its own
        # address, like every other part: what the act reaches — the
        # pickable itself, every other list offering it — cannot be read
        # off the row.
        "removes": "authoring-picklist-member-remove",
    },
}


#: What a thing always comes with, in the same shape as a kind's own
#: parts — but filed apart from them, because this is not one kind's
#: section. Every assignable can carry built-ins, so which pages draw
#: it is read off the model (``_carries_built_ins``) rather than listed,
#: and it sits alongside whatever else the kind carries: a weapon has
#: firing lines *and* can come with something.
#:
#: Naming itself in ``act`` is what lets it do that. A post that names
#: no section is for the kind's own parts, of which there is at most
#: one; this one shares its page and so has to say which form was
#: clicked.
#:
#: The words are ours rather than the part model's, because the row is a
#: DefaultAssignment — accurate, and nothing an author says. They avoid
#: naming any one carrier: a profile is hired and a piece of wargear is
#: bought, and both come with what is listed here.
BUILT_INS_PART = {
    "act": "built_in",
    "verb": "add_built_in",
    "parts": "built_in_members",
    "statline": False,
    "describe": _describe_built_in,
    "parts_label": "comes with",
    "part_name": "built-in",
    "parts_hint": _built_in_parts,
    "parts_description": (
        "What comes with this, free, the moment it is acquired — hired, "
        "for a profile; bought, for a weapon or a piece of wargear. Taking "
        "a line off changes only what is acquired next: the thing itself "
        "stays in the library, and anything already holding it keeps it."
    ),
    # Where a row's Remove control leads. A part is taken off at its
    # own address, never from the listing, because what the act means
    # cannot be read off the row.
    "removes": "authoring-built-in-remove",
    # A gun's own lines nest under it, so the listing reads the way a
    # card draws firing lines under weapons.
    "arrange": _arrange_built_ins,
    # The add form does not offer weapon profiles: a line means nothing
    # apart from its gun, so the section carries the way to the page
    # that adds one — a gun of the set from its own row, or here for a
    # gun the set does not bring.
    "door": lambda thing: (
        reverse("authoring-set-profiles", args=[thing.built_ins_id])
        if thing.built_ins_id
        else ""
    ),
    "door_label": "Add a weapon profile…",
}


#: The alternatives a thing offers when it is acquired, in the same
#: shape as a kind's own parts. Filed apart for the same reason
#: built-ins are: which pages draw it is read off the model
#: (``_offers_options``) rather than listed.
#:
#: An option's own set of things is never mentioned. The author says
#: what the choice is called, what taking it adds and what it brings;
#: the set that holds them is founded by the verb and named for authors
#: alone, because two profiles may both offer "As standard" while a set
#: name may appear once in a pack.
OPTIONS_PART = {
    "act": "option",
    "verb": "offer_option",
    "parts": "options",
    "statline": False,
    "describe": _describe_option,
    "parts_label": "options",
    "part_name": "option",
    "parts_hint": _option_parts,
    "parts_description": (
        "What a player picks when this is acquired. Each option's price "
        "is added to the base price."
    ),
    "nothing_yet": (
        "Acquired the same way every time. Add an option to offer an alternative."
    ),
    "removes": "authoring-option-remove",
}

#: A further set of options — the rulebook's second "…of the following"
#: list on one entry. A carrier needs none: options created without a
#: set form the main pick-one set on their own.
OPTION_SETS_PART = {
    "act": "option-set",
    "verb": "create_option_group",
    "parts": "option_groups",
    "statline": False,
    "describe": _describe_option_group,
    "parts_label": "sets of options",
    "part_name": "set of options",
    "parts_hint": lambda parts: parts.prefetch_related("options"),
    "parts_description": (
        "For a separate, further pick — a Sanctioner chooses its melee "
        "weapon and may also add grenades. Prices add up."
    ),
    "nothing_yet": "",
    "removes": "authoring-option-set-remove",
}


def _carries_modifiers(kind):
    """Whether this kind's rows can carry modifiers — true for every
    assignable (the mixin's M2M is the tell), never for the foundation
    shapes. Derived, not enumerated: a new assignable kind gets its
    modifier section without anyone remembering to say so."""
    return hasattr(_model_for(_spec_for(kind)), "modifiers")


def _carries_built_ins(kind):
    """Whether this kind's rows can come with things.

    Two facts, both read off the model. ``built_ins`` is a column on the
    assignable mixin, so coming with something is available to every
    assignable and absent from the foundation shapes; and the kind itself
    says whether a set would ever be materialised (``takes_built_ins``)
    — no, for the kinds that only arrive by being chosen. Derived for the
    same reason modifiers are, so a new assignable kind gets the section
    without anyone remembering to say so.
    """
    model = _model_for(_spec_for(kind))
    return hasattr(model, "built_in_members") and model.takes_built_ins


def _offers_options(kind):
    """Whether this kind's rows offer alternatives when acquired.

    Read off the model, like the built-ins section: a profile and a
    piece of wargear opt into the mixin that gives them ``options``, and
    a kind that opts in later gets these sections without anyone
    remembering to say so.
    """
    return hasattr(_model_for(_spec_for(kind)), "options")


def _part_sections(kind):
    """Every section of parts this kind's page draws, in the order they
    appear: what only this kind has, then what anything can come with,
    then what it lets the buyer choose between.

    The options come last, and their sets after them for the post
    routing's sake — the page draws the two as one section
    (``_hire_options_context``), grouped the way a hire offers them.
    """
    sections = []
    if kind in DETAIL_KINDS:
        sections.append(DETAIL_KINDS[kind])
    if _carries_built_ins(kind):
        sections.append(BUILT_INS_PART)
    if _offers_options(kind):
        sections.extend([OPTIONS_PART, OPTION_SETS_PART])
    return sections


def _narrow_a_slots_picklists(form, slot):
    """A choice offers its own slot type's picklists and no others.

    The page that *makes* a slot cannot narrow this — no slot type has
    been chosen at the moment the picker is drawn — but the page that
    corrects one knows the slot type already, and a picker offering
    picklists from another one is an invitation to write content whose
    pickables could never settle the choice.
    """
    form.fields["picklist"].queryset = slot.slot_type.picklists.all()


#: Where a kind's edit form narrows a picker to the rows that could
#: possibly be right for the row in hand. Keyed by kind, because what
#: narrows follows from what that row already says about itself, which
#: is not something a spec field can reach.
EDIT_NARROWING = {"slot": _narrow_a_slots_picklists}


def _narrowed_for_editing(kind, thing, form):
    """The edit form, with whatever its kind narrows narrowed."""
    narrowing = EDIT_NARROWING.get(kind)
    if narrowing is not None:
        narrowing(form, thing)
    return form


def _statline_editor_for(thing):
    """The statline form a thing's own page carries, or ``None``.

    Which kinds may own a statline is read off the columns that hold
    one, never listed here: a weapon has a statline type but it is a
    weapon's *firing lines* that carry values, and a new kind of owner
    should get its editor without anyone remembering to come back. A
    shape with no characteristics in it yet draws no editor — there
    would be nothing to type in.
    """
    from n26.library.models import Statline

    owners = {Statline._meta.get_field(f).related_model for f in Statline.OWNERS}
    if type(thing) not in owners:
        return None
    statline_type = thing.statline_type
    if statline_type is None or not statline_type.stats.exists():
        return None
    return statline_form_for(statline_type)


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


def _kind_slugs():
    """Which authoring page each model's rows are read on."""
    return {_model_for(specs()[verb]): kind for kind, verb in LEAF_KINDS.items()}


def _naming(row):
    """How a listing row says which thing it is about.

    Three separate facts, because they are read differently. The label
    is the thing itself, as a player would read it, and is what the link
    carries: clicking a name opens the thing, not the words an author
    hung beside it. The qualifier — author facing, never a player's —
    follows the link as plain text. The help is the author's own note
    about wielding this while building other content; the foundation
    kinds have neither, and plenty of rows have no help written yet.
    """
    return {
        "label": str(row),
        "qualifier": getattr(row, "qualifier", "") or "",
        "help": getattr(row, "library_author_help", "") or "",
    }


def _named_row(row, model, slugs):
    """One row, as a page naming other people's things prints it."""
    from n26.library.models import WeaponProfile

    kind = slugs.get(model)
    if kind:
        url = reverse("authoring-detail", args=[kind, row.pk])
    elif model is WeaponProfile:
        # A firing line is a part of its weapon rather than a kind, so
        # its page is not one of the kind pages the slugs cover.
        url = reverse("authoring-weapon-profile", args=[row.pk])
    else:
        # A kind with no authoring page of its own is still named; only
        # the link is missing.
        url = ""
    return {
        **_naming(row),
        "kind_name": str(model._meta.verbose_name),
        "kind": kind,
        "url": url,
        "pk": row.pk,
    }


def _carriers(modifier):
    """Everything holding this modifier, named and linked.

    A count says how far a change reaches; the names say whether this
    is the one the author meant. Both are wanted before an edit or a
    delete, and cost the same query — one per kind, a fixed number
    whatever the pack holds.
    """
    slugs = _kind_slugs()
    found = []
    for model in _assignable_models():
        rows = model.objects.select_related(*_forward_relations(model))
        for row in rows.filter(modifiers=modifier):
            found.append(_named_row(row, model, slugs))
    return sorted(
        found,
        key=lambda carrier: (
            carrier["kind_name"],
            carrier["label"],
            carrier["qualifier"],
        ),
    )


def _holders_of(default_set):
    """Everything that arrives with this set of defaults, named and linked.

    Usually one thing — a profile's built-ins are founded for that
    profile — but nothing makes that so: any assignable may point its
    ``built_ins`` at any set, and an option offers one as an
    alternative. A page about to change what a set holds asks who is
    holding it rather than assuming.
    """
    from n26.library.models import Option

    slugs = _kind_slugs()
    found = []
    for model in _assignable_models():
        rows = model.objects.select_related(*_forward_relations(model))
        for row in rows.filter(built_ins=default_set):
            found.append({**_named_row(row, model, slugs), "how": "comes with it"})
    for option in Option.objects.filter(default_set=default_set).select_related(
        *Option.ASSIGNABLE_FIELDS
    ):
        carrier = option.carrier
        found.append(
            {
                **_named_row(carrier, type(carrier), slugs),
                "how": "offers it as an option",
            }
        )
    return sorted(
        found,
        key=lambda holder: (holder["kind_name"], holder["label"], holder["qualifier"]),
    )


def _reach_said(reach, adding):
    """How far an addition to a set of defaults travels, in a sentence.

    Says who already holds the set and what the addition does to them.
    The consequence follows the feature flag, because reach is only
    promised while the passes that deliver it actually run: shut, the
    sentence says the change waits instead.
    """
    from n26.flags import BUILT_IN_PROPAGATION, switched_on

    if reach.uses == 0:
        return (
            f"Held by no gang yet, so {adding} changes only what is "
            f"acquired from now on."
        )
    times = "once" if reach.uses == 1 else f"{reach.uses} times"
    where = "in one gang" if reach.gangs == 1 else f"across {reach.gangs} gangs"
    standing = f"Already held {times}, {where}"
    if switched_on(BUILT_IN_PROPAGATION):
        reached = "it" if reach.uses == 1 else "every one of them"
        return f"{standing} — {adding} reaches {reached} within seconds."
    reached = "it" if reach.uses == 1 else "them"
    return (
        f"{standing} — {adding} will reach {reached} when built-in "
        f"propagation is switched on."
    )


def _built_in_reach_said(thing):
    """The reach sentence for a thing's own built-ins: the set it has,
    or — before a first built-in founds one — the set it would get,
    whose uses are the thing's own."""
    from n26.core.propagation import reach_of, reach_of_new_built_ins

    reach = (
        reach_of(thing.built_ins)
        if thing.built_ins_id
        else reach_of_new_built_ins(thing)
    )
    return _reach_said(reach, "a built-in added here")


def _article_for(word):
    """ "a" or "an" in front of a word we chose ourselves.

    The leading letter and nothing more, which is enough for the kind
    names: they are the app's own words, not the books', so there is no
    "a Unification Elder" here to get wrong.
    """
    return "an" if str(word)[:1].lower() in "aeiou" else "a"


def _opens_url(opens, part):
    """Where a part's name leads, blank where it leads nowhere.

    A URL name for a part with a page of its own, or a callable where
    the row joins two things and the name is one of them: a picklist
    member's name is a pickable's, and an author following it wants the
    pickable rather than the listing row.
    """
    if not opens:
        return ""
    if callable(opens):
        return opens(part)
    return reverse(opens, args=[part.pk])


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
    sorts, what it is priced at — rather than a column per kind. Kinds with
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


#: Kinds whose listing says something a generic reading would miss.
def _describe_profile(profile):
    """Whose list it hires from, its Type, and what a hire pays."""
    from n26.library.models import Collection

    notes = [profile.gang_type.name, profile.profile_type.name]
    if profile.price:
        notes.append(f"{profile.price}cr")
    # Archived members are skipped in Python so the listing's prefetch
    # of members stays warm; an archived list is one the profile no
    # longer hires with.
    accessible = [
        member.assignable.name
        for member in (profile.built_ins.members.all() if profile.built_ins_id else ())
        if not member.archived and isinstance(member.assignable, Collection)
    ]
    if accessible:
        notes.append(f"uses {', '.join(accessible)}")
    return notes


def _describe_gang_type(gang_type):
    """The founding budget, and whether the type can be founded at all.

    A type nobody can pick is the surprising state, so the listing says it
    rather than leaving an author to open each row to find out.
    """
    notes = []
    if gang_type.starting_credits is not None:
        notes.append(f"founds with {gang_type.starting_credits}cr")
    if not gang_type.foundable:
        notes.append("cannot be founded")
    return notes


def _describe_slot_type(slot_type):
    """How much has been built in this slot type, and whether one
    holder may pick the same pickable twice."""
    notes = [
        f"{count} {word}{'' if count == 1 else 's'}"
        for count, word in (
            (len(slot_type.pickables.all()), "pickable"),
            (len(slot_type.picklists.all()), "picklist"),
            (len(slot_type.slots.all()), "slot"),
        )
    ]
    if not slot_type.allows_repeats:
        notes.append("no repeats")
    return notes


def _pickable_notes(pickable):
    """How many picklists offer one pickable.

    On no list at all is the state worth seeing: a pickable nothing
    offers can only be handed over by an owner.
    """
    listed = len(pickable.listed_on.all())
    return [
        f"on {listed} list{'' if listed == 1 else 's'}" if listed else "on no list yet"
    ]


def _picklist_notes(picklist):
    """How many pickables are on one picklist."""
    offered = len(picklist.members.all())
    return [f"{offered} pickable{'' if offered == 1 else 's'}"]


def _describe_pickable(pickable):
    """The slot type it belongs to, and how many picklists offer it."""
    return [pickable.slot_type.name, *_pickable_notes(pickable)]


def _describe_picklist(picklist):
    """The slot type it offers, how many pickables are on it, and — on a
    roll table — the die it is rolled on."""
    notes = [picklist.slot_type.name, *_picklist_notes(picklist)]
    if picklist.dice:
        notes.append(f"rolled on a {picklist.get_dice_display()}")
    return notes


def _picks_said(slot):
    """How many picks a choice takes, as a listing prints it."""
    if slot.min_picks == slot.max_picks:
        return "one pick" if slot.max_picks == 1 else f"{slot.max_picks} picks"
    return f"{slot.min_picks} to {slot.max_picks} picks"


def _slot_terms(slot):
    """How many picks a choice takes, and the two things about it a
    reader would otherwise have to open it to learn: that the gang holds
    what is picked, and that it draws no row.

    Said apart from the picklist, because a page listing the slots that
    draw on one list would print that list once a row.
    """
    notes = [_picks_said(slot)]
    if slot.assigned_to == slot.WillBeAssignedTo.GANG:
        notes.append("the gang holds the pick")
    if slot.hidden:
        notes.append("draws no row")
    return notes


def _slot_notes(slot):
    """What the choice offers, and everything it says about itself."""
    return [f"from {slot.picklist.name}", *_slot_terms(slot)]


def _describe_slot(slot):
    """The slot type, and everything the choice says about itself."""
    return [slot.slot_type.name, *_slot_notes(slot)]


LEAF_DESCRIBE = {
    "skill": _describe_skill,
    "profile": _describe_profile,
    "gang-type": _describe_gang_type,
    "slot-type": _describe_slot_type,
    "pickable": _describe_pickable,
    "picklist": _describe_picklist,
    "slot": _describe_slot,
}


def _profile_listing(rows):
    """What ``_describe_profile`` walks, loaded for the whole listing at
    once — per row it reads two foreign keys and the built-ins' members,
    which unhinted is a handful of queries times every profile in the
    library."""
    from django.db.models import Prefetch

    from n26.library.models import DefaultAssignment

    return rows.select_related("gang_type", "profile_type").prefetch_related(
        Prefetch(
            "built_ins__members",
            queryset=DefaultAssignment.objects.select_related(
                *DefaultAssignment.ASSIGNABLE_FIELDS
            ),
        )
    )


#: Kinds whose describer — or whose own name — reads beyond the row.
LEAF_LISTING_HINTS = {
    "profile": _profile_listing,
    # A category says itself as "section: name".
    "category": lambda rows: rows.select_related("section"),
    # The choice kinds each read the slot type they belong to, and two
    # of them count a set as well — a query apiece, per listing rather
    # than per row.
    "slot-type": lambda rows: rows.prefetch_related("pickables", "picklists", "slots"),
    "pickable": lambda rows: rows.select_related("slot_type").prefetch_related(
        "listed_on"
    ),
    "picklist": lambda rows: rows.select_related("slot_type").prefetch_related(
        "members"
    ),
    "slot": lambda rows: rows.select_related("slot_type", "picklist"),
}


def _spec_for(kind):
    verb_name = LEAF_KINDS.get(kind)
    if verb_name is None:
        raise Http404(f"No authoring page for {kind!r}")
    return specs()[verb_name]


#: ``literal`` in a docstring, as the page should draw it.
_LITERAL = re.compile(r"``([^`]+)``")

#: **The load-bearing sentence** in a docstring, likewise. Docstrings
#: are written for two readers and the emphasis is for both, so a page
#: showing the asterisks is showing the author the punctuation instead
#: of the point. A lone ``**kwargs`` has no closing pair and is left
#: exactly as it was typed.
_EMPHASIS = re.compile(r"\*\*([^*]+)\*\*")


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
        mark_safe(  # nosec B703 B308 - escape() runs first; only our own markup is added
            _EMPHASIS.sub(
                r"<strong>\1</strong>",
                _LITERAL.sub(r"<code>\1</code>", escape(" ".join(paragraph.split()))),
            )
        )
        for paragraph in text.split("\n\n")
        if paragraph.strip()
    ]


def _model_for(spec):
    """The model this verb makes — the page needs its queryset."""
    return spec.creates


#: Kinds the menu lists out in full underneath their own row.
#:
#: A slot type is a place other content is filed under rather than a
#: thing in its own right, so what an author is after is nearly always
#: one particular slot type — the Skill Tree one, the Gang Legacy one —
#: and going by way of the listing to find it is a step for nothing.
#: There are few enough to read at a glance, which is what makes this
#: affordable; a kind with hundreds of rows would bury the menu it is
#: part of.
INDEX_LISTS = ("slot-type",)


def _listed_beneath(kind, model):
    """The rows the menu prints under a kind, in the kind's own order."""
    if kind not in INDEX_LISTS:
        return []
    rows = model.objects.all()
    hint = LEAF_LISTING_HINTS.get(kind)
    if hint is not None:
        rows = hint(rows)
    describe = LEAF_DESCRIBE.get(kind)
    return [
        {
            "label": str(row),
            "url": reverse("authoring-detail", args=[kind, row.pk]),
            "notes": describe(row) if describe else [],
        }
        for row in rows
    ]


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
                "rows": _listed_beneath(kind, model),
            }
        )
    families = [
        {"label": family.label, "kinds": sorted(kinds, key=lambda k: k["verbose_name"])}
        for family, kinds in grouped.items()
        if kinds
    ]
    return render(request, "authoring/index.html", {"families": families})


#: The documentation the authoring pages carry: url slug → (title, the
#: markdown file beside this module, the line the index reads). A page is
#: prose in a file and a row here; there is no other machinery.
DOCS = {
    "concepts": (
        "Core Concepts",
        "concepts.md",
        "What each kind is: one card per kind, with its fields and behaviour.",
    ),
    "recipes": (
        "Recipes",
        "recipes.md",
        "Step-by-step walkthroughs of whole rulebook setups.",
    ),
}


@staff_member_required
def docs(request):
    """What there is to read, and what each one holds."""
    return render(
        request,
        "authoring/docs.html",
        {
            "pages": [
                {"slug": slug, "title": title, "description": description}
                for slug, (title, _, description) in DOCS.items()
            ]
        },
    )


@staff_member_required
def doc(request, slug):
    """One documentation page: its markdown file, rendered.

    The prose lives beside this module, so a page is edited as prose,
    reviewed as prose, and never drifts from what the page shows. The
    cookbook is written for authors — the things to create and how to
    join them; the concepts page states what each kind is.
    """
    from pathlib import Path

    if slug not in DOCS:
        raise Http404(f"No documentation page for {slug!r}")
    title, filename, _ = DOCS[slug]
    source = (Path(__file__).parent / filename).read_text(encoding="utf-8")
    rendered, contents = _recipe_page(source)
    # Markdown committed to this repo, through the same renderer the kind
    # help goes through: nothing a reader writes reaches this page.
    document = mark_safe(rendered)  # nosec B703 B308 - our own markdown
    return render(
        request,
        "authoring/doc.html",
        {"title": title, "document": document, "contents": contents},
    )


def recipes(request):
    """A second address for the cookbook, kept because links to it are
    out in the world: it lands on the documentation page."""
    return redirect("authoring-doc", slug="recipes", permanent=True)


def _recipe_page(source):
    """A documentation file rendered for its page, plus a table of contents.

    Each file opens with its own title so it reads whole as markdown; the
    page supplies that heading itself, so the duplicate is dropped here.
    Every remaining heading gets an anchor and links to itself, and the
    contents nest the h3s under their h2 — one walk of the token stream
    answers both, which is what keeps the sidebar and the anchors from
    ever disagreeing.
    """
    from django.utils.text import slugify
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(source)
    if tokens and tokens[0].type == "heading_open" and tokens[0].tag == "h1":
        tokens = tokens[3:]

    taken = set()
    contents = []
    for position, token in enumerate(tokens):
        if token.type != "heading_open" or token.tag not in ("h2", "h3"):
            continue
        title = tokens[position + 1].content
        stem = slugify(title) or "section"
        slug, extra = stem, 2
        while slug in taken:
            slug, extra = f"{stem}-{extra}", extra + 1
        taken.add(slug)
        token.attrSet("id", slug)
        entry = {"title": title, "slug": slug, "children": []}
        if token.tag == "h3" and contents:
            contents[-1]["children"].append(entry)
        else:
            contents.append(entry)

    # The heading is its own link: click it and the address bar holds a
    # way back to this spot. The anchor wraps the words, opened after
    # the tag and closed before it — the close rule reads its opener two
    # tokens back (open, inline, close is the shape a heading parses to).
    def heading_open(self, tokens, idx, options, env):
        drawn = self.renderToken(tokens, idx, options, env)
        slug = tokens[idx].attrGet("id")
        return f'{drawn}<a href="#{slug}">' if slug else drawn

    def heading_close(self, tokens, idx, options, env):
        drawn = self.renderToken(tokens, idx, options, env)
        return f"</a>{drawn}" if tokens[idx - 2].attrGet("id") else drawn

    md.add_render_rule("heading_open", heading_open)
    md.add_render_rule("heading_close", heading_close)
    return md.renderer.render(tokens, md.options, {}), contents


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
    for row in _rows(model, kind):
        naming, notes = _naming(row), describe(row)
        rows.append(
            {
                **naming,
                "pk": row.pk,
                "kind": kind,
                "url": reverse("authoring-detail", args=[kind, row.pk]),
                "notes": notes,
                # What the in-page search reads. Lowercased here so the
                # comparison is a plain substring test in the browser.
                # Everything the row shows is in it: an author who can
                # only remember the qualifier, or a word from the help,
                # finds the row by typing that.
                "search": " ".join(
                    [naming["label"], naming["qualifier"], *notes, naming["help"]]
                ).lower(),
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
        form = form_class(request.POST, request.FILES)
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
            except ValidationError as refused:
                # A verb that turns something away in words is turning
                # away something an author typed — two boxes that make no
                # sense together, most often. The words belong on the form
                # they were typed into, not on an error page.
                form.add_error(None, refused)
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
def _hire_options_context(request, kind, thing, drawn):
    """The two option sections as one drawn block, grouped as a hire
    offers them: each set under a heading in the rulebook's own words
    ("one of the following", "any of the following"), options beneath
    it, and an add control per set.

    The option form's set is decided by which control was clicked — it
    rides the URL (``?set=``) into the form as a hidden field, so the
    form itself never asks. A refusal on that hidden field would be
    invisible, so it is said again as a form-wide error.
    """
    by_act = {section["act"]: section for section in drawn}
    option_section = by_act.get("option")
    sets_section = by_act.get("option-set")
    if option_section is None or sets_section is None:
        return None

    def named_set(pk):
        """The set ``pk`` names on *this* carrier, else None — a stray
        or malformed pk (a hand-edited URL) is nobody's set, not an
        error page."""
        if not pk:
            return None
        try:
            return thing.option_groups.filter(pk=pk).first()
        except ValidationError:
            return None

    form = option_section["form"]
    if form.is_bound:
        picked = form.data.get("group") or ""
        for error in form.errors.get("group", []):
            form.add_error(None, error)
    else:
        picked = request.GET.get("set", "")
    joins = named_set(picked)
    if not form.is_bound and joins is not None:
        form.initial["group"] = joins.pk
    form.fields["group"].widget = forms.HiddenInput()

    def row(option):
        label, _ = _describe_option(option)
        brings = ", ".join(
            _label_for(member.assignable) for member in _brought_by(option)
        )
        return {
            "label": label,
            "price": f"+{option.default_set.price}cr",
            "brings": brings or "nothing",
            "standard": False,
            # Where a second item joins this option — an option bringing
            # a claw and a baton is one option, not two.
            "add_url": reverse("authoring-option-add", args=[option.pk]),
            "remove_url": reverse("authoring-option-remove", args=[option.pk]),
        }

    grouped = [
        (group, [row(o) for o in opts]) for group, opts in thing.grouped_offers()
    ]
    # A set with no options yet still needs its heading and its add
    # control on the page, or the author who just made it has nowhere
    # to go next.
    seen = {group.pk for group, _ in grouped if group is not None}
    grouped += [
        (group, []) for group in thing.option_groups.all() if group.pk not in seen
    ]

    blocks = []
    for group, rows in grouped:
        if group is None and not rows:
            # No main set is not an empty main set: the hire simply
            # offers no pick-one. The add form below still defaults to
            # it, so the way in stays open.
            continue
        choose = group.choose if group else "one"
        if choose == "one" and rows:
            rows[0]["standard"] = True
        blocks.append(
            {
                "is_main": group is None,
                "choose": choose,
                "how": HOW_A_SET_IS_PICKED[choose],
                "label": group.name if group else "",
                "options": rows,
                # ?add=option (or ?set=) is what tells the redrawn page
                # to arrive with the add-option form open — the control
                # clicked is the state, and it lives in the URL.
                "add_url": (
                    f"{request.path}?set={group.pk}#add-option"
                    if group
                    else f"{request.path}?add=option#add-option"
                ),
                "remove_url": (
                    reverse("authoring-option-set-remove", args=[group.pk])
                    if group
                    else ""
                ),
            }
        )

    how = HOW_A_SET_IS_PICKED
    acquired = "hiring" if kind == "profile" else "buying"
    return {
        "title": "Hire options" if kind == "profile" else "Options when bought",
        "description": (
            f"What a player picks when {acquired} this. "
            "Each option's price is added to the base price."
        ),
        "nothing_yet": (
            f"{'Hired' if kind == 'profile' else 'Bought'} the same way every "
            "time. Add an option to offer an alternative."
        ),
        "groups": blocks,
        "option": option_section,
        "sets": sets_section,
        # The forms fold closed; a click that leads to one — or a
        # submission refused with errors — arrives with it open.
        "option_open": (
            form.is_bound or bool(picked) or request.GET.get("add") == "option"
        ),
        "sets_open": (sets_section["form"].is_bound or request.GET.get("add") == "set"),
        "joins_text": (
            f"This option joins {joins.name} — {how[joins.choose]}."
            if joins
            else (
                "This option joins the main pick — one of the following; "
                "the first option is what you get if the player doesn't choose."
            )
        ),
    }


def _prose_addresses(prose):
    """The prose, with every sentence pointed at its subject's page.

    The compiler knows no URLs, so each sentence carries its subject's
    identity instead — ``(model label, pk)`` — and this turns identities
    into addresses: a modifier's page, or the kind's own detail page for
    anything the authoring surface draws one for. A subject with no page
    of its own leaves the sentence as plain words, which is an answer
    rather than a gap.
    """
    from n26.library.prose import Prose

    slugs = {
        _model_for(specs()[verb])._meta.label_lower: slug
        for slug, verb in LEAF_KINDS.items()
    }

    def address(sentence):
        if not sentence.key:
            return sentence
        label, pk = sentence.key
        if label == "library.modifier":
            return sentence.at(reverse("authoring-modifier", args=[pk]))
        # A firing line is a part of its weapon rather than a kind, so
        # its page is not one of the kind pages the slugs cover.
        if label == "library.weaponprofile":
            return sentence.at(reverse("authoring-weapon-profile", args=[pk]))
        if label in slugs:
            return sentence.at(reverse("authoring-detail", args=[slugs[label], pk]))
        return sentence

    return Prose(
        referenced_by=tuple(address(s) for s in prose.referenced_by),
        does=tuple(address(s) for s in prose.does),
        assigned_to=prose.assigned_to,
    )


#: Where a kind's page stands under another's, so the bar leads back to
#: it. A picklist is made on its slot type's page and belongs to it for
#: good — the field is settled once and never offered again, so without
#: this the page never names the type at all.
DETAIL_PARENTS = {
    "picklist": ("slot-type", "slot_type"),
    # The same fact on the other two pages of the family: slot_type is
    # settled when the thing is made and dropped from the edit form, so
    # the breadcrumb is where a reader learns it.
    "pickable": ("slot-type", "slot_type"),
    "slot": ("slot-type", "slot_type"),
}


#: Rows a page names but does not own: things made elsewhere that point
#: at this one. Read-only, so each row is a name and a way to it; the
#: thing itself is corrected where it was made.
DETAIL_RELATED = {
    "picklist": {
        "kind": "slot",
        "title": "Slots drawing on this picklist",
        "description": "Every slot that uses this picklist.",
        "nothing_yet": ("No slot draws on this picklist yet, so nothing offers it."),
        "rows": lambda picklist: picklist.slots.select_related("picklist"),
        "notes": _slot_terms,
    },
}


def _parent_of(kind, thing):
    """The thing this one is filed under, for the bar that says so."""
    filed_under = DETAIL_PARENTS.get(kind)
    if filed_under is None:
        return None
    parent_kind, attribute = filed_under
    return {"kind": parent_kind, "thing": getattr(thing, attribute)}


def _related_sections(kind, thing):
    """The rows this page names but does not own, each with a way to it."""
    described = DETAIL_RELATED.get(kind)
    if described is None:
        return []
    return [
        {
            "title": described["title"],
            "description": described["description"],
            "nothing_yet": described["nothing_yet"],
            "rows": [
                {
                    "label": _label_for(row),
                    "notes": described["notes"](row),
                    "url": reverse(
                        "authoring-detail", args=[described["kind"], row.pk]
                    ),
                }
                for row in described["rows"](thing)
            ],
        }
    ]


@staff_member_required
def detail(request, kind, pk):
    """One thing, and the parts added to it over time.

    The shape everything above the leaves needs: a weapon and its
    profiles today; a collection and its sections, a carrier and its
    modifiers, next. The part form is spec-generated like any other,
    and where the part carries a statline the page composes one beside
    it — that form's fields come from the owner's statline type, which
    no spec can know. A thing that carries a statline of its own gets
    the same form inside its edit form, so a fighter's characteristics
    are typed where its name and price are.

    A page may carry more than one section of parts: a weapon has firing
    lines of its own *and*, like every assignable, can come with things.
    Each section says which it is, so a post reaches the form that was
    clicked; the one saying nothing is the kind's own.

    Kinds in ``DETAIL_VIEWS`` have a page of their own shape instead —
    a collection's page previews what its definition means right now,
    and draws none of these sections.
    """
    own_view = DETAIL_VIEWS.get(kind)
    if own_view is not None:
        return own_view(request, pk)
    spec = _spec_for(kind)
    model = _model_for(spec)
    thing = get_object_or_404(model, pk=pk)
    sections = _part_sections(kind)
    with_modifiers = _carries_modifiers(kind)

    composer = None
    act = request.POST.get("act", "")

    def adds_elsewhere(one):
        """Where this section's parts are added, or nothing — a route
        name for every row of the kind, a callable deciding row by row."""
        where = one.get("adds")
        if callable(where):
            return where(thing)
        return reverse(where, args=[thing.pk]) if where else ""

    # A section whose add form lives elsewhere has no form here to post
    # to, so it is not a candidate however the act reads.
    posted_to = next(
        (
            one
            for one in sections
            if one.get("act", "") == act and not adds_elsewhere(one)
        ),
        None,
    )
    if (
        request.method == "POST"
        and act
        and with_modifiers
        and act != "edit"
        and posted_to is None
    ):
        response, composer = _modifier_action(request, kind, thing, act)
        if response is not None:
            return response

    edit_class = generate_form(spec)
    # A thing that can own a statline is edited with its characteristics
    # in the same form: one click of Save writes both, or neither.
    statline_class = _statline_editor_for(thing)
    if request.method == "POST" and act == "edit":
        edit_form = _narrowed_for_editing(
            kind, thing, edit_class.opened_on(thing, request.POST, request.FILES)
        )
        statline_edit = (
            statline_class.opened_on(thing, request.POST) if statline_class else None
        )
        if edit_form.is_valid() and (statline_edit is None or statline_edit.is_valid()):
            try:
                with transaction.atomic():
                    edit_form.apply_to(thing)
                    if statline_edit is not None:
                        statline_edit.save_every_value(thing)
            except ValidationError as refused:
                # The row's own sense check turned the edit away in words;
                # they belong on the form the values were typed into.
                edit_form.add_error(None, refused)
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
        edit_form = _narrowed_for_editing(kind, thing, edit_class.opened_on(thing))
        statline_edit = statline_class.opened_on(thing) if statline_class else None

    drawn = []
    for section in sections:
        part_spec = specs()[section["verb"]]
        part_model = _model_for(part_spec)
        # A section that adds its parts elsewhere draws a way there
        # instead of a form, so neither form is built at all.
        elsewhere = adds_elsewhere(section)
        form_class = None if elsewhere else generate_form(part_spec)
        statline_class = (
            statline_form_for(thing.statline_type)
            if section["statline"] and thing.statline_type and not elsewhere
            else None
        )
        if elsewhere:
            form = statline_form = None
        elif section is posted_to and request.method == "POST":
            form = form_class(request.POST, request.FILES, carrier=thing)
            statline_form = statline_class(request.POST) if statline_class else None
            forms_valid = form.is_valid() and (
                statline_form is None or statline_form.is_valid()
            )
            if forms_valid:
                try:
                    with transaction.atomic():
                        part = part_spec.verb(thing, **form.verb_data())
                        if statline_form is not None:
                            statline_form.save(part)
                except ValidationError as refused:
                    # A verb turning a part away in words says something
                    # about what was typed, so it is said on the form.
                    form.add_error(None, refused)
                else:
                    said, _ = section["describe"](part)
                    messages.success(request, f"Added {said}.")
                    return redirect("authoring-detail", kind=kind, pk=pk)
        else:
            form = form_class(carrier=thing)
            statline_form = statline_class() if statline_class else None
        removes = section.get("removes")
        opens = section.get("opens")

        pairs = []
        for part in section.get("parts_hint", lambda parts: parts)(
            getattr(thing, section["parts"]).all()
        ):
            label, notes = section["describe"](part)
            pairs.append(
                (
                    part,
                    {
                        "label": label,
                        "notes": notes,
                        # Blank for a kind whose parts have no page of their
                        # own; the row's name is then plain words.
                        "href": _opens_url(opens, part),
                        # Blank for a kind whose parts cannot be taken off
                        # here; the row simply draws no control.
                        "remove_url": reverse(removes, args=[part.pk])
                        if removes
                        else "",
                    },
                )
            )
        arrange = section.get("arrange")
        parts = arrange(pairs) if arrange else [drawn for _part, drawn in pairs]

        def worded(value):
            return value(thing) if callable(value) else value

        part_name = str(worded(section.get("part_name", part_model._meta.verbose_name)))
        drawn.append(
            {
                "act": section.get("act", ""),
                "part_verbose_name": part_name,
                # "Add an option", "Add a firing line". Worked out rather
                # than written beside each name, so a kind renamed on its
                # model never leaves the heading ungrammatical.
                "part_article": _article_for(part_name),
                "part_verbose_name_plural": worded(
                    section.get("parts_label", part_model._meta.verbose_name_plural)
                ),
                "parts_description": worded(section.get("parts_description", "")),
                "nothing_yet": section.get("nothing_yet", ""),
                # Said beside the add form, so an author knows how far
                # the addition travels before committing it. Only the
                # built-ins section: a new option founds a set nobody
                # holds yet, so there is nothing to say there.
                "reach_said": (
                    _built_in_reach_said(thing)
                    if section.get("act") == "built_in"
                    else ""
                ),
                "part_help": kind_help(part_model),
                "wants_statline": section["statline"],
                "parts": parts,
                "form": form,
                "statline_form": statline_form,
                # Blank for a section adding its parts in a form here;
                # the page then draws that form rather than a way out.
                "add_url": elsewhere or "",
                # A further way in for parts the form cannot offer —
                # blank for every section that has none.
                "door_url": section.get("door", lambda thing: "")(thing),
                "door_label": section.get("door_label", ""),
            }
        )

    hire_options = None
    if _offers_options(kind):
        hire_options = _hire_options_context(request, kind, thing, drawn)
        drawn = [s for s in drawn if s["act"] not in ("option", "option-set")]

    from n26.library.models.assignable import Assignable
    from n26.library.prose import prose_for

    # The foundation kinds — a stat, a statline shape — are not
    # assignables: nothing carries them, nothing is assigned them, and
    # the compiler reads both. Their pages simply have no column.
    said = _prose_addresses(prose_for(thing)) if isinstance(thing, Assignable) else None

    return render(
        request,
        "authoring/detail.html",
        {
            "kind": kind,
            "thing": thing,
            "parent": _parent_of(kind, thing),
            "related_sections": _related_sections(kind, thing),
            "prose": said,
            "verbose_name": model._meta.verbose_name,
            "verbose_name_plural": model._meta.verbose_name_plural,
            "edit_form": edit_form,
            "statline_cells": statline_edit.cells() if statline_edit else None,
            "part_sections": drawn,
            "hire_options": hire_options,
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
        dropping = _dropped_condition(request)
        if dropping is not None:
            return _dropping_a_condition(request, dropping, attach_to=thing)
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


def _refuse_the_line(form, spec, refused):
    """Say a database refusal of a firing line on the box it is about.

    Two constraints can refuse the form that writes a line, and each is
    said where the author was typing. A weapon has one line that *is*
    the weapon, so a second line cannot be left nameless; and exclusive
    means never offered at the Trading Post, so an exclusive line cannot
    also carry a Trade Point price. The two pages writing a line — the
    one that adds and the one that corrects — say the same words,
    because it is the same refusal about the same box.
    """
    if "exclusive_has_no_tp" in str(refused):
        form.add_error(
            "trade_point_price",
            "An exclusive item is never offered at the Trading "
            "Post, so it cannot carry a Trade Point price. "
            "Clear one or the other.",
        )
    else:
        form.add_error(
            spec.identity,
            "This weapon already has its own unnamed line. Give this profile a name.",
        )


@staff_member_required
def weapon_profile(request, pk):
    """One firing line, on a page of its own.

    A weapon's page lists its lines and adds new ones; correcting one
    happens here, where there is room for the whole of it — the name and
    the price, the characteristics in their own boxes, and the traits as
    a set. The form is the spec-generated one that *adds* a line, opened
    on a line that already exists, so the two cannot come to ask for
    different things.

    Editing means something different by an empty box than adding does,
    so the characteristics are written with every value the form drew,
    blanks included: a line whose Strength was typed by mistake can be
    emptied again.
    """
    from n26.library.models import WeaponProfile
    from n26.library.prose import prose_for

    profile = get_object_or_404(WeaponProfile.objects.select_related("weapon"), pk=pk)
    spec = specs()["add_weapon_profile"]
    edit_class = generate_form(spec)
    statline_class = _statline_editor_for(profile)

    if request.method == "POST":
        edit_form = edit_class.opened_on(profile, request.POST, request.FILES)
        statline_edit = (
            statline_class.opened_on(profile, request.POST) if statline_class else None
        )
        if edit_form.is_valid() and (statline_edit is None or statline_edit.is_valid()):
            try:
                with transaction.atomic():
                    edit_form.apply_to(profile)
                    if statline_edit is not None:
                        statline_edit.save_every_value(profile)
            except ValidationError as refused:
                edit_form.add_error(None, refused)
            except IntegrityError as refused:
                _refuse_the_line(edit_form, spec, refused)
            else:
                messages.success(request, f"Saved {profile}.")
                return redirect("authoring-weapon-profile", pk=pk)
    else:
        edit_form = edit_class.opened_on(profile)
        statline_edit = statline_class.opened_on(profile) if statline_class else None

    return render(
        request,
        "authoring/weapon_profile.html",
        {
            # The bar stands in Weapons: a firing line has no listing of
            # its own, and the weapon is where its reader came from.
            "kind": "weapon",
            "thing": profile,
            "label": _label_for(profile),
            "weapon": profile.weapon,
            "weapons_plural": str(profile.weapon._meta.verbose_name_plural),
            "verbose_name": str(WeaponProfile._meta.verbose_name),
            "verbose_name_plural": str(WeaponProfile._meta.verbose_name_plural),
            "edit_form": edit_form,
            "statline_cells": statline_edit.cells() if statline_edit else None,
            "prose": _prose_addresses(prose_for(profile)),
        },
    )


@staff_member_required
def weapon_profile_add(request, pk):
    """One more firing line for a weapon, at an address of its own.

    Addressed by the weapon, there being no line yet to name. The form
    is the spec-generated one that adds a line, with the characteristics
    beside it in whatever shape the weapon's statline type sets — a form
    no spec can know, since its fields come from content.

    A page rather than a form under the weapon's listing of lines,
    because a line is a form and a whole statline both, and the weapon's
    own fields sit above them on that page. Adding means nothing by an
    empty box: a line typed with every characteristic blank is a line
    with no statline, not a statline of blanks.
    """
    from n26.library.models import Weapon, WeaponProfile

    weapon = get_object_or_404(Weapon, pk=pk)
    back = reverse("authoring-detail", args=["weapon", weapon.pk])
    spec = specs()["add_weapon_profile"]
    form_class = generate_form(spec)
    statline_class = (
        statline_form_for(weapon.statline_type) if weapon.statline_type else None
    )

    if request.method == "POST":
        form = form_class(request.POST, request.FILES, carrier=weapon)
        statline_form = statline_class(request.POST) if statline_class else None
        if form.is_valid() and (statline_form is None or statline_form.is_valid()):
            try:
                with transaction.atomic():
                    profile = spec.verb(weapon, **form.verb_data())
                    if statline_form is not None:
                        statline_form.save(profile)
            except IntegrityError as refused:
                _refuse_the_line(form, spec, refused)
            else:
                said, _ = _describe_weapon_profile(profile)
                messages.success(request, f"Added {said}.")
                return redirect(back)
    else:
        form = form_class(carrier=weapon)
        statline_form = statline_class() if statline_class else None

    return render(
        request,
        "authoring/weapon_profile_add.html",
        {
            # The bar stands in Weapons, as the line's own page does:
            # a firing line has no listing of its own.
            "kind": "weapon",
            "weapon": weapon,
            "weapons_plural": str(weapon._meta.verbose_name_plural),
            "verbose_name": str(WeaponProfile._meta.verbose_name),
            "verbose_name_plural": str(WeaponProfile._meta.verbose_name_plural),
            "part_help": kind_help(WeaponProfile),
            "form": form,
            "statline_cells": statline_form.cells() if statline_form else None,
            "back": back,
        },
    )


@staff_member_required
def weapon_profile_delete(request, pk):
    """The question asked before a firing line leaves its weapon.

    A line is a part of its weapon rather than an authored kind, so the
    generic delete page — which reads a kind out of the address — cannot
    ask for one. This is the same question at an address of its own.

    Deleting is for the unused, and the act itself is the one every
    delete page performs (``_deleting``): a line a gang holds, a list
    offers, or a hire comes with as an ammo type is refused in words,
    and nothing half-happens.

    The characteristics go with the line. The weapon and its other lines
    are untouched, and a weapon with none is a legitimate thing to have
    — an author part-way through correcting a table.
    """
    from n26.library.models import WeaponProfile

    profile = get_object_or_404(WeaponProfile.objects.select_related("weapon"), pk=pk)
    weapon = profile.weapon
    back = reverse("authoring-detail", args=["weapon", weapon.pk])

    if request.method == "POST":
        return redirect(back if _deleting(request, profile) else request.path)

    return render(
        request,
        "authoring/weapon_profile_delete.html",
        {
            "kind": "weapon",
            "thing": profile,
            "label": _label_for(profile),
            "weapon": weapon,
            "weapons_plural": str(weapon._meta.verbose_name_plural),
            "verbose_name": str(WeaponProfile._meta.verbose_name),
            "back": back,
        },
    )


def _back_to(holders):
    """Where the built-in page's way out leads.

    The one thing holding the set when exactly one does, which is where
    the reader came from. With several holders there is no single page
    to return to, so the way out is the library's front door.
    """
    pages = [holder for holder in holders if holder["kind"]]
    if len(pages) == 1:
        return reverse("authoring-detail", args=[pages[0]["kind"], pages[0]["pk"]])
    return reverse("authoring-index")


@staff_member_required
def built_in_remove(request, pk):
    """The question asked before a built-in is taken off, at its own address.

    What goes is the *membership*. The weapon, skill or equipment list
    named stays in the library and everything else holding it is
    untouched — worth saying before anything happens, because a control
    beside a weapon's name reads as one that deletes weapons.

    A page rather than a control in the row, because two things decide
    what the act means and neither can be read off the row: a set of
    defaults may be held by more than one thing, and a gun takes its
    ammo lines with it. GET asks and changes nothing; the POST from
    this page is the act.
    """
    from n26.library import authoring
    from n26.library.models import DefaultAssignment

    # An archived member is already off the set, so its address has
    # nothing left to ask about.
    member = get_object_or_404(
        DefaultAssignment.objects.select_related(
            "default_set", *DefaultAssignment.ASSIGNABLE_FIELDS
        ),
        pk=pk,
        archived=False,
    )
    holders = _holders_of(member.default_set)
    back = _back_to(holders)

    if request.method == "POST":
        said = _label_for(member.assignable)
        with transaction.atomic():
            authoring.remove_default_member(member)
        messages.success(
            request,
            f"Took {said} out of {member.default_set.name}. "
            f"The {said} itself is untouched.",
        )
        return redirect(back)

    riders = member.dependent_members.select_related("weapon_profile__weapon")
    return render(
        request,
        "authoring/built_in_remove.html",
        {
            "thing": member,
            "label": _label_for(member.assignable),
            "kind_name": str(member.assignable._meta.verbose_name),
            "set_name": member.default_set.name,
            "holders": holders,
            "shared": len(holders) > 1,
            "riders": [_label_for(rider.assignable) for rider in riders],
            "back": back,
        },
    )


def _priced_profile_rows(weapon, riding_pks=frozenset()):
    """One weapon's own priced lines, as an adding page lists them.

    Free lines are not offered: they arrive with the gun on their own,
    which the page says instead. ``riding_pks`` marks the lines the set
    already brings for this gun, so an author sees what is there without
    being refused a deliberate second copy.
    """
    rows = []
    for line in _weapon_parts(weapon.profiles.filter(price__gt=0)):
        label, notes = _describe_weapon_profile(line)
        if line.pk in riding_pks:
            notes.append("already comes with this gun")
        rows.append({"pk": line.pk, "label": label, "notes": notes})
    return rows


@staff_member_required
def built_in_profiles(request, pk):
    """One more of a gun's lines built in beside it, at the gun
    member's own address.

    The address names the weapon *member*, not the weapon: a set may
    bring the same gun twice, and which of them a line lands under is
    exactly what this page settles. Choosing a line writes the member
    anchored to this gun; the listing draws it under the gun by that
    anchor, in the order the lines were added.
    """
    from n26.core.propagation import reach_of
    from n26.library import authoring
    from n26.library.models import DefaultAssignment

    member = get_object_or_404(
        DefaultAssignment.objects.select_related("default_set", "weapon"),
        pk=pk,
        archived=False,
        weapon__isnull=False,
    )
    weapon = member.weapon
    holders = _holders_of(member.default_set)
    back = _back_to(holders)

    if request.method == "POST":
        line = get_object_or_404(
            weapon.profiles.filter(price__gt=0), pk=request.POST.get("weapon_profile")
        )
        # The verb's end-of-set position stands: the listing nests lines
        # by their anchor, so within one gun they read in the order they
        # were added.
        with transaction.atomic():
            added = authoring.add_default_member(
                member.default_set,
                line,
                gun_member=member,
                pack=member.default_set.pack,
            )
        messages.success(
            request,
            f"{member.default_set.name} now brings {added.assignable} "
            f"with its {weapon}.",
        )
        return redirect(back)

    riding = set(
        DefaultAssignment.objects.filter(gun_member=member, archived=False).values_list(
            "weapon_profile_id", flat=True
        )
    )
    return render(
        request,
        "authoring/built_in_profiles.html",
        {
            "weapon": weapon,
            "rows": _priced_profile_rows(weapon, riding),
            "set_name": member.default_set.name,
            "holders": holders,
            "back": back,
            "picker": None,
            "landing_said": f"Each line lands under this {weapon}.",
            "reach_said": _reach_said(
                reach_of(member.default_set), "a line added here"
            ),
        },
    )


@staff_member_required
def set_profiles(request, pk):
    """A weapon's line added to a set that does not bring the weapon —
    the two-step door an option set uses to arm a gun the built-ins
    bring.

    The weapon is picked first and carried in the address, so the page
    works reloaded and without scripting; its priced lines follow. The
    member written here names no gun of the set's own — unless the set
    does bring the weapon, in which case the verb settles the anchor
    exactly as an import would, refusing where the set brings it twice.
    """
    from n26.core.propagation import reach_of
    from n26.library import authoring
    from n26.library.models import DefaultAssignmentSet, Weapon

    default_set = get_object_or_404(DefaultAssignmentSet, pk=pk)
    holders = _holders_of(default_set)
    back = _back_to(holders)
    reach_said = _reach_said(reach_of(default_set), "a line added here")

    weapon = None
    named = request.POST.get("weapon") or request.GET.get("weapon")
    if named:
        weapon = get_object_or_404(Weapon, pk=named)

    if request.method == "POST" and weapon is not None:
        line = get_object_or_404(
            weapon.profiles.filter(price__gt=0), pk=request.POST.get("weapon_profile")
        )
        try:
            with transaction.atomic():
                added = authoring.add_default_member(
                    default_set, line, pack=default_set.pack
                )
        except ValidationError as refused:
            for said in refused.messages:
                messages.error(request, said)
            return redirect(f"{request.path}?weapon={weapon.pk}")
        messages.success(request, f"{default_set.name} now brings {added.assignable}.")
        return redirect(back)

    if weapon is None:
        return render(
            request,
            "authoring/built_in_profiles.html",
            {
                "weapon": None,
                "rows": [],
                "set_name": default_set.name,
                "holders": holders,
                "back": back,
                "picker": Weapon.objects.all(),
                "landing_said": "",
                "reach_said": reach_said,
            },
        )

    # The verb's own statement of the match, so the page's sentence and
    # the refusal underneath it cannot come to disagree.
    brings = authoring.gun_members_bringing(default_set, weapon).count()
    if brings == 0:
        landing_said = (
            f"{default_set.name} does not bring a {weapon}, so each line "
            f"will ride whatever {weapon} its acquirer already holds."
        )
    elif brings == 1:
        landing_said = f"Each line lands under the {weapon} this set brings."
    else:
        landing_said = (
            f"{default_set.name} brings a {weapon} {brings} times, so a "
            f"line added here will be refused — add it from one gun's own "
            f"row instead."
        )
    return render(
        request,
        "authoring/built_in_profiles.html",
        {
            "weapon": weapon,
            "rows": _priced_profile_rows(weapon),
            "set_name": default_set.name,
            "holders": holders,
            "back": back,
            "picker": None,
            "landing_said": landing_said,
            "reach_said": reach_said,
        },
    )


def _deleting(request, thing):
    """Take a row out of the library, or say what is standing in the way.

    ``True`` when the row went. On a refusal the words are already on
    the page and the caller sends the reader back to the question. The
    two delete pages differ in where they lead and in nothing else: what
    a refusal says is one sentence, said in one place.

    Deleting is for the unused, and the database is the authority — it
    refuses first, and its own list of protectors is what the words fall
    back on. What is standing in the way is otherwise read through the
    one reference reader (``n26.library.references``), the same one the
    reach column reads, so a page cannot come to name a different set of
    things from the one that explains where the row is used.
    """
    from django.db.models import ProtectedError

    from n26.library import authoring
    from n26.library.references import named

    said = _label_for(thing)
    try:
        with transaction.atomic():
            authoring.delete_content(thing)
    except ProtectedError as refusal:
        held_by = [
            reference.row for reference in references_to(thing) if reference.protects
        ] or list(refusal.protected_objects)
        naming = ", ".join(named(row) for row in held_by[:3])
        more = f" and {len(held_by) - 3} more" if len(held_by) > 3 else ""
        messages.error(
            request,
            f"{said} is still in use — {naming}{more} point at it. "
            "Remove those first; content that has been used is "
            "history, not clutter.",
        )
        return False
    messages.success(request, f"Deleted {said}.")
    return True


def _carrier_page(carrier):
    """The page of the thing an option or a set of options belongs to."""
    kind = _kind_slugs().get(type(carrier))
    if kind is None:
        return reverse("authoring-index")
    return reverse("authoring-detail", args=[kind, carrier.pk])


@staff_member_required
def thing_delete(request, kind, pk):
    """The question asked before an authored row leaves the library.

    Deleting is for the unused: the database protects every reference —
    a gang's assignment, a list's entry, an option's kit — so a row
    anybody relies on is refused, in words, and nothing half-happens.
    A page rather than a prompt, as every destructive act here is. The
    act itself is ``_deleting``, shared with the pages that delete
    something which is not an authored kind.
    """
    spec = _spec_for(kind)
    model = _model_for(spec)
    thing = get_object_or_404(model, pk=pk)
    back = reverse("authoring-detail", args=[kind, pk])

    if request.method == "POST":
        if _deleting(request, thing):
            return redirect("authoring-leaf", kind=kind)
        return redirect(request.path)

    return render(
        request,
        "authoring/thing_delete.html",
        {
            "thing": thing,
            "kind": kind,
            "label": _label_for(thing),
            "verbose_name": model._meta.verbose_name,
            "back": back,
        },
    )


@staff_member_required
def option_add(request, pk):
    """One more thing inside an option, at an address of its own.

    An option that hands over two items — "a claw and a baton" — is one
    option bringing both, so the second item joins the first option's
    set rather than becoming an option of its own. A page rather than a
    row control because the picker is a whole form: a kind, the row of
    that kind, and whatever attaching it asks for.
    """
    from n26.core.propagation import reach_of
    from n26.library.models import Option

    option = get_object_or_404(
        Option.objects.select_related(
            "group", "default_set", *Option.ASSIGNABLE_FIELDS
        ),
        pk=pk,
    )
    carrier = option.carrier
    back = _carrier_page(carrier)
    spec = specs()["add_default_member"]
    form_class = generate_form(spec)

    if request.method == "POST":
        form = form_class(request.POST, request.FILES, carrier=carrier)
        if form.is_valid():
            with transaction.atomic():
                member = spec.verb(option.default_set, **form.verb_data())
            messages.success(
                request, f"{option.name} now also brings {member.assignable}."
            )
            return redirect(back)
    else:
        form = form_class(carrier=carrier)

    return render(
        request,
        "authoring/option_add.html",
        {
            "thing": option,
            "label": option.name,
            "carrier": carrier,
            "brings": [_label_for(member.assignable) for member in _brought_by(option)],
            # Held only by the carriers that took this option, so the
            # sentence counts choosers rather than every use of the thing.
            "reach_said": _reach_said(
                reach_of(option.default_set), "anything added here"
            ),
            "form": form,
            "back": back,
            "profiles_url": reverse(
                "authoring-set-profiles", args=[option.default_set_id]
            ),
        },
    )


@staff_member_required
def option_remove(request, pk):
    """The question asked before an alternative is withdrawn.

    A page rather than a control in the row, because what the act
    reaches cannot be read off the row. The kit the option would have
    brought goes with it — that set was founded for this option and
    nothing else can reach it — while the weapons and skills it names
    stay in the library untouched.

    Taking the last option out of a set leaves the set empty, and taking
    every option out of the main pick makes the thing hired one way
    again. Both are said here, because both are changes to what a hire
    screen offers rather than to this row alone.
    """
    from n26.library import authoring
    from n26.library.models import Option

    option = get_object_or_404(
        Option.objects.select_related(
            "group", "default_set", *Option.ASSIGNABLE_FIELDS
        ),
        pk=pk,
    )
    carrier = option.carrier
    back = _carrier_page(carrier)

    if request.method == "POST":
        with transaction.atomic():
            authoring.stop_offering(option)
        messages.success(request, f"{carrier} no longer offers {option.name}.")
        return redirect(back)

    shared_with = [
        holder
        for holder in _holders_of(option.default_set)
        if not (
            holder["pk"] == carrier.pk and holder["how"] == "offers it as an option"
        )
    ]
    return render(
        request,
        "authoring/option_remove.html",
        {
            "thing": option,
            "label": option.name,
            "carrier": carrier,
            "set_label": option.group.name if option.group_id else "",
            "brings": [_label_for(member.assignable) for member in _brought_by(option)],
            # A set founded for this option is reached through it and
            # nothing else, so it goes when the option does. One offered
            # somewhere else as well stays, and so does everything in it.
            "shared_with": shared_with,
            "last_in_its_set": bool(option.group_id)
            and option.group.options.count() == 1,
            "back": back,
        },
    )


@staff_member_required
def option_set_remove(request, pk):
    """The question asked before a set of options is taken off.

    The options go with their set, and that is the whole reason this is
    a page: the heading says how many options a set holds and not what
    becomes of them. Loose in the main pick they would compete with the
    standard loadout instead of with each other, which is a different
    offer from the one the author wrote — so they go too.
    """
    from n26.library import authoring
    from n26.library.models import OptionGroup

    group = get_object_or_404(
        OptionGroup.objects.select_related(
            *OptionGroup.ASSIGNABLE_FIELDS
        ).prefetch_related("options__default_set"),
        pk=pk,
    )
    carrier = group.carrier
    back = _carrier_page(carrier)

    if request.method == "POST":
        said = group.name
        with transaction.atomic():
            authoring.remove_option_group(group)
        messages.success(request, f"Took {said} off {carrier}.")
        return redirect(back)

    return render(
        request,
        "authoring/option_set_remove.html",
        {
            "thing": group,
            "label": group.name,
            "carrier": carrier,
            "options": [option.name for option in group.options.all()],
            "back": back,
        },
    )


#: The formset prefix the condition chips are posted under, and the
#: management field that says how many of them there are.
CONDITION_PREFIX = "conditions"
CONDITION_TOTAL = f"{CONDITION_PREFIX}-TOTAL_FORMS"

#: The address keys the composer writes for itself. Anything else in an
#: address belongs to the page around it and is left where it is.
_COMPOSER_KEYS = ("chips", "name", "make_reusable", "scope_kind", "effect_kind")
_COMPOSER_PREFIXES = ("who-", "what-", f"{CONDITION_PREFIX}-")

#: Posted keys that describe the click rather than the form, and so
#: must not be written into an address a reader can reload.
_NOT_CARRIED = ("csrfmiddlewaretoken", "act", "drop_condition")

#: How long an address carrying a half-filled composer may get. A single
#: condition may name any number of weapons, and a request line runs into
#: server limits long before the same values would trouble a post body.
MAX_CARRIED_ADDRESS = 2000


def _carried_state(request):
    """The composer's own fields as this address carries them, or
    ``None`` where the address carries no form at all.

    A form written into the query string is what lets taking a condition
    off keep the rest: the click redirects, and everything typed arrives
    back as an ordinary GET.

    A count naming more chips than the composer will ever draw is
    shortened rather than obeyed — it comes off the address, where any
    number can be typed.
    """
    if CONDITION_TOTAL not in request.GET:
        return None
    carried = request.GET.copy()
    try:
        total = int(carried[CONDITION_TOTAL])
    except TypeError, ValueError:
        return None
    carried[CONDITION_TOTAL] = str(min(max(total, 0), MAX_CHIPS))
    return carried


def _composer_state(request, attach_to=None, bound_composer=None):
    """The composer as the URL describes it: closed, open at the named
    kinds, filled in from a form the address carries, or bound with
    errors after a refused submit. Shared by the carrier pages and the
    standalone modifiers page."""
    from n26.library.forms import ModifierComposerForm

    scope_kind = request.POST.get("scope_kind", request.GET.get("scope_kind", ""))
    effect_kind = request.POST.get("effect_kind", request.GET.get("effect_kind", ""))
    try:
        chips = max(0, int(request.GET.get("chips", 0)))
    except ValueError:
        chips = 0
    chips = min(chips, MAX_CHIPS)

    carried = _carried_state(request)
    composer = bound_composer
    if composer is None and scope_kind in specs() and effect_kind in specs():
        if carried is None:
            composer = ModifierComposerForm.unbound(
                scope_kind, effect_kind, attach_to=attach_to, chips=chips
            )
        else:
            composer = ModifierComposerForm.carried(carried, attach_to=attach_to)

    from n26.library.forms import effect_kind_cards, scope_kind_cards

    return {
        "kind_picker": ModifierComposerForm(
            initial={"scope_kind": scope_kind, "effect_kind": effect_kind}
        ),
        "composer": composer,
        "composer_scope": scope_kind,
        "composer_effect": effect_kind,
        "composer_chips": chips,
        # The two kind pickers as cards: each carries its own blurb and
        # example, what it produces or applies to (the client-side gate),
        # and — where the composer hangs on a carrier — whether it can
        # ever speak for it.
        "scope_cards": scope_kind_cards(picked=scope_kind, carrier=attach_to),
        "effect_cards": effect_kind_cards(picked=effect_kind),
        "add_condition_href": _one_more_chip(request, chips, scope_kind, effect_kind),
    }


def _dropped_condition(request):
    """Which condition chip the click was asking to remove, or ``None``
    when the submit was an ordinary one.

    A submit rather than a link, because the click must keep everything
    typed into the other chips and both panes — a link carries none of
    it. It saves nothing: taking a condition off is an edit to the form.
    """
    asked = request.POST.get("drop_condition", "")
    try:
        return int(asked)
    except TypeError, ValueError:
        return None


def _dropping_a_condition(request, index, *, attach_to=None, editing=None):
    """The answer to a "remove this condition" click, as ``(response,
    form)`` — one or the other, never both.

    The chip count is read off the address on every draw, so a click
    that only redrew the page would leave the address claiming a chip
    that is no longer on the screen, and a reload would bring it back.
    The click therefore redirects, and everything the author has typed
    rides the address with it.

    Some forms will not fit. A condition may name any number of weapons,
    and enough of them make an address longer than a server will accept;
    then the page redraws from the post instead. The chip still goes and
    nothing typed is lost — only the address stays as it was, so a
    reload of that one page brings the chip back.
    """
    from n26.library.forms import ModifierComposerForm, without_condition_chip

    surviving = without_condition_chip(request.POST, index)
    address = _carrying(request, surviving)
    if address is not None:
        return redirect(address), None
    return None, ModifierComposerForm.carried(
        surviving, attach_to=attach_to, editing=editing
    )


def _carrying(request, data):
    """This page's address with a posted composer written into it, or
    ``None`` when that address would be too long to send.

    The composer's own keys are cleared out of the query string before
    the posted ones go in: left in place, the fields of a form that has
    since lost a chip would sit alongside the fields of the form that
    replaced it, and the address would grow with every click.
    """
    params = request.GET.copy()
    for key in list(params):
        if key in _COMPOSER_KEYS or key.startswith(_COMPOSER_PREFIXES):
            del params[key]
    for key in data:
        if key not in _NOT_CARRIED:
            params.setlist(key, data.getlist(key))
    address = f"{request.path}?{params.urlencode()}"
    return address if len(address) <= MAX_CARRIED_ADDRESS else None


def _one_more_chip(request, chips, scope_kind, effect_kind):
    """This page's address with one more empty condition chip.

    Built from the whole query string rather than from the two kinds
    alone: the page is showing step two because the address says so, and
    everything else the address says — which carrier this is being
    composed for, and any form it carries — has to survive the click.
    The kinds are written in rather than read back off it, because the
    page also draws itself after a refused submit, where they arrived in
    the post body and the address has nothing in it.

    Where the address carries a form, that form's own count says how
    many chips there are and the plain count is not consulted: two
    numbers claiming to say the same thing disagree the moment one of
    them moves.
    """
    params = request.GET.copy()
    if scope_kind and effect_kind:
        params["scope_kind"] = scope_kind
        params["effect_kind"] = effect_kind
    carried = _carried_state(request)
    if carried is None:
        params["chips"] = str(min(chips + 1, MAX_CHIPS))
    else:
        params[CONDITION_TOTAL] = str(min(int(carried[CONDITION_TOTAL]) + 1, MAX_CHIPS))
    return f"?{params.urlencode()}"


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


#: A modifier that nothing holds, and one that something does. The
#: first is the interesting half: a composed modifier attached to no
#: carrier does nothing at all, so this is how an author finds the ones
#: left half-finished.
CARRIED_LABELS = (
    ("carried", "Carried by something"),
    ("uncarried", "Carried by nothing"),
)


def _facet_options(rows, key, labels):
    """The facet's options, narrowed to the values these rows actually
    hold.

    A filter offering a kind nothing on the page has is a control whose
    only effect is to empty the list. Order follows the declaration, not
    the rows, so the menu reads the same however the pack grows.
    """
    present = {row["facets"][key] for row in rows}
    return [
        {"value": value, "label": label} for value, label in labels if value in present
    ]


@staff_member_required
def modifiers(request):
    """Every modifier in the pack, with what it reaches and what it does.

    Reading and writing are separate pages, as they are for a leaf kind:
    this one lists, the New modifier button leads to the composer, and a
    row leads to its own page.

    Each row carries its own facets, so the search and the filters
    narrow what is already here rather than asking the server again —
    the page's cost is the same whichever of them is on.
    """
    from n26.library.forms import (
        _effect_choices,
        _effect_verb,
        _scope_choices,
        _scope_verb,
    )
    from n26.library.models import Modifier

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
        rows.append(
            {
                "pk": modifier.pk,
                "label": modifier.name,
                "notes": notes,
                "facets": {
                    # By the verb the author picked, not the column: one
                    # model can hold two verbs — the two gang reaches,
                    # the two placements — and a filter keyed on the
                    # column would lump each pair and filter for neither.
                    "scope": _scope_verb(modifier.scope),
                    "effect": _effect_verb(modifier.effect),
                    "carried": "carried" if carriers else "uncarried",
                    # What the search reads. Lowercased here so the
                    # comparison is a plain substring test in the browser.
                    "search": " ".join([modifier.name, *notes]).lower(),
                },
            }
        )

    return render(
        request,
        "authoring/modifiers.html",
        {
            "rows": rows,
            "count": len(rows),
            # The composer's own choices, so the filter and the WHO/WHAT
            # pickers stay one vocabulary.
            "scope_options": _facet_options(rows, "scope", _scope_choices()),
            "effect_options": _facet_options(rows, "effect", _effect_choices()),
            "carried_options": _facet_options(rows, "carried", CARRIED_LABELS),
        },
    )


def _composing_for(request):
    """The carrier this composer page is being used on behalf of, named
    in the address as ``for_kind`` and ``for``.

    A carrier's own page hands the composing over to this one rather
    than drawing it inline: a long page that reloads on every choice
    puts the reader back at the top, scrolling to find the form again.
    What the trip must not lose is which thing the modifier is being
    made for — so it rides the URL, where it survives a refresh and can
    be linked to.

    Reached with no carrier named, this is the standalone page it has
    always been, and the answer is ``(None, None)``.
    """
    kind = request.POST.get("for_kind", request.GET.get("for_kind", ""))
    pk = request.POST.get("for", request.GET.get("for", ""))
    if not kind or not pk or kind not in LEAF_KINDS or not _carries_modifiers(kind):
        return None, None
    model = _model_for(_spec_for(kind))
    return kind, get_object_or_404(model, pk=pk)


@staff_member_required
def modifier_create(request):
    """The composer on a page of its own.

    Two steps, as everywhere else it appears: a GET names the scope kind
    and the effect kind, and only then are the fields those kinds call
    for drawn. Both ride the URL, so step two survives a refresh and
    "add a condition" is a plain link.

    Reached from a carrier's page the carrier rides the URL too, and
    what is composed here hangs on it — the same modifier that page
    would have made inline, made somewhere the reader is not scrolled
    away from. Reached without one, what it makes attaches to nothing:
    reusable by construction, waiting in every carrier page's attach
    picker.
    """
    from n26.library.forms import ModifierComposerForm

    for_kind, carrier = _composing_for(request)
    landing = (
        redirect("authoring-detail", kind=for_kind, pk=carrier.pk)
        if carrier is not None
        else None
    )

    bound = None
    if request.method == "POST":
        dropping = _dropped_condition(request)
        if dropping is not None:
            dropped, bound = _dropping_a_condition(request, dropping, attach_to=carrier)
            if dropped is not None:
                return dropped
        else:
            bound = ModifierComposerForm(request.POST, attach_to=carrier)
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
                    if carrier is not None:
                        messages.success(request, f"Attached {made.name}.")
                        return landing
                    messages.success(
                        request,
                        f"Composed {made.name} — attach it from any carrier's page.",
                    )
                    return redirect("authoring-modifier", pk=made.pk)

    return render(
        request,
        "authoring/modifier_create.html",
        {
            "carrier": carrier,
            "carrier_kind": for_kind,
            # With a carrier there is something to name the modifier
            # after, so the choice between a name of its own and a
            # generic one is a real choice and the switch is offered.
            "show_reusable_flag": carrier is not None,
            # Composing for a carrier ends in the modifier hanging on it,
            # which "Create" does not say; composing for nothing creates
            # a row and hangs it nowhere, which "Attach" would misname.
            "composer_submit_label": (
                "Attach modifier" if carrier is not None else "Create modifier"
            ),
            "composer_cancel_url": (
                landing.url if landing is not None else reverse("authoring-modifiers")
            ),
            **_composer_state(request, attach_to=carrier, bound_composer=bound),
        },
    )


def _carriers_said(count):
    """How widely a modifier is held, as a page prints it."""
    if count == 1:
        return "One thing carries this modifier"
    return f"{count} things carry this modifier"


def _what_it_does(modifier):
    """The about column for a modifier: its sentence, and nothing else.

    The compiler also says who carries it, and this page drops that run:
    the carriers are a table further up, with their kinds, their author
    help and a link each, and the same fact said twice in two shapes is
    the weaker one being read.
    """
    from n26.library.prose import prose_for

    return _prose_addresses(replace(prose_for(modifier), referenced_by=()))


def _modifier_or_404(pk):
    """One modifier with everything its sentence reads already loaded."""
    from n26.library.models import Modifier

    return get_object_or_404(_reading_sentences(Modifier.objects.all()), pk=pk)


@staff_member_required
def modifier_page(request, pk):
    """One modifier: what it says, who carries it, and the form that
    corrects it.

    A modifier is shared — the same row hangs on as many carriers as
    have been given it — so editing one changes all of them at once.
    The carriers are therefore named above the form rather than counted
    after it.

    The kinds are not editable here (``ModifierComposerForm.opened_on``
    says why); everything inside them is, conditions included.
    """
    from n26.library.forms import ModifierComposerForm, chosen_kind_cards

    modifier = _modifier_or_404(pk)

    try:
        chips = max(0, int(request.GET.get("chips", 0)))
    except ValueError:
        chips = 0
    chips = min(chips, MAX_CHIPS)

    dropping = _dropped_condition(request) if request.method == "POST" else None
    if dropping is not None:
        # The condition row itself goes when the modifier is saved, not
        # on this click: every carrier holding this row would otherwise
        # be changed by a click that only edited a form.
        dropped, composer = _dropping_a_condition(request, dropping, editing=modifier)
        if dropped is not None:
            return dropped
    elif request.method == "POST":
        composer = ModifierComposerForm(request.POST, editing=modifier)
        if composer.is_valid():
            try:
                with transaction.atomic():
                    composer.save()
            except IntegrityError:
                # The write is undone, and the row in hand is the
                # half-written one — read it back before drawing it.
                modifier.refresh_from_db()
                composer.add_error(
                    "name",
                    "A modifier with that name already exists in this pack.",
                )
            else:
                messages.success(request, f"Saved {modifier.name}.")
                return redirect("authoring-modifier", pk=pk)
    else:
        # A form in the address is one a remove redirected here with:
        # it already holds the stored conditions minus the one taken
        # off, so reading them out of the row again would put it back.
        carried = _carried_state(request)
        composer = (
            ModifierComposerForm.opened_on(modifier, chips=chips)
            if carried is None
            else ModifierComposerForm.carried(carried, editing=modifier)
        )

    carriers = _carriers(modifier)
    who_card, what_card = chosen_kind_cards(modifier)
    return render(
        request,
        "authoring/modifier.html",
        {
            "thing": modifier,
            # The cards the kinds were picked from, restated read-only:
            # a correction is made against what the kind means, and the
            # page that offered that meaning is long gone.
            "who_card": who_card,
            "what_card": what_card,
            "sentence": f"{modifier.scope}: {modifier.effect}",
            "prose": _what_it_does(modifier),
            "carriers": carriers,
            "carrier_count": len(carriers),
            "carrier_said": _carriers_said(len(carriers)),
            # Shared means a change here is a change to several things
            # at once, which is the fact worth saying out loud.
            "shared": len(carriers) > 1,
            "composer": composer,
            "composer_chips": chips,
            # The kinds are not offered on this page and are read off
            # the row, so the link names neither.
            "add_condition_href": _one_more_chip(request, chips, "", ""),
        },
    )


@staff_member_required
def modifier_delete(request, pk):
    """The question asked before a modifier is deleted, at its own address.

    GET asks and changes nothing; the POST from that page is the act.
    What makes the question worth a page is sharing: deleting a
    modifier takes the behaviour off every carrier holding it, and an
    author reading a list has no way of knowing how many that is. So
    the page names them.
    """
    from n26.library import authoring

    modifier = _modifier_or_404(pk)
    if request.method == "POST":
        said = modifier.name
        with transaction.atomic():
            authoring.delete_modifier(modifier)
        messages.success(request, f"Deleted {said}.")
        return redirect("authoring-modifiers")

    carriers = _carriers(modifier)
    return render(
        request,
        "authoring/modifier_delete.html",
        {
            "thing": modifier,
            "sentence": f"{modifier.scope}: {modifier.effect}",
            "carriers": carriers,
            "carrier_count": len(carriers),
            "carrier_said": _carriers_said(len(carriers)),
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
    """A collection: its definition, edited here, and what it means.

    The definition is sweeps and entries; the preview is the same
    ``browse`` structure the player-side listing draws, so what an
    author sees here is exactly what a gang will get. Membership by
    criteria keeps itself: author a weapon with a TP price and it is
    simply here on the next load, ammo rows riding under their gun.

    Curation happens on this page: an entry form (the union picker, each
    kind's own override asks, and who this list offers the row to) and a
    section form for the schema. Two acts, as the parts pages have them,
    so a post says which form was clicked.
    """
    from n26.core.browse import EQUIPMENT_LIST, browse
    from n26.library.models import Collection
    from n26.library.models.assignable import USABLE_BY_LISTS
    from n26.library.models.collection import ENTRY_ASKS, ENTRY_ASSIGNABLE_FIELDS

    collection = get_object_or_404(Collection, pk=pk)

    entry_spec = specs()["add_entry"]
    section_spec = specs()["add_section"]
    edit_class = generate_form(_spec_for("collection"))
    entry_form_class = generate_form(entry_spec)
    section_form_class = generate_form(section_spec)
    edit_form = edit_class.opened_on(collection)
    entry_form = entry_form_class(carrier=collection)
    section_form = section_form_class(carrier=collection)

    def narrowed(form):
        """The entry form asks what *this* collection's entries take —
        a menu's ask for a price would be a question with no meaning."""
        asks = collection.entry_asks()
        for ask in ENTRY_ASKS:
            if ask not in asks:
                form.fields.pop(ask, None)
        return form

    entry_form = narrowed(entry_form)

    if request.method == "POST":
        act = request.POST.get("act", "")
        if act == "edit":
            edit_form = edit_class.opened_on(collection, request.POST, request.FILES)
            if edit_form.is_valid():
                try:
                    with transaction.atomic():
                        edit_form.apply_to(collection)
                except ValidationError as refused:
                    edit_form.add_error(None, refused)
                except IntegrityError:
                    edit_form.add_error(
                        "name",
                        "A collection named "
                        f"“{edit_form.cleaned_data['name']}” already exists "
                        "in this pack.",
                    )
                else:
                    messages.success(request, f"Saved {collection}.")
                    return redirect("authoring-detail", kind="collection", pk=pk)
        elif act == "entry":
            entry_form = narrowed(entry_form_class(request.POST, carrier=collection))
            if entry_form.is_valid():
                with transaction.atomic():
                    made = entry_spec.verb(collection, **entry_form.verb_data())
                messages.success(request, f"{collection} now lists {made.assignable}.")
                return redirect("authoring-detail", kind="collection", pk=pk)
        elif act == "section":
            section_form = section_form_class(request.POST, carrier=collection)
            if section_form.is_valid():
                try:
                    with transaction.atomic():
                        made = section_spec.verb(collection, **section_form.verb_data())
                except IntegrityError:
                    # The schema's two uniquenesses, said in words: one
                    # name per collection, one default per collection.
                    section_form.add_error(
                        None,
                        "This collection already has a section by that "
                        "name, or already has a default section.",
                    )
                else:
                    messages.success(request, f"Added the {made.name} section.")
                    return redirect("authoring-detail", kind="collection", pk=pk)

    # An author's own preview of what they wrote, never a shopping trip:
    # a post previewed on its buying terms would hide the Exclusive items
    # its author is here to check.
    view = browse(collection, EQUIPMENT_LIST)

    # The schema's own promise, kept on the preview: unplaced categories
    # fall into the default section, so the group of things with no home
    # prints under its name rather than "(no section)".
    default_section = next(
        (row for row in collection.sections.all() if row.is_default), None
    )

    sections = []
    line_count = 0
    for section in view.sections:
        categories = []
        for category in section.categories:
            rows = []
            for line in category.lines:
                notes = []
                if line.entry is not None and collection.prices_its_entries:
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
        sections.append(
            {
                # The schema's own promise, kept on the preview: unplaced
                # categories fall into the default section, so the group
                # with no home prints under its name, never "(no section)".
                "name": section.name
                or (default_section.name if default_section else ""),
                "categories": categories,
            }
        )

    entries = []
    for entry in collection.entries.prefetch_related(
        *ENTRY_ASSIGNABLE_FIELDS, *USABLE_BY_LISTS
    ):
        notes = []
        if entry.price_override is not None:
            notes.append(f"{entry.price_override}cr here")
        if entry.trade_point_override is not None:
            notes.append(f"TP {entry.trade_point_override} here")
        # Who this list offers the row to, where it says. The item's own
        # restriction is not repeated here: it belongs to the item, and
        # this table is the list's own word about its own lines.
        offered_to = entry.usable_by_words()
        if offered_to:
            notes.append(f"offered to {offered_to} only")
        entries.append(
            {
                "label": _label_for(entry.assignable),
                "notes": notes,
                "remove_url": reverse("authoring-entry-remove", args=[entry.pk]),
            }
        )

    return render(
        request,
        "authoring/collection.html",
        {
            "thing": collection,
            "kind": "collection",
            "kind_help": kind_help(Collection),
            "sweeps": [str(selector) for selector in collection.selectors.all()],
            "entries": entries,
            "schema_sections": list(collection.sections.all()),
            "edit_form": edit_form,
            "entry_form": entry_form,
            "entry_help": kind_help(_model_for(entry_spec)),
            "section_form": section_form,
            "section_help": kind_help(_model_for(section_spec)),
            "sections": sections,
            "line_count": line_count,
            "priced": collection.prices_its_entries,
            "entry_description": (
                "One more item this collection lists. Leave the overrides "
                "blank to offer it at its own reference price, and the "
                "narrowing blank to offer it to everyone."
                if collection.prices_its_entries
                else "One more thing this menu offers. Nothing is for "
                "sale here, so listing an item asks for nothing but the "
                "item."
            ),
            "preview_description": (
                "What the definition means right now — author an item "
                "that fits and it appears here on the next load. Browsed "
                "as a plain list; a trading trip withholds “E” rows and "
                "charges the TP shown."
                if collection.prices_its_entries
                else "What the definition means right now — the things "
                "this menu puts in front of a player, under its own "
                "headings."
            ),
        },
    )


@staff_member_required
def picklist_member_remove(request, pk):
    """The question asked before a pickable is taken off a list.

    What goes is the *listing*. The pickable stays in the library, on
    every other list that offers it, and on every card that has already
    picked it — worth saying before anything happens, because a control
    beside a pickable's name reads as one that deletes pickables.
    """
    from n26.library import authoring
    from n26.library.models import PicklistMember

    member = get_object_or_404(
        PicklistMember.objects.select_related("picklist", "pickable"), pk=pk
    )
    picklist = member.picklist
    back = reverse("authoring-detail", args=["picklist", picklist.pk])

    if request.method == "POST":
        said = member.label
        with transaction.atomic():
            authoring.remove_picklist_member(member)
        messages.success(request, f"{picklist} no longer offers {said}.")
        return redirect(back)

    return render(
        request,
        "authoring/picklist_member_remove.html",
        {
            "thing": member,
            "label": member.label,
            "picklist": picklist,
            "back": back,
        },
    )


@staff_member_required
def entry_remove(request, pk):
    """The question asked before a listing row is taken off.

    What goes is the *entry* — this collection's row for the thing, its
    overrides included. The thing named stays in the library and on
    every other list that names it, and nothing already bought changes:
    a purchase pinned its own record when it was made.
    """
    from n26.library import authoring
    from n26.library.models import CollectionEntry
    from n26.library.models.collection import ENTRY_ASSIGNABLE_FIELDS

    entry = get_object_or_404(
        CollectionEntry.objects.select_related("collection", *ENTRY_ASSIGNABLE_FIELDS),
        pk=pk,
    )
    collection = entry.collection
    back = reverse("authoring-detail", args=["collection", collection.pk])

    if request.method == "POST":
        said = _label_for(entry.assignable)
        with transaction.atomic():
            authoring.remove_entry(entry)
        messages.success(request, f"{collection} no longer lists {said}.")
        return redirect(back)

    return render(
        request,
        "authoring/entry_remove.html",
        {
            "thing": entry,
            "label": _label_for(entry.assignable),
            "collection": collection,
            "back": back,
        },
    )


#: What a slot type is built out of, in the order it is built: the
#: pickables, the picklists that offer them, the slots that draw on
#: those picklists. Each is a table of its own rows and a form that
#: makes one more, and each names the kind whose page a row leads to.
#:
#: The slot type itself is not on any of the three forms. It is the
#: page, so the field is taken off and the verb is handed the row
#: instead — which is also what makes the narrowing honest: a slot's
#: picker can only offer this slot type's picklists because the slot
#: type is already settled.
SLOT_TYPE_PARTS = (
    {
        "act": "pickable",
        "verb": "create_pickable",
        "parts": "pickables",
        "kind": "pickable",
        "title": "Pickables",
        "part_name": "pickable",
        "notes": _pickable_notes,
        "description": (
            "The values available to a choice of this slot type. A "
            "pickable does nothing until a modifier hangs on it, which is "
            "done on its own page."
        ),
        "nothing_yet": (
            "No pickables yet — a choice of this slot type has nothing to offer."
        ),
    },
    {
        "act": "picklist",
        "verb": "create_picklist",
        "parts": "picklists",
        "kind": "picklist",
        "title": "Picklists",
        "part_name": "picklist",
        "notes": _picklist_notes,
        "description": (
            "A list of pickables, in order. A slot type may have several "
            "picklists: what a leader picks from and what a champion picks "
            "from could be two lists of one slot type."
        ),
        "nothing_yet": (
            "No picklists yet — a choice draws its pickables from one of these."
        ),
    },
    {
        "act": "slot",
        "verb": "create_slot",
        "parts": "slots",
        "kind": "slot",
        "title": "Slots",
        "part_name": "slot",
        "notes": _slot_notes,
        "description": (
            "A specific, named use of a slot type: a picklist, a label, "
            "and how many picks. Adding to a model or gang causes the slot "
            "to be displayed."
        ),
        "nothing_yet": (
            "No slots yet — nothing puts this slot type's pickables in front "
            "of a player."
        ),
    },
)


def _slot_type_part_form(part, slot_type, posted=None):
    """The form that adds one part to a slot type.

    The spec-generated create form for that kind, with the slot type
    taken off: the page is the slot type, so asking again would be a box
    with one right answer. Handed the slot type as its carrier, which is
    what narrows a slot's picklist picker to the ones this slot type has.
    """
    spec = specs()[part["verb"]]
    form_class = generate_form(spec)
    form = (
        form_class(posted, carrier=slot_type)
        if posted is not None
        else form_class(carrier=slot_type)
    )
    form.fields.pop("slot_type", None)
    return spec, form


@staff_member_required
def slot_type_page(request, pk):
    """A slot type: what it is, and everything built in it.

    A slot type is a top-level kind and reads like one — its pickables,
    its picklists and its slots are all on this page, each a table and a
    form. They only mean anything together: a pickable nothing lists is
    unofferable, a picklist nothing draws on is unasked, and a slot is
    the only one of the three a card ever sees.

    Its own parts rather than the generic parts page, which draws at
    most one section of a kind's own. Three acts, so a post says which
    form was clicked.
    """
    from n26.library.models import SlotType

    slot_type = get_object_or_404(SlotType, pk=pk)
    edit_class = generate_form(_spec_for("slot-type"))
    edit_form = edit_class.opened_on(slot_type)
    act = request.POST.get("act", "") if request.method == "POST" else ""

    if act == "edit":
        edit_form = edit_class.opened_on(slot_type, request.POST)
        if edit_form.is_valid():
            try:
                with transaction.atomic():
                    edit_form.apply_to(slot_type)
            except ValidationError as refused:
                edit_form.add_error(None, refused)
            except IntegrityError:
                edit_form.add_error(
                    "name",
                    f"A slot type named “{edit_form.cleaned_data['name']}” "
                    "already exists in this pack.",
                )
            else:
                messages.success(request, f"Saved {slot_type}.")
                return redirect("authoring-detail", kind="slot-type", pk=pk)

    sections = []
    for part in SLOT_TYPE_PARTS:
        posted = request.POST if act == part["act"] else None
        spec, form = _slot_type_part_form(part, slot_type, posted)
        if posted is not None and form.is_valid():
            try:
                with transaction.atomic():
                    made = spec.verb(slot_type=slot_type, **form.verb_data())
            except IntegrityError:
                form.add_error(
                    spec.identity,
                    f"{spec.creates._meta.verbose_name.capitalize()} "
                    f"“{form.cleaned_data[spec.identity]}” already exists "
                    "in this pack.",
                )
            except ValidationError as refused:
                form.add_error(None, refused)
            else:
                messages.success(request, f"Created {made}.")
                return redirect("authoring-detail", kind="slot-type", pk=pk)
        rows = [
            {
                **_naming(row),
                "url": reverse("authoring-detail", args=[part["kind"], row.pk]),
                "notes": part["notes"](row),
            }
            for row in _slot_type_rows(slot_type, part)
        ]
        sections.append(
            {
                **part,
                "rows": rows,
                "form": form,
                "part_article": _article_for(part["part_name"]),
                "part_help": kind_help(spec.creates),
            }
        )

    return render(
        request,
        "authoring/slot_type.html",
        {
            "thing": slot_type,
            "kind": "slot-type",
            "edit_form": edit_form,
            "sections": sections,
        },
    )


def _slot_type_rows(slot_type, part):
    """One of a slot type's three sets of parts, with what its notes read.

    Each set is one query and its notes one more, whatever the slot type
    holds — one with eight pickables costs this page what one with a
    single pickable costs it.
    """
    rows = getattr(slot_type, part["parts"]).all()
    if part["act"] == "pickable":
        return rows.prefetch_related("listed_on")
    if part["act"] == "picklist":
        return rows.prefetch_related("members")
    return rows.select_related("picklist")


#: Kinds whose detail page is its own view rather than the
#: parts-and-add-form shape. Checked by ``detail`` before anything else.
DETAIL_VIEWS = {"collection": collection_page, "slot-type": slot_type_page}


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


class SheetUploadForm(forms.Form):
    """One file, for one named sheet.

    A page per sheet rather than one page of five pickers: an author
    uploads a corrected export of *one* thing, and a form offering the
    other four asks them to remember, every time, that leaving those
    empty is what keeps the sheets they already gave.
    """

    def __init__(self, *args, sheet=None, **kwargs):
        super().__init__(*args, **kwargs)
        label = SHEET_LABELS[sheet]
        self.fields["file"] = forms.FileField(
            required=True,
            label=f"The {label} sheet",
            help_text="A CSV export. Uploading replaces whichever file this "
            "sheet is holding.",
            widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
        )


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


def _ingest_reach_said(plan):
    """The preview's one line about existing gangs: which sets these
    sheets would add members to, and how far those additions travel.

    Only additions count — an amount corrected or a member superseded
    changes what is acquired next, not what anything already holds —
    and a set the sheets create is held by nobody, so an upload adding
    to no standing set says nothing at all.
    """
    from n26.core.propagation import reach_of_all
    from n26.library.models import DefaultAssignmentSet

    grown = {
        row.existing
        for row in plan.planned
        if row.kind == "DefaultAssignmentSet"
        and row.action == "update"
        and row.changes.get("members", {}).get("added")
    }
    if not grown:
        return ""
    reach = reach_of_all(DefaultAssignmentSet.objects.filter(pk__in=grown))
    said = _reach_said(reach, "each addition")
    return (
        f"Some of these additions grow what a thing comes with: "
        f"{said[0].lower()}{said[1:]}"
    )


def _sheets_standing(user):
    """Every sheet, held or not, in the order they are planned.

    The unheld ones are listed too: which sheets an upload is missing is
    what an author is checking for, and a table of only what arrived
    cannot show an absence.
    """
    from n26.library.ingest import held_sheets

    held = held_sheets(user)
    return [
        {
            "sheet": name,
            "label": label,
            "holds": holds,
            "upload": held.get(name),
        }
        for name, label, holds in INGEST_SHEETS
    ]


@staff_member_required
def ingest(request):
    """The sheets an author is holding, and what may be done with them.

    Uploading, previewing and importing are three pages because they are
    three acts. This one only says what is held: it reads no content and
    plans nothing, so it stays cheap however large the sheets are, and
    the two pages that do real work are each reached deliberately.

    Posting here removes a held sheet, or all of them. A removal is a
    post and never a link, because a link can be followed by accident,
    and by something that is not a person.
    """
    from n26.library.ingest import discard_sheets

    if request.method == "POST":
        remove = request.POST.get("remove")
        if remove == "everything":
            gone = discard_sheets(request.user)
            messages.success(
                request,
                f"Removed {gone} held sheet(s)." if gone else "Nothing was held.",
            )
        elif remove in SHEET_LABELS:
            gone = discard_sheets(request.user, [remove])
            messages.success(
                request,
                f"Removed the {SHEET_LABELS[remove]} sheet."
                if gone
                else f"No {SHEET_LABELS[remove]} sheet was held.",
            )
        else:
            messages.error(request, "No such sheet.")
        return redirect("authoring-ingest")

    standing = _sheets_standing(request.user)
    return render(
        request,
        "authoring/ingest.html",
        {
            "standing": standing,
            "held": [entry for entry in standing if entry["upload"]],
        },
    )


@staff_member_required
def ingest_sheet(request, sheet):
    """Upload one sheet, having picked which sheet it is.

    Which sheet is being uploaded is in the address rather than in a
    control, so the page the server draws — its heading, its help, what
    the file will be taken to mean — follows from where you are. That
    also makes each sheet's upload page a link somebody can be sent.

    The file is read here, not at planning time: an author who exported
    the wrong thing should learn it beside the file picker, and a file
    that cannot be read must never be held as though it could.
    """
    from n26.library.ingest import SheetRefused, held_sheets, store_sheet

    if sheet not in SHEET_LABELS:
        raise Http404("No such sheet")

    form = SheetUploadForm(sheet=sheet)
    if request.method == "POST":
        form = SheetUploadForm(request.POST, request.FILES, sheet=sheet)
        if form.is_valid():
            try:
                held = store_sheet(request.user, sheet, form.cleaned_data["file"])
            except SheetRefused as refused:
                form.add_error("file", str(refused))
            else:
                messages.success(
                    request,
                    f"Holding {held.filename} as the {SHEET_LABELS[sheet]} sheet "
                    f"— {held.lines} line(s).",
                )
                return redirect("authoring-ingest")

    return render(
        request,
        "authoring/ingest_sheet.html",
        {
            "form": form,
            "sheet": sheet,
            "label": SHEET_LABELS[sheet],
            "holds": SHEET_HOLDS[sheet],
            "upload": held_sheets(request.user).get(sheet),
        },
    )


@staff_member_required
def ingest_preview(request):
    """What the held sheets would write, and the button that writes it.

    Planning happens on the way in, every time — on the visit that shows
    the preview, and again on the post that imports. The preview *is*
    the contract, and it is a contract about the library as it stands:
    two plannings of the same files say the same thing, so what was
    shown is what is written, while a preview kept from earlier would be
    a promise about a library that has since moved.

    The files themselves are the ones already held, which is what lets
    this page be looked at twice, reloaded, or read tomorrow.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.library.ingest import held_sheets, perform, plan_ingest, rows_of

    held = held_sheets(request.user)
    if not held:
        messages.error(request, "No sheets are held. Upload one first.")
        return redirect("authoring-ingest")

    plan = plan_ingest(**rows_of(held))
    preview = plan.preview(examples=2)
    preview["shapes"] = _problems_by_shape(plan.problems)
    preview["errors"] = sum(1 for p in plan.problems if p.severity == "error")
    preview["notes"] = len(plan.problems) - preview["errors"]
    preview["diffs"] = _changes_by_shape(preview["changes"])
    preview["reach_said"] = _ingest_reach_said(plan)
    # Uploading last year's export over this year's content is the
    # realistic accident, and it is invisible row by row and
    # unmistakable in the aggregate.
    settled = preview["actions"].get("update", 0) + preview["actions"].get(
        "unchanged", 0
    )
    preview["mostly_changed"] = (
        settled > 0 and preview["actions"].get("update", 0) * 2 > settled
    )

    if request.method == "POST":
        if not plan.ok:
            messages.error(
                request,
                f"{preview['errors']} problem(s) block this upload — "
                f"nothing was written.",
            )
        else:
            with transaction.atomic():
                result = perform(plan)
            created = result.counts()
            # One event for the run, outside the transaction and carrying
            # totals. A row apiece would write thousands of events for one
            # click.
            record(
                request,
                N26Noun.INGEST,
                EventVerb.IMPORT,
                sheets=sorted(held),
                created=sum(created.values()),
                updated=len(result.updated),
            )
            messages.success(
                request,
                f"Created {sum(created.values())} rows, changed "
                f"{len(result.updated)}. Below is a fresh reading of the same "
                f"sheets against the library as it now stands.",
            )
        # However it went, come back by a fresh reading: a reload must not
        # offer to run the import a second time, and the honest
        # confirmation that an import did what it said is the same plan
        # made again, now finding nothing left to do.
        return redirect("authoring-ingest-preview")

    return render(
        request,
        "authoring/ingest_preview.html",
        {
            "preview": preview,
            "held": [
                {"label": SHEET_LABELS[name], "upload": held[name]}
                for name in SHEET_NAMES
                if name in held
            ],
            "missing": [
                label for name, label, _holds in INGEST_SHEETS if name not in held
            ],
        },
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


def _rows(model, kind=None):
    """Every row of a kind, in the order an author wants to read them.

    Not by recency: a listing is for checking content, and thirty-nine
    skills entered in one go would hide all but the last few. Kinds
    that sort into the taxonomy read set by set, and within a set by
    the number they are rolled on.

    With ``kind``, what that kind's labels and describers read is
    loaded up front (``LEAF_LISTING_HINTS``) — every reader of a set of
    rows wants the hints, so they live here rather than in each caller.
    """
    rows = model.objects.all()
    if any(field.name == "category" for field in model._meta.get_fields()):
        rows = rows.select_related("category").order_by(
            "category__position", "category__name", "position", "name"
        )
    hint = LEAF_LISTING_HINTS.get(kind)
    return hint(rows) if hint else rows


@dataclass(frozen=True)
class Coverage:
    """Whether a roll table's bands claim its die.

    Gaps and overlaps make a table unrollable, and neither is a fact
    about any one row — only the whole table can say. ``covered`` counts
    rolls claimed by at least one result; a roll claimed twice is
    covered and doubled both.
    """

    #: Every roll the die can produce.
    total: int
    #: How many of them at least one band claims.
    covered: int
    #: The rolls no band claims, in roll order.
    unclaimed: list
    #: ``(roll, members)`` for every roll more than one band claims.
    doubled: list
    #: Results with no band at all: on the list, never rolled.
    bandless: list


def coverage(picklist, members=None):
    """The table's bands checked against its die, as :class:`Coverage`.

    Pure over the rows it is handed, so a page can say "34 of 36 rolls
    covered; 23 and 24 unclaimed" and a test can assert it without
    rendering anything. A band may span rolls the die cannot produce —
    "31-46" on a D66 — and such rolls count for nothing: the check walks
    the die's own rolls, never the band's arithmetic. A caller that has
    already fetched the members hands them over rather than paying for
    the same rows twice.
    """
    from n26.library.models import Dice

    rolls = Dice.rolls(picklist.dice)
    if members is None:
        # One query however long the table: a member's label falls back
        # to its pickable's name, and every label it holds is printed.
        members = list(picklist.members.select_related("pickable"))
    claimed = {}
    for member in members:
        if member.roll_low is None:
            continue
        for roll in rolls:
            if member.roll_low <= roll <= member.roll_high:
                claimed.setdefault(roll, []).append(member)
    return Coverage(
        total=len(rolls),
        covered=len(claimed),
        unclaimed=[roll for roll in rolls if roll not in claimed],
        # In roll order, as everything about a table is read.
        doubled=sorted((roll, who) for roll, who in claimed.items() if len(who) > 1),
        bandless=[member for member in members if member.roll_low is None],
    )


@staff_member_required
def picklist_table(request, pk):
    """One roll table, whole: its rows in roll order, and whether its
    bands cover the die.

    The picklist's own page adds and removes members one at a time; this
    page exists for the fact no single row carries — a gap or an overlap
    in the table. The add-a-row form is the detail page's own, handed
    the picklist so its picker offers this slot type's pickables and
    nothing else. An ordinary list has no table to show, so its address
    here leads back to its own page.
    """
    from django.db.models import F

    from n26.library.models import Picklist

    picklist = get_object_or_404(Picklist, pk=pk)
    if not picklist.dice:
        return redirect("authoring-detail", kind="picklist", pk=pk)
    spec = specs()["add_picklist_member"]
    form_class = generate_form(spec)

    if request.method == "POST":
        form = form_class(request.POST, carrier=picklist)
        if form.is_valid():
            try:
                with transaction.atomic():
                    member = spec.verb(picklist, **form.verb_data())
            except ValidationError as refused:
                form.add_error(None, refused)
            else:
                messages.success(request, f"Added {member.label}.")
                return redirect("authoring-picklist-table", pk=pk)
    else:
        form = form_class(carrier=picklist)

    members = list(
        picklist.members.select_related("pickable").order_by(
            F("roll_low").asc(nulls_last=True), "position", "pickable__name"
        )
    )
    said = coverage(picklist, members)
    doubled_said = (
        [
            (roll, ", ".join(member.label for member in who))
            for roll, who in said.doubled
        ]
        if said
        else []
    )
    unclaimed_said = ", ".join(str(roll) for roll in said.unclaimed) if said else ""
    return render(
        request,
        "authoring/picklist_table.html",
        {
            "picklist": picklist,
            "members": members,
            "coverage": said,
            "unclaimed_said": unclaimed_said,
            "doubled_said": doubled_said,
            "form": form,
        },
    )
