from django.db import models
from simple_history.admin import SimpleHistoryAdmin

from gyrinx.core.widgets import TinyMCEWithUpload


class BaseAdmin(SimpleHistoryAdmin):
    formfield_overrides = {
        models.TextField: {"widget": TinyMCEWithUpload},
    }
