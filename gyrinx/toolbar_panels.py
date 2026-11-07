"""Deduplicate rendered context layers in the development Templates panel.

Store each distinct layer once and keep per-template references. Rebuild
the toolbar's context text when the panel opens, including history views.

settings_dev replaces the standard panel with this one. Import it after
Django app loading because the toolbar panels import a model.
"""

from debug_toolbar.panels.templates.panel import TemplatesPanel
from django.template.loader import render_to_string


class SharedContextTemplatesPanel(TemplatesPanel):
    # Retain the standard panel ID for toolbar links and visibility cookies.
    panel_id = "TemplatesPanel"

    def generate_stats(self, request, response):
        layers = []
        layer_ids = {}
        per_template = []
        if self.toolbar.config["SHOW_TEMPLATE_CONTEXT"]:
            for template_data in self.templates:
                if "context_list" not in template_data:
                    template_data["context_list"] = self.process_context_list(
                        template_data.get("context", [])
                    )
                ids = []
                for text in template_data["context_list"]:
                    if text not in layer_ids:
                        layer_ids[text] = len(layers)
                        layers.append(text)
                    ids.append(layer_ids[text])
                per_template.append(ids)
                # Prevent the base panel from joining and storing a separate full context
                # string for every template.
                template_data["context_list"] = []
        super().generate_stats(request, response)
        if not per_template:
            return
        templates = self.get_stats()["templates"]
        for info, ids in zip(templates, per_template, strict=True):
            del info["context"]
            info["context_layers"] = ids
        self.record_stats({"templates": templates, "context_layers": layers})

    @property
    def content(self):
        stats = self.get_stats()
        layers = stats.get("context_layers")
        if layers is None:
            return super().content
        templates = []
        for info in stats["templates"]:
            info = dict(info)
            info["context"] = "\n".join(
                layers[i] for i in info.pop("context_layers", ())
            )
            templates.append(info)
        return render_to_string(self.template, {**stats, "templates": templates})
