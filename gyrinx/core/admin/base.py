import uuid

from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponseRedirect
from simple_history.admin import SimpleHistoryAdmin

from gyrinx.core.widgets import TinyMCEWithUpload


class BaseAdmin(SimpleHistoryAdmin):
    formfield_overrides = {
        models.TextField: {"widget": TinyMCEWithUpload},
    }

    # Names of changelist actions (entries in ``actions``) that are also
    # rendered as buttons on the object's change page, running against just
    # that object. See admin/gyrinx_change_form.html.
    object_actions = []

    change_form_template = "admin/gyrinx_change_form.html"

    def get_search_results(self, request, queryset, search_term):
        results, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        # Core models all have UUID primary keys, which don't belong in
        # search_fields (a non-UUID term against a UUID column is a database
        # error), so match exact IDs separately. Filtering the incoming
        # queryset keeps any changelist filters applied.
        try:
            uuid_term = uuid.UUID(search_term.strip())
        except ValueError:
            pass
        else:
            results |= queryset.filter(pk=uuid_term)
        return results, may_have_duplicates

    def get_object_actions(self, request):
        """The subset of ``actions`` exposed as change-page buttons."""
        actions = self.get_actions(request)
        return [
            {"name": name, "description": actions[name][2]}
            for name in self.object_actions
            if name in actions
        ]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method == "POST" and "_object_action" in request.POST:
            return self._run_object_action(request, object_id)
        extra_context = {
            **(extra_context or {}),
            "object_actions": self.get_object_actions(request),
        }
        return super().change_view(request, object_id, form_url, extra_context)

    def _run_object_action(self, request, object_id):
        name = request.POST["_object_action"]
        allowed = {action["name"] for action in self.get_object_actions(request)}
        obj = self.get_object(request, unquote(object_id))
        if name not in allowed or obj is None:
            raise PermissionDenied
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        func = self.get_actions(request)[name][0]
        queryset = self.get_queryset(request).filter(pk=obj.pk)
        response = func(self, request, queryset)
        # Actions usually return None; bounce back to the change page so the
        # messages they queued are visible.
        return response or HttpResponseRedirect(request.get_full_path())
