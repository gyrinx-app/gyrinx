from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def active_view(context, name):
    return "active" if context["request"].resolver_match.url_name == name else ""
