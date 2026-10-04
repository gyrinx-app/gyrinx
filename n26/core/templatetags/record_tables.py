"""Display props for controls over server-rendered listings."""

from django import template

register = template.Library()


@register.simple_tag
def record_table_controls(action, query, noun, singular, type_options):
    return {
        "action": action,
        "query": query or "",
        "noun": noun,
        "singular": singular,
        "typeOptions": [
            {"value": str(option["value"]), "label": str(option["label"])}
            for option in type_options
        ],
    }
