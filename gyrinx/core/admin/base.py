from django.db import models
from simple_history.admin import SimpleHistoryAdmin
from tinymce.widgets import TinyMCE


class BaseAdmin(SimpleHistoryAdmin):
    formfield_overrides = {
        models.TextField: {"widget": TinyMCE},
    }
