"""Staff authoring of scenario tables through the library's generated forms."""

from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import capfirst

from n26.library import authoring
from n26.library.forms import generate_form
from n26.library.models import ScenarioTable
from n26.library.scenario_tables import load_catalogue
from n26.library.specs import specs


def _fields(form):
    fields = []
    for bound in form:
        field = bound.field
        kind = (
            "file"
            if isinstance(field, forms.FileField)
            else "textarea"
            if isinstance(field.widget, forms.Textarea)
            else "number"
            if isinstance(field, forms.IntegerField)
            else "text"
        )
        fields.append(
            {
                "name": bound.html_name,
                "id": bound.auto_id,
                "label": capfirst(str(bound.label)),
                "help": str(field.help_text),
                "required": field.required,
                "value": ""
                if kind == "file"
                else str(bound.value() if bound.value() is not None else ""),
                "kind": kind,
                "errors": list(bound.errors),
                "min": getattr(field, "min_value", None),
                "max": getattr(field, "max_value", None),
                "maxLength": getattr(field, "max_length", None),
            }
        )
    return {"fields": fields, "errors": list(form.non_field_errors())}


def _refuse(form, error):
    if hasattr(error, "error_dict"):
        for name, problems in error.error_dict.items():
            form.add_error(name if name in form.fields else None, problems)
    else:
        form.add_error(None, error)


def _render(
    request, table, table_form, add_form=None, entries=(), errors=(), editing=""
):
    preview = ""
    complete = False
    if table:
        try:
            table.check_complete()
            complete = True
        except ValidationError:
            complete = False
        if complete and not table.archived:
            picks = {"generate": "1"}
            if table.purpose == ScenarioTable.Purpose.SIDE_JOB:
                picks.update(
                    {
                        "deployment_pick": "leave",
                        "objective_pick": "leave",
                        "crew_pick": "leave",
                        "side_job_pick": table.key,
                    }
                )
            preview = f"{reverse('n26-generate-scenario')}?{urlencode(picks)}"
    return render(
        request,
        "authoring/scenario_table.html",
        {
            "kind": "scenario-table",
            "page_title": table.name if table else "New side-job set",
            "editor": {
                "csrfToken": get_token(request),
                "table": {
                    "name": table.name,
                    "purpose": table.get_purpose_display(),
                    "staged": table.staged,
                    "archived": table.archived,
                    "sideJobs": table.purpose == ScenarioTable.Purpose.SIDE_JOB,
                }
                if table
                else None,
                "tableForm": _fields(table_form),
                "addForm": _fields(add_form) if add_form else None,
                "entries": entries,
                "errors": list(errors),
                "editing": editing,
                "complete": complete,
                "previewUrl": preview,
            },
        },
    )


@staff_member_required
def new_table(request):
    form_class = generate_form(specs()["create_scenario_table"])
    form = form_class(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            table = form.compile()
        except ValidationError as error:
            _refuse(form, error)
        else:
            messages.success(
                request,
                "Side-job set created. Add its six entries before putting it live.",
            )
            return redirect("authoring-detail", kind="scenario-table", pk=table.pk)
    return _render(request, None, form)


@staff_member_required
def table_page(request, pk):
    table = get_object_or_404(ScenarioTable.objects.select_related("pack"), pk=pk)
    table_class = generate_form(specs()["create_scenario_table"])
    entry_class = generate_form(specs()["add_scenario_entry"])
    act = request.POST.get("act", "") if request.method == "POST" else ""
    table_form = table_class.opened_on(table, request.POST if act == "edit" else None)
    add_form = entry_class(
        request.POST if act == "add-entry" else None,
        request.FILES if act == "add-entry" else None,
        carrier=table,
    )
    add_form.fields.pop("table")
    edited_form, editing = None, ""
    errors = []
    if act:
        try:
            with transaction.atomic():
                if act == "edit":
                    if table_form.is_valid():
                        table_form.apply_to(table)
                    else:
                        raise ValidationError("Review the table fields.")
                elif act == "add-entry":
                    if add_form.is_valid():
                        authoring.add_scenario_entry(table, **add_form.verb_data())
                    else:
                        raise ValidationError("Review the entry fields.")
                elif act == "edit-entry":
                    entry = get_object_or_404(
                        table.entries, pk=request.POST.get("entry")
                    )
                    editing = str(entry.pk)
                    edited_form = entry_class.opened_on(
                        entry, request.POST, request.FILES, prefix=f"entry-{entry.pk}"
                    )
                    if edited_form.is_valid():
                        edited_form.apply_to(entry)
                    else:
                        raise ValidationError("Review the entry fields.")
                elif act in ("put_live", "stage"):
                    (authoring.put_live if act == "put_live" else authoring.stage)(
                        table
                    )
                elif act in ("retire", "restore"):
                    authoring.revise(table, archived=act == "retire")
                else:
                    raise ValidationError("Select an action for this table.")
        except ValidationError as error:
            target = (
                table_form
                if act == "edit"
                else add_form
                if act == "add-entry"
                else edited_form
            )
            if target is not None:
                _refuse(target, error)
            else:
                errors.extend(error.messages)
            table.refresh_from_db()
        except IntegrityError:
            add_form.add_error(
                "roll", "This table already has an entry for that D6 result."
            )
        else:
            messages.success(request, "Scenario table saved.")
            return redirect("authoring-detail", kind="scenario-table", pk=table.pk)
    catalogue = load_catalogue(include_staged=True)
    display = (
        catalogue.side_job_set(table.key)
        if table.purpose == ScenarioTable.Purpose.SIDE_JOB
        else catalogue.table(table.purpose)
    )
    entries = []
    for entry in table.entries.all():
        form = (
            edited_form
            if str(entry.pk) == editing
            else entry_class.opened_on(entry, prefix=f"entry-{entry.pk}")
        )
        shown = display.entry(entry.roll) if display else None
        entries.append(
            {
                "id": str(entry.pk),
                "roll": entry.roll,
                "name": entry.name,
                "text": entry.text,
                "form": _fields(form),
                "image": shown.image_url if shown else "",
                "imageAlt": shown.diagram_alt if shown else "",
            }
        )
    return _render(
        request,
        table,
        table_form,
        add_form if len(entries) < 6 else None,
        entries,
        errors,
        editing,
    )
