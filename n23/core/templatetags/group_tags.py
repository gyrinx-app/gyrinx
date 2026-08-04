from django import template
from django.contrib.auth.models import Group

register = template.Library()


@register.filter
def in_group(user, group_name):
    """
    Check if a user is in a specific group by name.

    Usage in templates:
        {% if user|in_group:"Campaigns Alpha" %}
            <!-- Content only visible to group members -->
        {% endif %}

    Returns False if:
    - User is not authenticated
    - Group doesn't exist
    - User is not in the group
    """
    if not user or not user.is_authenticated:
        return False

    try:
        group = Group.objects.get(name=group_name)
        return user.groups.filter(pk=group.pk).exists()
    except Group.DoesNotExist:
        return False
