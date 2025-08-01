from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import generic
from django.views.decorators.http import require_http_methods

from gyrinx.core.forms.print_config import PrintConfigForm
from gyrinx.core.models import List, ListFighter, PrintConfig
from gyrinx.core.models.events import EventField, EventNoun, EventVerb, log_event


class PrintConfigIndexView(generic.ListView):
    """
    Display a list of print configurations for a list.

    **Context**

    ``list``
        The :model:`core.List` object.
    ``print_configs``
        A list of :model:`core.PrintConfig` objects for the list.
    ``has_default``
        Whether the list has a default print configuration.

    **Template**

    :template:`core/print_config/index.html`
    """

    template_name = "core/print_config/index.html"
    context_object_name = "print_configs"

    def dispatch(self, request, *args, **kwargs):
        self.list = get_object_or_404(List, id=kwargs["list_id"], owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return PrintConfig.objects.filter(list=self.list, archived=False).order_by(
            "-is_default", "name"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["list"] = self.list
        context["has_default"] = self.get_queryset().filter(is_default=True).exists()
        return context


@login_required
def print_config_create(request, list_id):
    """Create a new print configuration for a list."""
    list_obj = get_object_or_404(List, id=list_id, owner=request.user)

    if request.method == "POST":
        form = PrintConfigForm(request.POST, list_obj=list_obj)
        if form.is_valid():
            with transaction.atomic():
                print_config = form.save(commit=False)
                print_config.list = list_obj
                print_config.owner = request.user
                print_config.save()
                form.save_m2m()

                log_event(
                    user=request.user,
                    noun=EventNoun.LIST,
                    verb=EventVerb.UPDATE,
                    target=list_obj,
                    fields=[
                        EventField(
                            field_name="print_config",
                            old_value=None,
                            new_value=print_config.name,
                        )
                    ],
                )

                messages.success(
                    request, f"Print configuration '{print_config.name}' created."
                )
                return redirect("core:print-config-index", list_id=list_obj.id)
    else:
        # Pre-populate with sensible defaults
        initial = {
            "name": "Custom Configuration",
            "include_assets": True,
            "include_attributes": True,
            "include_stash": True,
            "include_actions": False,
            "include_dead_fighters": False,
        }

        # Pre-select all active fighters
        active_fighters = list_obj.listfighter_set.filter(
            archived=False, state__in=[ListFighter.ACTIVE, ListFighter.CAPTURED]
        )
        initial["included_fighters"] = active_fighters

        form = PrintConfigForm(initial=initial, list_obj=list_obj)

    return render(
        request,
        "core/print_config/form.html",
        {
            "form": form,
            "list": list_obj,
            "title": "Create Print Configuration",
        },
    )


@login_required
def print_config_edit(request, list_id, config_id):
    """Edit an existing print configuration."""
    list_obj = get_object_or_404(List, id=list_id, owner=request.user)
    print_config = get_object_or_404(
        PrintConfig, id=config_id, list=list_obj, archived=False
    )

    if request.method == "POST":
        form = PrintConfigForm(request.POST, instance=print_config, list_obj=list_obj)
        if form.is_valid():
            with transaction.atomic():
                old_name = print_config.name
                form.save()

                if old_name != print_config.name:
                    log_event(
                        user=request.user,
                        noun=EventNoun.LIST,
                        verb=EventVerb.UPDATE,
                        target=list_obj,
                        fields=[
                            EventField(
                                field_name="print_config",
                                old_value=old_name,
                                new_value=print_config.name,
                            )
                        ],
                    )

                messages.success(
                    request, f"Print configuration '{print_config.name}' updated."
                )
                return redirect("core:print-config-index", list_id=list_obj.id)
    else:
        form = PrintConfigForm(instance=print_config, list_obj=list_obj)

    return render(
        request,
        "core/print_config/form.html",
        {
            "form": form,
            "list": list_obj,
            "print_config": print_config,
            "title": "Edit Print Configuration",
        },
    )


@login_required
@require_http_methods(["POST"])
def print_config_delete(request, list_id, config_id):
    """Delete a print configuration."""
    list_obj = get_object_or_404(List, id=list_id, owner=request.user)
    print_config = get_object_or_404(
        PrintConfig, id=config_id, list=list_obj, archived=False
    )

    with transaction.atomic():
        print_config.archived = True
        print_config.save()

        log_event(
            user=request.user,
            noun=EventNoun.LIST,
            verb=EventVerb.UPDATE,
            target=list_obj,
            fields=[
                EventField(
                    field_name="print_config",
                    old_value=print_config.name,
                    new_value=None,
                )
            ],
        )

        messages.success(request, f"Print configuration '{print_config.name}' deleted.")

    return redirect("core:print-config-index", list_id=list_obj.id)


@login_required
def print_config_print(request, list_id, config_id=None):
    """Redirect to the print view with the specified configuration."""
    list_obj = get_object_or_404(List, id=list_id, owner=request.user)

    if config_id:
        # Verify the config exists and belongs to this list
        get_object_or_404(PrintConfig, id=config_id, list=list_obj, archived=False)
        # Redirect with config_id as query parameter
        return redirect(
            f"{reverse('core:list-print', args=[list_obj.id])}?config_id={config_id}"
        )
    else:
        # Use default config or fallback to standard print view
        return redirect("core:list-print", list_id=list_obj.id)
