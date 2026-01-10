"""Fighter skills views."""

from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Case, When
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.content.models import ContentSkill, ContentSkillCategory
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
def edit_list_fighter_skills(request, id, fighter_id):
    """
    Edit the skills of an existing :model:`core.ListFighter`.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being edited.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``categories``
        All skill categories with their skills.
    ``category_filter``
        The current filter applied to the skill categories,
        one of "primary-secondary-only" (default), "all" or
        "all-with-restricted".

    **Template**

    :template:`core/list_fighter_skills_edit.html`
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
    category_filter = request.GET.get("category_filter", "primary-secondary-only")

    # Create boolean flags based on value of filter parameter.
    # Note that we don't explicitly handle `all` because it's the default query behaviour.
    show_primary_secondary_only = category_filter == "primary-secondary-only"
    show_restricted = category_filter == "all-with-restricted"

    # Get default skills from ContentFighter
    default_skills = fighter.content_fighter.skills.all()
    disabled_skill_ids = set(fighter.disabled_skills.values_list("id", flat=True))

    # Build default skills with status
    default_skills_display = []
    for skill in default_skills:
        default_skills_display.append(
            {
                "skill": skill,
                "is_disabled": skill.id in disabled_skill_ids,
            }
        )

    # Get current fighter skills (user-added)
    current_skill_ids = set(fighter.skills.values_list("id", flat=True))

    # Get all skill categories with annotations
    # Get fighter's primary and secondary categories including equipment modifications
    primary_categories = fighter.get_primary_skill_categories()
    secondary_categories = fighter.get_secondary_skill_categories()

    # Extract IDs once to avoid duplicate list comprehensions
    primary_category_ids = [cat.id for cat in primary_categories]
    secondary_category_ids = [cat.id for cat in secondary_categories]

    # Build skill categories query
    skill_cats_query = ContentSkillCategory.objects.all()
    if show_restricted:
        # When showing restricted, exclude house-specific categories from regular categories
        # They will be added separately as special categories
        skill_cats_query = skill_cats_query.filter(houses__isnull=True)
    else:
        # Otherwise, exclude restricted categories
        skill_cats_query = skill_cats_query.filter(restricted=False)

    skill_cats = skill_cats_query.annotate(
        primary=Case(
            When(id__in=primary_category_ids, then=True),
            default=False,
            output_field=models.BooleanField(),
        ),
        secondary=Case(
            When(id__in=secondary_category_ids, then=True),
            default=False,
            output_field=models.BooleanField(),
        ),
    )

    # Get special categories
    if show_restricted:
        # When showing restricted, get all house-specific categories from all houses
        special_cats = (
            ContentSkillCategory.objects.filter(houses__isnull=False)
            .distinct()
            .annotate(
                primary=Case(
                    When(id__in=primary_category_ids, then=True),
                    default=False,
                    output_field=models.BooleanField(),
                ),
                secondary=Case(
                    When(id__in=secondary_category_ids, then=True),
                    default=False,
                    output_field=models.BooleanField(),
                ),
            )
        )
    else:
        # Default behavior: only show categories from the fighter's house
        special_cats = fighter.content_fighter.house.skill_categories.all().annotate(
            primary=Case(
                When(id__in=primary_category_ids, then=True),
                default=False,
                output_field=models.BooleanField(),
            ),
            secondary=Case(
                When(id__in=secondary_category_ids, then=True),
                default=False,
                output_field=models.BooleanField(),
            ),
        )

    # Combine all categories
    all_categories = []

    # Process regular categories
    for cat in skill_cats:
        if show_primary_secondary_only and not (cat.primary or cat.secondary):
            continue

        # Get skills for this category that fighter doesn't have
        skills_qs = cat.skills.exclude(id__in=current_skill_ids)

        # Apply search filter
        if search_query:
            skills_qs = skills_qs.filter(name__icontains=search_query)

        if skills_qs.exists():
            all_categories.append(
                {
                    "category": cat,
                    "skills": list(skills_qs.order_by("name")),
                    "is_special": False,
                    "primary": cat.primary,
                    "secondary": cat.secondary,
                }
            )

    # Process special categories
    for cat in special_cats:
        if show_primary_secondary_only and not (cat.primary or cat.secondary):
            continue

        # Get skills for this category that fighter doesn't have
        skills_qs = cat.skills.exclude(id__in=current_skill_ids)

        # Apply search filter
        if search_query:
            skills_qs = skills_qs.filter(name__icontains=search_query)

        if skills_qs.exists():
            all_categories.append(
                {
                    "category": cat,
                    "skills": list(skills_qs.order_by("name")),
                    "is_special": True,
                    "primary": cat.primary,
                    "secondary": cat.secondary,
                }
            )

    return render(
        request,
        "core/list_fighter_skills_edit.html",
        {
            "fighter": fighter,
            "list": lst,
            "default_skills_display": default_skills_display,
            "categories": all_categories,
            "search_query": search_query,
            "category_filter": category_filter,
        },
    )


@login_required
def add_list_fighter_skill(request, id, fighter_id):
    """
    Add a single skill to a :model:`core.ListFighter`.
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

    skill_id = request.POST.get("skill_id")
    if skill_id:
        skill = get_object_or_404(ContentSkill, id=skill_id)
        fighter.skills.add(skill)

        # Log the skill addition event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            field="skills",
            action="add_skill",
            skill_name=skill.name,
            skills_count=fighter.skills.count(),
        )

        messages.success(request, f"Added {skill.name}")

    return HttpResponseRedirect(
        reverse("core:list-fighter-skills-edit", args=(lst.id, fighter.id))
    )


@login_required
def remove_list_fighter_skill(request, id, fighter_id, skill_id):
    """
    Remove a single skill from a :model:`core.ListFighter`.
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

    skill = get_object_or_404(ContentSkill, id=skill_id)
    fighter.skills.remove(skill)

    # Log the skill removal event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="skills",
        action="remove_skill",
        skill_name=skill.name,
        skills_count=fighter.skills.count(),
    )

    messages.success(request, f"Removed {skill.name}")

    return HttpResponseRedirect(
        reverse("core:list-fighter-skills-edit", args=(lst.id, fighter.id))
    )


@login_required
def toggle_list_fighter_skill(request, id, fighter_id, skill_id):
    """
    Toggle (enable/disable) a default skill for a :model:`core.ListFighter`.
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
    skill = get_object_or_404(ContentSkill, id=skill_id)

    # Ensure this is a default skill for the fighter
    if not fighter.content_fighter.skills.filter(id=skill_id).exists():
        messages.error(request, "This skill is not a default skill for this fighter.")
        return HttpResponseRedirect(
            reverse("core:list-fighter-skills-edit", args=(lst.id, fighter.id))
        )

    # Toggle the disabled status
    if fighter.disabled_skills.filter(id=skill_id).exists():
        fighter.disabled_skills.remove(skill)
        action = "enabled"
    else:
        fighter.disabled_skills.add(skill)
        action = "disabled"

    # Log the skill toggle event
    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="skills",
        action=f"{action}_skill",
        skill_name=skill.name,
    )

    messages.success(request, f"{skill.name} {action}")
    return HttpResponseRedirect(
        reverse("core:list-fighter-skills-edit", args=(lst.id, fighter.id))
    )
