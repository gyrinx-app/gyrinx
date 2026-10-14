"""The campaign gangs island's display props."""

from django import template

from n26.core.campaign_table import gang_table_props

register = template.Library()
register.simple_tag(gang_table_props)


@register.simple_tag
def campaign_view_link(href, label, variant="default", class_name=""):
    return {"href": href, "label": label, "variant": variant, "className": class_name}
