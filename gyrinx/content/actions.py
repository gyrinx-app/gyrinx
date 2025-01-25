from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import render
from django.utils.translation import gettext as _

from gyrinx.content.forms import CopySelectedToFighterForm, CopySelectedToHouseForm
from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.models import QuerySetOf


@admin.action(description="Copy to another Fighter")
def copy_selected_to_fighter(self, request, queryset):
    selected = queryset.values_list("pk", flat=True)

    if request.POST.get("post"):
        try:
            for fighter_id in request.POST.getlist("to_fighters"):
                for item in queryset:
                    item.pk = None
                    item.fighter_id = fighter_id
                    item.save()
        except Exception as e:
            self.message_user(
                request,
                _("An error occurred while copying: %s") % str(e),
                messages.ERROR,
            )
            return None

        self.message_user(
            request,
            _("The selected items have been copied."),
            messages.SUCCESS,
        )
        return None

    form = CopySelectedToFighterForm(initial={"_selected_action": selected})
    title = _("Copy items to another ContentFighter?")
    subtitle = _(
        "Select one or more ContentFighters to which you want to copy the selected items."
    )

    context = {
        **self.admin_site.each_context(request),
        "title": title,
        "subtitle": subtitle,
        "queryset": queryset,
        "form": form,
        "action_name": "copy_selected_to_fighter",
    }
    request.current_app = self.admin_site.name
    return render(
        request,
        "content/copy_selected_to.html",
        context,
    )


@admin.action(description="Copy to another House")
def copy_selected_to_house(self, request, queryset: QuerySetOf[ContentFighter]):
    selected = queryset.values_list("pk", flat=True)

    if request.POST.get("post"):
        try:
            for house_id in request.POST.getlist("to_houses"):
                house = ContentHouse.objects.get(pk=house_id)
                with transaction.atomic():
                    for item in queryset:
                        item.copy_to_house(house)

        except Exception as e:
            self.message_user(
                request,
                _("An error occurred while copying: %s") % str(e),
                messages.ERROR,
            )
            return None

        self.message_user(
            request,
            _("The selected items have been copied."),
            messages.SUCCESS,
        )
        return None

    form = CopySelectedToHouseForm(initial={"_selected_action": selected})
    title = _("Copy items to another ContentHouse?")
    subtitle = _(
        "Select one or more ContentHouses to which you want to copy the selected items."
    )

    context = {
        **self.admin_site.each_context(request),
        "title": title,
        "subtitle": subtitle,
        "queryset": queryset,
        "form": form,
        "action_name": "copy_selected_to_house",
    }
    request.current_app = self.admin_site.name
    return render(
        request,
        "content/copy_selected_to.html",
        context,
    )
