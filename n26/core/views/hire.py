"""Hiring a fighter — the web face of :mod:`n26.core.hire`."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.text import slugify

from n26.core.views.permissions import _own_gang_or_404


@login_required
def hire_fighter(request, pk):
    """Hire a fighter: the design system's picker over the real gang list.

    GET is ``build_hire_list`` shelved by each profile's home category.
    POST is the picker's own contract: every Hire button submits the form
    carrying ``profile``, and each option group's inputs are scoped
    ``{profile_pk}:{group_index}`` with option indices as values. The
    indices are mapped back through ``build_hire_entry`` — the same
    derivation the rows were drawn from — because the entry *synthesises*
    a default group when the profile has only named ones, so raw
    ``grouped_options()`` would be off by one exactly there.

    An overspend is refused by the operation itself (``NotEnoughCredits``
    unwinds the transaction), and lands back here as a message: nothing
    half-written, nothing lost but a click.
    """
    from n26.core.forms import HireFighterForm
    from n26.core.hire import build_hire_entry, build_hire_list, shelve_hire_list
    from n26.core.operations import NotEnoughCredits, operation
    from n26.library.models import Profile

    gang = _own_gang_or_404(request, pk)

    if request.method == "POST":
        form = HireFighterForm(request.POST)
        try:
            profile = Profile.objects.filter(
                pk=request.POST.get("profile"), gang_type=gang.gang_type
            ).first()
        except ValidationError:
            # A tampered pk, not a ULID at all. The genuine buttons never
            # send one, so redisplaying the list is all it deserves.
            profile = None
        if profile is not None and form.is_valid():
            entry = build_hire_entry(profile)
            chosen = []
            # The row template scopes its option inputs with
            # `value|slugify`, which lowercases the pk — so the keys must
            # be read back through the same filter, or every option ticked
            # in a real browser is silently ignored and the fighter buys
            # as default. (A test posting the raw pk would pass anyway,
            # which is exactly how that bug shipped the first time.)
            scope = slugify(str(profile.pk))
            for group_index, group in enumerate(entry.groups):
                picked = request.POST.getlist(f"{scope}:{group_index}")
                for value in picked:
                    try:
                        option = group.options[int(value)]
                    except ValueError, IndexError:
                        raise Http404("No such option") from None
                    if option.default_set is not None:
                        chosen.append(option.default_set)
            try:
                with operation(gang, actor=request.user) as op:
                    miniature = op.hire(
                        profile,
                        form.cleaned_data["name"] or profile.name,
                        option=chosen,
                    )
            except NotEnoughCredits as refusal:
                messages.error(request, str(refusal))
                return redirect("n26-hire-fighter", pk=gang.pk)
            except ValueError:
                # Two picks in a choose-one group, or a set the profile
                # does not offer — resolve_selection refuses tampering
                # the option indices cannot express. Same answer as a
                # bad index: this is a broken link, not a rule to explain.
                raise Http404("No such option") from None
            messages.success(request, f"Hired {miniature.name}.")
            return redirect("n26-gang", pk=gang.pk)
    else:
        form = HireFighterForm()

    section_rows = shelve_hire_list(build_hire_list(gang.gang_type))
    entries = [
        entry
        for section_row in section_rows
        for category in section_row["categories"]
        for entry in category["entries"]
    ]
    prices = [entry.base_price for entry in entries]
    return render(
        request,
        "n26/hire_fighter.html",
        {
            "gang": gang,
            "form": form,
            "section_rows": [
                {"section": section_row, "first": index == 0}
                for index, section_row in enumerate(section_rows)
            ],
            # Tabs only when *every* section is named. The tab strip is
            # the picker's whole navigation once it is on: a section
            # whose name is not in this list can never be the active tab,
            # so mixed content — some profiles homed, some not — would
            # serve the unnamed shelf in the HTML and make it unreachable.
            # All-or-nothing keeps every row reachable either way.
            "sections": (
                [row["name"] for row in section_rows]
                if section_rows and all(row["name"] for row in section_rows)
                else []
            ),
            # The picker's all-on category state. These are *registration*
            # names — an item in an unnamed category registers under its
            # section's name (possibly ""), and a list that omits that name
            # silently hides every such row: categoryOn("") is the filter.
            "categories": list(
                dict.fromkeys(
                    category["name"] or section_row["name"]
                    for section_row in section_rows
                    for category in section_row["categories"]
                )
            ),
            "category_options": [
                {"value": name, "label": name}
                for name in dict.fromkeys(
                    category["name"]
                    for section_row in section_rows
                    for category in section_row["categories"]
                    if category["name"]
                )
            ],
            "price_floor": min(prices, default=0),
            "price_ceiling": max(prices, default=0),
        },
    )
