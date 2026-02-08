"""Fighter rules views."""

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.content.models import ContentRule
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.views.list.common import get_clean_list_or_404
from gyrinx.models import QuerySetOf, is_valid_uuid


@login_required
def edit_list_fighter_rules(request, id, fighter_id):
    """
    Edit the rules of an existing :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``default_rules``
        Rules from the ContentFighter with their disabled status.
    ``custom_rules``
        Custom rules added to the fighter.
    ``available_rules``
        All ContentRules available for adding.

    **Template**

    :template:`core/list_fighter_rules_edit.html`
    """
    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Get query parameters
    search_query = request.GET.get("q", "").strip()

    # Get default rules from ContentFighter (uses prefetched data)
    default_rules = fighter.content_fighter.rules.all()
    # Use prefetched disabled_rules instead of values_list query
    disabled_rule_ids = {r.id for r in fighter.disabled_rules.all()}

    # Build default rules with status
    default_rules_display = []
    for rule in default_rules:
        default_rules_display.append(
            {
                "rule": rule,
                "is_disabled": rule.id in disabled_rule_ids,
            }
        )

    # Get custom rules
    custom_rules = fighter.custom_rules.all()

    # Get all available rules for search, including rules from subscribed packs
    available_rules: QuerySetOf[ContentRule] = ContentRule.objects.with_packs(
        lst.packs.all()
    )

    if search_query:
        available_rules = available_rules.filter(Q(name__icontains=search_query))

    # Exclude those already in custom rules
    available_rules = available_rules.exclude(
        id__in=custom_rules.values_list("id", flat=True)
    )

    # Sort alphabetically
    available_rules = available_rules.order_by("name")

    # Paginate the results
    paginator = Paginator(available_rules, 20)  # Show 20 rules per page
    page_number = request.GET.get("page", 1)

    # Validate page number and redirect if necessary
    try:
        page_number = int(page_number)
        if page_number < 1:
            page_number = 1
    except (TypeError, ValueError):
        page_number = 1

    # If the requested page is out of range due to search, redirect to page 1
    if page_number > paginator.num_pages and paginator.num_pages > 0:
        # Build redirect URL with search query preserved
        url = reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
        params = {}
        if search_query:
            params["q"] = search_query
        if params:
            url = f"{url}?{urlencode(params)}"
        return redirect(url)

    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "core/list_fighter_rules_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "default_rules_display": default_rules_display,
            "custom_rules": custom_rules,
            "available_rules": available_rules,
            "page_obj": page_obj,
            "search_query": search_query,
        },
    )


@login_required
def toggle_list_fighter_rule(request, id, fighter_id, rule_id):
    """
    Toggle (enable/disable) a default rule for a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    rule = get_object_or_404(
        ContentRule.objects.with_packs(lst.packs.all()), id=rule_id
    )

    # Ensure this is a default rule for the fighter
    if not fighter.content_fighter.rules.filter(id=rule_id).exists():
        messages.error(request, "This rule is not a default rule for this fighter.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
        )

    # Toggle the disabled status
    if fighter.disabled_rules.filter(id=rule_id).exists():
        fighter.disabled_rules.remove(rule)
        action = "enabled"
    else:
        fighter.disabled_rules.add(rule)
        action = "disabled"

    # Log the rule toggle event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="rules",
        action=f"{action}_rule",
        rule_name=rule.name,
    )

    messages.success(request, f"{rule.name} {action}")
    return HttpResponseRedirect(
        reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
    )


@login_required
def add_list_fighter_rule(request, id, fighter_id):
    """
    Add a custom rule to a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    rule_id = request.POST.get("rule_id")
    if rule_id and is_valid_uuid(rule_id):
        rule = get_object_or_404(
            ContentRule.objects.with_packs(lst.packs.all()), id=rule_id
        )
        fighter.custom_rules.add(rule)

        # Log the rule addition event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            field="rules",
            action="add_rule",
            rule_name=rule.name,
            rules_count=fighter.custom_rules.count(),
        )

        messages.success(request, f"Added {rule.name}")
    elif rule_id:
        messages.error(request, "Invalid rule ID provided.")

    return HttpResponseRedirect(
        reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
    )


@login_required
def remove_list_fighter_rule(request, id, fighter_id, rule_id):
    """
    Remove a custom rule from a :model:`core.ListFighter`.
    """
    if request.method != "POST":
        raise Http404()

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    rule = get_object_or_404(
        ContentRule.objects.with_packs(lst.packs.all()), id=rule_id
    )
    # Delete from the through table directly because the default ContentRule
    # manager excludes pack content, which causes the M2M remove() to silently
    # skip pack rules.
    ListFighter.custom_rules.through.objects.filter(
        listfighter_id=fighter.id, contentrule_id=rule.id
    ).delete()

    # Log the rule removal event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="rules",
        action="remove_rule",
        rule_name=rule.name,
        rules_count=fighter.custom_rules.count(),
    )

    messages.success(request, f"Removed {rule.name}")
    return HttpResponseRedirect(
        reverse("core:list-fighter-rules-edit", args=(lst.id, fighter.id))
    )
