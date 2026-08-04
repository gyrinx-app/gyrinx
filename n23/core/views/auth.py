"""Authentication and authorization utilities for views."""

from functools import wraps

from django.http import Http404


def group_membership_required(group_names):
    """Decorator that returns 404 if the user is not in any of the given groups.

    Usage:
        @login_required
        @group_membership_required(["Custom Content"])
        def my_view(request):
            ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise Http404
            if not request.user.groups.filter(name__in=group_names).exists():
                raise Http404
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


class GroupMembershipRequiredMixin:
    """Mixin that returns 404 if the user is not in any of the required groups.

    Usage:
        class MyView(GroupMembershipRequiredMixin, generic.ListView):
            required_groups = ["Custom Content"]
    """

    required_groups = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise Http404
        if not request.user.groups.filter(name__in=self.required_groups).exists():
            raise Http404
        return super().dispatch(request, *args, **kwargs)
