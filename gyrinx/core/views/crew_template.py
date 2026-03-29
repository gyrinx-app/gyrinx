from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import generic

from gyrinx.core.forms.crew_template import CrewTemplateForm
from gyrinx.core.models import CrewTemplate, List
from gyrinx.core.models.events import EventNoun, EventVerb, log_event


class CrewTemplateIndexView(generic.ListView):
    """
    Display a list of crew templates for a list.

    **Context**

    ``list``
        The :model:`core.List` object.
    ``crew_templates``
        A list of :model:`core.CrewTemplate` objects for the list.

    **Template**

    :template:`core/crew_template/index.html`
    """

    template_name = "core/crew_template/index.html"
    context_object_name = "crew_templates"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("core:index")

        self.list = get_object_or_404(List, id=kwargs["list_id"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return CrewTemplate.objects.filter(list=self.list, archived=False).order_by(
            "name"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["list"] = self.list
        context["is_owner"] = self.request.user == self.list.owner
        return context


@login_required
def crew_template_create(request, list_id):
    """Create a new crew template for a list."""
    list_obj = get_object_or_404(
        List.objects.with_related_data(), id=list_id, owner=request.user
    )

    if request.method == "POST":
        form = CrewTemplateForm(request.POST, list_obj=list_obj)
        if form.is_valid():
            with transaction.atomic():
                crew_template = form.save(commit=False)
                crew_template.list = list_obj
                crew_template.owner = request.user
                crew_template.save()
                form.save_m2m()

                log_event(
                    user=request.user,
                    noun=EventNoun.CREW_TEMPLATE,
                    verb=EventVerb.CREATE,
                    object=crew_template,
                    request=request,
                    list_id=str(list_obj.id),
                    crew_template_name=crew_template.name,
                )

                messages.success(
                    request, f"Crew template '{crew_template.name}' created."
                )
                return redirect("core:crew-template-index", list_id=list_obj.id)
    else:
        initial = {
            "name": "New Crew",
            "random_count": 0,
        }
        form = CrewTemplateForm(initial=initial, list_obj=list_obj)

    return render(
        request,
        "core/crew_template/form.html",
        {
            "form": form,
            "list": list_obj,
            "title": "Create Crew Template",
        },
    )


@login_required
def crew_template_edit(request, list_id, template_id):
    """Edit an existing crew template."""
    list_obj = get_object_or_404(
        List.objects.with_related_data(), id=list_id, owner=request.user
    )
    crew_template = get_object_or_404(
        CrewTemplate, id=template_id, list=list_obj, archived=False
    )

    if request.method == "POST":
        form = CrewTemplateForm(request.POST, instance=crew_template, list_obj=list_obj)
        if form.is_valid():
            with transaction.atomic():
                old_name = crew_template.name
                form.save()

                if old_name != crew_template.name:
                    log_event(
                        user=request.user,
                        noun=EventNoun.CREW_TEMPLATE,
                        verb=EventVerb.UPDATE,
                        object=crew_template,
                        request=request,
                        list_id=str(list_obj.id),
                        old_name=old_name,
                        new_name=crew_template.name,
                    )

                messages.success(
                    request, f"Crew template '{crew_template.name}' updated."
                )
                return redirect("core:crew-template-index", list_id=list_obj.id)
    else:
        form = CrewTemplateForm(instance=crew_template, list_obj=list_obj)

    return render(
        request,
        "core/crew_template/form.html",
        {
            "form": form,
            "list": list_obj,
            "crew_template": crew_template,
            "title": "Edit Crew Template",
        },
    )


@login_required
def crew_template_delete(request, list_id, template_id):
    """Delete a crew template."""
    list_obj = get_object_or_404(List, id=list_id, owner=request.user)
    crew_template = get_object_or_404(
        CrewTemplate, id=template_id, list=list_obj, archived=False
    )

    if request.method == "POST":
        with transaction.atomic():
            crew_template.archived = True
            crew_template.save()

            log_event(
                user=request.user,
                noun=EventNoun.CREW_TEMPLATE,
                verb=EventVerb.DELETE,
                object=crew_template,
                request=request,
                list_id=str(list_obj.id),
                crew_template_name=crew_template.name,
            )

            messages.success(request, f"Crew template '{crew_template.name}' deleted.")

        return redirect("core:crew-template-index", list_id=list_obj.id)

    # GET request - show confirmation page
    return render(
        request,
        "core/crew_template/delete.html",
        {
            "list": list_obj,
            "crew_template": crew_template,
        },
    )
