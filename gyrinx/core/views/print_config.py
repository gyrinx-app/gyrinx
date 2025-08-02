from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import generic

from gyrinx.core.forms.print_config import PrintConfigForm
from gyrinx.core.models import List, PrintConfig
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.utils import safe_redirect


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
        # Redirect anonymous users to the default print page
        if not request.user.is_authenticated:
            list_id = kwargs["list_id"]
            return redirect("core:list-print", id=list_id)

        self.list = get_object_or_404(List, id=kwargs["list_id"], owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return PrintConfig.objects.filter(list=self.list, archived=False).order_by(
            "name"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["list"] = self.list
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
                form.save_m2m()  # This will handle the select_all_fighters logic

                log_event(
                    user=request.user,
                    noun=EventNoun.LIST,
                    verb=EventVerb.CREATE,
                    object=print_config,
                    request=request,
                    list_id=str(list_obj.id),
                    print_config_name=print_config.name,
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

        # Don't pre-select any fighters since we default to "all fighters"
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
                        object=print_config,
                        request=request,
                        list_id=str(list_obj.id),
                        old_name=old_name,
                        new_name=print_config.name,
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
def print_config_delete(request, list_id, config_id):
    """Delete a print configuration."""
    list_obj = get_object_or_404(List, id=list_id, owner=request.user)
    print_config = get_object_or_404(
        PrintConfig, id=config_id, list=list_obj, archived=False
    )

    if request.method == "POST":
        with transaction.atomic():
            print_config.archived = True
            print_config.save()

            log_event(
                user=request.user,
                noun=EventNoun.LIST,
                verb=EventVerb.DELETE,
                object=print_config,
                request=request,
                list_id=str(list_obj.id),
                print_config_name=print_config.name,
            )

            messages.success(
                request, f"Print configuration '{print_config.name}' deleted."
            )

        return redirect("core:print-config-index", list_id=list_obj.id)

    # GET request - show confirmation page
    return render(
        request,
        "core/print_config/delete.html",
        {
            "list": list_obj,
            "print_config": print_config,
        },
    )


@login_required
def print_config_print(request, list_id, config_id=None):
    """Redirect to the print view with the specified configuration."""
    list_obj = get_object_or_404(List, id=list_id, owner=request.user)

    if config_id:
        # Verify the config exists and belongs to this list
        get_object_or_404(PrintConfig, id=config_id, list=list_obj, archived=False)
        # Redirect with config_id as query parameter
        return safe_redirect(
            request,
            f"{reverse('core:list-print', args=[list_obj.id])}?config_id={config_id}",
        )
    else:
        # Use default config or fallback to standard print view
        return redirect("core:list-print", list_id=list_obj.id)
