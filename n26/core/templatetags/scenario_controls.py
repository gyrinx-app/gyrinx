"""Scenario action links that retain the controls' URL state."""

from django import template

from n26.core.scenarios import SCENARIO_PICK_KEYS

register = template.Library()


@register.simple_tag
def scenario_pick_keys():
    return list(SCENARIO_PICK_KEYS)


@register.inclusion_tag("n26/includes/scenario_link.html")
def scenario_link(url, label, variant="default", size="md", aria_label="", icon=""):
    return {
        "link": {
            "url": str(url),
            "label": label,
            "variant": variant,
            "size": size,
            "ariaLabel": aria_label or label,
            "icon": icon,
            "queryKeys": list(SCENARIO_PICK_KEYS),
        }
    }
