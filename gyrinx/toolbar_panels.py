"""
A debug toolbar Templates panel that keeps each context layer once.

The toolbar's own Templates panel records, for every template a page renders,
the context that template saw as one long string: each layer of the context
pretty-printed, then joined. Nested templates share most of their layers, the
view's own context above all, so a page that renders hundreds of Cotton
components keeps the same few megabytes of text hundreds of times over. A
fighter edit page renders about 530 templates, which comes to about 330 MB in
that panel, and the toolbar keeps the last 25 requests.

This panel pretty-prints each layer exactly as the toolbar does, but records
each distinct layer once, plus the list of layers each template saw. It joins
them only when someone opens the panel, so it shows the same text as the
toolbar's own panel, both for the page just rendered and for a past request
read from the History panel.

It is development-only. ``settings_dev`` puts it in ``DEBUG_TOOLBAR_PANELS`` in
place of the toolbar's own. It lives apart from ``gyrinx/toolbar_dev.py`` for
the same reason as ``gyrinx/toolbar_store.py``: the toolbar's panels import a
model, so this module cannot be imported while apps are still loading.
"""

from debug_toolbar.panels.templates.panel import TemplatesPanel
from django.template.loader import render_to_string


class SharedContextTemplatesPanel(TemplatesPanel):
    # Keep the toolbar's own id, so the browser cookie that turns the panel on
    # or off, and the toolbar's links to the panel, still find it.
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
                # The toolbar joins this list into the template's context
                # string. Emptying it stops super() building the full join,
                # which is the memory this panel exists to save.
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
