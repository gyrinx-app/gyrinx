"""Fighter counter editing views."""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.content.models import ContentCounter
from gyrinx.core.forms.list import EditCounterForm
from gyrinx.core.models.list import ListFighterCounter
from gyrinx.core.views.fighter.permissions import get_list_and_fighter


@login_required
def edit_list_fighter_counter(request, id, fighter_id, counter_id):
    """
    Edit a single counter for a :model:`core.ListFighter`.

    **Template**

    :template:`core/list_fighter_counters_edit.html`
    """
    result = get_list_and_fighter(request, id, fighter_id)
    if result[0] is None:
        return result[2]  # redirect response
    lst, fighter, _perms = result

    # Look up the specific counter, ensuring it applies to this fighter
    counter = get_object_or_404(
        ContentCounter,
        id=counter_id,
        restricted_to_fighters=fighter.content_fighter,
    )

    # Get existing value if any
    existing = (
        fighter.counters.filter(counter=counter).select_related("counter").first()
    )
    current_value = existing.value if existing else 0

    if request.method == "POST":
        form = EditCounterForm(
            request.POST,
            counter=counter,
            current_value=current_value,
        )

        if form.is_valid():
            new_value = form.cleaned_data["value"]

            if new_value != current_value:
                with transaction.atomic():
                    if existing:
                        existing.value = new_value
                        existing.save_with_user(user=request.user)
                    else:
                        ListFighterCounter.objects.create_with_user(
                            user=request.user,
                            fighter=fighter,
                            counter=counter,
                            value=new_value,
                            owner=lst.owner,
                        )

            messages.success(request, f"{counter.name} updated for {fighter.name}")
            return HttpResponseRedirect(
                reverse("core:list", args=(lst.id,)) + f"#{fighter.id}"
            )
    else:
        form = EditCounterForm(
            counter=counter,
            current_value=current_value,
        )

    return render(
        request,
        "core/list_fighter_counters_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "counter": counter,
            "form": form,
        },
    )
